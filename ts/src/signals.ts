// Saathi Intelligence: the same phone number, payment account, sponsor or employer showing up in more
// than one case. Port of gulf_saathi/signals.py.
//
// A signal is a reason for a trained person to look, never a finding. Person names are left out on
// purpose: "Raju" or "Mohammed" would link strangers. Employer names are linked only together with the
// country, and marked weak: company names repeat.
import { asInt, CaseError, normalizePhone, rank } from './cases.js';
import { FEE_CAP_INR } from './config.js';
import type { Row, Store } from './db.js';
import { predepartureChecks } from './promise.js';
import { cut, orStr, pyNum, pySorted, pyStr, pyTitle, squash, truthy } from './py.js';

// [field on the worker, label shown, kind of value, strong?]
export const ENTITY_FIELDS: Array<[string, string, string, boolean]> = [
  ['sub_agent_phone', "Village agent's phone", 'phone', true],
  ['payment_to', 'Money paid to (UPI / account / number)', 'text', true],
  ['sponsor_id', 'Sponsor ID', 'text', true],
  ['employer_phone', "Employer's phone", 'phone', true],
  ['employer_name', 'Employer name (same country)', 'company', false],
];

// Words that make two spellings of one company look different.
const COMPANY_NOISE = new Set(['llc', 'l.l.c', 'co', 'company', 'est', 'establishment', 'trading', 'services', 'service',
  'group', 'the', 'and', '&', 'wll', 'w.l.l', 'spc', 'fze', 'fzco', 'ltd', 'limited', 'pvt']);

export function norm(value: unknown, kind: string, worker: Row | null = null): string | null {
  if (!truthy(value)) return null;
  if (kind === 'phone') {
    try { return normalizePhone(value); } catch (e) { if (e instanceof CaseError) return null; throw e; }
  }
  if (kind === 'company') {
    const words = (pyStr(value).toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((x) => !COMPANY_NOISE.has(x));
    const country = orStr((worker ?? {}).dest_country).toLowerCase().replace(/[^a-z]/g, '');
    if (words.length < 2 || !country) return null; // one word ("Noor") or no country links strangers
    return words.join(' ') + ' / ' + country;
  }
  const v = pyStr(value).replace(/\s+/gu, '').toLowerCase();
  return v || null;
}

/** Demo cases never feed warnings given to real callers, unless switched on for a demo. */
export const includeDemo = () => (process.env.GS_SIGNALS_INCLUDE_DEMO ?? '0') === '1';

function districts(ws: Row[]): string[] {
  return pySorted(new Set(ws.filter((w) => truthy(w.agent_district)).map((w) => pyTitle(squash(pyStr(w.agent_district))))));
}

/** Every value shared by at least `minCases` cases, most worrying first. */
export function repeatedSignals(workers: Row[], minCases = 2): Row[] {
  const seen = new Map<string, { label: string; value: string; strong: boolean; ws: Row[] }>();
  for (const w of workers) {
    for (const [field, label, kind, strong] of ENTITY_FIELDS) {
      const v = norm(w[field], kind, w);
      if (v) {
        const key = JSON.stringify([label, v]);
        if (!seen.has(key)) seen.set(key, { label, value: v, strong, ws: [] });
        seen.get(key)!.ws.push(w);
      }
    }
  }
  const out: Row[] = [];
  for (const { label, value, strong, ws } of seen.values()) {
    if (ws.length < minCases) continue;
    out.push({
      label, value, strong,
      cases: ws.map((w) => w.case_id),
      at_risk: ws.filter((w) => rank(w.risk_level) >= rank('high')).length,
      flagged: ws.filter((w) => predepartureChecks(w).length).length,
      districts: districts(ws),
      demo: ws.every((w) => truthy(w.is_demo)),
    });
  }
  return pySorted(out, (s) => [!s.strong, -s.at_risk, -s.flagged, -s.cases.length, s.label]);
}

export function signalsForCase(worker: Row, workers: Row[]): Row[] {
  return repeatedSignals(workers).filter((s) => s.cases.includes(worker.case_id));
}

function contactKeys(phone = '', payment = ''): [string | null, string | null] {
  return [phone ? norm(phone, 'phone') : null, payment ? norm(payment, 'text') : null];
}

/** Save an agent phone / payment account a caller told Saathi, with what the agent asked for. Every
 * call adds to the picture, not only registered cases. */
export async function recordContact(store: Store, data: Row, nowIso: string): Promise<Row | null> {
  const [phone, payment] = contactKeys(orStr(data.phone), orStr(data.payment));
  if (!(phone || payment)) return null;
  let caller: string | null = null;
  try { caller = truthy(data.caller_phone) ? normalizePhone(data.caller_phone) : null; } catch (e) {
    if (!(e instanceof CaseError)) throw e;
  }
  const text = (k: string, n = 200) => cut(orStr(data[k]).trim(), n) || null;
  return store.insert('contact_reports', {
    created_at: nowIso, phone, payment, amount_asked: asInt(data.amount),
    visa_type: (text('visa_type', 20) || '').toLowerCase() || null, agent_name: text('agent_name'),
    caller_district: text('district', 60), reporter: (text('reporter', 20) || 'worker').toLowerCase(),
    caller_phone: caller, notes: text('notes', 500), is_demo: false,
  });
}

function reportsFor(reports: Row[], phone: string | null, payment: string | null, skipCaller: string | null): Row[] {
  return reports.filter((r) => ((phone && r.phone === phone) || (payment && r.payment === payment))
    && !(skipCaller && r.caller_phone === skipCaller));
}

const overCap = (r: Row) => truthy(r.amount_asked) && pyNum(r.amount_asked) > FEE_CAP_INR;
const isVisit = (r: Row) => r.visa_type === 'visit' || r.visa_type === 'tourist';
const who = (r: Row) => (truthy(r.caller_phone) ? r.caller_phone : r.id);

/** Live check during a call, before the worker pays: has this agent phone or payment account come up
 * in other Saathi cases, or been reported by other callers? Returns counts only, never names or case
 * details, and an instruction for the voice agent. */
export function checkContact(workers: Row[], phone = '', payment = '', reports: Row[] | null = null, callerPhone = ''): Row {
  const [p, m] = contactKeys(phone, payment);
  if (!(p || m)) {
    return { found: false, cases: 0, at_risk: 0, callers: 0,
      instruction: "Ask for the agent's phone number (10 digits) or the UPI ID / account the money goes " +
        'to, read it back digit by digit to confirm, then check again.' };
  }
  const keys: Array<[string, string[]]> = [...(p ? [[p, ['sub_agent_phone', 'employer_phone']] as [string, string[]]] : []),
    ...(m ? [[m, ['payment_to']] as [string, string[]]] : [])];
  const pool = workers.filter((w) => includeDemo() || !truthy(w.is_demo));
  const hits = new Map<string, Row>();
  for (const w of pool) {
    for (const [value, fields] of keys) {
      if (fields.some((f) => norm(w[f], f.includes('phone') ? 'phone' : 'text') === value)) hits.set(w.case_id, w);
    }
  }
  const ws = [...hits.values()];
  const atRisk = ws.filter((w) => rank(w.risk_level) >= rank('high')).length;
  const flagged = ws.filter((w) => predepartureChecks(w).length).length;
  let me: string | null = null;
  try { me = callerPhone ? normalizePhone(callerPhone) : null; } catch (e) { if (!(e instanceof CaseError)) throw e; }
  const rs = reportsFor(reports ?? [], p, m, me);
  const callers = new Set(rs.map(who)).size;
  const over = new Set(rs.filter(overCap).map(who)).size;
  const visit = new Set(rs.filter(isVisit).map(who)).size;
  let say: string;
  if (atRisk || flagged) {
    say = `Say calmly: this number has come up in ${ws.length} other Saathi case(s); ${atRisk} of those workers ` +
      'reported serious problems after travelling' + (flagged ? ` and ${flagged} had red flags before travelling` : '') +
      '. This is not proof against anyone, but please do not pay any more money until a Saathi caseworker ' +
      'has checked it. Never name the other workers or say the agent is a criminal.';
  } else if (over || visit) {
    const parts = [...(over ? [`${over} other caller(s) said this agent asked for more than the legal limit of 35,400 rupees`] : []),
      ...(visit ? [`${visit} other caller(s) were offered a visit or tourist visa for a job`] : [])];
    say = 'Say calmly: ' + parts.join('; ') + '. This is not proof against anyone, but do not pay more than ' +
      '35,400 rupees, pay only digitally with a receipt, and never go on a visit visa for a job.';
  } else if (ws.length || callers) {
    say = `Say: other people have asked Saathi about this number before (${ws.length} case(s), ${callers} other ` +
      'caller(s)), and none reported a problem so far. That is not a check of the agent: still check the ' +
      'licence and get a written contract.';
  } else {
    say = 'Say: this number is not in any Saathi case yet. That does not mean the agent is safe: still check ' +
      'the licence, ask for an employment visa and a written contract, and pay only with a receipt.';
  }
  const ds = districts(ws);
  const districtCount = ds.length ? ds.length : new Set(rs.filter((r) => truthy(r.caller_district)).map((r) => r.caller_district)).size;
  return { found: Boolean(ws.length || callers), cases: ws.length, at_risk: atRisk, flagged,
    callers, callers_over_limit: over, callers_visit_visa: visit, districts: districtCount, instruction: say };
}

/** Numbers and accounts callers told Saathi about, grouped, most worrying first. */
export function reportedContacts(reports: Row[], workers: Row[]): Row[] {
  const groups = new Map<string, { kind: string; value: string; rs: Row[] }>();
  for (const r of reports) {
    if (truthy(r.is_demo) && !includeDemo()) continue;
    for (const kind of ['phone', 'payment']) {
      if (truthy(r[kind])) {
        const key = JSON.stringify([kind, r[kind]]);
        if (!groups.has(key)) groups.set(key, { kind, value: r[kind], rs: [] });
        groups.get(key)!.rs.push(r);
      }
    }
  }
  const out: Row[] = [];
  for (const { kind, value, rs } of groups.values()) {
    const linked = kind === 'phone' ? checkContact(workers, value) : checkContact(workers, '', value);
    const dates = pySorted(rs.map((r) => orStr(r.created_at)));
    const amounts = rs.filter((r) => truthy(r.amount_asked)).map((r) => pyNum(r.amount_asked));
    out.push({
      kind: kind === 'phone' ? 'Agent phone' : 'Paid to (UPI / account)', value,
      callers: new Set(rs.map(who)).size, reports: rs.length,
      over_limit: rs.filter(overCap).length,
      visit_visa: rs.filter(isVisit).length,
      max_amount: amounts.length ? Math.max(...amounts) : null,
      districts: pySorted(new Set(rs.filter((r) => truthy(r.caller_district)).map((r) => pyTitle(String(r.caller_district))))),
      family_reports: rs.filter((r) => r.reporter === 'family').length,
      cases: linked.cases, at_risk: linked.at_risk,
      first_seen: dates.length ? cut(dates[0], 10) : '', last_seen: dates.length ? cut(dates[dates.length - 1], 10) : '',
    });
  }
  return pySorted(out, (g) => [-g.at_risk, -g.callers, -g.over_limit, g.value]);
}
