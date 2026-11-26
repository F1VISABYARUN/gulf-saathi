// Port of tests/test_cases.py: the same cases, against the TypeScript case logic.
import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import * as bolna from '../src/bolna.js';
import * as cases from '../src/cases.js';
import { CaseError, casePacket, processCallRecord, recordCheckin, registerWorker } from '../src/cases.js';
import { MemoryStore, SupabaseStore, type Row } from '../src/db.js';
import { LicensedList } from '../src/matcher.js';
import * as sms from '../src/sms.js';

export const NOW = new Date(Date.UTC(2026, 9, 21, 6, 0)); // 11:30 IST
export const licensed = LicensedList.load();
const H = 3600_000, D = 24 * H;
export const at = (ms: number) => new Date(NOW.getTime() + ms);

export let store: MemoryStore;
export let placed: Row[];
export let texts: Array<[string, string]>;
let savedEnv: NodeJS.ProcessEnv;

/** Stand-in for Bolna: records each requested call and returns an execution id. */
export const fakePlace = (phone: string, userData: Row, scheduledAt: Date | null = null) => {
  placed.push({ phone, user_data: userData, scheduled_at: scheduledAt ?? null });
  return { ok: true, execution_id: `exec-${placed.length}`, error: null };
};

beforeEach(() => {
  savedEnv = { ...process.env };
  process.env.GS_AUTO_CALLS = '1'; // most tests describe the full schedule
  store = new MemoryStore();
  placed = [];
  texts = [];
  bolna.hooks.placeCall = fakePlace;
  sms.hooks.sendSms = (to, text) => { texts.push([to, text]); return 'demo: not sent'; };
});

afterEach(() => {
  process.env = savedEnv;
  bolna.hooks.placeCall = null;
  sms.hooks.sendSms = null;
  bolna.hooks.fetch = (...a) => fetch(...a);
});

export const YADAIAH: Row = {
  worker_name: 'Yadaiah', worker_name_te: 'యాదయ్య', worker_phone: '98765 43210',
  family_name: 'Lakshmi', family_relation: 'wife', family_phone: '9123456780',
  employer_name: 'Al Noor Cleaning LLC', employer_phone: '+971 50 123 4567',
  sponsor_name: 'Hamad', sponsor_id: '784-1990-1234567-1',
  dest_country: 'UAE', dest_city: 'Dubai', job_title: 'Cleaner',
  contract_salary: '1500', salary_currency: 'AED',
  agent_name: 'Gagan Manpower', agent_owner: 'Bolle Ganga Narsaiah', agent_district: 'Jagtial',
  payments: '50000; 30000',
  departure_date: '2026-10-24', flight_no: 'EK 527',
  arrival_call_at: '2026-10-25T09:30', // India time
};

// The welcome SMS has its own test; leaving it out keeps `texts` to alerts only.
export const register = (over: Row = {}) => registerWorker(store, licensed, { ...YADAIAH, ...over }, NOW, false, false);
export const getW = async (id: string) => (await store.get('workers', { id }))!;

export function payload(callId: string, caseId: string, kind: string, status = 'completed', talked = true, extracted: Row | null = null): Row {
  return {
    id: callId, status, conversation_duration: talked ? 40 : 0,
    transcript: talked ? 'assistant: నమస్కారం\nuser: అవును వచ్చాను' : 'assistant: నమస్కారం\n',
    telephony_data: { recording_url: `https://api.bolna.ai/recordings/call/${callId}`, to_number: '+919876543210' },
    context_details: { recipient_data: { case_id: caseId, call_kind: kind } },
    extracted_data: extracted ?? {},
  };
}

const codes = (rs: Row[]) => new Set(rs.map((r) => r.code));
const rejects = (p: Promise<unknown>, re: RegExp) => assert.rejects(p, (e: Error) => e instanceof CaseError && re.test(e.message));

// --- registration -----------------------------------------------------------------

test('registration builds the trail and books the arrival call', async () => {
  const w = (await register()).worker;
  assert.match(w.case_id, /^GS-[A-Z2-9]{6}$/);
  assert.equal(w.worker_phone, '+919876543210'); assert.equal(w.family_phone, '+919123456780');
  assert.equal(w.employer_phone, '+971501234567');
  assert.equal(w.agent_check, 'confirmed_in_list');
  assert.equal(w.amount_paid_total, 80000); assert.equal(w.fee_status, 'over_cap');
  assert.equal(w.code_phrase, cases.DEFAULT_CODE_PHRASE);
  // Arrival call booked with Bolna for 09:30 India time = 04:00 UTC.
  assert.equal(placed.length, 1);
  assert.equal(placed[0].scheduled_at.getTime(), Date.UTC(2026, 9, 25, 4, 0));
  assert.equal(placed[0].user_data.case_id, w.case_id);
  assert.equal(placed[0].user_data.call_kind, 'arrival');
  assert.equal(placed[0].user_data.employer_name, 'Al Noor Cleaning LLC');
  assert.equal((await store.get('calls', { id: 'exec-1' }))!.status, 'scheduled');
  assert.equal(w.next_call_at, '2026-10-25T04:00:00+00:00');
});

for (const [bad, message] of [
  [{ worker_name: '' }, /worker name/], [{ family_phone: '' }, /family phone/], [{ worker_phone: '12' }, /phone/],
  [{ departure_date: '24/10/2026' }, /YYYY-MM-DD/], [{ contract_salary: 'fifteen hundred' }, /number/],
] as Array<[Row, RegExp]>) {
  test(`registration rejects bad input ${JSON.stringify(bad)}`, () => rejects(register(bad), message));
}

test('registration works without bolna', async () => {
  bolna.hooks.placeCall = null;
  delete process.env.BOLNA_API_KEY;
  const out = await register();
  assert.ok(out.worker.case_id);
  assert.equal(out.arrival_call!.ok, false);
  assert.match(out.arrival_call!.error, /not configured/);
});

// --- arrival call: the Najeeb moment -----------------------------------------------

test('wrong person at airport is critical', async () => {
  let w = (await register()).worker;
  const r = await recordCheckin(store, { case_id: w.case_id.toLowerCase(), call_kind: 'arrival',
    pickup_status: 'other_person', pickup_person: 'a man named Faisal' }, NOW);
  assert.equal(r.risk_level, 'critical'); assert.ok(r.escalated);
  assert.ok(r.instruction.includes('Never promise rescue') && r.instruction.includes('a caseworker will act on it right away'));
  assert.ok(r.instruction.includes('call the embassy themselves'));
  assert.ok(r.instruction.includes('Al Noor Cleaning LLC'));
  w = await getW(w.id);
  assert.equal(w.risk_level, 'critical'); assert.equal(w.status, 'abroad');
  const [to, text] = texts[0];
  assert.equal(to, '+919123456780');
  assert.ok(text.includes('యాదయ్య') && text.includes('అత్యవసరం'));
  assert.ok(!/[A-Za-z]/.test(text.replace(w.case_id, '')));
});

test('code phrase keeps the call quiet', async () => {
  const w = (await register()).worker;
  const r = await recordCheckin(store, { case_id: w.case_id, code_phrase_used: 'yes' }, NOW);
  assert.equal(r.risk_level, 'critical');
  assert.ok(r.instruction.includes('Do NOT mention'));
  assert.ok(texts[0][1].includes('నేరుగా అడగకండి'));
});

test('all clear checkin', async () => {
  const w = (await register()).worker;
  const r = await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'employer',
    salary_received: 'yes', passport_with_worker: 'అవును' }, NOW);
  assert.equal(r.risk_level, 'ok'); assert.ok(!r.escalated); assert.deepEqual(texts, []);
});

test('unknown case does not crash', async () => {
  const r = await recordCheckin(new MemoryStore(), { case_id: 'GS-NOPE' }, NOW);
  assert.equal(r.ok, false); assert.ok(r.instruction.includes('do not promise'));
});

// --- weekly check-ins ------------------------------------------------------------

test('unpaid and passport taken is high and not repeated', async () => {
  const w = (await register()).worker;
  const answers = { case_id: w.case_id, salary_received: 'no', months_unpaid: '2 months', passport_with_worker: 'no', food_ok: 'yes' };
  const r = await recordCheckin(store, answers, NOW);
  assert.equal(r.risk_level, 'high'); assert.ok(r.escalated);
  assert.deepEqual(codes((await getW(w.id)).risk_reasons), new Set(['unpaid_2plus', 'passport_taken']));
  assert.equal((await recordCheckin(store, answers, at(7 * D))).escalated, false);
  assert.equal(texts.length, 1);
  assert.equal((await recordCheckin(store, { ...answers, threatened: 'yes' }, at(8 * D))).escalated, true);
  assert.equal(texts.length, 2);
});

test('one month unpaid is medium without sms', async () => {
  const w = (await register()).worker;
  assert.equal((await recordCheckin(store, { case_id: w.case_id, salary_received: 'no' }, NOW)).risk_level, 'medium');
  assert.deepEqual(texts, []);
});

// --- webhook: calls ending ------------------------------------------------------

test('answered arrival call books weekly call', async () => {
  let w = (await register()).worker;
  const r = await processCallRecord(store, payload('exec-1', w.case_id, 'arrival'), NOW);
  assert.ok(r.processed && !r.missed);
  const call = (await store.get('calls', { id: 'exec-1' }))!;
  assert.ok(call.answered && call.recording_url.endsWith('exec-1') && call.transcript.includes('అవును'));
  w = await getW(w.id);
  assert.equal(w.status, 'abroad'); assert.equal(w.missed_checkins, 0);
  assert.equal(placed.at(-1)!.user_data.call_kind, 'weekly');
  assert.equal(placed.at(-1)!.scheduled_at.getTime(), at(7 * D).getTime());
});

test('two missed calls raise high and redelivery is ignored', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  await store.update('workers', { id: w.id }, { status: 'abroad' });
  await processCallRecord(store, payload('exec-a', w.case_id, 'weekly', 'no-answer', false), NOW);
  await processCallRecord(store, payload('exec-a', w.case_id, 'weekly', 'no-answer', false), NOW);
  const w1 = await getW(w.id);
  assert.equal(w1.missed_checkins, 1); assert.equal(w1.risk_level, 'medium'); assert.deepEqual(texts, []);
  assert.equal(placed.at(-1)!.scheduled_at.getTime(), at(24 * H).getTime());

  await store.update('calls', { worker_id: w.id }, { status: 'completed' });
  const r = await processCallRecord(store, payload('exec-b', w.case_id, 'weekly', 'completed', false), at(D));
  assert.ok(r.missed && r.risk_level === 'high' && r.escalated);
  assert.ok((texts as Array<[string, string]>)[0][1].includes('వరుసగా 2 కాల్స్‌కు జవాబు రాలేదు'));

  await store.update('calls', { worker_id: w.id }, { status: 'completed' });
  await processCallRecord(store, payload('exec-c', w.case_id, 'weekly'), at(2 * D));
  const w3 = await getW(w.id);
  assert.equal(w3.missed_checkins, 0); assert.equal(w3.risk_level, 'high');
  const esc = (await store.select('escalations', { worker_id: w.id }))[0];
  await cases.resolveEscalation(store, esc.id, at(2 * D));
  assert.equal((await getW(w.id)).risk_level, 'ok');
});

test('no second booking when one is pending', async () => {
  const w = (await register()).worker;
  await processCallRecord(store, payload('exec-x', w.case_id, 'weekly'), NOW);
  assert.equal(placed.length, 1);
});

test('empty extraction keeps what the tool recorded', async () => {
  const w = (await register()).worker;
  await recordCheckin(store, { case_id: w.case_id, salary_received: 'no' }, NOW);
  await processCallRecord(store, payload('exec-1', w.case_id, 'weekly'), NOW);
  assert.equal((await getW(w.id)).risk_level, 'medium');
});

test('extracted data is used when present', async () => {
  const w = (await register()).worker;
  await processCallRecord(store, payload('exec-1', w.case_id, 'weekly', 'completed', true, { passport_with_worker: 'no' }), NOW);
  assert.equal((await getW(w.id)).risk_level, 'high');
});

test('call from the agent check line is stored not processed', async () => {
  const p = payload('exec-z', '', '');
  p.context_details = { recipient_data: { timezone: 'Asia/Kolkata' } };
  assert.deepEqual(await processCallRecord(store, p, NOW), { stored: true, processed: false, worker: null });
  assert.equal((await store.get('calls', { id: 'exec-z' }))!.kind, 'other');
});

// --- case packet -----------------------------------------------------------------

test('case packet has the whole trail', async () => {
  const w = (await register()).worker;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'other_person' }, NOW);
  await processCallRecord(store, payload('exec-1', w.case_id, 'arrival'), NOW);
  const text = await casePacket(store, await getW(w.id), NOW);
  for (const expected of [w.case_id, 'CRITICAL', 'Al Noor Cleaning LLC', '784-1990-1234567-1', 'Hamad', 'Dubai',
    'Gagan Manpower', 'confirmed_in_list', 'OVER the Rs 35,400 limit',
    'someone other than the registered employer', 'Recording: https://api.bolna.ai/recordings/call/exec-1',
    'have not been independently verified', 'madad.gov.in', 'అవును']) {
    assert.ok(text.includes(expected), expected);
  }
  assert.ok(!text.toLowerCase().includes('rescue'));
});

// --- outside services: exact requests ----------------------------------------------

test('supabase requests', async () => {
  const seen: Array<{ url: URL; method: string; headers: Headers }> = [];
  const real = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL, init: RequestInit = {}) => {
    const h = new Headers(init.headers);
    seen.push({ url: new URL(String(input)), method: init.method ?? 'GET', headers: h });
    if ((init.method ?? 'GET') === 'GET') return new Response(JSON.stringify([{ id: '1' }]), { status: 200 });
    return new Response(JSON.stringify([JSON.parse(String(init.body))]), { status: 201 });
  }) as typeof fetch;
  try {
    const s = new SupabaseStore('https://abc.supabase.co/', 'sb_secret_xyz');
    assert.deepEqual(await s.get('workers', { case_id: 'GS-ABC234' }), { id: '1' });
    await s.insert('workers', { case_id: 'GS-ABC234' });
    await s.upsert('calls', { id: 'exec-1' });
    await s.update('workers', { id: '1' }, { risk_level: 'high' });
  } finally { globalThis.fetch = real; }
  const [get, ins, ups, upd] = seen;
  assert.ok(String(get.url).startsWith('https://abc.supabase.co/rest/v1/workers?'));
  assert.equal(get.url.searchParams.get('case_id'), 'eq.GS-ABC234'); assert.equal(get.url.searchParams.get('limit'), '1');
  assert.equal(get.headers.get('apikey'), 'sb_secret_xyz'); assert.equal(get.headers.get('authorization'), null);
  assert.equal(ins.headers.get('prefer'), 'return=representation');
  assert.equal(ups.url.searchParams.get('on_conflict'), 'id'); assert.ok(ups.headers.get('prefer')!.includes('merge-duplicates'));
  assert.equal(upd.method, 'PATCH'); assert.equal(upd.url.searchParams.get('id'), 'eq.1');
  const legacy = new SupabaseStore('https://abc.supabase.co', 'eyJhbGciOi.legacy');
  assert.equal((legacy as any).headers.Authorization, 'Bearer eyJhbGciOi.legacy');
});

test('bolna call request', async () => {
  const seen: Row = {};
  bolna.hooks.placeCall = null;
  bolna.hooks.fetch = (async (url: string, init: RequestInit) => {
    Object.assign(seen, { url, json: JSON.parse(String(init.body)), headers: init.headers });
    return new Response(JSON.stringify({ execution_id: 'exec-99', status: 'queued' }), { status: 200 });
  }) as typeof fetch;
  process.env.BOLNA_API_KEY = 'bn-test';
  process.env.BOLNA_CHECKIN_AGENT_ID = 'agent-123';
  const r = await bolna.placeCall('+919876543210', { case_id: 'GS-ABC234', n: null }, new Date(Date.UTC(2026, 9, 25, 4, 0)));
  assert.deepEqual(r, { ok: true, execution_id: 'exec-99', error: null });
  assert.equal(seen.url, 'https://api.bolna.ai/call');
  assert.equal(seen.headers.Authorization, 'Bearer bn-test');
  assert.deepEqual(seen.json, { agent_id: 'agent-123', recipient_phone_number: '+919876543210',
    user_data: { case_id: 'GS-ABC234', n: '' }, scheduled_at: '2026-10-25T04:00:00+00:00' });
});

test('real bolna event sequence processes once', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  for (const status of ['initiated', 'ringing', 'in-progress']) {
    const r = await processCallRecord(store, payload('exec-live', w.case_id, 'weekly', status, false), NOW);
    assert.equal(r.processed, false);
  }
  assert.equal((await getW(w.id)).missed_checkins, 0);
  let r = await processCallRecord(store, payload('exec-live', w.case_id, 'weekly', 'call-disconnected'), NOW);
  assert.ok(r.processed && !r.missed);
  r = await processCallRecord(store, payload('exec-live', w.case_id, 'weekly', 'completed'), NOW);
  assert.equal(r.processed, false);
  assert.equal(placed.length, 1); assert.equal(placed[0].user_data.call_kind, 'weekly');
});

// --- fixes from the first live registration ------------------------------------------

const offPlace = () => ({ ok: false, execution_id: null, error: 'Bolna not configured' });

test('failed booking does not show a booked call', async () => {
  bolna.hooks.placeCall = offPlace;
  const w = (await register()).worker;
  assert.equal(w.next_call_at ?? null, null);
  assert.ok(!(await cases.arrivalCallBooked(store, w)));
});

test('book arrival call later', async () => {
  bolna.hooks.placeCall = offPlace;
  const w = (await register()).worker;
  bolna.hooks.placeCall = fakePlace; // Bolna set up afterwards
  let res = await cases.bookArrivalCall(store, w, NOW);
  assert.ok(res.ok && (await cases.arrivalCallBooked(store, w)));
  assert.equal(placed.at(-1)!.scheduled_at.getTime(), Date.UTC(2026, 9, 25, 4, 0));
  assert.equal((await getW(w.id)).next_call_at, '2026-10-25T04:00:00+00:00');
  res = await cases.bookArrivalCall(store, w, new Date(Date.UTC(2026, 9, 26)));
  assert.ok(res.ok); assert.equal(placed.at(-1)!.scheduled_at, null);
});

test('book arrival needs a time', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  await rejects(cases.bookArrivalCall(store, w, NOW), /no arrival-day call time/);
});

for (const [phrase, ok] of [['అమ్మ బాగుందా', true], ['Is Amma well?', true], ['ANNA', false], ['అన్నా', false],
  ['anna.', false], ['hello', false], ['', false], ['ok', false]] as Array<[string, boolean]>) {
  test(`code phrase rule ${phrase}`, () => assert.equal(cases.codePhraseOk(phrase), ok));
}

test('registration rejects a weak code phrase', () => rejects(register({ code_phrase: 'ANNA' }), /too easy to say by accident/));

test('edit corrects details and keeps the case', async () => {
  const w = (await register()).worker;
  const edited = await cases.updateWorker(store, licensed, w, { ...YADAIAH, worker_phone: '9000000013',
    agent_name: 'Golconda Overseas', agent_owner: '', payments: '20000' }, at(H));
  assert.equal(edited.case_id, w.case_id); assert.equal(edited.id, w.id);
  assert.equal(edited.worker_phone, '+919000000013');
  assert.equal(edited.agent_check, 'not_found'); assert.equal(edited.fee_status, 'within_cap');
  assert.equal(edited.status, 'registered'); assert.equal(edited.risk_level, 'ok');
  await rejects(cases.updateWorker(store, licensed, w, { ...YADAIAH, code_phrase: 'anna' }, NOW), /too easy/);
});

test('edit clears a next call time with nothing booked', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  await store.update('workers', { id: w.id }, { next_call_at: '2026-10-30T10:57:00+00:00' });
  assert.equal((await cases.updateWorker(store, licensed, w, YADAIAH, NOW)).next_call_at, null);
});

test('edit keeps a really booked next call', async () => {
  const booked = (await register()).worker;
  assert.equal((await cases.updateWorker(store, licensed, booked, YADAIAH, NOW)).next_call_at, '2026-10-25T04:00:00+00:00');
});

// --- CM's three points: state view and pre-departure briefing ------------------------

test('summary counts and agent stats', async () => {
  const a = (await register({ arrival_call_at: '', payments: '20000' })).worker;
  await register({ arrival_call_at: '', agent_name: 'Golconda Overseas', agent_owner: '', agent_district: 'jagtial',
    employer_name: 'Al Noor Cleaning LLC' });
  const c = (await register({ arrival_call_at: '', agent_name: 'GOLCONDA  OVERSEAS', agent_owner: '', agent_district: 'Jagtial',
    employer_name: 'Desert Star', dest_city: 'Riyadh', dest_country: 'Saudi Arabia' })).worker;
  await recordCheckin(store, { case_id: c.case_id, call_kind: 'arrival', pickup_status: 'other_person' }, NOW);
  await recordCheckin(store, { case_id: a.case_id, call_kind: 'briefing', briefing_understood: 'yes' }, NOW);
  const workers = await store.select('workers');
  assert.deepEqual(cases.summaryCounts(workers, await cases.briefedWorkerIds(store)),
    { registered: 3, in_india: 2, abroad: 1, briefed: 1, at_risk: 1, red_flags: 2 });
  const [golconda, gagan] = cases.agentStats(workers);
  assert.equal(golconda.agent, 'GOLCONDA OVERSEAS');
  assert.deepEqual([golconda.cases, golconda.not_in_list, golconda.over_cap, golconda.critical], [2, 2, 2, 1]);
  assert.deepEqual(golconda.districts, ['Jagtial']);
  assert.deepEqual(golconda.employers, ['Al Noor Cleaning LLC (Dubai, UAE)', 'Desert Star (Riyadh, Saudi Arabia)']);
  assert.equal(gagan.agent, 'GAGAN MAN POWER CONSULTANTS'); assert.ok(gagan.licensed); assert.equal(gagan.over_cap, 0);
});

test('briefing is recorded without touching risk', async () => {
  const w = (await register()).worker;
  await recordCheckin(store, { case_id: w.case_id, salary_received: 'no' }, NOW);
  const r = await recordCheckin(store, { case_id: w.case_id, call_kind: 'briefing', briefing_understood: 'no' }, NOW);
  assert.equal(r.risk_level, 'ok'); assert.ok(r.instruction.includes('land'));
  assert.equal((await getW(w.id)).risk_level, 'medium');
  assert.equal((await cases.briefedWorkerIds(store))[w.id].answers.briefing_understood, false);
});

test('danger on a briefing call still alerts', async () => {
  const w = (await register()).worker;
  const r = await recordCheckin(store, { case_id: w.case_id, call_kind: 'briefing', threatened: 'yes' }, NOW);
  assert.equal(r.risk_level, 'critical'); assert.ok(r.escalated); assert.equal(texts.length, 1);
});

test('missed briefing is not a missed checkin', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  const r = await processCallRecord(store, payload('exec-br', w.case_id, 'briefing', 'no-answer', false), NOW);
  assert.equal(r.processed, false);
  assert.equal((await getW(w.id)).missed_checkins, 0); assert.deepEqual(texts, []); assert.deepEqual(placed, []);
});

// --- promise vs reality, welcome SMS, help line ---------------------------------------

test('welcome sms once at registration', async () => {
  const w = (await registerWorker(store, licensed, YADAIAH, NOW)).worker;
  assert.equal(texts.length, 1); assert.equal(texts[0][0], '+919123456780');
  assert.ok(texts[0][1].includes(w.case_id) && texts[0][1].includes('యాదయ్య'));
  assert.ok(!/[A-Za-z]/.test(texts[0][1].replace(w.case_id, '')));
  assert.equal(w.welcome_sms_status, 'demo: not sent'); assert.equal(w.source, 'dashboard'); assert.equal(w.is_demo, false);
});

test('different work on arrival is flagged', async () => {
  const w = (await register({ visa_type: 'employment', visa_job: 'Cleaner' })).worker;
  const r = await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'employer',
    current_job: 'herding goats', current_city: 'Al Ain' }, NOW);
  assert.equal(r.risk_level, 'high'); assert.ok(r.escalated);
  const rs = (await getW(w.id)).risk_reasons;
  assert.deepEqual(rs.map((x: Row) => x.code), ['job_mismatch', 'city_mismatch']);
  assert.ok(cases.reasonText(rs[0]).includes('herding goats'));
});

test('same work is not flagged', async () => {
  const w = (await register()).worker;
  const r = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', current_job: 'cleaning offices',
    current_city: 'Dubai Marina', salary_received: 'yes' }, NOW);
  assert.equal(r.risk_level, 'ok'); assert.deepEqual(texts, []);
});

test('visa fields and red flags', async () => {
  const w = (await register({ visa_type: 'Visit', visa_job: 'Shepherd', sub_agent_phone: '98480 12345' })).worker;
  assert.equal(w.visa_type, 'visit'); assert.equal(w.sub_agent_phone, '+919848012345');
  assert.ok(cases.hasPredepartureFlags(w));
  await rejects(register({ visa_type: 'business' }), /visa type/);
});

test('help line opens a case and alerts', async () => {
  const r = await cases.reportProblem(store, { caller_phone: '+971 50 111 2222', caller_name: 'Srinu',
    family_phone: '9000012345', threatened: 'yes', notes: 'boss beats me' }, NOW);
  assert.ok(r.ok && r.new_case && r.risk_level === 'critical' && r.escalated);
  const w = (await store.get('workers', { case_id: r.case_id }))!;
  assert.equal(w.source, 'help_call'); assert.equal(w.worker_phone, '+971501112222');
  assert.equal(texts[0][0], '+919000012345');
  assert.equal((await store.select('checkins', { worker_id: w.id }))[0].kind, 'help');
  const r2 = await cases.reportProblem(store, { caller_phone: '971501112222', months_unpaid: '3' }, NOW);
  assert.equal(r2.case_id, r.case_id); assert.ok(!r2.new_case);
});

test('help line needs a way to find the caller', async () => {
  const r = await cases.reportProblem(store, { needs_help: 'yes' }, NOW);
  assert.equal(r.ok, false); assert.ok(r.instruction.includes('phone number'));
});

test('demo story never calls or texts', async () => {
  const { runDemo } = await import('../src/demo.js');
  const { repeatedSignals } = await import('../src/signals.js');
  const { predepartureChecks } = await import('../src/promise.js');
  const out = await runDemo(store, licensed, NOW);
  assert.deepEqual(placed, []); assert.deepEqual(texts, []);
  const y = (await store.get('workers', { case_id: out.yadaiah }))!;
  assert.ok(y.is_demo); assert.equal(y.risk_level, 'critical');
  for (const c of ['job_mismatch', 'city_mismatch', 'wrong_pickup', 'passport_taken']) assert.ok(codes(y.risk_reasons).has(c), c);
  assert.equal((await store.select('escalations'))[0].sms_status, 'demo: not sent');
  const sig = repeatedSignals(await store.select('workers'));
  assert.ok(sig.length && sig.every((s) => s.demo));
  assert.deepEqual(new Set(sig[0].cases), new Set([out.yadaiah, out.ramesh]));
  const sara = (await store.get('workers', { case_id: out.saraswathi }))!;
  assert.ok(predepartureChecks(sara).some((f) => f.code === 'domestic_visit_visa'));
});

// --- help line safety net (Bolna after-call extraction) -----------------------------

const x = (objective: unknown = null, subjective: unknown = null) => ({ objective, subjective, confidence: 0.9 });

// Shape of extracted_data from the live call d5acc09e (21 Oct 2026, "Oman airport").
const OMAN_EXTRACTION = { help_check: {
  notes: x(null, 'The caller says someone took them in Oman, that they are being beaten, and asks for help.'),
  abroad: x('yes'), needs_help: x('yes'), threatened: x('yes'),
  caller_name: x(null, 'not_said'), current_job: x(null, 'not_said'),
  current_city: x(null, 'Oman, at the airport'), months_unpaid: x(null, 'not_said'),
  movement_restricted: x('not_said'), passport_with_worker: x('not_said'),
} };

const gulfLineCall = (callId: string, extracted: Row, number = '+971501112222'): Row => ({
  id: callId, agent_id: 'gulf-saathi', status: 'completed', conversation_duration: 180,
  transcript: 'assistant: నమస్కారం\nuser: ఓమన్ ఎయిర్పోర్ట్ లో ఉన్నాను', user_number: number,
  telephony_data: { recording_url: `https://api.bolna.ai/recordings/call/${callId}` },
  context_details: { recipient_data: { timezone: 'Asia/Kolkata' } }, extracted_data: extracted,
});

test('flatten extraction reads bolna categories', () => {
  const flat = cases.flattenExtraction(OMAN_EXTRACTION);
  assert.equal(flat.abroad, 'yes'); assert.equal(flat.threatened, 'yes'); assert.equal(flat.current_city, 'Oman, at the airport');
  assert.equal(flat.caller_name, ''); assert.equal(flat.passport_with_worker, '');
  assert.deepEqual(cases.flattenExtraction({ abroad: 'yes' }), { abroad: 'yes' });
});

test('after call extraction opens a help case when the live ai missed it', async () => {
  const out = await processCallRecord(store, gulfLineCall('x1', OMAN_EXTRACTION), NOW);
  assert.ok(out.processed && out.help.new_case);
  const w = (await store.get('workers', { case_id: out.worker }))!;
  assert.equal(w.source, 'help_call'); assert.equal(w.risk_level, 'critical'); assert.equal(w.worker_phone, '+971501112222');
  assert.ok(codes(w.risk_reasons).has('threatened') && codes(w.risk_reasons).has('needs_help'));
  assert.equal((await store.select('escalations')).length, 1);
  const again = await processCallRecord(store, gulfLineCall('x1', OMAN_EXTRACTION), NOW);
  assert.equal(again.processed, false); assert.equal((await store.select('escalations')).length, 1);
  assert.deepEqual(placed, []);
});

test('after call extraction after the live tool sends no second alert', async () => {
  await cases.reportProblem(store, { caller_phone: '+971501112222', threatened: 'yes', needs_help: 'yes' }, NOW);
  await processCallRecord(store, gulfLineCall('x2', OMAN_EXTRACTION), NOW);
  assert.equal((await store.select('workers')).length, 1); assert.equal((await store.select('escalations')).length, 1);
});

test('a caller only checking an agent opens no case', async () => {
  const checking = { help_check: { abroad: x('no'), needs_help: x('not_said'), threatened: x('not_said'),
    notes: x(null, 'Asked whether an agent in Jagtial is licensed.') } };
  const out = await processCallRecord(store, gulfLineCall('x3', checking, '+919000011111'), NOW);
  assert.deepEqual(await store.select('workers'), []); assert.ok(!out.help);
});

test('taken by a stranger is critical with airport advice', async () => {
  const r = await cases.reportProblem(store, { caller_phone: '+96890001111', taken_by_stranger: 'yes' }, NOW);
  assert.equal(r.risk_level, 'critical'); assert.ok(r.instruction.includes('airport help desk or airport police'));
  assert.ok(r.instruction.includes('G S, '));
});

test('family is only said to be told when the sms went out', async () => {
  sms.hooks.sendSms = () => 'demo: not sent (no SMS provider configured)';
  let r = await cases.reportProblem(store, { caller_phone: '+971501112222', family_phone: '9000012345', threatened: 'yes' }, NOW);
  assert.ok(!r.instruction.includes('family has been sent a message'));
  sms.hooks.sendSms = () => 'sent';
  r = await cases.reportProblem(store, { caller_phone: '+971502223333', family_phone: '9000012346', threatened: 'yes' }, NOW);
  assert.ok(r.instruction.includes('Their family has been sent a message'));
});

test('help line keeps trace details on the case', async () => {
  const r = await cases.reportProblem(store, { caller_phone: '+971501112222', needs_help: 'yes', caller_name: 'Mallayya',
    home_district: 'Jagtial', agent_name: 'Rajesh', agent_phone: '98480 12345',
    landmark: 'near a big mosque', current_city: 'Al Ain' }, NOW);
  const w = (await store.get('workers', { case_id: r.case_id }))!;
  assert.equal(w.worker_name, 'Mallayya'); assert.equal(w.agent_name, 'Rajesh'); assert.equal(w.sub_agent_phone, '+919848012345');
  assert.ok(w.notes.includes('Home: Jagtial') && w.notes.includes('Near: near a big mosque')); assert.equal(w.dest_city, 'Al Ain');
  const ans = (await store.select('checkins'))[0].answers;
  assert.equal(ans.landmark, 'near a big mosque'); assert.equal(ans.home_district, 'Jagtial');
});

test('arrival call scored from bolna extraction when the tool was missed', async () => {
  let w = (await register()).worker;
  const extracted = { checkin: { pickup_status: x('other_person'), current_job: x(null, 'herding goats'),
    current_city: x(null, 'Al Kharj'), threatened: x('not_said') } };
  const out = await processCallRecord(store, payload('a1', w.case_id, 'arrival', 'completed', true, extracted), NOW);
  w = await getW(w.id);
  assert.ok(out.processed); assert.equal(w.risk_level, 'critical');
  for (const c of ['wrong_pickup', 'job_mismatch', 'city_mismatch']) assert.ok(codes(w.risk_reasons).has(c));
});

test('extraction arriving with completed after disconnect is scored', async () => {
  let w = (await register()).worker;
  const first = await processCallRecord(store, payload('d1', w.case_id, 'arrival', 'call-disconnected'), NOW);
  assert.ok(first.processed); assert.equal((await getW(w.id)).risk_level, 'ok');
  const extracted = { help_check: { taken_by_stranger: x('yes'), current_job: x(null, 'herding sheep'),
    passport_with_worker: x('no'), abroad: x('yes') } };
  const late = await processCallRecord(store, payload('d1', w.case_id, 'arrival', 'completed', true, extracted), NOW);
  w = await getW(w.id);
  assert.ok(late.late_extraction); assert.equal(w.risk_level, 'critical');
  for (const c of ['wrong_pickup', 'job_mismatch', 'passport_taken']) assert.ok(codes(w.risk_reasons).has(c));
  assert.equal((await store.select('escalations')).length, 1);
  const again = await processCallRecord(store, payload('d1', w.case_id, 'arrival', 'completed', true, extracted), NOW);
  assert.equal(again.processed, false); assert.equal((await store.select('escalations')).length, 1);
  assert.equal(placed.length, 1);
});

test('critical answer brings saathi back within hours', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'other_person' }, NOW);
  await processCallRecord(store, payload('c1', w.case_id, 'arrival'), NOW);
  assert.equal(placed.at(-1)!.scheduled_at.getTime(), at(3 * H).getTime());
  const w2 = (await register({ arrival_call_at: '', worker_phone: '9876500000' })).worker;
  await processCallRecord(store, payload('c2', w2.case_id, 'weekly'), NOW);
  assert.equal(placed.at(-1)!.scheduled_at.getTime(), at(7 * D).getTime());
});

test('automatic calls are off unless switched on', async () => {
  delete process.env.GS_AUTO_CALLS;
  const w = (await register({ arrival_call_at: '' })).worker;
  await processCallRecord(store, payload('o1', w.case_id, 'weekly'), NOW);
  await processCallRecord(store, payload('o2', w.case_id, 'weekly', 'completed', false), NOW);
  assert.deepEqual(placed, []);
  const r = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', threatened: 'yes' }, NOW);
  assert.ok(!r.instruction.includes('call back within a few hours'));
});

test('a call placed at once cannot loop', async () => {
  const w = (await register({ arrival_call_at: '' })).worker;
  await processCallRecord(store, payload('L1', w.case_id, 'weekly'), NOW);
  assert.equal(placed.length, 1);
  await processCallRecord(store, payload('exec-1', w.case_id, 'weekly'), at(2 * 60_000));
  assert.equal(placed.length, 1);
});

test('checking caller who asks for help opens no case', async () => {
  const checking = { help_check: { abroad: x('not_said'), needs_help: x('yes'), threatened: x('not_said'),
    notes: x(null, "Agent asking 15 lakh; caller checked the agent's number.") } };
  const out = await processCallRecord(store, gulfLineCall('x9', checking, '+919000022222'), NOW);
  assert.deepEqual(await store.select('workers'), []); assert.deepEqual(await store.select('escalations'), []); assert.ok(!out.help);
});

// --- family callers and Pravasi Prajavani petitions ---------------------------------

test('family caller opens a case as the family contact', async () => {
  const r = await cases.reportProblem(store, { caller_phone: '9440012345', caller_relation: 'mother', caller_name: 'Lakshmi',
    worker_name: 'Ravi', current_city: 'Muscat', passport_with_worker: 'no', threatened: 'yes', notes: 'Son locked in a room, no food' }, NOW);
  const w = (await store.get('workers', { case_id: r.case_id }))!;
  assert.ok(r.new_case); assert.equal(w.source, 'family_call'); assert.equal(w.reported_by, 'mother');
  assert.equal(w.worker_name, 'Ravi'); assert.equal(w.family_name, 'Lakshmi'); assert.equal(w.family_phone, '+919440012345');
  assert.ok(w.notes.includes("Worker's own phone not known"));
  assert.ok(r.instruction.includes('Pravasi Prajavani petition') && r.instruction.includes('do not need to travel'));
  assert.ok(!r.instruction.includes('airport'));
  const r2 = await cases.reportProblem(store, { caller_phone: '+919440012345', caller_relation: 'mother' }, NOW);
  assert.equal(r2.case_id, r.case_id); assert.ok(!r2.new_case);
});

test('petition is filled from the case and its status is told to callers', async () => {
  let w = (await register({ visa_job: 'Agricultural worker', sub_agent_phone: '98480 12345' })).worker;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'other_person',
    current_job: 'herding goats', landmark: 'near a big mosque' }, NOW);
  w = await getW(w.id);
  const { english: en, telugu: te } = await cases.prajavaniPetition(store, w, NOW);
  assert.ok(en.to.includes('Pravasi Prajavani') && en.subject.includes(w.case_id));
  assert.ok(en.facts.some((f: string) => f.includes('+919848012345')) && en.facts.some((f: string) => f.includes('herding goats')));
  assert.ok(en.facts.some((f: string) => f.includes('near a big mosque')));
  assert.ok(te.to.includes('ప్రవాసీ ప్రజావాణి') && te.body.some((b: string) => b.includes('యాదయ్య')));
  assert.ok(en.note.includes('not independently verified'));
  await rejects(cases.updatePetition(store, w, 'lost', '', NOW), /status/);
  w = await cases.updatePetition(store, w, 'submitted', 'PPV-123', NOW);
  assert.ok(w.petition_submitted_at && cases.petitionLine(w).includes('submitted') && cases.petitionLine(w).includes('PPV-123'));
  const r = await cases.reportProblem(store, { caller_phone: w.worker_phone, months_unpaid: '2' }, NOW);
  assert.ok(r.instruction.includes('petition is submitted'));
});

// --- women going for housework --------------------------------------------------------

const flagCodes = async (w: Row) => new Set((await import('../src/promise.js')).predepartureChecks(w).map((f) => f.code));
const { STOP_FLAGS, predepartureChecks } = await import('../src/promise.js');

test('woman housemaid on tourist visa is stopped', async () => {
  const w = (await register({ worker_gender: 'woman', worker_age: '27', job_title: 'Housemaid', visa_type: 'tourist', payments: '' })).worker;
  const c = await flagCodes(w);
  for (const k of ['domestic_visit_visa', 'woman_under_30', 'visit_visa']) assert.ok(c.has(k), k);
  assert.ok(STOP_FLAGS.has('domestic_visit_visa'));
  const m = (await register({ worker_gender: 'man', job_title: 'Housemaid', visa_type: 'tourist' })).worker;
  const mc = await flagCodes(m);
  assert.ok(!mc.has('domestic_visit_visa') && !mc.has('woman_under_30'));
});

test('woman housemaid on employment visa gets the state agency flag', async () => {
  const w = (await register({ worker_gender: 'woman', worker_age: '35', job_title: 'Driver', visa_job: 'House maid',
    visa_type: 'employment', payments: '' })).worker;
  const c = await flagCodes(w);
  assert.ok(c.has('domestic_woman') && !c.has('woman_under_30'));
});

for (const [bad, message] of [[{ worker_gender: 'female' }, /gender/], [{ worker_age: '7' }, /age/]] as Array<[Row, RegExp]>) {
  test(`gender and age are checked ${JSON.stringify(bad)}`, () => rejects(register(bad), message));
}

test('one missed call is high for a woman in housework', async () => {
  let w = (await register({ worker_gender: 'woman', job_title: 'Housemaid' })).worker;
  await processCallRecord(store, payload('m1', w.case_id, 'weekly', 'no-answer', false), NOW);
  w = await getW(w.id);
  assert.equal(w.risk_level, 'high'); assert.equal(w.risk_reasons[0].code, 'missed_1_domestic');
  const y = (await register({ worker_phone: '9876500000' })).worker;
  await processCallRecord(store, payload('m2', y.case_id, 'weekly', 'no-answer', false), NOW);
  assert.equal((await getW(y.id)).risk_level, 'medium');
});

test('moved to another employer is high', async () => {
  const w = (await register()).worker;
  const out = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', employer_changed: 'yes' }, NOW);
  assert.equal(out.risk_level, 'high');
  assert.equal((await getW(w.id)).risk_reasons[0].code, 'employer_changed');
});

// --- when a worker dies abroad ---------------------------------------------------------

test('family reports a death on the line', async () => {
  let w = (await register()).worker;
  const out = await cases.reportProblem(store, { caller_phone: '9123456780', caller_relation: 'wife', worker_died: 'yes',
    current_city: 'Dubai', informed_by: 'his roommate', notes: 'Heart attack at the camp' }, NOW);
  assert.ok(out.ok); assert.equal(out.case_id, w.case_id); assert.ok(!out.new_case);
  assert.ok(out.instruction.includes('very sorry') && out.instruction.includes('support money'));
  assert.ok(out.instruction.includes('G S,'));
  w = await getW(w.id);
  assert.equal(w.status, 'death_reported'); assert.equal(w.risk_level, 'critical');
  assert.ok(w.death_note.includes('his roommate')); assert.equal(w.remains_status, 'reported');
  const alert = (await store.select('escalations'))[0];
  assert.equal(alert.level, 'critical'); assert.equal(alert.family_sms, ''); assert.deepEqual(texts, []);
  const booked = placed.length;
  assert.equal((await cases.scheduleCall(store, w, 'weekly', null, NOW)).ok, false); assert.equal(placed.length, booked);
  const out2 = await processCallRecord(store, payload('late', w.case_id, 'arrival', 'no-answer', false), NOW);
  assert.equal(out2.processed, false); assert.deepEqual(texts, []); assert.equal(placed.length, booked);
  await cases.reportProblem(store, { caller_phone: '9123456780', caller_relation: 'wife', worker_died: 'yes' }, NOW);
  assert.equal((await store.select('escalations')).length, 1);
});

test('death reported by a stranger to saathi opens a family case', async () => {
  const out = await cases.reportProblem(store, { caller_phone: '9000011111', worker_died: 'yes', worker_name: 'Rajanna',
    current_city: 'Riyadh, Saudi Arabia' }, NOW);
  const w = (await store.get('workers', { case_id: out.case_id }))!;
  assert.ok(out.new_case); assert.equal(w.source, 'family_call'); assert.equal(w.family_phone, '+919000011111');
  assert.equal(w.worker_name, 'Rajanna'); assert.ok(w.death_reported_at);
});

test('death papers and embassy alert', async () => {
  let w = (await register()).worker;
  w = await cases.reportDeath(store, w, { reported_by: 'employer', place: 'Rashid Hospital, Dubai' }, NOW);
  const alert = await cases.embassyAlert(store, w, NOW);
  assert.ok(alert.subject.startsWith('Death of Indian worker reported'));
  assert.ok(alert.body.includes('Lakshmi (wife), +919123456780') && alert.body.includes('Rashid Hospital'));
  const text = JSON.stringify(cases.deathPacket(store, w, NOW));
  assert.ok(text.includes('Passport number: ____') && text.includes('G.O. 216') && text.includes('ICWF'));
  assert.ok(text.includes('ఎక్స్‌గ్రేషియా'));
  await store.update('workers', { id: w.id }, { dest_country: 'Malaysia', dest_city: 'Kuala Lumpur' });
  assert.ok(!JSON.stringify(cases.deathPacket(store, await getW(w.id), NOW)).includes('G.O. 216'));
  assert.ok((await casePacket(store, w, NOW)).includes('DEATH REPORTED'));
});

test('death report can be cleared and statuses tracked', async () => {
  let w = (await register()).worker;
  w = await cases.reportDeath(store, w, { reported_by: 'a friend', notes: 'rumour on WhatsApp' }, NOW);
  w = await cases.updateDeathStatus(store, w, 'embassy_informed', 'applied', NOW);
  assert.deepEqual([w.remains_status, w.ex_gratia_status], ['embassy_informed', 'applied']);
  await rejects(cases.updateDeathStatus(store, w, 'lost', 'applied', NOW), /remains status/);
  w = await cases.clearDeath(store, w, NOW);
  assert.ok(!w.death_reported_at); assert.equal(w.status, 'abroad'); assert.ok(w.notes.includes('rumour on WhatsApp'));
  assert.equal((await cases.scheduleCall(store, w, 'weekly', null, NOW)).ok, true);
});

test('after call extraction catches a death report from india', async () => {
  const extracted = { help_check: { abroad: x('no'), worker_died: x('yes'), current_city: x(null, 'Kuwait'), notes: x(null, 'Son died in Kuwait') } };
  const p = { id: 'd1', status: 'completed', conversation_duration: 60, transcript: 'user: మా అబ్బాయి చనిపోయాడు',
    telephony_data: { to_number: '+919000022222' }, context_details: { recipient_data: {} },
    extracted_data: extracted, user_number: '+919000022222' };
  const out = await processCallRecord(store, p, NOW);
  assert.ok(out.help, JSON.stringify(out));
  const w = (await store.get('workers', { case_id: out.help.case_id }))!;
  assert.ok(w.death_reported_at && w.death_note.includes('Son died in Kuwait'));
});

// --- salary vs promise, papers problems, proof of work -----------------------------------

test('paid less than the contract is high', async () => {
  const w = (await register()).worker;
  const out = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', salary_received: 'yes', salary_amount: '900' }, NOW);
  assert.equal(out.risk_level, 'high');
  const r = (await getW(w.id)).risk_reasons[0];
  assert.equal(r.code, 'salary_short'); assert.ok(cases.reasonText(r).includes('900 AED') && cases.reasonText(r).includes('1500 AED'));
  const ok = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', salary_amount: '1450' }, NOW);
  assert.equal(ok.risk_level, 'ok');
});

test('papers problem says saathi is not the police', async () => {
  const w = (await register()).worker;
  const out = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', papers_problem: 'sponsor filed an absconding case' }, NOW);
  assert.equal(out.risk_level, 'high'); assert.ok(out.instruction.startsWith('FIRST say gently: Saathi is not the police'));
  const alert = (await cases.embassyAlert(store, await getW(w.id), NOW)).body;
  assert.ok(alert.includes('victim of illegal recruitment (agent: Gagan Manpower)') && alert.includes('Emergency Certificate'));
  assert.equal((await recordCheckin(store, { case_id: w.case_id, papers_problem: 'no' }, NOW)).risk_level, 'ok');
  const quiet = await recordCheckin(store, { case_id: w.case_id, papers_problem: 'visit visa', code_phrase_used: 'yes' }, NOW);
  assert.ok(!quiet.instruction.includes('not the police'));
});

test('proof of work shows dates work and when pay stopped', async () => {
  const w = (await register()).worker;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'employer', current_city: 'Dubai', current_job: 'cleaning offices' }, NOW);
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', salary_received: 'no', months_unpaid: '2', current_job: 'cleaning offices' }, at(60 * D));
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'briefing', briefing_understood: 'yes' }, NOW);
  const rec = await cases.proofOfWork(store, await getW(w.id), at(61 * D));
  assert.deepEqual(rec.rows.map((r: Row) => r.kind), ['arrival', 'weekly']);
  assert.equal(rec.rows[0].work, 'cleaning offices'); assert.equal(rec.rows[1].pay, 'not paid (2 months)');
  const text = rec.summary.join(' ');
  assert.ok(text.includes('Cleaner, 1500 AED') && text.includes('Salary first reported unpaid'));
});

test('proof of work merges saves from one call', async () => {
  const w = (await register()).worker;
  const extras = [{ needs_help: 'yes' }, { current_city: 'Deira, Dubai' }, { passport_with_worker: 'no' }];
  for (const [i, extra] of extras.entries()) {
    await cases.reportProblem(store, { case_id: w.case_id, caller_phone: '9876543210', ...extra }, at(i * 60_000));
  }
  await cases.reportProblem(store, { case_id: w.case_id, caller_phone: '9876543210', needs_help: 'yes' }, at(2 * H));
  const rows = (await cases.proofOfWork(store, await getW(w.id), at(3 * H))).rows;
  assert.equal(rows.length, 2);
  assert.equal(rows[0].where, 'Deira, Dubai'); assert.equal(rows[0].passport, 'NO');
  assert.ok(rows[0].said.includes('Asked for urgent help') && rows[0].said.includes('Passport is not with the worker'));
});

// --- review fixes (27 Oct): honest promises, the promise in their own words --------------

test('promise in their words and no contract before paying', async () => {
  const w = (await register({ promise_words: 'HR said: "B1 visa = sure job"', contract_before_payment: 'no' })).worker;
  const flags = await flagCodes(w);
  assert.ok(flags.has('no_contract_before_paying') && !STOP_FLAGS.has('no_contract_before_paying'));
  const packet = await casePacket(store, w, NOW);
  assert.ok(packet.includes('HR said: "B1 visa = sure job"') && packet.includes('contract received before paying: no'));
  assert.ok(JSON.stringify(await cases.prajavaniPetition(store, w, NOW)).includes('B1 visa = sure job'));
  const ok = (await register({ worker_phone: '9876500001', contract_before_payment: 'yes' })).worker;
  assert.ok(!(await flagCodes(ok)).has('no_contract_before_paying'));
});

test('voice never claims the embassy was already told', async () => {
  const w = (await register()).worker;
  const crit = await recordCheckin(store, { case_id: w.case_id, call_kind: 'arrival', pickup_status: 'other_person' }, NOW);
  const papers = await recordCheckin(store, { case_id: w.case_id, papers_problem: 'visa expired' }, NOW);
  for (const say of [crit.instruction, papers.instruction]) assert.ok(!say.includes('is alerting') && !say.includes('go home even'));
  assert.ok(crit.instruction.includes('marked urgent and a caseworker will act on it right away'));
  assert.ok(crit.instruction.includes('stay inside') && crit.instruction.includes('airport police'));
  assert.ok(papers.instruction.includes('emergency travel papers even when your papers are not in order'));
  const dead = await cases.reportProblem(store, { caller_phone: '9123456780', caller_relation: 'wife', worker_died: 'yes' }, NOW);
  assert.ok(dead.instruction.includes('no one should ask you for money to bring the body home; if someone asks, tell the caseworker'));
  const pkt = JSON.stringify(cases.deathPacket(store, await getW(w.id), NOW));
  assert.ok(pkt.includes('No one should ask you for money to bring the body home. If someone asks, tell the caseworker.'));
  assert.ok(pkt.includes('G.O. 205 (16 Sep 2024)') && pkt.includes('G.O. 216 (Oct 2024)') && !pkt.includes('as reported in the news'));
});

test('verbal promise kept apart from the papers', async () => {
  const w = (await register({ promise_by: 'sub-agent Ramu', promise_date: '10 Oct 2026',
    promise_words: 'salary 1,500 riyal, cleaning job, free food', contract_before_payment: 'no' })).worker;
  const said = 'Verbal promise (not on paper): sub-agent Ramu on 10 Oct 2026 said: salary 1,500 riyal, cleaning job, free food';
  assert.ok((await casePacket(store, w, NOW)).includes(said));
  assert.ok(predepartureChecks(w).some((f) => f.code === 'no_contract_before_paying' && f.text === 'Payment taken before contract shown'));
});

test('consent notice is stored on the first call', async () => {
  const w = (await register({ call_consent: 'yes' })).worker;
  assert.equal(w.call_consent, 'yes'); assert.ok(!w.consent_notice_at);
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly' }, NOW);
  const first = (await getW(w.id)).consent_notice_at;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly' }, at(7 * D));
  assert.ok(first); assert.equal((await getW(w.id)).consent_notice_at, first);
});

for (const said of [{ threatened: 'yes' }, { movement_restricted: 'yes' }, { needs_help: 'yes' }]) {
  test(`danger words are critical without the code phrase ${JSON.stringify(said)}`, async () => {
    const w = (await register()).worker;
    const out = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', code_phrase_used: 'no', ...said }, NOW);
    assert.equal(out.risk_level, 'critical');
  });
}

// --- emigration papers, routes, case clock (28 Oct) ---------------------------------------

test('ecr worker without clearance or pbby is flagged', async () => {
  const w = (await register({ passport_type: 'ecr', emigration_clearance: 'no', pbby: 'no' })).worker;
  const c = await flagCodes(w);
  assert.ok(c.has('no_emigration_clearance') && c.has('no_pbby') && STOP_FLAGS.has('no_emigration_clearance'));
  const ok = (await register({ worker_phone: '9876500002', passport_type: 'ecnr', emigration_clearance: 'no', pbby: 'no' })).worker;
  const oc = await flagCodes(ok);
  assert.ok(!oc.has('no_emigration_clearance') && !oc.has('no_pbby'));
  const unknown = (await register({ worker_phone: '9876500003', emigration_clearance: 'no' })).worker;
  assert.ok(predepartureChecks(unknown).find((f) => f.code === 'no_emigration_clearance')!.text.startsWith('If the passport is ECR'));
  await rejects(register({ worker_phone: '9876500004', passport_type: 'blue' }), /passport type/);
});

test('routes the government has warned about', async () => {
  for (const [i, country] of ['Russia', 'Myanmar', 'Cambodia', 'Laos'].entries()) {
    const w = (await register({ worker_phone: `900000003${i}`, dest_country: country, dest_city: '' })).worker;
    assert.ok((await flagCodes(w)).has('high_risk_route'));
  }
  assert.ok(!(await flagCodes((await register({ worker_phone: '9876500009' })).worker)).has('high_risk_route'));
});

test('case clock turns overdue after a week without action', async () => {
  let w = (await register()).worker;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', threatened: 'yes' }, NOW);
  const alerts = await store.select('escalations', { status: 'open' });
  w = await getW(w.id);
  assert.deepEqual(cases.caseClock(w, alerts, at(3 * D)), { open_days: 3, last_action_days: null, overdue: false });
  assert.equal(cases.caseClock(w, alerts, at(8 * D))!.overdue, true);
  await cases.updatePetition(store, w, 'submitted', '', at(8 * D));
  w = await getW(w.id);
  assert.deepEqual(cases.caseClock(w, alerts, at(10 * D)), { open_days: 10, last_action_days: 2, overdue: false });
  assert.equal(cases.caseClock(w, [], NOW), null);
});

test('family hears how long the case has been open', async () => {
  const w = (await register()).worker;
  await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', threatened: 'yes' }, NOW);
  const out = await cases.reportProblem(store, { caller_phone: '9123456780', caller_relation: 'wife' }, at(12 * D));
  assert.ok(out.instruction.includes('open for 12 days') && out.instruction.includes('Do not promise a date'));
});

test('home district from the help line and the form', async () => {
  const w = (await register({ home_district: 'Jagtial', home_mandal: 'Korutla', pbby: 'yes', pbby_nominee: 'wife' })).worker;
  const packet = await casePacket(store, w, NOW);
  assert.ok(packet.includes('Home: Korutla, Jagtial') && packet.includes('PBBY insurance: yes (nominee: wife)'));
  const out = await cases.reportProblem(store, { caller_phone: '+971501110000', needs_help: 'yes', home_district: 'Nirmal' }, NOW);
  assert.equal((await store.get('workers', { case_id: out.case_id }))!.home_district, 'Nirmal');
});

// --- from the 2026 Prajavani cases (29 Oct) -----------------------------------------------

test('penalty to leave or cancel the visa is a red flag', async () => {
  const w = (await register({ exit_penalty: 'AED 4,100 to cancel the visa' })).worker;
  assert.ok(predepartureChecks(w).some((f) => f.code === 'exit_penalty' &&
    f.text === 'The contract makes the worker pay to leave or cancel the visa: AED 4,100 to cancel the visa'));
  assert.ok((await casePacket(store, w, NOW)).includes('AED 4,100'));
  const none = (await register({ worker_phone: '9000000041', exit_penalty: 'no' })).worker;
  assert.equal(none.exit_penalty, null);
});

test("someone using the worker's id or phone is high", async () => {
  const w = (await register()).worker;
  const out = await recordCheckin(store, { case_id: w.case_id, call_kind: 'weekly', papers_problem: 'a colleague took a loan on his phone number' }, NOW);
  assert.equal(out.risk_level, 'high'); assert.ok(out.instruction.includes('This is not your wrongdoing'));
  assert.ok((await cases.embassyAlert(store, await getW(w.id), NOW)).body.includes('misusing their ID, phone or bank account'));
});

test('death papers deadline relief fund and visit visa caveat', async () => {
  let w = (await register({ visa_type: 'visit' })).worker;
  w = await cases.reportDeath(store, w, { reported_by: 'wife' }, NOW);
  const text = JSON.stringify(cases.deathPacket(store, w, NOW));
  for (const s of ['within 6 months', "Chief Minister's Relief Fund", 'recorded as a visit visa', '6 నెలల లోపు', 'ముఖ్యమంత్రి సహాయ నిధి']) assert.ok(text.includes(s), s);
});

// --- weekly scam alerts (31 Oct) ---------------------------------------------------------

const alerts = await import('../src/alerts.js');

test('weekly alert goes only to people who agreed', async () => {
  await register({ alerts_opt_in: 'yes' });
  await register({ worker_phone: '9000000051', family_phone: '9000000052', alerts_opt_in: 'no' });
  const dead = (await register({ worker_phone: '9000000053', family_phone: '9000000054', alerts_opt_in: 'yes' })).worker;
  await cases.reportDeath(store, dead, { reported_by: 'wife' }, NOW);
  const people = alerts.recipients(await store.select('workers'));
  assert.deepEqual(new Set(people.map((p) => p.phone)), new Set(['+919876543210', '+919123456780']));
  const row = await alerts.sendAlert(store, await store.select('workers'), alerts.TEMPLATES[0][2], 'voice', NOW);
  assert.equal(row.recipients, 2); assert.equal(row.sent, 2); assert.ok(placed.length >= 2);
  assert.equal(placed.at(-1)!.user_data.call_kind, 'alert');
  const smsRow = await alerts.sendAlert(store, await store.select('workers'), alerts.TEMPLATES[1][2], 'sms', NOW);
  assert.equal(smsRow.prepared + smsRow.sent, 2);
});

test('alert never names a number and needs people', async () => {
  assert.throws(() => alerts.cleanMessage('ఈ నంబర్ 98480 12345 మోసం'), /phone number/);
  await rejects(alerts.sendAlert(store, [], 'గల్ఫ్ సాథి హెచ్చరిక', 'voice', NOW), /nobody/);
  assert.throws(() => alerts.cleanMessage('అ'.repeat(301)), /300/);
});

test("alert suggestions from this week's calls", () => {
  const reports = [{ created_at: NOW.toISOString(), amount_asked: 150000, visa_type: 'visit' },
    { created_at: at(-20 * D).toISOString(), visa_type: 'visit' }];
  const hints = alerts.suggestions(reports, NOW);
  assert.deepEqual(hints.map((h) => h.template), ['visit_visa', 'fee']); assert.ok(hints[0].text.startsWith('1 caller'));
});
