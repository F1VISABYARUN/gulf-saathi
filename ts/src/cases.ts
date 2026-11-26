// Worker cases: registration, check-in answers, risk levels, family alerts, call scheduling and the
// English case packet. Port of gulf_saathi/cases.py.
//
// Everything here takes a store (MemoryStore or SupabaseStore) and the current time, so the whole flow
// runs in tests without Supabase or Bolna. Store calls are async, so most functions here are too.
import { randomInt } from 'node:crypto';
import * as bolna from './bolna.js';
import { parseCall } from './calls.js';
import { isoUtc, type Row, type Store } from './db.js';
import { checkFee, fmtRupees } from './fees.js';
import { LicensedList } from './matcher.js';
import * as promise from './promise.js';
import { cut, maxBy, orStr, pyInt, pyNum, pySorted, pyStr, pyTitle, truthy } from './py.js';
import * as sms from './sms.js';

export type { Row };

const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR;
const IST_OFFSET = 5.5 * HOUR; // India has no daylight saving
export const CHECKIN_DAYS = parseInt(process.env.GS_CHECKIN_DAYS ?? '7', 10);
export const RETRY_HOURS: Record<string, number> = { arrival: 3, weekly: 24 }; // after a missed call
// After an answered call, how soon Saathi calls back, by the worker's risk now: a person in danger is
// not left for a week.
export const FOLLOW_UP: Record<string, number> = { critical: 3 * HOUR, high: DAY };
// Never more than one automatic call to the same worker in this window, whatever else happens (a
// booking Bolna places at once instead of later must not loop).
export const autoCallGap = () => parseInt(process.env.GS_AUTO_CALL_GAP_HOURS ?? '6', 10) * HOUR;

/** Calls the server books by itself after a call ends (retries, follow-ups, next week). Off unless
 * GS_AUTO_CALLS=1: on 22 Oct 2026 booked calls came at once and looped. "Call now" always works. */
export const autoCallsOn = () => (process.env.GS_AUTO_CALLS ?? '0') === '1';

export const later = (d: Date, ms: number) => new Date(d.getTime() + ms);

/** A call other than the one just ended was created in the last AUTO_CALL_GAP. */
async function recentCallOtherThan(store: Store, workerId: string, thisCall: string, now: Date): Promise<boolean> {
  for (const c of await store.select('calls', { worker_id: workerId })) {
    if (c.id === thisCall || c.status === 'scheduled') continue; // booked for later and not yet happened
    const made = parseTs(c.created_at);
    if (made && now.getTime() - made.getTime() < autoCallGap()) return true;
  }
  return false;
}

export const DEFAULT_CODE_PHRASE = 'అమ్మ బాగుందా'; // "Is Amma well?": says "I can't talk freely" without saying it
export const CHECKIN_KINDS = ['arrival', 'weekly']; // calls that count towards misses and alerts
export const CALL_KINDS = [...CHECKIN_KINDS, 'briefing']; // briefing: pre-departure, before the worker flies
// "help": the worker called the Gulf Saathi line themselves and asked for help. Not a scheduled call, so
// it is recorded as a check-in but never booked or counted as missed.
export const CHECKIN_RECORD_KINDS = [...CALL_KINDS, 'help'];

export const LEVELS = ['ok', 'medium', 'high', 'critical'];
export const GENDERS = ['woman', 'man'];

// code: [level, English for the dashboard and packet, Telugu for the family SMS]
export const REASONS: Record<string, [string, string, string]> = {
  wrong_pickup: ['critical', 'Picked up at the airport by someone other than the registered employer',
    'విమానాశ్రయంలో నమోదైన యజమాని కాకుండా వేరే వ్యక్తి తీసుకెళ్లారు'],
  no_pickup: ['critical', 'Nobody came to pick the worker up at the airport',
    'విమానాశ్రయంలో తీసుకెళ్లడానికి ఎవరూ రాలేదు'],
  threatened: ['critical', 'Reports threats or violence', 'బెదిరింపులు లేదా హింస జరుగుతోందని చెప్పారు'],
  movement_restricted: ['critical', 'Not allowed to go out', 'బయటకు వెళ్లనివ్వడం లేదని చెప్పారు'],
  needs_help: ['critical', 'Asked for urgent help', 'వెంటనే సహాయం కావాలని అడిగారు'],
  code_phrase: ['critical', 'Said the agreed danger phrase: may not be able to speak freely',
    'ముందే చెప్పుకున్న ప్రమాద సంకేతం చెప్పారు'],
  death_reported: ['critical', 'Death reported: {detail}', 'మరణించినట్లు సమాచారం వచ్చింది'],
  job_mismatch: ['high', 'Doing different work from the job promised: {detail}',
    'చెప్పిన ఉద్యోగం కాకుండా వేరే పని చేయిస్తున్నారు'],
  employer_changed: ['high', 'Moved to a different employer or house than the one registered',
    'నమోదైన యజమాని కాకుండా వేరే ఇంటికి లేదా వేరే యజమాని దగ్గరకు పంపారు'],
  missed_1_domestic: ['high', 'Missed the last check-in call. She works inside a private house, so one missed ' +
    'call is a warning sign', 'చివరి కాల్‌కు జవాబు రాలేదు; ఇంటి పనిలో ఉన్నందున ఇది ప్రమాద సంకేతం'],
  passport_taken: ['high', 'Passport is not with the worker', 'పాస్‌పోర్ట్ వారి దగ్గర లేదు'],
  unpaid_2plus: ['high', 'Salary unpaid for {n} months', '{n} నెలలుగా జీతం రాలేదు'],
  missed_2plus: ['high', '{n} check-in calls missed in a row', 'వరుసగా {n} కాల్స్‌కు జవాబు రాలేదు'],
  unpaid_1: ['medium', 'Salary unpaid this month', 'ఈ నెల జీతం రాలేదు'],
  salary_short: ['high', 'Paid less than the contract: {detail}', 'ఒప్పందంలో చెప్పిన జీతం కంటే తక్కువ ఇస్తున్నారు'],
  papers_problem: ['high', "Legal or papers problem (risk of arrest; not the worker's wrongdoing): {detail}",
    'వీసా, పత్రాలు లేదా కేసు సమస్య ఉంది; అరెస్టు భయం ఉంది'],
  city_mismatch: ['medium', 'In a different city from the one promised: {detail}',
    'చెప్పిన ఊరు కాకుండా వేరే చోట ఉన్నారు'],
  food_not_ok: ['medium', 'Problems with food or accommodation', 'భోజనం లేదా వసతి సరిగా లేదు'],
  missed_1: ['medium', 'Missed the last check-in call', 'చివరి కాల్‌కు జవాబు రాలేదు'],
};

export class CaseError extends Error {
  constructor(message: string) { super(message); this.name = 'CaseError'; }
}

// --- small helpers ------------------------------------------------------------

export const rank = (level: unknown): number => (typeof level === 'string' && LEVELS.includes(level) ? LEVELS.indexOf(level) : 0);

export const iso = (d: Date): string => isoUtc(d);

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2})(?::(\d{2})(?::(\d{2})(?:[.,](\d{1,6}))?)?)?(Z|[+-]\d{2}(?::?\d{2}(?::?\d{2})?)?)?)?$/;

/** Python datetime.fromisoformat for the forms Saathi sees. Returns the time and whether it had a zone. */
function fromIso(s: string): { d: Date; aware: boolean } | null {
  const m = ISO_RE.exec(s);
  if (!m) return null;
  const [, y, mo, da, h = '0', mi = '0', se = '0', frac = '', tz] = m;
  const Y = +y, M = +mo, D = +da, H = +h, Mi = +mi, S = +se;
  const t = Date.UTC(Y, M - 1, D, H, Mi, S, Math.floor(Number((frac + '000000').slice(0, 6)) / 1000));
  const check = new Date(t);
  if (check.getUTCFullYear() !== Y || check.getUTCMonth() !== M - 1 || check.getUTCDate() !== D || H > 23 || Mi > 59 || S > 59) return null;
  if (!tz) return { d: check, aware: false };
  if (tz === 'Z') return { d: check, aware: true };
  const sign = tz[0] === '-' ? -1 : 1;
  const digits = tz.slice(1).replace(/:/g, '');
  const off = (+digits.slice(0, 2) * 60 + +(digits.slice(2, 4) || 0)) * MIN + +(digits.slice(4, 6) || 0) * 1000;
  return { d: new Date(t - sign * off), aware: true };
}

export function parseTs(value: unknown): Date | null {
  if (!truthy(value)) return null;
  if (value instanceof Date) return value;
  const r = fromIso(pyStr(value).replace(/Z/g, '+00:00').replace('+00:00', 'Z'));
  return r ? r.d : null; // a time with no zone is UTC
}

/** A time typed on the dashboard ("2026-10-25T09:30") is India time. */
export function parseIndiaTime(value: unknown): Date | null {
  if (!truthy(value)) return null;
  if (value instanceof Date) return value;
  const r = fromIso(pyStr(value).trim().replace(/Z/g, '+00:00').replace('+00:00', 'Z'));
  if (!r) throw new CaseError(`not a date and time: ${pyStr(value)}`);
  return r.aware ? r.d : new Date(r.d.getTime() - IST_OFFSET);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const p2 = (n: number) => String(n).padStart(2, '0');

/** A UTC time shown in India time, with a strftime-like pattern (%d %b %Y %H %M %A %B %-d). */
export function strftimeIst(d: Date, fmt: string): string {
  const t = new Date(d.getTime() + IST_OFFSET);
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const full = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  return fmt.replace(/%(-?)([dbYHMABmSy%])/g, (_m, dash: string, c: string) => {
    switch (c) {
      case 'd': return dash ? String(t.getUTCDate()) : p2(t.getUTCDate());
      case 'b': return MONTHS[t.getUTCMonth()];
      case 'B': return full[t.getUTCMonth()];
      case 'm': return p2(t.getUTCMonth() + 1);
      case 'Y': return String(t.getUTCFullYear());
      case 'y': return p2(t.getUTCFullYear() % 100);
      case 'H': return p2(t.getUTCHours());
      case 'M': return p2(t.getUTCMinutes());
      case 'S': return p2(t.getUTCSeconds());
      case 'A': return days[(t.getUTCDay() + 6) % 7];
      default: return '%';
    }
  });
}

export function fmtIst(value: unknown): string {
  const d = parseTs(value);
  return d ? strftimeIst(d, '%d %b %Y, %H:%M IST') : '—';
}

/** "98765 43210" -> "+919876543210". Numbers with a country code keep it. */
export function normalizePhone(raw: unknown): string {
  let s = orStr(raw).replace(/[^\p{Nd}+]/gu, '');
  if (!s) return '';
  if (s.startsWith('00')) s = '+' + s.slice(2);
  const digits = s.replace(/^\++/, '');
  const n = Array.from(digits).length;
  let out: string;
  if (s.startsWith('+')) out = '+' + digits;
  else if (n === 10) out = '+91' + digits;
  else out = '+' + digits; // 12 digits starting 91 gets the same
  const len = Array.from(out).length - 1;
  if (!(len >= 9 && len <= 15)) throw new CaseError(`not a phone number: ${pyStr(raw ?? null)}`);
  return out;
}

const ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'; // no 0/O, 1/I/L: easy to read out on a call

export async function newCaseId(store: Store): Promise<string> {
  for (;;) {
    let cid = 'GS-';
    for (let i = 0; i < 6; i++) cid += ALPHABET[randomInt(ALPHABET.length)];
    if (!(await store.get('workers', { case_id: cid }))) return cid;
  }
}

export interface Reason { code: string; n?: number; detail?: string }

export function reasonText(reason: Row, lang = 'en'): string {
  const [, en, te] = REASONS[reason.code];
  const n = Object.hasOwn(reason, 'n') ? pyStr(reason.n) : '';
  const detail = Object.hasOwn(reason, 'detail') ? pyStr(reason.detail) : '';
  return (lang === 'te' ? te : en).replace(/\{n\}/g, () => n).replace(/\{detail\}/g, () => detail);
}

// --- answers and risk -----------------------------------------------------------

const YES = new Set(['yes', 'y', 'true', '1', 'haan', 'ha', 'avunu', 'అవును', 'ఔను', 'ఉంది', 'వచ్చింది', 'అందింది']);
const NO = new Set(['no', 'n', 'false', '0', 'ledu', 'లేదు', 'కాదు', 'raledu', 'రాలేదు']);
const PICKUP: Record<string, string> = {
  employer: 'employer', named_employer: 'employer', registered_employer: 'employer',
  other_person: 'other_person', other: 'other_person', someone_else: 'other_person', stranger: 'other_person',
  nobody: 'nobody', none: 'nobody', no_one: 'nobody',
  not_arrived: 'not_arrived', not_landed: 'not_arrived',
};

export function yesNo(v: unknown): boolean | null {
  if (typeof v === 'boolean') return v;
  const s = orStr(v).trim().toLowerCase();
  return YES.has(s) ? true : NO.has(s) ? false : null;
}

export function asInt(v: unknown): number | null {
  if (typeof v === 'number') return Math.trunc(v);
  if (typeof v === 'boolean') return null;
  const m = /\p{Nd}+/u.exec(orStr(v));
  return m ? pyInt(m[0]) : null;
}

const hasKey = (o: Row, k: string) => Object.hasOwn(o, k);

/** Answers from the record_checkin tool or Bolna's extracted_data, cleaned up. */
export function normalizeAnswers(input: Row | null | undefined): Row {
  const raw: Row = {};
  for (const [k, v] of Object.entries(input ?? {})) raw[k.toLowerCase()] = v;
  let pickup: string | null = PICKUP[orStr(raw.pickup_status).trim().toLowerCase().replace(/ /g, '_')] ?? null;
  if (!hasKey(PICKUP, orStr(raw.pickup_status).trim().toLowerCase().replace(/ /g, '_'))) pickup = null;
  if (pickup === null && hasKey(raw, 'picked_up_by_named_employer')) { // older field name, still accepted
    const named = yesNo(raw.picked_up_by_named_employer);
    pickup = named === true ? 'employer' : named === false ? 'other_person' : null;
  }
  if (pickup === null && yesNo(raw.taken_by_stranger)) {
    // Help line: "someone I don't know took me from the airport / is taking me now".
    pickup = 'other_person';
  }
  const text = (k: string) => (orStr(raw[k]).trim().toLowerCase() === 'not_said' ? '' : cut(orStr(raw[k]).trim(), 500));
  const papers = text('papers_problem');
  return {
    pickup_status: pickup,
    pickup_person: text('pickup_person'),
    current_location: text('current_location'),
    current_job: text('current_job'),
    current_city: text('current_city'),
    landmark: text('landmark'),
    home_district: text('home_district'),
    agent_name: text('agent_name'),
    agent_phone: text('agent_phone'),
    salary_received: yesNo(raw.salary_received),
    salary_amount: text('salary_amount') ? asInt(raw.salary_amount) : null,
    papers_problem: NO.has(papers.toLowerCase()) || ['none', 'fine', 'ok'].includes(papers.toLowerCase()) ? '' : papers,
    months_unpaid: asInt(raw.months_unpaid),
    passport_with_worker: yesNo(raw.passport_with_worker),
    food_ok: yesNo(raw.food_ok),
    threatened: yesNo(raw.threatened),
    movement_restricted: yesNo(raw.movement_restricted),
    employer_changed: yesNo(raw.employer_changed),
    needs_help: yesNo(raw.needs_help),
    code_phrase_used: yesNo(raw.code_phrase_used),
    briefing_understood: yesNo(raw.briefing_understood),
    notes: text('notes'),
  };
}

/** Fixed rules turn answers into a risk level. With the worker's case, also compares the work and city
 * they describe now with what they were promised. */
export function assess(answers: Row, missedInRow = 0, worker: Row | null = null): [string, Row[]] {
  const reasons: Row[] = [];
  if (answers.pickup_status === 'other_person') reasons.push({ code: 'wrong_pickup' });
  else if (answers.pickup_status === 'nobody') reasons.push({ code: 'no_pickup' });
  for (const [key, code] of [['threatened', 'threatened'], ['movement_restricted', 'movement_restricted'],
    ['needs_help', 'needs_help'], ['code_phrase_used', 'code_phrase']]) {
    if (answers[key] === true) reasons.push({ code });
  }
  const w = truthy(worker) ? worker! : null;
  if (w && promise.compareJobs(w.job_title, answers.current_job) === 'conflict') {
    reasons.push({ code: 'job_mismatch', detail: `promised "${pyStr(w.job_title)}", says "${pyStr(answers.current_job)}"` });
  }
  if (answers.employer_changed === true) reasons.push({ code: 'employer_changed' });
  if (answers.passport_with_worker === false) reasons.push({ code: 'passport_taken' });
  let months = answers.months_unpaid ?? null;
  if (answers.salary_received === false && !truthy(months)) months = 1;
  if (truthy(months) && months >= 2) reasons.push({ code: 'unpaid_2plus', n: months });
  else if (months === 1) reasons.push({ code: 'unpaid_1' });
  if (w && promise.comparePlaces(w.dest_city, answers.current_city) === 'conflict') {
    reasons.push({ code: 'city_mismatch', detail: `promised "${pyStr(w.dest_city)}", says "${pyStr(answers.current_city)}"` });
  }
  const paid = answers.salary_amount ?? null, promised = (w ?? {}).contract_salary ?? null;
  if (w && promise.compareSalary(w, answers) === 'conflict') {
    const cur = orStr(w.salary_currency);
    reasons.push({ code: 'salary_short',
      detail: `gets ${pyStr(paid)} ${cur}, contract says ${Math.trunc(pyNum(promised))} ${cur}`.replaceAll('  ', ' ') });
  }
  if (truthy(answers.papers_problem)) reasons.push({ code: 'papers_problem', detail: answers.papers_problem });
  if (answers.food_ok === false) reasons.push({ code: 'food_not_ok' });
  if (missedInRow >= 2) reasons.push({ code: 'missed_2plus', n: missedInRow });
  else if (missedInRow === 1 && w && promise.isWomanDomestic(w)) reasons.push({ code: 'missed_1_domestic' });
  else if (missedInRow === 1) reasons.push({ code: 'missed_1' });
  const level = maxBy(reasons.map((r) => REASONS[r.code][0]), rank, 'ok') as string;
  return [level, reasons];
}

/** The badge: the latest assessment, but never lower than an alert nobody has resolved. */
export async function overallLevel(store: Store, workerId: string, latest: string): Promise<string> {
  const open = (await store.select('escalations', { worker_id: workerId, status: 'open' })).map((e) => e.level);
  return maxBy([latest, ...open], rank) as string;
}

// --- family alert ---------------------------------------------------------------

/** All Telugu (the case number is the only Latin text). Never promises rescue. */
export function familySms(worker: Row, level: string, reasons: Row[]): string {
  const name = truthy(worker.worker_name_te) ? worker.worker_name_te : worker.worker_name;
  const what = reasons.map((r) => reasonText(r, 'te')).join(', ');
  const parts = [(level === 'critical' ? 'అత్యవసరం: ' : '') + `గల్ఫ్ సాథీ: ${pyStr(name)} గారి విషయంలో ${what}.`];
  if (reasons.some((r) => r.code === 'code_phrase')) parts.push('దయచేసి వారికి ఫోన్ చేయండి, కానీ ఈ విషయం ఫోన్‌లో నేరుగా అడగకండి.');
  else parts.push('దయచేసి వెంటనే వారికి ఫోన్ చేయండి.');
  parts.push(`భారత రాయబార కార్యాలయానికి ఇవ్వడానికి ఫిర్యాదు వివరాలు సిద్ధం చేశాం. కేసు నంబర్ ${pyStr(worker.case_id)}.`);
  return parts.join(' ');
}

/** Open an alert and text the family, unless an unresolved alert already covers the same problems.
 * Repeating the same SMS every day would teach families to ignore it; a new kind of problem still
 * gets through. */
export async function escalate(store: Store, worker: Row, level: string, reasons: Row[], now: Date,
  notifyFamily = true): Promise<Row | null> {
  const codes = new Set(reasons.map((r) => r.code));
  for (const e of await store.select('escalations', { worker_id: worker.id, status: 'open' })) {
    const theirs = new Set(((truthy(e.reasons) ? e.reasons : []) as Row[]).map((r) => r.code));
    if (rank(e.level) >= rank(level) && [...codes].every((c) => theirs.has(c))) return null;
  }
  let text: string, status: string;
  if (!notifyFamily) {
    text = ''; status = 'not sent: a death is told to the family by a person, never by SMS';
  } else {
    text = familySms(worker, level, reasons);
    status = truthy(worker.is_demo) ? 'demo: not sent' : await sms.sendSms(orStr(worker.family_phone), text);
  }
  return store.insert('escalations', {
    worker_id: worker.id, level, reasons, family_sms: text, sms_status: status, status: 'open', created_at: iso(now),
  });
}

// --- registration -----------------------------------------------------------------

export function textField(data: Row, key: string, limit = 200): string | null {
  const v = orStr(data[key]).trim();
  return cut(v, limit) || null;
}
const _text = textField;

// Everyday words make bad danger phrases: the worker would say them by accident. "Anna" (elder
// brother) is also how the voice agent itself talks.
const WEAK_PHRASES = new Set(['anna', 'annaa', 'అన్న', 'అన్నా', 'amma', 'అమ్మ', 'hello', 'హలో', 'ok', 'okay']);
export const CODE_PHRASE_HELP = 'Use a short sentence the worker would never say by accident, e.g. ' + DEFAULT_CODE_PHRASE;

/** Python str.strip(chars). */
const stripChars = (s: string, chars: string) => {
  let a = 0, b = s.length;
  while (a < b && chars.includes(s[a])) a++;
  while (b > a && chars.includes(s[b - 1])) b--;
  return s.slice(a, b);
};

export function codePhraseOk(phrase: unknown): boolean {
  const p = stripChars(orStr(phrase).trim(), '.!?,').toLowerCase();
  return p.split(/\s+/u).filter(Boolean).length >= 2 && !WEAK_PHRASES.has(p);
}

const yn = (v: unknown) => { const b = yesNo(v); return b === true ? 'yes' : b === false ? 'no' : null; };

function validDate(s: string): boolean {
  const m = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(s);
  if (!m || (s.includes('-') && s.length !== 10)) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
}

/** Validate and normalise everything a caseworker types in, for registering or editing a case. Re-runs
 * the agent and fee checks. Throws CaseError. */
export function cleanCaseFields(data: Row, licensed: LicensedList): Row {
  const name = _text(data, 'worker_name');
  if (!name) throw new CaseError('worker name is required');
  const workerPhone = normalizePhone(data.worker_phone);
  const familyPhone = normalizePhone(data.family_phone);
  if (!workerPhone || !familyPhone) throw new CaseError('worker phone and family phone are required');

  const agent: Row = {};
  for (const k of ['agent_name', 'agent_owner', 'agent_licence', 'agent_district']) agent[k] = _text(data, k);
  let agentCheck: string | null = null, agentDetail: Row = {};
  if (agent.agent_name || agent.agent_owner || agent.agent_licence) {
    const res = licensed.check(agent.agent_name || '', agent.agent_owner || '', agent.agent_district || '', agent.agent_licence || '', '');
    agentCheck = res.match;
    agentDetail = { candidates: res.candidates, reason: res.reason };
  }

  const fee = checkFee(truthy(data.payments) ? data.payments : '');
  const departure = _text(data, 'departure_date', 10);
  if (departure && !validDate(departure)) throw new CaseError(`departure date must be YYYY-MM-DD: ${departure}`);
  const arrivalCallAt = parseIndiaTime(data.arrival_call_at);
  let salary: number | null = null;
  const rawSalary = data.contract_salary;
  if (orStr(rawSalary).trim()) {
    try { salary = pyNum(pyStr(rawSalary).replace(/,/g, '')); } catch { throw new CaseError(`salary must be a number: ${pyStr(rawSalary ?? null)}`); }
  }
  const visaType = (_text(data, 'visa_type', 20) || '').toLowerCase() || null;
  if (visaType && !(promise.VISA_TYPES as readonly string[]).includes(visaType)) {
    throw new CaseError(`visa type must be one of ${promise.VISA_TYPES.join(', ')}: ${visaType}`);
  }
  const gender = (_text(data, 'worker_gender', 10) || '').toLowerCase() || null;
  if (gender && !GENDERS.includes(gender)) throw new CaseError(`gender must be one of ${GENDERS.join(', ')}: ${gender}`);
  const age = orStr(data.worker_age).trim() ? asInt(data.worker_age) : null;
  if (age !== null && !(age >= 14 && age <= 90)) throw new CaseError(`age must be a number of years: ${pyStr(data.worker_age ?? null)}`);
  const subAgentPhone = truthy(data.sub_agent_phone) ? normalizePhone(data.sub_agent_phone) : null;
  const passportType = (_text(data, 'passport_type', 10) || '').toLowerCase() || null;
  if (passportType && !(promise.PASSPORT_TYPES as readonly string[]).includes(passportType)) {
    throw new CaseError(`passport type must be one of ${promise.PASSPORT_TYPES.join(', ')}: ${passportType}`);
  }
  const codePhrase = _text(data, 'code_phrase') || DEFAULT_CODE_PHRASE;
  if (!codePhraseOk(codePhrase)) {
    throw new CaseError(`danger code phrase "${codePhrase}" is too easy to say by accident. ${CODE_PHRASE_HELP}`);
  }
  const noPenalty = ['', 'no', 'none', 'లేదు'].includes(orStr(data.exit_penalty).trim().toLowerCase());

  return {
    worker_name: name, worker_name_te: _text(data, 'worker_name_te'), worker_phone: workerPhone,
    worker_gender: gender, worker_age: age,
    family_name: _text(data, 'family_name'), family_phone: familyPhone,
    family_relation: _text(data, 'family_relation'),
    employer_name: _text(data, 'employer_name'),
    employer_phone: truthy(data.employer_phone) ? normalizePhone(data.employer_phone) : null,
    sponsor_name: _text(data, 'sponsor_name'), sponsor_id: _text(data, 'sponsor_id'),
    dest_country: _text(data, 'dest_country'), dest_city: _text(data, 'dest_city'),
    job_title: _text(data, 'job_title'),
    visa_job: _text(data, 'visa_job'), visa_type: visaType,
    contract_salary: salary, salary_currency: _text(data, 'salary_currency', 10),
    ...agent, agent_check: agentCheck, agent_check_detail: agentDetail,
    sub_agent_name: _text(data, 'sub_agent_name'), sub_agent_phone: subAgentPhone,
    payment_to: _text(data, 'payment_to'),
    promise_by: _text(data, 'promise_by'), promise_words: _text(data, 'promise_words', 1000),
    promise_date: _text(data, 'promise_date', 40),
    exit_penalty: noPenalty ? null : _text(data, 'exit_penalty', 120),
    call_consent: yn(data.call_consent),
    alerts_opt_in: yn(data.alerts_opt_in),
    passport_type: passportType, emigration_clearance: yn(data.emigration_clearance),
    pbby: yn(data.pbby), pbby_nominee: _text(data, 'pbby_nominee'),
    home_district: _text(data, 'home_district', 60), home_mandal: _text(data, 'home_mandal', 60),
    contract_before_payment: yn(data.contract_before_payment),
    payments: fee.payments, amount_paid_total: fee.total, fee_status: fee.status,
    departure_date: departure, flight_no: _text(data, 'flight_no', 20),
    arrival_call_at: arrivalCallAt ? iso(arrivalCallAt) : null,
    code_phrase: codePhrase,
    notes: _text(data, 'notes', 2000),
  };
}

/** Who promised what, and when, in their own words: kept apart from what the papers say. */
export function promiseSaid(w: Row): string {
  if (!truthy(w.promise_words)) return '';
  const who = [w.promise_by, truthy(w.promise_date) ? `on ${pyStr(w.promise_date)}` : ''].filter(truthy).join(' ');
  return (who ? `${who} said: ` : '') + pyStr(w.promise_words);
}

/** The one SMS the family gets at registration, so they know the number and the case. */
export function welcomeSms(worker: Row): string {
  const name = truthy(worker.worker_name_te) ? worker.worker_name_te : worker.worker_name;
  return `గల్ఫ్ సాథీ: ${pyStr(name)} గారి వివరాలు నమోదు చేశాం. కేసు నంబర్ ${pyStr(worker.case_id)}. ` +
    'వారు చేరిన రోజు, తర్వాత ప్రతి వారం సాథీ వారికి ఫోన్ చేస్తుంది. ' +
    'ఏదైనా సమస్య ఉంటే మీకు మెసేజ్ వస్తుంది. ఈ నంబర్ దాచుకోండి.';
}

/** Create the pre-departure case and text the family once. Returns {worker, arrival_call}. */
export async function registerWorker(store: Store, licensed: LicensedList, data: Row, now: Date, isDemo = false,
  sendWelcome = true): Promise<{ worker: Row; arrival_call: Row | null }> {
  const fields = cleanCaseFields(data, licensed);
  const worker = await store.insert('workers', {
    case_id: await newCaseId(store), created_at: iso(now), updated_at: iso(now), ...fields,
    status: 'registered', risk_level: 'ok', risk_reasons: [], missed_checkins: 0,
    source: isDemo ? 'demo' : 'dashboard', is_demo: isDemo,
  });
  if (sendWelcome) {
    const text = welcomeSms(worker);
    const status = isDemo ? 'demo: not sent' : await sms.sendSms(worker.family_phone, text);
    await store.update('workers', { id: worker.id }, { welcome_sms: text, welcome_sms_status: status });
  }
  const arrivalAt = parseTs(fields.arrival_call_at);
  const arrival = arrivalAt ? await scheduleCall(store, worker, 'arrival', arrivalAt, now) : null;
  return { worker: (await store.get('workers', { id: worker.id }))!, arrival_call: arrival };
}

/** Correct a case's details. The case ID, status, risk and timeline stay as they are. Does not book or
 * move calls: the case page offers that. */
export async function updateWorker(store: Store, licensed: LicensedList, worker: Row, data: Row, now: Date): Promise<Row> {
  const fields = cleanCaseFields(data, licensed);
  const changes: Row = { ...fields, updated_at: iso(now), last_action_at: iso(now) };
  if (!(await otherBookedCall(store, worker.id, '', now))) {
    // Clears a "next call" time saved when booking had actually failed.
    changes.next_call_at = null;
  }
  await store.update('workers', { id: worker.id }, changes);
  return (await store.get('workers', { id: worker.id }))!;
}

export async function arrivalCallBooked(store: Store, worker: Row): Promise<boolean> {
  return (await store.select('calls', { worker_id: worker.id })).some((c) => c.kind === 'arrival');
}

/** Book the arrival call that registration couldn't (e.g. Bolna wasn't set up yet). If its time has
 * already passed, call now. */
export async function bookArrivalCall(store: Store, worker: Row, now: Date): Promise<Row> {
  const when = parseTs(worker.arrival_call_at);
  if (!when) throw new CaseError('no arrival-day call time is set for this case');
  return scheduleCall(store, worker, 'arrival', when > later(now, MIN) ? when : null, now);
}

// --- calls ------------------------------------------------------------------------

/** Variables the check-in agent's prompt can use ({{case_id}}, {{employer_name}}, ...). */
export function callUserData(worker: Row, kind: string): Row {
  return {
    case_id: worker.case_id, call_kind: kind,
    worker_name: truthy(worker.worker_name_te) ? worker.worker_name_te : worker.worker_name,
    employer_name: worker.employer_name || '',
    promised_job: worker.job_title || '',
    employer_phone: worker.employer_phone || '',
    sponsor_name: worker.sponsor_name || '',
    dest_city: worker.dest_city || '', dest_country: worker.dest_country || '',
    code_phrase: worker.code_phrase || DEFAULT_CODE_PHRASE,
  };
}

/** Ask Bolna to call the worker at `when` (or now). Records the call so the webhook can match it and
 * the dashboard can show it. */
export async function scheduleCall(store: Store, worker: Row, kind: string, when: Date | null, now: Date): Promise<Row> {
  const isLater = when !== null && when > later(now, MIN);
  if (truthy(worker.death_reported_at)) {
    return { ok: false, execution_id: null, kind, when: iso(now),
      error: 'A death was reported for this case: Saathi does not call this number. ' +
        'If the report was a mistake, clear it on the case page.' };
  }
  if (truthy(worker.is_demo)) {
    // Demo numbers are made up but could belong to real people, and calls cost credits.
    return { ok: false, execution_id: null, error: 'Demo case: Saathi never calls demo numbers', kind, when: iso(now) };
  }
  const res = await bolna.placeCall(worker.worker_phone, callUserData(worker, kind), isLater ? when : null);
  if (res.ok && isLater) {
    // Only after Bolna accepted it: the dashboard must not show a call that isn't booked.
    await store.update('workers', { id: worker.id }, { next_call_at: iso(when!), updated_at: iso(now) });
  }
  if (res.ok && res.execution_id) {
    await store.upsert('calls', {
      id: res.execution_id, worker_id: worker.id, kind, status: isLater ? 'scheduled' : 'queued',
      scheduled_at: isLater ? iso(when!) : iso(now), created_at: iso(now), updated_at: iso(now),
    });
  }
  return { ...res, kind, when: isLater ? iso(when!) : iso(now) };
}

function trimRaw(payload: Row): Row {
  // Latency and billing details are large and not part of the evidence trail.
  return Object.fromEntries(Object.entries(payload).filter(([k]) => !['latency_data', 'usage_breakdown', 'cost_breakdown'].includes(k)));
}

async function findWorker(store: Store, caseId: string, existingCall: Row | null, phone: string | null): Promise<Row | null> {
  if (caseId) {
    const w = await store.get('workers', { case_id: caseId });
    if (w) return w;
  }
  if (existingCall && truthy(existingCall.worker_id)) {
    const w = await store.get('workers', { id: existingCall.worker_id });
    if (w) return w;
  }
  if (phone) {
    try { return await store.get('workers', { worker_phone: normalizePhone(phone) }); } catch (e) {
      if (e instanceof CaseError) return null;
      throw e;
    }
  }
  return null;
}

/** Is a different call already booked for this worker, not yet made? */
async function otherBookedCall(store: Store, workerId: string, thisCall: string, now: Date): Promise<boolean> {
  for (const c of await store.select('calls', { worker_id: workerId })) {
    const when = parseTs(c.scheduled_at);
    if (c.id !== thisCall && when && when > later(now, 30 * MIN) && (c.status === 'scheduled' || c.status === 'queued')) return true;
  }
  return false;
}

const notBlank = (v: unknown) => v !== null && v !== undefined && v !== '';

/** Webhook: save the call, and once it has ended, count a miss or a contact, raise alerts and book the
 * next call. Safe to receive many times per call. */
export async function processCallRecord(store: Store, payload: Row, now: Date): Promise<Row> {
  const c = parseCall(payload) as Row;
  if (!truthy(c.call_id)) return { stored: false, reason: 'no call id' };
  const rd: Row = truthy(c.recipient_data) ? c.recipient_data : {};
  const existing = await store.get('calls', { id: c.call_id });
  const ex: Row = existing ?? {};
  let worker = await findWorker(store, orStr(rd.case_id).trim().toUpperCase(), existing, c.user_number || null);
  const kind = rd.call_kind || ex.kind || 'other';

  const row: Row = {
    id: c.call_id, worker_id: worker ? worker.id : null, kind,
    status: c.status, answered: c.answered, missed: c.missed,
    duration_seconds: c.duration_seconds, transcript: c.transcript,
    recording_url: c.recording_url, extracted: c.extracted, raw: trimRaw(payload),
    updated_at: iso(now),
  };
  if (!existing) row.created_at = iso(now);
  await store.upsert('calls', row);
  if (worker && c.answered && !truthy(worker.consent_notice_at)) {
    await store.update('workers', { id: worker.id }, { consent_notice_at: iso(now) });
  }

  if (c.terminal && !CALL_KINDS.includes(kind) && truthy(c.extracted) && !truthy(ex.processed_at)) {
    // A call to the Gulf Saathi line (Saathi didn't place it). Bolna's after-call extraction is the
    // safety net if the live voice AI missed report_problem.
    const helpOut = await helpFromExtraction(store, c, now);
    if (helpOut !== null) {
      const hw = (await store.get('workers', { case_id: helpOut.case_id }))!;
      await store.update('calls', { id: c.call_id }, { processed_at: iso(now), kind: 'help', worker_id: hw.id });
      return { stored: true, processed: true, worker: hw.case_id, help: helpOut };
    }
  }
  if (c.terminal && worker && CHECKIN_KINDS.includes(kind) && truthy(ex.processed_at)
    && truthy(c.extracted) && !truthy(ex.extracted) && c.answered) {
    // Bolna sends "call-disconnected" (processed above) before "completed", and only "completed"
    // carries the after-call extraction. Score it now: the safety net for when the live voice AI never
    // called record_checkin.
    return applyLateExtraction(store, worker, kind, c, now);
  }
  if (worker && truthy(worker.death_reported_at)) {
    // A call booked before the death was reported: keep the record, but never count a miss, text the
    // family or book another call.
    return { stored: true, processed: false, worker: worker.case_id, death_reported: true };
  }
  if (!c.terminal || !worker || !CHECKIN_KINDS.includes(kind) || truthy(ex.processed_at)) {
    return { stored: true, processed: false, worker: worker ? worker.case_id : null };
  }
  await store.update('calls', { id: c.call_id }, { processed_at: iso(now) });

  let level: string | null, reasons: Row[], changes: Row, nextWhen: Date, nextKind: string;
  if (c.missed) {
    const missed = pyInt(truthy(worker.missed_checkins) ? worker.missed_checkins : 0) + 1;
    [level, reasons] = assess({}, missed, worker);
    changes = { missed_checkins: missed };
    nextWhen = later(now, RETRY_HOURS[kind] * HOUR);
    nextKind = kind;
  } else {
    // Answers normally arrive during the call through record_checkin. Only use Bolna's extracted_data
    // if it actually has some, so an empty one doesn't wipe what the tool recorded.
    const answers = normalizeAnswers(flattenExtraction(c.extracted));
    const hasAnswers = Object.values(answers).some(notBlank);
    [level, reasons] = hasAnswers ? assess(answers, 0, worker) : [null, []];
    changes = { missed_checkins: 0, last_contact_at: iso(now) };
    if (kind === 'arrival') changes.status = 'abroad';
    nextKind = 'weekly';
    nextWhen = now;
  }

  const escalation = level && rank(level) >= rank('high') ? await escalate(store, worker, level, reasons, now) : null;
  changes.updated_at = iso(now);
  if (level) Object.assign(changes, { risk_level: await overallLevel(store, worker.id, level), risk_reasons: reasons });
  await store.update('workers', { id: worker.id }, changes);
  worker = (await store.get('workers', { id: worker.id }))!;

  if (!c.missed) {
    const gap = Object.hasOwn(FOLLOW_UP, worker.risk_level) ? FOLLOW_UP[worker.risk_level] : CHECKIN_DAYS * DAY;
    nextWhen = later(now, gap);
  }
  // Book the next call unless another one is already booked for later, automatic calls are off, or
  // this worker already had a call recently.
  let nextCall: Row | null = null;
  if (autoCallsOn() && !(await otherBookedCall(store, worker.id, c.call_id, now))
    && !(await recentCallOtherThan(store, worker.id, c.call_id, now))) {
    nextCall = await scheduleCall(store, worker, nextKind, nextWhen, now);
  }
  return { stored: true, processed: true, worker: worker.case_id, missed: c.missed,
    risk_level: worker.risk_level, escalated: Boolean(escalation), next_call: nextCall };
}

async function applyLateExtraction(store: Store, worker: Row, kind: string, c: Row, now: Date): Promise<Row> {
  const answers = normalizeAnswers(flattenExtraction(c.extracted));
  if (!Object.values(answers).some(notBlank)) return { stored: true, processed: false, worker: worker.case_id };
  answers.notes = ('From the after-call summary. ' + (answers.notes || '')).trim();
  const [level, reasons] = assess(answers, 0, worker);
  await store.insert('checkins', { worker_id: worker.id, kind, answers, risk_level: level, risk_reasons: reasons, created_at: iso(now) });
  const escalation = rank(level) >= rank('high') ? await escalate(store, worker, level, reasons, now) : null;
  await store.update('workers', { id: worker.id }, { risk_level: await overallLevel(store, worker.id, level),
    risk_reasons: reasons, updated_at: iso(now) });
  return { stored: true, processed: true, worker: worker.case_id, late_extraction: true,
    risk_level: level, escalated: Boolean(escalation) };
}

/** What the voice agent says after recording. Saathi acts for the worker: the team alerts the embassy;
 * the worker is never told to go and find a number. */
export function checkinInstruction(worker: Row, kind: string, level: string, codes: Set<string>, escalation: Row | null): string {
  const country = truthy(worker.dest_country) ? worker.dest_country : 'that country';
  const family = escalation && escalation.sms_status === 'sent' ? 'Their family has been sent a message. ' : '';
  if (codes.has('code_phrase')) {
    return 'IMPORTANT: the worker said the danger phrase and may not be able to talk freely. Do NOT mention ' +
      'danger, help, complaints, family or embassy. Chat normally for a few seconds and end the call politely.';
  }
  if (level === 'critical') {
    let say = 'Speak calmly and slowly. Say: you are not alone. Your case is marked urgent and a caseworker will ' +
      `act on it right away. ${family}`;
    if (codes.has('wrong_pickup') || codes.has('no_pickup')) {
      const employer = truthy(worker.employer_name) ? worker.employer_name : 'your registered employer';
      say += 'Then: if you are still inside the airport, stay inside. Go to the airport help desk or airport ' +
        'police and tell them you are an Indian worker and need help. Do not go with anyone except ' +
        `${employer}. If you are already in a vehicle, stay calm, do not fight, and look for any sign, ` +
        'building or road name. ';
    } else {
      say += 'Then: if you can, stay where there are other people. Keep your phone hidden and charged. ';
    }
    const back = kind !== 'help' && autoCallsOn() ? 'say Saathi will call back within a few hours'
      : 'say the team will try to reach them on this phone; keep it with you';
    say += `Ask ONE question: where are you now, any building, shop, mosque or road name? Then ${back}. ` +
      'Never tell them to call the embassy themselves. Never promise rescue.';
    return say;
  }
  if (level === 'high') {
    return 'Say: you are not alone. Your problem is registered and a Saathi caseworker will take it up with the ' +
      `Indian Embassy in ${country}. ${family}` + (kind !== 'help' && autoCallsOn() ? 'Saathi will call you again tomorrow. ' : '') +
      'Do not promise that the salary or passport will be recovered. Never tell them to call the embassy themselves.';
  }
  if (kind === 'help') {
    return 'Say: your problem is registered and a Saathi caseworker will look at it. Do not promise that anyone will come or that money will be recovered.';
  }
  if (kind === 'briefing') {
    return 'Thank them warmly. Say: Saathi will call on the day you land. If something feels wrong at the ' +
      'airport, stay inside near the help desk or airport police and ask them for help. Saathi will check on you.';
  }
  if (level === 'medium') return 'Say: noted. Saathi will keep checking on you. Tell Saathi on the next call if anything gets worse.';
  return 'Say: good, everything is noted as fine. Saathi will call again next week.';
}

// Workers on a visit visa, an expired visa or a false "absconding" report fear the local police will
// arrest them, so they stay silent. Saathi is not the police.
export const PAPERS_FIRST = 'FIRST say gently: Saathi is not the police; we never give your details to the police in that country. ' +
  'This is not your wrongdoing. The Indian Embassy can give emergency travel papers even when your ' +
  'papers are not in order. Do not promise they will not be fined or sent back. Then: ';

/** Bolna tool, called by the check-in agent with the worker's answers during the call. Returns what the
 * voice agent should say next. */
export async function recordCheckin(store: Store, data: Row, now: Date): Promise<Row> {
  const caseId = orStr(data.case_id).trim().toUpperCase();
  const worker = caseId ? await store.get('workers', { case_id: caseId }) : null;
  if (!worker) {
    return { ok: false, instruction: 'The case was not found. Thank the caller, do not promise anything, ' +
      'and say Saathi will call back.' };
  }
  let kind = (truthy(data.call_kind) ? pyStr(data.call_kind) : 'weekly').trim().toLowerCase();
  kind = CHECKIN_RECORD_KINDS.includes(kind) ? kind : 'weekly';
  const answers = normalizeAnswers(data);
  // Danger answers count on any call, a briefing included.
  const [level, reasons] = assess(answers, 0, worker);
  await store.insert('checkins', { worker_id: worker.id, kind, answers, risk_level: level, risk_reasons: reasons, created_at: iso(now) });
  const escalation = rank(level) >= rank('high') ? await escalate(store, worker, level, reasons, now) : null;
  const changes: Row = { last_contact_at: iso(now), missed_checkins: 0, updated_at: iso(now) };
  if (!truthy(worker.consent_notice_at)) changes.consent_notice_at = iso(now); // every call opens by saying it is recorded and why
  if (kind !== 'briefing' || level !== 'ok') {
    // A quiet briefing says nothing about safety abroad: leave the risk as it is.
    Object.assign(changes, { risk_reasons: reasons, risk_level: await overallLevel(store, worker.id, level) });
  }
  if (kind === 'arrival') changes.status = 'abroad';
  await store.update('workers', { id: worker.id }, changes);

  const codes = new Set(reasons.map((r) => r.code as string));
  let say = checkinInstruction(worker, kind, level, codes, escalation);
  if (codes.has('papers_problem') && !codes.has('code_phrase')) say = PAPERS_FIRST + say;
  return { ok: true, risk_level: level, escalated: Boolean(escalation), instruction: say };
}

const SELF = ['', 'self', 'worker', 'me', 'not_said'];

function phoneOrEmpty(v: unknown): string {
  try { return normalizePhone(v); } catch (e) { if (e instanceof CaseError) return ''; throw e; }
}

/** Bolna tool for the Gulf Saathi line: a worker abroad, or their family in India, calls with a problem.
 * Finds the case by case number or phone, or opens a minimal help case, then records the answers like a
 * check-in, so the same rules and alerts apply. A family caller is the case's family contact, never the
 * worker. */
export async function reportProblem(store: Store, data: Row, now: Date): Promise<Row> {
  let relation = (_text(data, 'caller_relation', 30) || '').toLowerCase();
  const died = yesNo(data.worker_died) === true;
  if (died && SELF.includes(relation)) relation = 'family'; // whoever reports a death is not the worker
  const family = !SELF.includes(relation);
  const caseId = orStr(data.case_id).trim().toUpperCase();
  let worker = caseId ? await store.get('workers', { case_id: caseId }) : null;
  const phone = phoneOrEmpty(data.caller_phone);
  const abroadPhone = truthy(data.worker_phone) ? phoneOrEmpty(data.worker_phone) : '';
  if (!worker && family) {
    worker = (abroadPhone ? await store.get('workers', { worker_phone: abroadPhone }) : null)
      || (phone ? await store.get('workers', { family_phone: phone }) : null) || null;
  } else if (!worker && phone) {
    worker = await store.get('workers', { worker_phone: phone });
  }
  let opened = false;
  if (!worker) {
    if (!phone) {
      return { ok: false, instruction: 'Ask for their phone number with the country code, or their Saathi ' +
        'case number, then call report_problem again.' };
    }
    if (family) {
      worker = await store.insert('workers', {
        case_id: await newCaseId(store), created_at: iso(now), updated_at: iso(now),
        worker_name: _text(data, 'worker_name') || 'Name not given (reported by family)',
        // The worker's own number if the family knows it; otherwise the family's, marked in notes.
        worker_phone: abroadPhone || phone, family_phone: phone, family_relation: relation,
        family_name: _text(data, 'caller_name'), dest_city: _text(data, 'current_city'),
        code_phrase: DEFAULT_CODE_PHRASE, status: 'abroad', risk_level: 'ok', risk_reasons: [],
        missed_checkins: 0, source: 'family_call', reported_by: relation,
        notes: 'Opened from a family call to the Gulf Saathi line.' +
          (abroadPhone ? '' : " Worker's own phone not known: the phone here is the family's."),
      });
    } else {
      const fam = phoneOrEmpty(data.family_phone);
      worker = await store.insert('workers', {
        case_id: await newCaseId(store), created_at: iso(now), updated_at: iso(now),
        worker_name: _text(data, 'caller_name') || 'Caller (name not given)', worker_phone: phone,
        family_phone: fam || null, dest_city: _text(data, 'current_city'),
        code_phrase: DEFAULT_CODE_PHRASE, status: 'abroad', risk_level: 'ok', risk_reasons: [],
        missed_checkins: 0, source: 'help_call', reported_by: 'self',
        notes: 'Opened from a call to the Gulf Saathi line.',
      });
    }
    opened = true;
  }
  const w = worker!;
  const trace: Row = { ...data };
  if (family) { // the caller's name is the family member's, not the worker's
    trace.caller_name = truthy(data.worker_name) ? data.worker_name : '';
    if (truthy(data.caller_name) && !truthy(w.family_name)) {
      await store.update('workers', { id: w.id }, { family_name: _text(data, 'caller_name') });
    }
  }
  await saveTrace(store, w, trace, now);
  const reread = async () => (await store.get('workers', { id: w.id }))!;
  if (died) {
    const dead = await reportDeath(store, await reread(), {
      reported_by: relation, informed_by: data.informed_by ?? null, place: data.current_city ?? null,
      notes: data.notes ?? null }, now);
    const say = deathInstruction(dead) + ` The case number is ${spokenCaseId(dead.case_id)}: read it slowly, ` +
      'one letter at a time, and ask them to keep it.';
    return { ok: true, risk_level: 'critical', escalated: true, instruction: say, case_id: dead.case_id, new_case: opened };
  }
  const out = await recordCheckin(store, { ...data, case_id: w.case_id, call_kind: 'help' }, now);
  if (out.ok && family) out.instruction = familyInstruction(await reread(), relation, out.risk_level);
  if (out.ok) {
    out.instruction += ` The case number is ${spokenCaseId(w.case_id)}: read it slowly, one ` +
      'letter at a time, and ask them to keep it.';
    const status = petitionLine(await reread());
    if (status && !opened) out.instruction += ' ' + status;
    const age = !opened ? await caseAgeLine(store, await reread(), now) : '';
    if (age) out.instruction += ' ' + age;
  }
  return { ...out, case_id: w.case_id, new_case: opened };
}

/** For a parent, wife or brother calling from India about someone abroad. */
export function familyInstruction(worker: Row, relation: string, level: string): string {
  const country = worker.dest_country || worker.dest_city || 'that country';
  const who = relation !== 'family' && relation !== 'yes' ? relation : 'family member';
  const urgent = rank(level) >= rank('high');
  return (urgent ? `Speak calmly and warmly to the ${who}: you are not alone. ` : `Speak warmly to the ${who}: `) +
    (urgent ? 'The case is marked URGENT, and a Saathi caseworker will take it to the Indian Embassy in ' +
      `${country} with these details. ` : 'The problem is registered and a Saathi caseworker will look at it. ') +
    'Saathi will prepare the Pravasi Prajavani petition for them, so they do not need to travel to ' +
    'Hyderabad; a Saathi caseworker will hand it in and contact them on this phone. Never promise rescue ' +
    'or that money will come back.';
}

export const PETITION_STATUSES = ['prepared', 'submitted', 'acknowledged', 'closed'];

/** What the voice agent can tell a caller about their Pravasi Prajavani petition. */
export function petitionLine(worker: Row): string {
  const st = worker.petition_status;
  if (!PETITION_STATUSES.includes(st) || st === 'prepared') return '';
  const when = truthy(worker.petition_submitted_at) ? fmtIst(worker.petition_submitted_at).split(',')[0] : '';
  const ref = truthy(worker.petition_ref) ? `, reference ${pyStr(worker.petition_ref)}` : '';
  return `Also tell them: their Pravasi Prajavani petition is ${st}` + (when ? ` (handed in ${when}${ref})` : ref) + '.';
}

export async function updatePetition(store: Store, worker: Row, status: string, ref: string, now: Date): Promise<Row> {
  if (!PETITION_STATUSES.includes(status)) throw new CaseError(`status must be one of ${PETITION_STATUSES.join(', ')}`);
  const changes: Row = { petition_status: status, petition_ref: cut((ref || '').trim(), 100) || null, updated_at: iso(now),
    last_action_at: iso(now) };
  if (status === 'submitted' && !truthy(worker.petition_submitted_at)) changes.petition_submitted_at = iso(now);
  await store.update('workers', { id: worker.id }, changes);
  return (await store.get('workers', { id: worker.id }))!;
}

// --- how a case ended (the pilot's numbers) ------------------------------------------

export const OUTCOMES = ['solved', 'partly_solved', 'not_solved', 'withdrawn'];
export const OUTCOME_PROBLEMS = ['unpaid_wages', 'passport', 'wrong_job', 'agent_fee', 'death', 'other'];

/** A caseworker records how the case ended. A blank outcome reopens it. It never changes the worker's
 * status or stops check-in calls: a worker whose wages came back is still abroad. */
export async function updateOutcome(store: Store, worker: Row, data: Row, now: Date): Promise<Row> {
  const outcome = orStr(data.outcome).trim().toLowerCase();
  const problem = orStr(data.problem).trim().toLowerCase();
  if (outcome && !OUTCOMES.includes(outcome)) throw new CaseError(`outcome must be one of ${OUTCOMES.join(', ')}`);
  if (problem && !OUTCOME_PROBLEMS.includes(problem)) throw new CaseError(`problem must be one of ${OUTCOME_PROBLEMS.join(', ')}`);
  const raw = pyStr(data.amount_recovered !== undefined && data.amount_recovered !== null ? data.amount_recovered : '').replace(/[,\s]/gu, '');
  if (raw && !/^\p{Nd}+$/u.test(raw)) throw new CaseError('money recovered must be a whole number of rupees, 0 or more');
  const changes: Row = { outcome_problem: problem || null, updated_at: iso(now), last_action_at: iso(now) };
  if (outcome) {
    Object.assign(changes, { outcome, amount_recovered: raw ? pyInt(raw) : null,
      outcome_note: cut(orStr(data.note).trim(), 500) || null,
      outcome_at: worker.outcome === outcome ? worker.outcome_at ?? null : iso(now) });
  } else {
    Object.assign(changes, { outcome: null, amount_recovered: null, outcome_note: null, outcome_at: null });
  }
  await store.update('workers', { id: worker.id }, changes);
  return (await store.get('workers', { id: worker.id }))!;
}

/** timedelta.days: whole days, rounded down. */
export const daysBetween = (a: Date, b: Date) => Math.floor((a.getTime() - b.getTime()) / DAY);

/** Totals for the dashboard. Made-up demo cases are never counted. */
export function outcomeTotals(workers: Row[]): Row {
  const done = workers.filter((w) => OUTCOMES.includes(w.outcome) && !truthy(w.is_demo));
  const days: number[] = [];
  for (const w of done) {
    const a = parseTs(w.outcome_at), b = parseTs(w.created_at);
    if (a && b) { const d = daysBetween(a, b); if (d >= 0) days.push(d); }
  }
  days.sort((x, y) => x - y);
  let median: number | null = null;
  if (days.length) {
    const mid = Math.floor(days.length / 2);
    median = days.length % 2 ? days[mid] : (days[mid - 1] + days[mid]) / 2;
  }
  return { closed: done.length, solved: done.filter((w) => w.outcome === 'solved' || w.outcome === 'partly_solved').length,
    recovered: done.reduce((s, w) => s + pyInt(truthy(w.amount_recovered) ? w.amount_recovered : 0), 0), median_days: median };
}

// --- a family already in trouble, entered by a caseworker ------------------------------

/** A family comes to a caseworker (for example at Pravasi Prajavani) with a worker already in trouble
 * abroad. Opens or finds the case from the family's phone and runs the same fixed rules as the help
 * line. No call is placed. */
export async function intakeFamily(store: Store, data: Row, now: Date): Promise<Row> {
  if (yesNo(data.consent) !== true) throw new CaseError('the family must agree before Saathi keeps their details');
  const familyPhone = phoneOrEmpty(data.family_phone);
  if (!familyPhone) throw new CaseError("the family's phone number is required");
  const problem = orStr(data.problem).trim().toLowerCase();
  if (!OUTCOME_PROBLEMS.includes(problem)) throw new CaseError(`problem must be one of ${OUTCOME_PROBLEMS.join(', ')}`);
  const workerPhone = orStr(data.worker_phone).trim() ? normalizePhone(data.worker_phone) : '';
  const months = asInt(data.months_unpaid);
  const call: Row = {
    caller_phone: familyPhone, caller_relation: _text(data, 'family_relation', 30) || 'family',
    caller_name: _text(data, 'family_name'), worker_name: _text(data, 'worker_name'),
    worker_phone: workerPhone, current_city: _text(data, 'dest_city'),
    home_district: _text(data, 'home_district', 60), agent_name: _text(data, 'agent_name'),
    months_unpaid: truthy(months) ? months : problem === 'unpaid_wages' ? 1 : null,
    passport_with_worker: problem === 'passport' ? 'no' : data.passport_with_worker ?? null,
    threatened: data.threatened ?? null, worker_died: problem === 'death' ? 'yes' : '',
    notes: ('Entered by a caseworker at intake (no call). ' + (_text(data, 'notes', 400) || '')).trim(),
  };
  const before = await store.get('workers', { family_phone: familyPhone });
  const out = await reportProblem(store, call, now);
  if (!truthy(out.ok)) throw new CaseError('could not open the case');
  const w = (await store.get('workers', { case_id: out.case_id }))!;
  const changes: Row = { outcome_problem: w.outcome_problem || problem, call_consent: 'yes', updated_at: iso(now) };
  if (truthy(out.new_case)) changes.source = 'prajavani';
  for (const [field, key, limit] of [['dest_country', 'dest_country', 60], ['employer_name', 'employer_name', 200]] as const) {
    if (_text(data, key, limit) && !truthy(w[field])) changes[field] = _text(data, key, limit);
  }
  if (!truthy((before ?? {}).consent_notice_at)) changes.consent_notice_at = null; // no call was made, so no notice was played
  await store.update('workers', { id: w.id }, changes);
  return { case_id: w.case_id, risk_level: out.risk_level ?? null, new_case: Boolean(out.new_case) };
}

// --- when a worker dies abroad ------------------------------------------------------
// The hard part for families is not the grief alone: bodies wait in mortuaries while volunteers search
// for the village, and illiterate parents face English papers. A Saathi case already links the worker,
// employer, sponsor and family from day zero.

export const REMAINS_STATUSES = ['reported', 'embassy_informed', 'family_decided', 'papers_signed', 'remains_home',
  'buried_abroad', 'closed'];
export const EX_GRATIA_STATUSES = ['not_applied', 'applied', 'paid', 'rejected'];
// Telangana ex-gratia: G.O. 205 (16 Sep 2024) sanctioned the Rs 5 lakh ex-gratia; G.O. 216 (Oct 2024)
// gave the guidelines. Deaths on or after 7 Dec 2023, any cause, in 7 Gulf countries (The Hindu, 20 Nov 2024).
export const EX_GRATIA_PLACES = ['bahrain', 'manama', 'iraq', 'kuwait', 'oman', 'muscat', 'salalah', 'qatar', 'doha', 'saudi',
  'ksa', 'riyadh', 'jeddah', 'dammam', 'mecca', 'makkah', 'medina', 'uae', 'emirates', 'dubai',
  'abu dhabi', 'sharjah', 'ajman', 'al ain', 'fujairah', 'ras al'];

/** Did the worker go to a country Telangana's ex-gratia covers? null if not known. */
export function exGratiaCountry(w: Row): boolean | null {
  const at = `${orStr(w.dest_country)} ${orStr(w.dest_city)}`.toLowerCase().trim();
  if (!at) return null;
  return EX_GRATIA_PLACES.some((p) => at.includes(p));
}

/** Record that someone reported the worker's death. Stops Saathi calling the number, opens a CRITICAL
 * alert for the embassy, and never texts the family: news like this must come from a person. A
 * caseworker can clear it if it was wrong. */
export async function reportDeath(store: Store, worker: Row, info: Row, now: Date): Promise<Row> {
  const clean = (k: string, n = 200) => {
    const s = orStr(info[k]).trim();
    return ['', 'not_said'].includes(s.toLowerCase()) ? '' : cut(s, n);
  };
  const parts = [clean('reported_by') ? `reported by ${clean('reported_by', 40)}` : '',
    clean('informed_by') ? `they heard it from ${clean('informed_by')}` : '',
    clean('place') ? `place: ${clean('place')}` : '',
    clean('when') ? `when: ${clean('when', 60)}` : '', clean('notes', 500)];
  const fresh = parts.filter(Boolean).join('; ');
  const old = orStr(worker.death_note);
  const note = old.includes(fresh) ? old : old ? `${old} | ${fresh}` : fresh;
  const detail = clean('place') || worker.dest_city || worker.dest_country || 'place not known';
  const reasons = [{ code: 'death_reported', detail: `${detail}, as told by ${clean('reported_by', 40) || 'a caller'}` }];
  await escalate(store, worker, 'critical', reasons, now, false);
  await store.update('workers', { id: worker.id }, {
    death_reported_at: worker.death_reported_at || iso(now), death_note: cut(note, 2000) || null,
    remains_status: worker.remains_status || 'reported',
    ex_gratia_status: worker.ex_gratia_status || 'not_applied',
    status: 'death_reported', next_call_at: null, risk_level: 'critical', risk_reasons: reasons,
    updated_at: iso(now) });
  return (await store.get('workers', { id: worker.id }))!;
}

/** The report was a mistake (wrong person, a rumour). Calls can be made again. */
export async function clearDeath(store: Store, worker: Row, now: Date): Promise<Row> {
  const note = cut((orStr(worker.notes) + ` Death report cleared as a mistake on ${fmtIst(now)}: ` +
    orStr(worker.death_note)).trim(), 2000);
  await store.update('workers', { id: worker.id }, {
    death_reported_at: null, death_note: null, remains_status: null, ex_gratia_status: null,
    status: 'abroad', notes: note, updated_at: iso(now), last_action_at: iso(now) });
  return (await store.get('workers', { id: worker.id }))!;
}

export async function updateDeathStatus(store: Store, worker: Row, remains: string, exGratia: string, now: Date): Promise<Row> {
  if (!REMAINS_STATUSES.includes(remains)) throw new CaseError(`remains status must be one of ${REMAINS_STATUSES.join(', ')}`);
  if (!EX_GRATIA_STATUSES.includes(exGratia)) throw new CaseError(`ex-gratia status must be one of ${EX_GRATIA_STATUSES.join(', ')}`);
  await store.update('workers', { id: worker.id }, { remains_status: remains, ex_gratia_status: exGratia,
    updated_at: iso(now), last_action_at: iso(now) });
  return (await store.get('workers', { id: worker.id }))!;
}

/** What the voice agent says to a family member who reports a death. */
export function deathInstruction(worker: Row): string {
  const country = worker.dest_country || worker.dest_city || 'that country';
  const support = exGratiaCountry(worker)
    ? 'Say: the Telangana government gives support money to families of workers who die in Gulf countries, ' +
      'and a Saathi caseworker will help them apply. Do not say an amount. '
    : 'Say: a Saathi caseworker will check what government support the family can get. ';
  return 'Speak slowly and gently. Say: I am very sorry. You are not alone; Saathi will stay with your family ' +
    `through this. A Saathi caseworker will inform the Indian Embassy in ${country} with these details, so ` +
    'they can help with bringing them home and with the papers. Also say: no one should ask you for money to ' +
    'bring the body home; if someone asks, tell the caseworker. ' + support +
    'Then, only what they have not said yet, ONE question at a time: who told you, and that person\'s phone ' +
    'number; in which city it happened. Do not press for how it happened. Never promise when the body will ' +
    'come home or that money will come. Never ask for the passport number or bank details.';
}

/** "GS-W9HWSY" -> "G S, W 9 H W S Y", so the voice reads it letter by letter. */
export const spokenCaseId = (caseId: string) => 'G S, ' + Array.from(caseId).slice(3).join(' ');

/** Help line: keep what helps trace the caller (name, home, agent, nearby place) on the case. Fills
 * empty fields only; never overwrites what a caseworker typed. */
async function saveTrace(store: Store, worker: Row, data: Row, now: Date): Promise<void> {
  const a = normalizeAnswers(data);
  const changes: Row = {};
  const name = _text(data, 'caller_name');
  if (name && name.toLowerCase() !== 'not_said' && String(worker.worker_name ?? '').startsWith('Caller (')) changes.worker_name = name;
  if (a.agent_name && !truthy(worker.agent_name)) changes.agent_name = cut(a.agent_name, 200);
  if (a.agent_phone && !truthy(worker.sub_agent_phone)) {
    try { changes.sub_agent_phone = normalizePhone(a.agent_phone); } catch (e) { if (!(e instanceof CaseError)) throw e; }
  }
  if (a.current_city && !truthy(worker.dest_city)) changes.dest_city = cut(a.current_city, 200);
  if (a.home_district && !truthy(worker.home_district)) changes.home_district = cut(a.home_district, 60);
  const notes = orStr(worker.notes);
  const extra = ([['home_district', 'Home'], ['landmark', 'Near']] as const)
    .filter(([k, label]) => a[k] && !notes.includes(`${label}: ${a[k]}`)).map(([k, label]) => `${label}: ${a[k]}`);
  if (extra.length) changes.notes = cut((notes + ' ' + extra.join('. ') + '.').trim(), 2000);
  if (Object.keys(changes).length) {
    changes.updated_at = iso(now);
    await store.update('workers', { id: worker.id }, changes);
    Object.assign(worker, changes);
  }
}

const isObj = (v: unknown): v is Row => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Bolna puts after-call extractions under a category, each with an `objective` (pre-defined answer)
 * or `subjective` (free text) value:
 * {"help_check": {"abroad": {"objective": "yes", ...}, "notes": {"subjective": "...", ...}}}
 * Flat {"field": "value"} data is accepted too. "not_said" becomes empty. */
export function flattenExtraction(extracted: unknown): Row {
  const out: Row = {};
  const shaped = (v: unknown) => isObj(v) && (Object.hasOwn(v, 'objective') || Object.hasOwn(v, 'subjective'));
  const value = (v: unknown): unknown => {
    if (shaped(v)) {
      const o = v as Row;
      v = o.objective !== null && o.objective !== undefined && o.objective !== '' ? o.objective : o.subjective ?? null;
    }
    return v === null || v === undefined || pyStr(v).trim().toLowerCase() === 'not_said' ? '' : v;
  };
  for (const [k, v] of Object.entries(truthy(extracted) && isObj(extracted) ? extracted : {})) {
    if (isObj(v) && !shaped(v)) {
      for (const [k2, v2] of Object.entries(v)) out[k2.toLowerCase()] = value(v2);
    } else {
      out[k.toLowerCase()] = value(v);
    }
  }
  return out;
}

/** After a call to the Gulf Saathi line: if Bolna's extraction says the caller is abroad or in danger,
 * open or update their help case, even if the live voice AI never called report_problem. null when
 * there is nothing to act on. */
export async function helpFromExtraction(store: Store, c: Row, now: Date): Promise<Row | null> {
  const ex = flattenExtraction(truthy(c.extracted) ? c.extracted : {});
  const a = normalizeAnswers(ex);
  // "Needs help" alone is not danger: someone checking an agent before paying also asks for help (live
  // call 22 Oct 2026). Act only when they are abroad or report harm that only happens abroad.
  const danger = a.threatened === true || a.movement_restricted === true
    || a.passport_with_worker === false || (a.months_unpaid || 0) > 0
    || a.pickup_status === 'other_person' || a.pickup_status === 'nobody' || Boolean(a.papers_problem);
  const died = yesNo(ex.worker_died) === true; // reported by family in India: "abroad" may be no
  const abroad = yesNo(ex.abroad);
  if (!truthy(c.user_number) || (!died && (abroad === false || !(abroad || danger)))) return null;
  const data: Row = Object.fromEntries(Object.entries(ex).filter(([k]) => k !== 'case_id'));
  data.caller_phone = c.user_number;
  data.notes = ('After-call summary: ' + orStr(ex.notes)).trim();
  const out = await reportProblem(store, data, now);
  return truthy(out.ok) ? out : null;
}

/** worker id -> the latest briefing check-in, for workers who had one. */
export async function briefedWorkerIds(store: Store): Promise<Record<string, Row>> {
  const out: Record<string, Row> = {};
  for (const ch of await store.select('checkins', null, { order: 'created_at', desc: false })) {
    if (ch.kind === 'briefing') out[ch.worker_id] = ch;
  }
  return out;
}

export const hasPredepartureFlags = (w: Row) => promise.predepartureChecks(w).length > 0;

/** The team's own phones (GS_TEAM_PHONES, comma separated): their test calls are not traction. */
export function teamPhones(): Set<string> {
  const out = new Set<string>();
  for (const raw of (process.env.GS_TEAM_PHONES ?? '').split(',')) {
    try { if (raw.trim()) out.add(normalizePhone(raw)); } catch (e) { if (!(e instanceof CaseError)) throw e; }
  }
  return out;
}

/** Answered calls on the live system, never demo cases. 'outside_team' is null until the team's own
 * phones are listed, so test calls never pass as real users. */
export function callCounts(calls: Row[], workers: Row[], team: Set<string>): Row {
  const demoIds = new Set(workers.filter((w) => truthy(w.is_demo)).map((w) => w.id));
  const phones = new Map(workers.map((w) => [w.id, w.worker_phone ?? null]));
  let answered = 0, outside = 0;
  const callers = new Set<string>();
  for (const c of calls) {
    if (!truthy(c.answered) || demoIds.has(c.worker_id)) continue;
    const raw: Row = truthy(c.raw) ? c.raw : {};
    let number: unknown = raw.user_number || (truthy(raw.telephony_data) ? raw.telephony_data : {}).to_number || phones.get(c.worker_id);
    try { number = truthy(number) ? normalizePhone(number) : null; } catch (e) { if (!(e instanceof CaseError)) throw e; number = null; }
    answered += 1;
    if (team.size && number && !team.has(number as string)) {
      outside += 1;
      callers.add(number as string);
    }
  }
  return { answered, outside_team: team.size ? outside : null, outside_callers: team.size ? callers.size : null };
}

export const CLOCK_DAYS = 7; // an open alert with no caseworker action for this long is overdue

/** A caseworker did something on this case (placed a call, recorded a death...). */
export async function markAction(store: Store, worker: Row, now: Date): Promise<void> {
  await store.update('workers', { id: worker.id }, { last_action_at: iso(now) });
}

/** How long the oldest open alert has waited, and when a caseworker last acted. The "48 days, no
 * update" problem: nobody should be forgotten after the alert. */
export function caseClock(worker: Row, openAlerts: Row[], now: Date): Row | null {
  const started = openAlerts.filter((e) => e.worker_id === worker.id).map((e) => parseTs(e.created_at)).filter((t): t is Date => t !== null);
  if (!started.length) return null;
  const first = new Date(Math.min(...started.map((t) => t.getTime())));
  const openDays = daysBetween(now, first);
  let last = parseTs(worker.last_action_at);
  last = last && last >= first ? last : null; // actions before the alert don't count
  const lastDays = last ? daysBetween(now, last) : null;
  const overdue = (lastDays !== null ? lastDays : openDays) >= CLOCK_DAYS;
  return { open_days: openDays, last_action_days: lastDays, overdue };
}

/** What the voice agent tells a family calling again about an open case. */
export async function caseAgeLine(store: Store, worker: Row, now: Date): Promise<string> {
  const clock = caseClock(worker, await store.select('escalations', { worker_id: worker.id, status: 'open' }), now);
  if (!clock || clock.open_days < 1) return '';
  return `Also tell them gently: their case has been open for ${clock.open_days} days and is still being worked ` +
    'on. Do not promise a date.';
}

/** The numbers a state office asks for first. */
export function summaryCounts(workers: Row[], briefed: Record<string, Row>): Row {
  return {
    registered: workers.length,
    in_india: workers.filter((w) => w.status === 'registered').length,
    abroad: workers.filter((w) => w.status === 'abroad').length,
    briefed: workers.filter((w) => Object.hasOwn(briefed, w.id)).length,
    at_risk: workers.filter((w) => rank(w.risk_level) >= rank('high')).length,
    red_flags: workers.filter(hasPredepartureFlags).length,
  };
}

const squashWs = (s: string) => s.split(/\s+/u).filter(Boolean).join(' ');

function agentKey(w: Row): string | null {
  const detail: Row = truthy(w.agent_check_detail) ? w.agent_check_detail : {};
  if (w.agent_check === 'confirmed_in_list' && truthy(detail.candidates)) return String(detail.candidates[0].agency).toUpperCase();
  const name = w.agent_name || w.agent_owner;
  return name ? squashWs(String(name)).toUpperCase() : null;
}

/** Per recruiting agent named in our cases: how its workers are doing. The evidence a state agent
 * register would want; no claim about the agent itself. */
export function agentStats(workers: Row[]): Row[] {
  const groups = new Map<string, Row>();
  for (const w of workers) {
    const key = agentKey(w);
    if (!key) continue;
    if (!groups.has(key)) groups.set(key, { agent: key, licensed: false, cases: 0, not_in_list: 0, over_cap: 0,
      at_risk: 0, critical: 0, districts: new Set<string>(), employers: new Set<string>(), case_ids: [] });
    const g = groups.get(key)!;
    g.cases += 1;
    g.case_ids.push(w.case_id);
    g.licensed = g.licensed || w.agent_check === 'confirmed_in_list';
    g.not_in_list += Number(w.agent_check === 'not_found' || w.agent_check === 'need_more_info');
    g.over_cap += Number(w.fee_status === 'over_cap');
    g.at_risk += Number(rank(w.risk_level) >= rank('high'));
    g.critical += Number(w.risk_level === 'critical');
    if (truthy(w.agent_district)) g.districts.add(pyTitle(squashWs(String(w.agent_district))));
    if (truthy(w.employer_name)) {
      const at = [w.dest_city, w.dest_country].filter(truthy).join(', ');
      g.employers.add(squashWs(String(w.employer_name)) + (at ? ` (${at})` : ''));
    }
  }
  const out: Row[] = [...groups.values()].map((g) => ({ ...g, districts: pySorted(g.districts), employers: pySorted(g.employers) }));
  return pySorted(out, (g) => [-g.critical, -g.at_risk, -g.not_in_list, -g.over_cap, -g.cases, g.agent]);
}

export async function resolveEscalation(store: Store, escalationId: string, now: Date): Promise<Row | null> {
  const rows = await store.update('escalations', { id: escalationId }, { status: 'resolved', resolved_at: iso(now) });
  if (!rows.length) return null;
  const w = (await store.get('workers', { id: rows[0].worker_id }))!;
  const latest = await store.select('checkins', { worker_id: w.id }, { limit: 1 });
  const level = latest.length ? latest[0].risk_level : 'ok';
  await store.update('workers', { id: w.id }, { risk_level: await overallLevel(store, w.id, level), updated_at: iso(now),
    last_action_at: iso(now) });
  return rows[0];
}

/** Python ", ".join(x for x in xs if x). */
const joinSet = (xs: unknown[], sep = ', ') => xs.filter(truthy).map(pyStr).join(sep);
/** x if x not in (None, "") else default, as text. */
const orDefault = (x: unknown, d = 'not recorded') => (x === null || x === undefined || x === '' ? d : pyStr(x));
const upper = (v: unknown) => pyStr(v).toUpperCase();
const latestAnswers = async (store: Store, w: Row): Promise<Row> => {
  const latest = (await store.select('checkins', { worker_id: w.id }, { limit: 5 }))[0] ?? null;
  return truthy((latest ?? {}).answers) ? latest!.answers : {};
};
const reasonsOf = (w: Row): Row[] => (truthy(w.risk_reasons) ? w.risk_reasons : []);

/** Short urgent message a caseworker sends to the Indian Embassy / Consulate (or MADAD) for a worker
 * in danger: who, where, what they said, how to reach them. */
export async function embassyAlert(store: Store, worker: Row, now: Date): Promise<{ subject: string; body: string }> {
  const w = worker;
  if (truthy(w.death_reported_at)) return deathAlert(w, now);
  const a = await latestAnswers(store, w);
  const where = joinSet([a.current_city, a.landmark, a.current_location]) || joinSet([w.dest_city, w.dest_country]) || 'not known';
  const lines = [
    `URGENT: Indian worker may need help. Gulf Saathi case ${pyStr(w.case_id)}, ${fmtIst(now)}.`,
    '',
    `Name: ${pyStr(w.worker_name)}   Phone: ${pyStr(w.worker_phone)}`,
    `Where (as told on the call): ${where}`,
    `Risk: ${upper(w.risk_level || 'ok')}`,
    ...reasonsOf(w).map((r) => `  - ${reasonText(r)}`),
    `Employer: ${w.employer_name || 'not recorded'}   Sponsor: ${w.sponsor_name || 'not recorded'} ` +
      `(ID ${w.sponsor_id || 'not recorded'})`,
    `Recruiting agent: ${w.agent_name || 'not recorded'}`,
    `Family in India: ${w.family_phone || 'not recorded'}`,
  ];
  if (truthy(a.notes)) lines.push(`Worker said: ${pyStr(a.notes)}`);
  const papers = reasonsOf(w).find((r) => r.code === 'papers_problem');
  if (papers) {
    const agent = joinSet([w.agent_name, w.sub_agent_phone]) || 'not known yet';
    lines.push('', `Legal or papers problem: ${pyStr(papers.detail ?? null)}. The worker may be a victim of illegal recruitment ` +
      `(agent: ${agent}) or of someone misusing their ID, phone or bank account. May need an Emergency ` +
      'Certificate to return home. Please do not treat the worker as an offender.');
  }
  lines.push('', 'Reported by phone to Gulf Saathi (Telangana) and not independently verified. ' +
    'Please contact the worker. Full case packet available on request.');
  return { subject: `URGENT: Indian worker in distress, ${w.dest_country || 'Gulf'}, case ${pyStr(w.case_id)}`, body: lines.join('\n') };
}

const byCreated = (rows: Row[]) => pySorted(rows, (c) => c.created_at || '');
const filled = (o: unknown): Row => Object.fromEntries(Object.entries(truthy(o) ? (o as Row) : {}).filter(([, v]) => notBlank(v)));

/** Dated record of every call: where the worker said they were, what work, whether pay came and the
 * passport was with them. If the employer files a false absconding report, this shows the worker was in
 * contact and working, and when pay stopped. */
export async function proofOfWork(store: Store, worker: Row, now: Date): Promise<Row> {
  const w = worker;
  const calls = byCreated(await store.select('calls', { worker_id: w.id }));
  const checkins = byCreated(await store.select('checkins', { worker_id: w.id }));
  // The voice AI saves several times during one call: merge saves of the same kind less than 15
  // minutes apart into one row per call.
  const callsSaid: Row[] = [];
  for (const ch of checkins) {
    if (ch.kind === 'briefing') continue;
    const at = parseTs(ch.created_at);
    const last = callsSaid.length ? callsSaid[callsSaid.length - 1] : null;
    const rs = (truthy(ch.risk_reasons) ? ch.risk_reasons : []) as Row[];
    if (last && last.kind === (ch.kind ?? null) && at && last.last && at.getTime() - last.last.getTime() < 15 * MIN) {
      Object.assign(last.answers, filled(ch.answers));
      for (const r of rs) last.reasons.set(r.code, r);
      last.last = at;
    } else {
      callsSaid.push({ at: ch.created_at, last: at, kind: ch.kind ?? null, answers: filled(ch.answers),
        reasons: new Map(rs.map((r) => [r.code, r])) });
    }
  }
  const rows: Row[] = [];
  const ynText = (v: unknown) => (v === true ? 'yes' : v === false ? 'NO' : '');
  for (const g of callsSaid) {
    const a = g.answers;
    let pay = a.salary_received === false || truthy(a.months_unpaid)
      ? 'not paid' + (truthy(a.months_unpaid) ? ` (${pyStr(a.months_unpaid)} months)` : '')
      : truthy(a.salary_received) ? 'paid' : '';
    if (truthy(a.salary_amount)) pay = stripChars(pay + `, ${pyStr(a.salary_amount)} ${orStr(w.salary_currency)}`, ', ').trim();
    rows.push({ when: fmtIst(g.at), kind: g.kind, where: joinSet([a.current_city, a.landmark, a.current_location]),
      work: a.current_job || '', pay, passport: ynText(a.passport_with_worker),
      said: [...g.reasons.values()].map((r: Row) => reasonText(r)).join('; ') || 'no problem reported' });
  }
  const first = (test: (a: Row) => boolean) => {
    const i = callsSaid.findIndex((g, k) => k < rows.length && test(g.answers));
    return i >= 0 ? rows[i].when : null;
  };
  const unpaidFrom = first((a) => a.salary_received === false || truthy(a.months_unpaid));
  const passportFrom = first((a) => a.passport_with_worker === false);
  const answered = calls.filter((c) => truthy(c.answered));
  const said = promiseSaid(w);
  const summary = [
    `Worker: ${pyStr(w.worker_name)}   Phone: ${pyStr(w.worker_phone)}   Gulf Saathi case ${pyStr(w.case_id)}`,
    `Employer: ${w.employer_name || 'not recorded'}   Sponsor: ${w.sponsor_name || 'not recorded'} ` +
      `(ID ${w.sponsor_id || 'not recorded'})`,
    `Promised before departure: ${w.job_title || 'job not recorded'}, ` +
      (truthy(w.contract_salary) ? `${Math.trunc(pyNum(w.contract_salary))} ${orStr(w.salary_currency)}`.trim() : 'salary not recorded') +
      `, in ${joinSet([w.dest_city, w.dest_country]) || 'place not recorded'}` +
      ` (recorded ${fmtIst(w.created_at)})`,
    ...(said ? [`Verbal promise (not on paper): ${said}`] : []),
    `Calls answered: ${answered.length}. First: ${answered.length ? fmtIst(answered[0].created_at) : 'none'}. ` +
      `Last contact: ${fmtIst(w.last_contact_at)}.`,
  ];
  if (unpaidFrom) summary.push(`Salary first reported unpaid: ${unpaidFrom}.`);
  if (passportFrom) summary.push(`Passport first reported not with the worker: ${passportFrom}.`);
  const recordings = calls.filter((c) => truthy(c.recording_url)).map((c) => `${fmtIst(c.created_at)}: ${pyStr(c.recording_url)}`);
  return {
    title: `Record of contact and work: ${pyStr(w.worker_name)} (Gulf Saathi case ${pyStr(w.case_id)})`,
    summary, rows, recordings,
    note: `Prepared by Gulf Saathi (Telangana) on ${fmtIst(now)} from dated phone calls with the worker. ` +
      'What the worker said is recorded as said and not independently verified; the call recordings are ' +
      'the evidence. Gulf Saathi is a helpline, not a government body.',
  };
}

function deathAlert(w: Row, now: Date): { subject: string; body: string } {
  const v = (x: unknown) => orDefault(x);
  const lines = [
    `Reported death of an Indian worker. Gulf Saathi case ${pyStr(w.case_id)}, ${fmtIst(now)}.`,
    '',
    `Name: ${pyStr(w.worker_name)}   Phone: ${pyStr(w.worker_phone)}`,
    `What was reported: ${v(w.death_note)}`,
    `Went to: ${joinSet([w.dest_city, w.dest_country]) || 'not recorded'}   Job: ${v(w.job_title)}`,
    `Employer: ${v(w.employer_name)}   Employer phone: ${v(w.employer_phone)}`,
    `Sponsor: ${v(w.sponsor_name)} (ID ${v(w.sponsor_id)})`,
    `Recruiting agent: ${v(w.agent_name)}`,
    `Next of kin in India: ${v(w.family_name)} (${v(w.family_relation)}), ${v(w.family_phone)}`,
    `Last contact with Gulf Saathi: ${fmtIst(w.last_contact_at)}`,
    '',
    'The family asks for help to: confirm the death and its cause, get the death certificate, bring the body home ' +
      'or arrange burial there (as the next of kin decides), and recover unpaid wages and dues.',
    'Reported by phone to Gulf Saathi (Telangana) and not independently verified. Full case packet available on request.',
  ];
  return { subject: `Death of Indian worker reported, ${w.dest_country || 'Gulf'}, case ${pyStr(w.case_id)}`, body: lines.join('\n') };
}

/** Papers for the family and the caseworker after a death: the facts the embassy needs, and the steps,
 * in English and Telugu. Saathi does not make the NOC or consent form: the embassy has its own, which
 * the next of kin signs. */
export function deathPacket(_store: Store, worker: Row, now: Date): Row {
  const w = worker;
  const v = orDefault;
  const nameTe = truthy(w.worker_name_te) ? w.worker_name_te : w.worker_name;
  const country = v(w.dest_country, 'the country where it happened');
  const eg = exGratiaCountry(w);
  const facts = [
    `Worker: ${pyStr(w.worker_name)}   Phone: ${pyStr(w.worker_phone)}   Gulf Saathi case: ${pyStr(w.case_id)}`,
    "Passport number: ____________________ (copy it from the family's passport copy; Saathi never stores it)",
    `What was reported: ${v(w.death_note)} (reported ${fmtIst(w.death_reported_at)})`,
    (`Went to: ${joinSet([w.dest_city, w.dest_country]) || 'not recorded'}   ` +
      `Job: ${v(w.job_title)}   Departure: ${v(w.departure_date)} ${orStr(w.flight_no)}`).trimEnd(),
    `Employer: ${v(w.employer_name)}   Phone: ${v(w.employer_phone)}`,
    `Sponsor (kafeel): ${v(w.sponsor_name)}   Sponsor ID: ${v(w.sponsor_id)}`,
    `Recruiting agent: ${v(w.agent_name)}   Village agent phone: ${v(w.sub_agent_phone)}`,
    `Next of kin: ${v(w.family_name, '____________')} (${v(w.family_relation, '______')}), ` +
      `phone ${v(w.family_phone, '____________')}`,
    `Last contact with Gulf Saathi: ${fmtIst(w.last_contact_at)}`,
  ];
  const steps = [
    `Tell the Indian Embassy / Consulate in ${country} with the facts above, and register it on MADAD ` +
      '(madad.gov.in). The embassy works with the employer and the local authorities.',
    'The next of kin decides: bring the body home, or burial / cremation there. The embassy gives its own ' +
      'consent (NOC) form; the next of kin signs it. Read it to them in Telugu before they sign.',
    'Costs: ask the employer to pay, as the contract usually requires. If they do not, ask the embassy whether the ' +
      'Indian Community Welfare Fund (ICWF) can help.',
    'Keep copies of: the local death certificate and its translation, the embassy\'s papers, the cancelled ' +
      'passport, the airline cargo papers, and the job contract or visa.',
    'Unpaid salary and end-of-service money: ask the embassy to claim them from the employer for the family.',
    'If the employer will not pay to bring the body home and the embassy says it has no funds, ask the Telangana ' +
      "government through CM Pravasi Prajavani for help from the Chief Minister's Relief Fund (it paid Rs 1.5 lakh " +
      'in an Oman case in 2026).',
    'Tell the family: "No one should ask you for money to bring the body home. If someone asks, tell the ' +
      'caseworker." (People have posed as helpers and demanded large sums.)',
    'If the death was an accident: Pravasi Bharatiya Bima Yojana (PBBY, compulsory for ECR workers going to ECR ' +
      'countries) pays Rs 10 lakh for accidental death. Claim it through the insurer. PBBY on this case: ' +
      `${v(w.pbby, 'not recorded')}; nominee: ${v(w.pbby_nominee, 'not recorded')}.`,
  ];
  if (eg !== false) {
    steps.push('Telangana ex-gratia: G.O. 205 (16 Sep 2024) sanctioned the Rs 5 lakh ex-gratia; G.O. 216 (Oct 2024) gave the guidelines. Deaths on or after 7 Dec 2023, any cause, in 7 Gulf countries ' +
      '(Bahrain, Iraq, Kuwait, Oman, Qatar, Saudi Arabia, UAE). ' +
      "Apply at the District Collector's office within 6 months of the death (or of receiving the " +
      'body) with the death certificate, cancelled passport, proof of work abroad (work visa or ' +
      "employment contract) and the family's bank details. Check the current rules at the Collectorate." +
      (w.visa_type === 'visit' || w.visa_type === 'tourist'
        ? ` This worker's visa is recorded as a ${pyStr(w.visa_type)} visa: without a work visa or contract ` +
          'the claim may be refused, so ask the Collectorate early.' : ''));
  }
  const teSteps = [
    `సాథి కేస్‌వర్కర్ ${country} లోని భారత రాయబార కార్యాలయానికి వివరాలు పంపుతారు.`,
    'మృతదేహాన్ని ఇంటికి తీసుకురావాలా, అక్కడే అంత్యక్రియలు చేయాలా అనేది కుటుంబమే నిర్ణయిస్తుంది. ' +
      'రాయబార కార్యాలయం ఇచ్చే అనుమతి పత్రం (NOC) పై కుటుంబ సభ్యులు సంతకం చేయాలి. ' +
      'సంతకం చేసే ముందు సాథి కేస్‌వర్కర్ దాన్ని తెలుగులో చదివి వినిపిస్తారు.',
    'ఖర్చులు యజమాని భరించాలి. భరించకపోతే, రాయబార కార్యాలయాన్ని ICWF నిధి నుంచి సహాయం అడుగుతాం.',
    'ఈ పత్రాలు దాచుకోండి: మరణ ధ్రువీకరణ పత్రం, రద్దు చేసిన పాస్‌పోర్ట్, ఉద్యోగ పత్రాలు, బ్యాంక్ ఖాతా వివరాలు.',
    'రావాల్సిన జీతం, ఇతర డబ్బుల కోసం రాయబార కార్యాలయం ద్వారా యజమానిని అడుగుతాం.',
    'యజమాని, రాయబార కార్యాలయం ఖర్చు భరించకపోతే, ప్రవాసీ ప్రజావాణి ద్వారా ముఖ్యమంత్రి సహాయ నిధి నుంచి సహాయం అడుగుతాం.',
    'మృతదేహాన్ని ఇంటికి తీసుకురావడానికి ఎవరూ మిమ్మల్ని డబ్బులు అడగకూడదు. ఎవరైనా అడిగితే కేస్‌వర్కర్‌కి చెప్పండి.',
  ];
  if (eg !== false) {
    teSteps.push('గల్ఫ్ దేశాల్లో మరణించిన కార్మికుల కుటుంబాలకు తెలంగాణ ప్రభుత్వం ఎక్స్‌గ్రేషియా ఇస్తుంది. ' +
      'మరణించిన 6 నెలల లోపు జిల్లా కలెక్టర్ కార్యాలయంలో దరఖాస్తు చేయాలి. సాథి కేస్‌వర్కర్ సహాయం చేస్తారు.');
  }
  return {
    english: {
      title: `Death of a worker abroad: facts and next steps (Gulf Saathi case ${pyStr(w.case_id)})`,
      facts, steps,
      status: `Body: ${v(w.remains_status)}   Ex-gratia: ${v(w.ex_gratia_status)}`,
      note: `Prepared by Gulf Saathi on ${fmtIst(now)}. Facts are as reported by phone and not independently ` +
        'verified. The rules above can change: check each one with the embassy or the Collectorate.',
    },
    telugu: {
      title: `${pyStr(nameTe)} గారి మరణం: తర్వాత ఏం చేయాలి (గల్ఫ్ సాథి కేసు ${pyStr(w.case_id)})`,
      opening: 'మీకు కలిగిన నష్టానికి చాలా బాధగా ఉంది. మీరు ఒంటరి కాదు. ఈ పనులన్నీ సాథి కేస్‌వర్కర్ మీతో కలిసి చేస్తారు.',
      steps: teSteps,
    },
  };
}

// --- case packet ------------------------------------------------------------------

export async function timeline(store: Store, worker: Row): Promise<Row[]> {
  const events: Row[] = [{ at: worker.created_at, type: 'registered', text: 'Case registered before departure' }];
  for (const c of await store.select('calls', { worker_id: worker.id })) events.push({ at: c.updated_at || c.created_at, type: 'call', call: c });
  for (const ch of await store.select('checkins', { worker_id: worker.id })) events.push({ at: ch.created_at, type: 'checkin', checkin: ch });
  for (const e of await store.select('escalations', { worker_id: worker.id })) events.push({ at: e.created_at, type: 'escalation', escalation: e });
  return pySorted(events, (e) => parseTs(e.at)?.getTime() ?? -8.64e15, true);
}

/** A petition the family does not have to carry to Hyderabad: Saathi fills it from the case; a
 * caseworker hands it in at Pravasi Prajavani (Praja Bhavan) for them. Telugu is machine-drafted from
 * fixed sentences and needs a native speaker's check. */
export async function prajavaniPetition(store: Store, worker: Row, now: Date): Promise<Row> {
  const w = worker;
  const v = (x: unknown, d = 'not known') => orDefault(x, d);
  const a = await latestAnswers(store, w);
  const where = joinSet([a.current_city, a.landmark, a.current_location]) || joinSet([w.dest_city, w.dest_country]) || 'not known';
  const reasons = reasonsOf(w);
  const petitioner = w.family_name || '';
  const relation = w.family_relation || w.reported_by || '';
  const nameTe = truthy(w.worker_name_te) ? w.worker_name_te : w.worker_name;
  const country = v(w.dest_country, 'Gulf');
  let jobLine: string | null = null;
  if (truthy(w.job_title) || truthy(a.current_job) || truthy(w.visa_job)) {
    jobLine = `Promised job: ${v(w.job_title)}. Job on the visa: ${v(w.visa_job)}. ` +
      `Work he/she says they are made to do: ${v(a.current_job)}.`;
  }
  const events: string[] = [];
  for (const e of (await timeline(store, w)).slice(0, 10).reverse()) {
    const when = fmtIst(e.at).split(',')[0];
    if (e.type === 'registered') events.push(`${when}: case registered with Gulf Saathi`);
    else if (e.type === 'checkin') {
      const ch = e.checkin;
      const what = ((truthy(ch.risk_reasons) ? ch.risk_reasons : []) as Row[]).map((r) => reasonText(r)).join('; ') || 'no problem reported';
      events.push(`${when}: ${pyStr(ch.kind ?? null)} call, worker said: ${what}`);
    } else if (e.type === 'escalation') {
      events.push(`${when}: Gulf Saathi raised a ${upper(e.escalation.level)} alert`);
    }
  }
  const said = promiseSaid(w);
  return {
    english: {
      to: 'To: The Officer in charge, Pravasi Prajavani, Praja Bhavan, Hyderabad, Telangana',
      subject: `Subject: Request for help for ${pyStr(w.worker_name)}, a worker from Telangana in distress in ` +
        `${country} (Gulf Saathi case ${pyStr(w.case_id)})`,
      facts: [
        `Worker: ${pyStr(w.worker_name)}   Phone: ${pyStr(w.worker_phone)}`,
        `Where he/she is now (as told on the phone): ${where}`,
        `Employer: ${v(w.employer_name)}   Sponsor (kafeel): ${v(w.sponsor_name)} ` +
          `(ID ${v(w.sponsor_id)})`,
        `Recruiting agent: ${v(w.agent_name)}   Village agent phone: ${v(w.sub_agent_phone)}   ` +
          `Check against the MEA licensed list: ${v(w.agent_check, 'not checked')}`,
        ...(said ? [`Verbal promise (not on paper): ${said}`] : []),
        ...(truthy(w.amount_paid_total) ? [`Paid to the agent: Rs ${fmtRupees(pyInt(w.amount_paid_total))} (legal limit Rs 35,400)`] : []),
        ...(jobLine ? [jobLine] : []),
      ],
      problems: reasons.length ? reasons.map((r) => reasonText(r)) : ['See timeline below.'],
      timeline: events,
      requests: [
        `Forward this case to the Indian Embassy / Consulate in ${country} so that they contact the worker.`,
        'Help the worker get his/her passport and unpaid wages, and return home safely if he/she wishes.',
        'Look into the recruiting agent named above (eMigrate complaint / police), if the facts are confirmed.',
      ],
      note: `Prepared by Gulf Saathi on ${fmtIst(now)} from phone calls with the worker and family. Facts are as ` +
        'reported and not independently verified. Call recordings and the full case packet are available on ' +
        'request.',
      petitioner: `Petitioner: ${v(petitioner, '____________')} (${v(relation, 'relation ______')}), ` +
        `phone ${v(w.family_phone, '____________')}`,
    },
    telugu: {
      to: 'గౌరవనీయులైన అధికారి గారికి, ప్రవాసీ ప్రజావాణి, ప్రజా భవన్, హైదరాబాద్.',
      subject: `విషయం: గల్ఫ్‌లో ఇబ్బందుల్లో ఉన్న ${pyStr(nameTe)} గారికి సహాయం కోసం విన్నపం ` +
        `(గల్ఫ్ సాథి కేసు ${pyStr(w.case_id)})`,
      body: [`${pyStr(nameTe)} గారు ${country} కి పనికి వెళ్లారు. ఫోన్‌లో వారు చెప్పినదాని ప్రకారం:`,
        ...reasons.map((r) => `• ${reasonText(r, 'te')}`),
        'దయచేసి ఈ విషయాన్ని భారత రాయబార కార్యాలయానికి పంపి, వారిని సురక్షితంగా ఇంటికి తీసుకురావడానికి, ' +
          'జీతం, పాస్‌పోర్ట్ ఇప్పించడానికి, ఏజెంట్‌పై చర్య తీసుకోవడానికి సహాయం చేయగలరు.',
        'పూర్తి వివరాలు ఇంగ్లీష్‌లో క్రింద ఉన్నాయి.'],
      petitioner: `విన్నపం చేసేవారు: ${v(petitioner, '____________')}, ఫోన్ ${v(w.family_phone, '____________')}`,
    },
  };
}

/** Plain English summary for MADAD, TOMCOM or the Indian Embassy. A person files it. */
export async function casePacket(store: Store, worker: Row, now: Date): Promise<string> {
  const w = worker;
  const v = (x: unknown) => orDefault(x);
  const lines: string[] = [
    `GULF SAATHI CASE PACKET - ${pyStr(w.case_id)}`,
    `Prepared ${fmtIst(now)} from the worker's own phone answers. Facts below are as reported and have not ` +
      'been independently verified.',
    '',
    `CURRENT RISK LEVEL: ${upper(w.risk_level)}`,
  ];
  for (const r of reasonsOf(w)) lines.push(`  - ${reasonText(r)}`);
  if (truthy(w.death_reported_at)) {
    lines.push(`DEATH REPORTED ${fmtIst(w.death_reported_at)}: ${orStr(w.death_note)}. ` +
      `Body: ${w.remains_status || '-'}. Ex-gratia: ${w.ex_gratia_status || '-'}.`);
  }
  lines.push(
    '',
    '1. WORKER',
    `  Name: ${pyStr(w.worker_name)}`,
    `  Phone: ${pyStr(w.worker_phone)}`,
    `  Status: ${pyStr(w.status)}`,
    `  Last contact: ${fmtIst(w.last_contact_at)}   Missed check-ins in a row: ${pyStr(Object.hasOwn(w, 'missed_checkins') ? w.missed_checkins : 0)}`,
    `  Home: ${v(joinSet([w.home_mandal, w.home_district]))}`,
    `  Passport type: ${v(orStr(w.passport_type).toUpperCase())}   Emigration clearance: ` +
      `${v(w.emigration_clearance)}   PBBY insurance: ${v(w.pbby)} (nominee: ${v(w.pbby_nominee)})`,
    '',
    '2. FAMILY CONTACT',
    `  ${v(w.family_name)} (${v(w.family_relation)}), ${pyStr(w.family_phone ?? null)}`,
    '',
    '3. EMPLOYER / SPONSOR',
    `  Employer: ${v(w.employer_name)}   Phone: ${v(w.employer_phone)}`,
    `  Sponsor (kafeel): ${v(w.sponsor_name)}   Sponsor ID: ${v(w.sponsor_id)}`,
    `  Destination: ${v(w.dest_city)}, ${v(w.dest_country)}   Job: ${v(w.job_title)}`,
    `  Contract salary: ${v(w.contract_salary)} ${orStr(w.salary_currency)}`.trimEnd(),
    '',
    '4. RECRUITING AGENT',
    `  Agency: ${v(w.agent_name)}   Owner: ${v(w.agent_owner)}`,
    `  Licence no. given: ${v(w.agent_licence)}   District: ${v(w.agent_district)}`,
    `  Check against MEA licensed list: ${v(w.agent_check)}`,
    `  Verbal promise (not on paper): ${promiseSaid(w) || 'not recorded'}`,
    `  Full written contract received before paying: ${v(w.contract_before_payment)}`,
    `  Penalty in the contract for leaving or cancelling the visa: ${v(w.exit_penalty)}`,
  );
  if (truthy(w.amount_paid_total)) {
    lines.push(`  Paid to agent: Rs ${fmtRupees(pyInt(w.amount_paid_total))} ` +
      `(${w.fee_status === 'over_cap' ? 'OVER' : 'within'} the Rs 35,400 limit)`);
  }
  lines.push('', '5. TRAVEL', `  Departure: ${v(w.departure_date)}   Flight: ${v(w.flight_no)}`, '', '6. TIMELINE (newest first)');
  const tl = await timeline(store, w);
  for (const e of tl) {
    const when = fmtIst(e.at);
    if (e.type === 'registered') lines.push(`  ${when}  Registered`);
    else if (e.type === 'call') {
      const c = e.call;
      const state = truthy(c.answered) ? 'answered' : truthy(c.missed) ? 'MISSED' : orStr(c.status);
      lines.push(`  ${when}  ${pyTitle(pyStr(c.kind || 'call'))} call, ${state}` +
        (truthy(c.duration_seconds) ? `, ${pyInt(c.duration_seconds)}s` : '') +
        (truthy(c.recording_url) ? `  Recording: ${pyStr(c.recording_url)}` : ''));
    } else if (e.type === 'checkin') {
      const ch = e.checkin;
      const said = Object.entries(filled(ch.answers)).map(([k, val]) => `${k}=${pyStr(val)}`).join(', ');
      lines.push(`  ${when}  Worker's answers (${pyStr(ch.kind ?? null)}): ${said || 'none recorded'}`);
    } else {
      const es = e.escalation;
      lines.push(`  ${when}  ALERT ${upper(es.level)}: ` +
        ((truthy(es.reasons) ? es.reasons : []) as Row[]).map((r) => reasonText(r)).join('; ') +
        `. Family SMS: ${pyStr(es.sms_status ?? null)}`);
    }
  }
  const last = tl.find((e) => e.type === 'call' && truthy(e.call.transcript))?.call;
  if (last) {
    lines.push('', '7. LATEST CALL TRANSCRIPT (Telugu, as recognised by speech software; needs translation)',
      String(last.transcript).trim());
  }
  lines.push(
    '',
    'WHERE TO FILE',
    '  - MADAD (madad.gov.in): grievance for Indians abroad',
    `  - Indian Embassy / Consulate in ${v(w.dest_country)}`,
    '  - eMigrate (emigrate.gov.in) > Register Grievance: complaint against the recruiting agent',
    '  - Telangana: TOMCOM / NRI cell',
  );
  return lines.join('\n') + '\n';
}
