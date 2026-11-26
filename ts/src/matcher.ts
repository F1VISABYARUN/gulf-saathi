// Check a spoken agent name against the MEA licensed recruiting-agent list.
//
// Safety rules:
// - Only a licence/RA number match, or owner + agency, or a strong name + the right
//   district, counts as "confirmed_in_list".
// - Anything weaker comes back as up to 2 candidates for the caller to confirm.
// - Nothing close enough is "not_found". The closest guess is never returned as confirmed.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { findDir } from './config.js';
import { ratio, tokenSetRatio, tokenSortRatio } from './fuzz.js';
import { pyRound } from './py.js';
import { isCombining, teluguToItrans } from './translit.js';

export const MAX_CANDIDATES = 2; // read back at most this many on a phone call
const HOME_STATES = new Set(['Telangana', 'Andhra Pradesh']); // where the callers live; wins ties
const CANDIDATE_MIN = 78; // below this a record isn't worth reading back to the caller
const STRONG = 90; // one name this strong + the right district confirms
const OWNER_OK = 85; // owner + agency both at least this good confirms
const AGENCY_OK = 80;

// Words in nearly every agency name. They can't identify an agency on their own.
const GENERIC = [
  'overseas', 'manpower', 'consultants', 'consultancy', 'consultant', 'travels', 'travel',
  'tours', 'tour', 'international', 'recruiting', 'recruitment', 'recruiters', 'services',
  'service', 'enterprises', 'enterprise', 'agency', 'agencies', 'placement', 'placements',
  'solutions', 'global', 'resources', 'human', 'hr', 'and', 'the', 'of', 'india',
  'gulf', 'dubai', 'saudi', 'arabia', 'jobs', 'job', 'visa', 'visas', 'employment', 'career',
  'careers', 'world', 'worldwide', 'group', 'associates', 'management', 'staffing',
];
const LEGAL_NOISE = new Set(['m', 's', 'ms', 'pvt', 'private', 'ltd', 'limited', 'llp', 'p', 'co', 'company', 'mr', 'mrs', 'smt', 'sri', 'shri', 'dr']);

// Letters as spoken, after transliteration ("సి ఎం ఆర్" -> "si em ar" -> "cmr").
const LETTER_NAMES: Record<string, string> = {
  e: 'a', ey: 'a', bi: 'b', si: 'c', di: 'd', i: 'e', ef: 'f', ji: 'g',
  hec: 'h', ec: 'h', ai: 'i', je: 'j', ke: 'k', el: 'l', em: 'm', en: 'n',
  o: 'o', pi: 'p', kyu: 'q', ar: 'r', es: 's', ti: 't', yu: 'u', vi: 'v',
  eks: 'x', vai: 'y', jed: 'z',
};

const DISTRICTS: Array<[string, string[]]> = [
  ['jagtial', ['jagtial', 'jagityal', 'jagityala', 'jagitial', 'jagithyal']],
  ['nizamabad', ['nizamabad', 'nijamabad', 'indur', 'induru']],
  ['karimnagar', ['karimnagar', 'karimnagaram']],
  ['rajanna sircilla', ['sircilla', 'sirisilla', 'siricilla', 'rajanna sircilla']],
  ['nirmal', ['nirmal']],
  ['kamareddy', ['kamareddy', 'kamareddi', 'kamaredi']],
  ['hyderabad', ['hyderabad', 'haidarabad', 'hyd']],
  ['ranga reddy', ['ranga reddy', 'rangareddy', 'rangareddi']],
  ['medchal malkajgiri', ['medchal', 'malkajgiri']],
];

export function romanize(text: string): string {
  let t = text;
  if (/[ఀ-౿]/.test(t)) {
    t = teluguToItrans(t).replace(/M/g, 'm'); // anusvara
  }
  // Strip accents that ITRANS puts on e/o, and zero-width joiners.
  t = Array.from(t.normalize('NFKD')).filter((c) => !isCombining(c)).join('');
  return t.replace(/‌/g, '').replace(/‍/g, '');
}

/** Flatten spellings that Telugu speech-to-text and English records disagree on. */
export function phonetic(word: string): string {
  let w = word.replace(/c(?=[aoukrlt])/g, 'k'); // hard c: "consultancy", "cargo"
  for (const [a, b] of [['tion', 'san'], ['aiah', 'aia'], ['ayya', 'aia'], ['aya', 'aia'], ['sh', 's'], ['ch', 's'], ['c', 's'],
    ['th', 't'], ['dh', 't'], ['d', 't'], ['kh', 'k'], ['gh', 'g'], ['bh', 'b'], ['ph', 'f'],
    ['w', 'v'], ['z', 'j'], ['q', 'k'], ['y', 'i'], ['ee', 'i'], ['oo', 'u']]) {
    w = w.split(a).join(b);
  }
  w = w.replace(/m(?=[kgsjtdpb])/g, 'n');
  w = w.replace(/(.)\1+/g, '$1');
  return w.replace(/(?<=[aeiou])h$/, '');
}

/** Consonants only: "manpower" and Telugu-spoken "myanpavar" are both "mnpvr". */
export function skeleton(word: string): string {
  return phonetic(word).replace(/[aeiou]/g, '').replace(/(.)\1+/g, '$1');
}

const GENERIC_KEYS = GENERIC.map((g) => [g, phonetic(g), skeleton(g)] as const);

/** "myanpavar" (Telugu-spoken "manpower") -> "manpower". */
export function canonicalGeneric(token: string): string | null {
  if (GENERIC.includes(token)) return token;
  if (token.length < 4) return null;
  const p = phonetic(token), s = skeleton(token);
  for (const [g, gp, gs] of GENERIC_KEYS) {
    if (p[0] === gp[0] && (ratio(p, gp) >= 80 || (gs.length >= 3 && s === gs))) return g;
  }
  return null;
}

export function tokens(text: string): string[] {
  const t = romanize(text).toLowerCase().split('man power').join('manpower').split('&').join(' and ');
  const words = t.match(/[a-z0-9]+/g) ?? [];
  // Join runs of 2+ spoken letters into one acronym; a lone one stays a word.
  const out: string[] = [];
  let run: string[] = [];
  for (const w of [...words, '']) {
    if (Object.hasOwn(LETTER_NAMES, w) || (w.length === 1 && /^[a-z]$/.test(w))) {
      run.push(w);
      continue;
    }
    if (run.length >= 2) out.push(run.map((x) => (Object.hasOwn(LETTER_NAMES, x) ? LETTER_NAMES[x] : x)).join(''));
    else out.push(...run);
    run = [];
    if (w) out.push(w);
  }
  return out.filter((w) => !LEGAL_NOISE.has(w));
}

/** (distinctive part, generic part), both as space-joined phonetic keys. */
export function splitAgency(text: string): [string, string] {
  const distinct: string[] = [], generic: string[] = [];
  for (const t of tokens(text)) {
    const g = canonicalGeneric(t);
    (g ? generic : distinct).push(g || phonetic(t));
  }
  return [distinct.join(' '), generic.join(' ')];
}

type Person = [string, string, string[], string[]];

function person(text: string): Person {
  const plain = tokens(text);
  const flat = plain.map(phonetic);
  return [plain.join(' '), flat.join(' '), plain, flat];
}

/** Best match against any owner. Plain spelling first; phonetic is a weaker fallback. */
export function ownerScore(said: Person, owners: Person[]): number {
  const [sPlain, sFlat, sPt, sFt] = said;
  if (!sPt.length) return 0;
  let best = 0;
  for (const [oPlain, oFlat, oPt, oFt] of owners) {
    if (!oPt.length) continue;
    const full = Math.max(tokenSortRatio(sPlain, oPlain), tokenSortRatio(sFlat, oFlat) - 3);
    const n = Math.min(sPt.length, sFt.length);
    const per: number[] = [];
    for (let k = 0; k < n; k++) {
      const m = Math.min(oPt.length, oFt.length);
      let mx = -Infinity;
      for (let j = 0; j < m; j++) mx = Math.max(mx, Math.max(ratio(sPt[k], oPt[j]), ratio(sFt[k], oFt[j]) - 3));
      per.push(mx);
    }
    const coverage = Math.min(1.0, sPt.length / oPt.length);
    const partial = Math.min(...per) >= 75 ? (per.reduce((a, b) => a + b, 0) / per.length) * (0.75 + 0.25 * coverage) : 0;
    best = Math.max(best, full, partial);
  }
  return best;
}

export function agencyScore(said: [string, string], agency: [string, string]): number {
  const [sD, sG] = said;
  const [aD, aG] = agency;
  if (!aD) {
    // A name made only of common words must be said almost exactly.
    return !sD && tokenSortRatio(sG, aG) >= 95 ? tokenSortRatio(sG, aG) : 0;
  }
  if (!sD) return 0; // "overseas" alone identifies nobody
  const distinct = tokenSortRatio(sD, aD);
  if (distinct < 80) return distinct * 0.8;
  let generic: number;
  if (sG && aG) generic = tokenSetRatio(sG, aG);
  else if (sG || aG) generic = 70;
  else generic = 100;
  return 0.85 * distinct + 0.15 * generic;
}

/** Canonical district for what the caller said ("జగిత్యాల" -> "jagtial"). */
export function districtKey(said: string): string {
  const [found] = findDistrict(said);
  return phonetic(found || tokens(said).join(' '));
}

/** Pull a district name out of free text: (district, the text without it). */
export function findDistrict(text: string): [string | null, string] {
  const words = tokens(text);
  for (const [canon, names] of DISTRICTS) {
    for (const n of names) {
      const pn = phonetic(n);
      const hits = words.filter((w) => ratio(phonetic(w), pn) >= 85);
      if (hits.length) return [canon, words.filter((w) => !hits.includes(w)).join(' ')];
    }
  }
  return [null, text];
}

function normId(s: string): string {
  return romanize(s).toUpperCase().replace(/[^A-Z0-9]/g, '');
}

export interface Agent { raid: string; agency: string; sign: string; state: string; district: string; rc: string; phone: string }

export function publicAgent(a: Agent) {
  return { agency: a.agency, owner: a.sign, district: a.district, state: a.state, licence_no: a.rc, ra_id: a.raid };
}

/** Minimal RFC 4180 CSV reader (quoted fields, doubled quotes, CRLF). */
export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else q = false;
      } else field += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const header = (rows.shift() ?? []).map((h) => h.replace(/^﻿/, ''));
  return rows.filter((r) => r.length > 1 || r[0]).map((r) => Object.fromEntries(header.map((h, k) => [h, r[k] ?? ''])));
}

export interface MatchResult {
  match: string;
  candidates: Array<ReturnType<typeof publicAgent> & { score: number }>;
  reason: string;
  instruction: string;
}

type Key = [[string, string], Person[], string];

export class LicensedList {
  agents: Agent[];
  private keys: Key[];
  private byId = new Map<string, Agent>();

  constructor(agents: Agent[]) {
    this.agents = agents;
    this.keys = agents.map((a) => [splitAgency(a.agency), a.sign.split(',').map(person), phonetic(tokens(a.district).join(' '))]);
    for (const a of agents) {
      const r = normId(a.raid);
      this.byId.set(r, a);
      this.byId.set(r.startsWith('RA') ? r.slice(2) : r, a);
      this.byId.set(normId(a.rc), a);
    }
  }

  static load(path = join(findDir('data'), 'licensed_agents.csv')): LicensedList {
    const rows = parseCsv(readFileSync(path, 'utf8'));
    return new LicensedList(rows.map((r) => ({ raid: r.raid, agency: r.agency, sign: r.sign, state: r.state,
      district: r.district, rc: r.rc, phone: r.phone })));
  }

  byNumber(num: string): Agent | null {
    const n = normId(num);
    if (n.length < 4) return null;
    if (this.byId.has(n)) return this.byId.get(n)!;
    // "B 1293" style: the first part of the licence number.
    const m = /^B0*(\d+)$/.exec(n);
    if (m) {
      const re = new RegExp(`^B-0*${m[1]}/`);
      const hits = this.agents.filter((a) => re.test(a.rc));
      if (hits.length === 1) return hits[0];
    }
    return null;
  }

  /** `query` is free text when the caller's words weren't split up. */
  check(agency = '', owner = '', district = '', licenceNo = '', query = ''): MatchResult {
    let queryRest = '';
    const given = `${agency} ${owner}`.trim(); // names the caller's words were split into
    if (licenceNo) {
      const a = this.byNumber(licenceNo);
      if (a) return result('confirmed_in_list', [[a, 100]], 'licence number matched');
    }
    if (query) {
      const [found, rest] = findDistrict(query);
      district = district || found || '';
      queryRest = rest;
      agency = agency || rest;
      owner = owner || rest;
    }
    if (!(agency || owner)) return result('need_more_info', [], 'no name given');

    // One word alone (a first name like "Ramayya") matches too many agents across India.
    const saidWords = new Set(tokens(query ? queryRest : `${agency} ${owner}`));
    if (saidWords.size === 1 && !district && !canonicalGeneric([...saidWords][0])) {
      return result('need_more_info', [], 'only one word was given');
    }

    const saidAgency = agency ? splitAgency(agency) : null;
    const saidOwner = owner ? person(owner) : null;
    const wantDistrict = district ? districtKey(district) : '';
    const scored: Array<[Agent, number, number, number, boolean]> = [];
    this.agents.forEach((a, idx) => {
      const [aKey, oKeys, aDistrict] = this.keys[idx];
      const o = owner ? ownerScore(saidOwner!, oKeys) : 0;
      const g = agency ? agencyScore(saidAgency!, aKey) : 0;
      let score = owner && agency && !query ? Math.max((o + g) / 2, Math.max(o, g) - 8) : Math.max(o, g);
      const dOk = !!wantDistrict && ratio(wantDistrict, aDistrict) >= 90;
      if (district) score += dOk ? 4 : -8;
      scored.push([a, score, o, g, dOk]);
    });
    // Ties go to Telangana / Andhra agents; the bonus only orders the list.
    const key = (x: (typeof scored)[number]) => x[1] + (HOME_STATES.has(x[0].state) ? 0.5 : 0);
    scored.sort((p, q) => key(q) - key(p));

    const nameWords = given ? new Set(tokens(given)) : saidWords;
    const oneWord = nameWords.size === 1 && !canonicalGeneric([...nameWords][0]);
    const plausible = (x: (typeof scored)[number]) => {
      const [, score, o, g, dOk] = x;
      if (oneWord && district) return score >= CANDIDATE_MIN && dOk;
      return score >= CANDIDATE_MIN && (!district || dOk || Math.max(o, g) >= STRONG);
    };
    const top = scored.filter(plausible).slice(0, MAX_CANDIDATES);
    if (!top.length) return result('not_found', [], 'no name close enough in the licensed list');

    const [a, score, o, g, dOk] = top[0];
    const runnerUp = top.length > 1 ? top[1][1] : 0;
    const clearWinner = score - runnerUp >= 5;
    const both = !!owner && !!agency && !query && o >= OWNER_OK && g >= AGENCY_OK;
    const onePlusDistrict = dOk && Math.max(o, g) >= STRONG && !oneWord;
    if (clearWinner && (both || onePlusDistrict)) return result('confirmed_in_list', [[a, score]], 'name and owner/district matched');
    return result('needs_confirmation', top.map((x) => [x[0], x[1]] as [Agent, number]), 'ask the caller which one, if any');
  }
}

const SAY: Record<string, string> = {
  confirmed_in_list: "This name appears in the government's licensed list. Other checks are still needed.",
  needs_confirmation: "Read the candidates back (agency, owner, district) and ask which one, if any, is the caller's agent.",
  not_found: 'Not found in the licensed list. Ask for the exact agency name, owner name, district or licence number.',
  need_more_info: 'One name alone is not enough to check. Ask for the agency name or the district (or the licence number), then check again. Do not say the agent is or is not in the list yet.',
};

function result(match: string, cands: Array<[Agent, number]>, reason: string): MatchResult {
  return {
    match,
    // Scores are for ranking; the district bonus can push one past 100, so cap what's shown.
    candidates: cands.map(([a, s]) => ({ ...publicAgent(a), score: pyRound(Math.min(s, 100), 1) })),
    reason,
    instruction: SAY[match],
  };
}
