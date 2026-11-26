// Weekly scam alerts: one short Telugu warning, sent to every worker and family who agreed to receive
// them. Asked for by officials at Pravasi Prajavani (Oct 2026). Port of gulf_saathi/alerts.py.
//
// Alerts warn about scam patterns, never about a person: a message that contains a phone number is
// refused, so nobody is named or accused in a broadcast. Voice alerts go out as a short Bolna call (the
// check-in agent's "alert" section reads the text); SMS goes out once an SMS provider is configured.
import * as bolna from './bolna.js';
import { CaseError, iso, normalizePhone, parseTs } from './cases.js';
import { FEE_CAP_INR } from './config.js';
import type { Row, Store } from './db.js';
import { orStr, pyNum, squash, truthy } from './py.js';
import * as sms from './sms.js';

export const CHANNELS = ['voice', 'sms'];
export const MAX_LEN = 300;
const ALERT_BATCH = 8;

// Ready warnings a caseworker can pick, each about a pattern Saathi sees.
export const TEMPLATES: Array<[string, string, string]> = [
  ['visit_visa', 'Visit visa jobs',
    'గల్ఫ్ సాథి హెచ్చరిక: విజిట్ లేదా టూరిస్ట్ వీసా మీద పని ఇస్తామంటే నమ్మకండి. ఉద్యోగానికి ఎంప్లాయ్‌మెంట్ వీసా మాత్రమే.'],
  ['fee', 'Fee over the legal limit',
    'గల్ఫ్ సాథి హెచ్చరిక: ఏజెంట్‌కు 35,400 రూపాయల కంటే ఎక్కువ ఇవ్వకండి. ప్రతి చెల్లింపుకు రసీదు తీసుకోండి.'],
  ['licence', 'Unlicensed agents',
    'గల్ఫ్ సాథి హెచ్చరిక: డబ్బు ఇచ్చే ముందు ఏజెంట్ ప్రభుత్వ లైసెన్స్ జాబితాలో ఉన్నాడో సాథికి ఫోన్ చేసి చెక్ చేయండి.'],
  ['id_misuse', 'ID, SIM and bank card',
    'గల్ఫ్ సాథి హెచ్చరిక: మీ ID, సిమ్, ఫోన్ లేదా బ్యాంక్ కార్డు ఎవరికీ ఇవ్వకండి. మీ పేరుతో లోన్ తీసుకుంటే మీరు జైలుకు వెళ్లవచ్చు.'],
  ['routes', 'Russia and South-East Asia jobs',
    'గల్ఫ్ సాథి హెచ్చరిక: రష్యా, మయన్మార్, కంబోడియా, లావోస్ ఉద్యోగాల పేరుతో మోసాలు జరుగుతున్నాయి. వెళ్లే ముందు సాథికి చెప్పండి.'],
  ['contract', 'Contract before paying',
    'గల్ఫ్ సాథి హెచ్చరిక: పూర్తి ఒప్పందం కాగితం చూపించే వరకు ఏజెంట్‌కు డబ్బు ఇవ్వకండి.'],
];

export function cleanMessage(text: unknown): string {
  const msg = squash(orStr(text));
  if (!msg) throw new CaseError('write the alert, or pick one');
  const n = Array.from(msg).length;
  if (n > MAX_LEN) throw new CaseError(`keep the alert under ${MAX_LEN} characters (${n} now)`);
  if (/\p{Nd}[\p{Nd}\s-]{7,}\p{Nd}/u.test(msg)) {
    throw new CaseError('an alert must not contain a phone number: warn about the pattern, never a person');
  }
  return msg;
}

/** Every number that agreed to alerts: the worker and the family, once each. Never demo cases, never a
 * case where a death was reported. */
export function recipients(workers: Row[]): Row[] {
  const out: Row[] = [];
  const seen = new Set<string>();
  for (const w of workers) {
    if (w.alerts_opt_in !== 'yes' || truthy(w.is_demo) || truthy(w.death_reported_at)) continue;
    for (const [who, raw] of [['worker', w.worker_phone], ['family', w.family_phone]]) {
      let phone = '';
      try { phone = truthy(raw) ? normalizePhone(raw) : ''; } catch (e) { if (!(e instanceof CaseError)) throw e; }
      if (phone && !seen.has(phone)) {
        seen.add(phone);
        out.push({ phone, case_id: w.case_id, who });
      }
    }
  }
  return out;
}

/** What callers reported in the last 7 days, as hints for this week's topic. */
export function suggestions(reports: Row[], now: Date): Row[] {
  const weekAgo = now.getTime() - 7 * 24 * 3600_000;
  const week = reports.filter((r) => !truthy(r.is_demo) && (parseTs(r.created_at) ?? now).getTime() >= weekAgo);
  const over = week.filter((r) => truthy(r.amount_asked) && pyNum(r.amount_asked) > FEE_CAP_INR).length;
  const visit = week.filter((r) => r.visa_type === 'visit' || r.visa_type === 'tourist').length;
  const hints: Row[] = [];
  if (visit) hints.push({ template: 'visit_visa', text: `${visit} caller(s) this week were offered a visit or tourist visa for a job` });
  if (over) hints.push({ template: 'fee', text: `${over} caller(s) this week were asked for more than the legal fee` });
  return hints;
}

/** Send one alert to everyone who opted in, and keep a record of it. */
export async function sendAlert(store: Store, workers: Row[], message: unknown, channel: string, now: Date): Promise<Row> {
  if (!CHANNELS.includes(channel)) throw new CaseError(`channel must be one of ${CHANNELS.join(', ')}`);
  const msg = cleanMessage(message);
  const people = recipients(workers);
  if (!people.length) throw new CaseError('nobody has agreed to receive alerts yet');
  let sent = 0, failed = 0, prepared = 0;
  const sendOne = async (p: Row): Promise<string> => {
    if (channel === 'sms') return sms.sendSms(p.phone, msg);
    const res = await bolna.placeCall(p.phone, { call_kind: 'alert', alert_text: msg, case_id: p.case_id });
    return res.ok ? 'sent' : `failed: ${res.error}`;
  };
  // A few at a time: one by one, a few hundred numbers would outlast the request; all at once would
  // flood Bolna.
  for (let i = 0; i < people.length; i += ALERT_BATCH) {
    for (const status of await Promise.all(people.slice(i, i + ALERT_BATCH).map(sendOne))) {
      if (status === 'sent') sent++;
      else if (status.startsWith('demo')) prepared++;
      else failed++;
    }
  }
  return store.insert('scam_alerts', { created_at: iso(now), message: msg, channel, recipients: people.length,
    sent, prepared, failed });
}
