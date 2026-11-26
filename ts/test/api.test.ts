// Port of tests/test_api.py: the same requests, against the Express server.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { afterEach, beforeEach, test } from 'node:test';
import * as api from '../src/api.js';
import * as bolna from '../src/bolna.js';
import * as cases from '../src/cases.js';
import { MemoryStore, isoUtc, type Row } from '../src/db.js';
import * as sms from '../src/sms.js';
import { client } from './client.js';

const AUTH: [string, string] = ['anyone', 'pw-123'];
const REPO = new URL('../../', import.meta.url);
let mem: MemoryStore;
let saved: NodeJS.ProcessEnv;

beforeEach(() => {
  saved = { ...process.env };
  mem = new MemoryStore();
  api.state.store = mem;
  process.env.GS_DASHBOARD_PASSWORD = 'pw-123';
  delete process.env.BOLNA_API_KEY;
  delete process.env.GS_WEBHOOK_TOKEN;
  delete process.env.GS_AUTO_CALLS;
  sms.hooks.sendSms = () => 'demo: not sent';
  bolna.hooks.placeCall = null;
});
afterEach(() => {
  process.env = saved;
  sms.hooks.sendSms = null;
  bolna.hooks.placeCall = null;
});

const register = async (json: Row) => client.post('/api/workers', { auth: AUTH, json });
const ok = { ok: true, execution_id: 'e', error: null };

test('health reports agents loaded', async () => {
  assert.equal((await client.get('/health')).json().licensed_agents_loaded, 2447);
});

test('check agent post', async () => {
  const r = (await client.post('/check-agent', { json: { owner: 'Seedi Kavitha' } })).json();
  assert.equal(r.match, 'needs_confirmation'); assert.equal(r.candidates[0].agency, 'GTM INTERNATIONAL');
  assert.equal((await client.post('/check-agent', { json: { query: 'చెల్లా మల్లేశం జగిత్యాల్' } })).json().match, 'confirmed_in_list');
  assert.equal((await client.post('/check-agent', { json: { agency: 'Golconda Overseas' } })).json().match, 'not_found');
});

test('check agent tolerates missing fields from bolna', async () => {
  const r = await client.post('/check-agent', { json: { agency: 'Gagan Manpower', owner: null, district: { $var: 'district' },
    licence_no: '%(licence_no)s', query: 'unknown' } });
  assert.equal(r.status, 200);
  assert.equal(r.json().candidates[0].agency, 'GAGAN MAN POWER CONSULTANTS');
});

test('check agent from browser link', async () => {
  const r = (await client.get('/check-agent', { params: { owner: 'బొల్లె గంగా నరసయ్య' } })).json();
  assert.equal(r.candidates[0].agency, 'GAGAN MAN POWER CONSULTANTS');
});

test('dashboard needs password', async () => {
  assert.equal((await client.get('/dashboard')).status, 401);
  const form = await client.get('/dashboard', { headers: { Accept: 'text/html' } });
  assert.equal(form.status, 401); assert.ok(form.text.includes('Team login') && form.text.includes('Open the demo (no password)'));
  assert.equal(form.headers.get('www-authenticate'), null);
  assert.equal((await client.get('/dashboard', { auth: ['x', 'wrong'] })).status, 401);
  assert.equal((await client.get('/dashboard', { auth: AUTH })).status, 200);
  assert.equal((await client.post('/api/workers', { json: {} })).status, 401);
  delete process.env.GS_DASHBOARD_PASSWORD;
  assert.equal((await client.get('/dashboard', { auth: AUTH })).status, 503);
});

test('register view call and packet', async () => {
  let r = await register({ worker_name: '<script>alert(1)</script>', worker_phone: '9876543210', family_phone: '9123456780',
    employer_name: 'Al Noor', agent_name: 'Golconda Overseas', payments: '80000' });
  assert.equal(r.status, 200, r.text);
  const caseId = r.json().case_id;
  const page = (await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text;
  assert.ok(page.includes('&lt;script&gt;alert(1)&lt;/script&gt;') && !page.includes('<script>alert(1)'));
  assert.ok(page.includes('not_found') && page.includes('OVER the Rs 35,400 limit'));
  assert.ok((await client.get('/dashboard', { auth: AUTH })).text.includes(caseId));
  r = await client.post(`/api/cases/${caseId}/call`, { auth: AUTH, json: { kind: 'arrival' } });
  assert.equal(r.status, 502); assert.ok(r.json().detail.includes('not configured'));
  assert.equal((await client.post(`/api/cases/${caseId}/call`, { auth: AUTH, json: { kind: 'bogus' } })).status, 400);
  const c = (await client.post('/tools/record-checkin', { json: { case_id: caseId, call_kind: 'arrival',
    pickup_status: 'other_person', months_unpaid: '%(months_unpaid)s' } })).json();
  assert.equal(c.risk_level, 'critical'); assert.ok(c.escalated);
  assert.ok((await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text.includes('CRITICAL'));
  const packet = await client.get(`/dashboard/case/${caseId}/packet.txt`, { auth: AUTH });
  assert.ok(packet.headers.get('content-disposition')!.includes('attachment'));
  assert.ok(packet.text.includes('GULF SAATHI CASE PACKET') && packet.text.includes('Al Noor'));
  const escId = (await mem.select('escalations'))[0].id;
  assert.deepEqual((await client.post(`/api/escalations/${escId}/resolve`, { auth: AUTH })).json(), { ok: true });
  assert.equal((await client.post('/api/escalations/nope/resolve', { auth: AUTH })).status, 404);
});

test('register rejects bad input', async () => {
  const r = await register({ worker_name: 'A' });
  assert.equal(r.status, 400); assert.ok(r.json().detail.includes('required'));
});

test('record checkin tool checks token', async () => {
  process.env.GS_WEBHOOK_TOKEN = 't0k';
  assert.equal((await client.post('/tools/record-checkin', { json: { case_id: 'GS-X' } })).status, 401);
  assert.equal((await client.post('/tools/record-checkin?token=t0k', { json: { case_id: 'GS-X' } })).json().ok, false);
});

test('health shows config and db', async () => {
  const h = (await client.get('/health')).json();
  assert.equal(h.storage, 'memory'); assert.equal(h.dashboard, true); assert.equal(h.bolna_checkin_calls, false);
  const tables = Object.fromEntries(['workers', 'calls', 'checkins', 'escalations', 'contact_reports', 'scam_alerts',
    'workers (new columns)'].map((t) => [t, 'ok']));
  assert.deepEqual((await client.get('/health/db')).json(), { storage: 'memory', ok: true, tables });
});

test('case page notices edit and book arrival', async () => {
  let r = await register({ worker_name: 'MALLAIAH', worker_phone: '9000000011', family_phone: '9000000012',
    payments: '500000', arrival_call_at: '2026-10-30T16:27' });
  const caseId = r.json().case_id;
  let page = (await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text;
  assert.ok(page.includes('is not booked') && page.includes('Book arrival call'));
  assert.ok(page.includes('Next call: —'));
  assert.ok(page.includes('family SMS will use the English name'));
  assert.ok(page.includes(`/dashboard/case/${caseId}/edit`));
  r = await client.post(`/api/cases/${caseId}/book-arrival`, { auth: AUTH });
  assert.equal(r.status, 502); assert.ok(r.json().detail.includes('not configured'));
  const edit = (await client.get(`/dashboard/case/${caseId}/edit`, { auth: AUTH })).text;
  assert.ok(edit.includes('value="+919000000011"') && edit.includes('value="500000"') && edit.includes('value="2026-10-30T16:27"'));
  assert.ok(edit.includes('Save changes'));
  r = await client.post(`/api/cases/${caseId}`, { auth: AUTH, json: { worker_name: 'MALLAIAH', worker_name_te: 'మల్లయ్య',
    worker_phone: '9000000013', family_phone: '9000000012', payments: '500000', arrival_call_at: '2026-10-30T16:27',
    code_phrase: 'అమ్మ బాగుందా' } });
  assert.deepEqual(r.json(), { case_id: caseId });
  page = (await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text;
  assert.ok(page.includes('+919000000013') && !page.includes('English name'));
  const bad = await client.post(`/api/cases/${caseId}`, { auth: AUTH, json: { worker_name: 'M', worker_phone: '9000000013',
    family_phone: '9000000012', code_phrase: 'ANNA' } });
  assert.equal(bad.status, 400); assert.ok(bad.json().detail.includes('too easy'));
  assert.equal((await client.post(`/api/cases/${caseId}`, { json: {} })).status, 401);
  assert.equal((await client.get('/dashboard/case/GS-NOPE/edit', { auth: AUTH })).status, 404);
});

test('old case with weak code phrase shows warning', async () => {
  const caseId = (await register({ worker_name: 'M', worker_phone: '9000000011', family_phone: '9000000012' })).json().case_id;
  await mem.update('workers', { case_id: caseId }, { code_phrase: 'ANNA' });
  assert.ok((await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text.includes('Danger code phrase "ANNA" is too easy to say by accident'));
});

test('book arrival without a time', async () => {
  const caseId = (await register({ worker_name: 'M', worker_phone: '9000000011', family_phone: '9000000012' })).json().case_id;
  const r = await client.post(`/api/cases/${caseId}/book-arrival`, { auth: AUTH });
  assert.equal(r.status, 400); assert.ok(r.json().detail.includes('no arrival-day call time'));
});

test('state view agents page and briefing', async () => {
  const caseId = (await register({ worker_name: 'M', worker_phone: '9000000011', family_phone: '9000000012',
    agent_name: '<b>Fake</b> Overseas', payments: '300000' })).json().case_id;
  assert.equal((await client.get('/dashboard/agents')).status, 401);
  const agents = (await client.get('/dashboard/agents', { auth: AUTH })).text;
  assert.ok(agents.includes('&lt;B&gt;FAKE&lt;/B&gt; OVERSEAS') && !agents.includes('<b>FAKE'));
  assert.ok(agents.includes('not found in licensed list') && agents.includes(caseId));
  const home = (await client.get('/dashboard', { auth: AUTH })).text;
  assert.ok(home.includes('Workers registered') && home.includes('Pre-departure red flags'));
  assert.equal((await client.post(`/api/cases/${caseId}/call`, { auth: AUTH, json: { kind: 'briefing' } })).status, 502);
  assert.ok((await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text.includes('Briefing: not done yet'));
  await client.post('/tools/record-checkin', { json: { case_id: caseId, call_kind: 'briefing', briefing_understood: 'yes' } });
  const page = (await client.get(`/dashboard/case/${caseId}`, { auth: AUTH })).text;
  assert.ok(page.includes('Briefing: done') && page.includes('(understood)') && page.includes('Understood the briefing'));
});

const noHref = (page: string) => page.replace(/href="[^"]*"/g, '').toLowerCase();

test('home page is public and shows totals only', async () => {
  await register({ worker_name: 'Secret Name', worker_phone: '9876543210', family_phone: '9123456780' });
  const page = (await client.get('/')).text;
  assert.ok(page.includes('Get a call from Saathi') && page.includes('Aadujeevitham'));
  assert.ok(!page.includes('Hindi') && page.includes('8 Apr 2026') && page.includes('ready to send'));
  assert.ok(page.includes('src="/gulf-saathi-demo.mp4"') && !page.includes('autoplay'));
  assert.ok(page.includes('Demo video · real Bolna calls'));
  assert.equal(page.split('AI-generated illustration<').length - 1, 4); assert.ok(page.includes('Najeeb Muhammad'));
  for (const img of ['gs_hero_airport.webp', 'gs_desert_goats.webp', 'gs_family_sms.webp', 'gs_caseworker.webp', 'gs_dashboard.webp']) assert.ok(page.includes(`/${img}`));
  assert.ok(page.includes('Lok Sabha USQ 2190, 31 Jul 2026, Annex I') && page.includes('118 action-taken reports'));
  assert.ok(page.includes('3,647 Indian women were sent home from Oman'));
  assert.ok(!page.includes('Rs ') && page.includes('₹35,400') && page.includes('Caseworker view'));
  assert.ok(!page.includes('Secret Name') && !page.includes('9876543210'));
  const words = noHref(page);
  for (const banned of ['fraud', 'genuine', 'government-ready', 'rescue', 'safe', 'trusted']) assert.ok(!words.includes(banned), banned);
  assert.equal(page.split('<img').length, page.split('alt="').length);
});

test('demo call needs the code', async () => {
  const calls: Array<[string, string]> = [];
  bolna.hooks.placeCall = (phone, _d, _s, agentId) => { calls.push([phone, agentId ?? '']); return { ok: true, execution_id: 'e1', error: null }; };
  delete process.env.GS_DEMO_CODE;
  assert.equal((await client.post('/api/demo-call', { json: { phone: '9876543210', code: 'x' } })).status, 503);
  process.env.GS_DEMO_CODE = 'judge-2026';
  process.env.BOLNA_AGENT_ID = 'agent-1';
  api.lastDemoCall.clear();
  assert.equal((await client.post('/api/demo-call', { json: { phone: '9876543210', code: 'nope' } })).status, 403);
  assert.equal((await client.post('/api/demo-call', { json: { phone: '+971501112222', code: 'judge-2026' } })).status, 400);
  assert.equal((await client.post('/api/demo-call', { json: { phone: '98765 43210', code: 'judge-2026' } })).status, 200);
  assert.deepEqual(calls, [['+919876543210', 'agent-1']]);
  assert.equal((await client.post('/api/demo-call', { json: { phone: '9876543210', code: 'judge-2026' } })).status, 429);
});

test('demo story pages', async () => {
  const out = (await client.post('/api/demo/run', { auth: AUTH })).json();
  const c = (await client.get(`/dashboard/case/${out.yadaiah}`, { auth: AUTH })).text;
  assert.ok(c.includes('DEMO') && c.includes('Promise vs reality') && c.includes('herding goats'));
  assert.ok(c.includes('Seen in 2 cases') && c.includes('not a finding of fraud'));
  const agents = (await client.get('/dashboard/agents', { auth: AUTH })).text;
  assert.ok(agents.includes('Saathi Intelligence') && agents.includes('DEMO DATA'));
  assert.ok((await client.get(`/dashboard/case/${out.ramesh}`, { auth: AUTH })).text.includes('do not travel until'));
});

test('report problem tool', async () => {
  const r = (await client.post('/tools/report-problem', { json: { caller_phone: '+971501112222', needs_help: 'yes', case_id: '%(case_id)s' } })).json();
  assert.ok(r.ok && r.risk_level === 'critical' && r.new_case);
});

test('passwords ignore spaces pasted into vercel', async () => {
  process.env.GS_DASHBOARD_PASSWORD = ' pw-123\n';
  assert.equal((await client.get('/dashboard', { auth: ['x', 'pw-123'] })).status, 200);
  process.env.GS_DEMO_CODE = 'judge-2026 \n';
  process.env.BOLNA_AGENT_ID = 'agent-1';
  bolna.hooks.placeCall = () => ok;
  api.lastDemoCall.clear();
  assert.equal((await client.post('/api/demo-call', { json: { phone: '9876543210', code: 'judge-2026' } })).status, 200);
});

test('demo cases are never called', async () => {
  const calls: unknown[] = [];
  bolna.hooks.placeCall = (...a) => { calls.push(a); return ok; };
  const out = (await client.post('/api/demo/run', { auth: AUTH })).json();
  const r = await client.post(`/api/cases/${out.yadaiah}/call`, { auth: AUTH, json: { kind: 'weekly' } });
  assert.equal(r.status, 502); assert.ok(r.json().detail.toLowerCase().includes('demo')); assert.deepEqual(calls, []);
  assert.ok((await client.get(`/dashboard/case/${out.yadaiah}`, { auth: AUTH })).text.includes('never calls demo numbers'));
  assert.ok((await client.get(`/dashboard/case/${out.ramesh}`, { auth: AUTH })).text.includes('RED FLAGS'));
});

test('case page offers an embassy alert when at risk', async () => {
  const cid = (await register({ worker_name: 'Mallaiah', worker_phone: '9876543210', family_phone: '9123456780', dest_country: 'UAE' })).json().case_id;
  assert.ok(!(await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text.includes('Alert the Indian Embassy now'));
  await cases.recordCheckin(mem, { case_id: cid, call_kind: 'arrival', pickup_status: 'other_person', current_city: 'Al Ain',
    landmark: 'near a big mosque' }, new Date());
  const page = (await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text;
  assert.ok(page.includes('Alert the Indian Embassy now') && page.includes('Al Ain, near a big mosque') && page.includes('+919876543210'));
});

test('check contact endpoint', async () => {
  await register({ worker_name: 'A', worker_phone: '9876543210', family_phone: '9123456780', sub_agent_phone: '9848012345' });
  const r = (await client.post('/check-contact', { json: { phone: '+91 98480 12345', payment: '%(payment)s' } })).json();
  assert.ok(r.found && r.cases === 1 && !r.instruction.split(/\s+/).includes('A'));
  assert.equal((await client.get('/check-contact', { params: { phone: '9000011111' } })).json().found, false);
});

test('contact reports saved by post not by browser get', async () => {
  await client.get('/check-contact', { params: { phone: '9848012345' } });
  assert.deepEqual(await mem.select('contact_reports'), []);
  await client.post('/check-contact', { json: { phone: '98480 12345', amount: '100000', caller_phone: '+919000000001',
    district: 'Jagtial', visa_type: '%(visa_type)s' } });
  const rep = await mem.select('contact_reports');
  assert.equal(rep.length, 1); assert.equal(rep[0].phone, '+919848012345'); assert.equal(rep[0].amount_asked, 100000);
  assert.ok((await client.get('/dashboard/agents', { auth: AUTH })).text.includes('Agent numbers reported on calls'));
});

test('petition page and status', async () => {
  const cid = (await register({ worker_name: 'Ravi', worker_phone: '9876543210', family_phone: '9123456780', dest_country: 'Oman' })).json().case_id;
  assert.equal((await client.get(`/dashboard/case/${cid}/petition`)).status, 401);
  const page = (await client.get(`/dashboard/case/${cid}/petition`, { auth: AUTH })).text;
  assert.ok(page.includes('Pravasi Prajavani') && page.includes('ప్రవాసీ ప్రజావాణి') && page.includes('Print'));
  assert.equal((await client.post(`/api/cases/${cid}/petition`, { auth: AUTH, json: { status: 'nope' } })).status, 400);
  assert.ok((await client.post(`/api/cases/${cid}/petition`, { auth: AUTH, json: { status: 'submitted', ref: 'A1' } })).json().ok);
  assert.ok((await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text.includes('handed in'));
});

test('death report from the dashboard', async () => {
  const cid = (await register({ worker_name: 'Rajanna', worker_phone: '9876543210', family_phone: '9123456780',
    family_name: 'Lakshmi', dest_country: 'Saudi Arabia', dest_city: 'Riyadh' })).json().case_id;
  let page = (await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text;
  assert.ok(page.includes('Record a death report') && !page.includes('Death reported'));
  assert.equal((await client.get(`/dashboard/case/${cid}/death`, { auth: AUTH })).status, 404);
  assert.equal((await client.post(`/api/cases/${cid}/death`, { json: {} })).status, 401);
  await client.post(`/api/cases/${cid}/death`, { auth: AUTH, json: { reported_by: 'employer', place: 'King Saud hospital' } });
  page = (await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text;
  assert.ok(page.includes('Death reported') && page.includes('Tell the Indian Embassy about the death') && page.includes('King Saud hospital'));
  assert.ok(page.includes('A death was reported'));
  const papers = (await client.get(`/dashboard/case/${cid}/death`, { auth: AUTH })).text;
  assert.ok(papers.includes('Lakshmi') && papers.includes('G.O. 216') && papers.includes('తెలంగాణ'));
  assert.equal((await client.post(`/api/cases/${cid}/death-status`, { auth: AUTH, json: { remains: 'papers_signed', ex_gratia: 'applied' } })).json().remains_status, 'papers_signed');
  assert.equal((await client.post(`/api/cases/${cid}/death-status`, { auth: AUTH, json: { remains: 'x', ex_gratia: 'applied' } })).status, 400);
  await client.post(`/api/cases/${cid}/death-clear`, { auth: AUTH });
  assert.ok((await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text.includes('Record a death report'));
});

test('find a case by phone or employer', async () => {
  for (const [name, phone, employer] of [['Rajanna', '9876543210', 'Al Safi Farms'], ['Mallesh', '9000011111', 'Noor Cleaning']]) {
    await register({ worker_name: name, worker_phone: phone, family_phone: '9123456780', employer_name: employer });
  }
  let page = (await client.get('/dashboard', { params: { q: '98765 43210' }, auth: AUTH })).text;
  assert.ok(page.includes('Rajanna') && !page.includes('Mallesh'));
  page = (await client.get('/dashboard', { params: { q: 'noor' }, auth: AUTH })).text;
  assert.ok(page.includes('Mallesh') && !page.includes('Rajanna'));
  assert.ok((await client.get('/dashboard', { params: { q: 'zzz' }, auth: AUTH })).text.includes('No case matches'));
});

test('register form has gender and age', async () => {
  const page = (await client.get('/dashboard/new', { auth: AUTH })).text;
  assert.ok(page.includes('name="worker_gender"') && page.includes('name="worker_age"'));
  const r = await register({ worker_name: 'Saraswathi', worker_phone: '9876543210', family_phone: '9123456780',
    worker_gender: 'woman', worker_age: '26', job_title: 'Housemaid', visa_type: 'tourist' });
  const c = (await client.get(`/dashboard/case/${r.json().case_id}`, { auth: AUTH })).text;
  assert.ok(c.includes('Woman going for housework on a tourist visa') && c.includes('do not travel'));
});

test('proof of work page', async () => {
  const cid = (await register({ worker_name: 'Mallesh', worker_phone: '9876543210', family_phone: '9123456780', employer_name: 'Noor Cleaning' })).json().case_id;
  assert.ok((await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text.includes('Proof of work'));
  assert.equal((await client.get(`/dashboard/case/${cid}/proof-of-work`)).status, 401);
  const page = (await client.get(`/dashboard/case/${cid}/proof-of-work`, { auth: AUTH })).text;
  assert.ok(page.includes('Record of contact and work: Mallesh') && page.includes('Noor Cleaning') && page.includes('No calls answered yet'));
});

for (const [query, match, first] of [
  [{ owner: 'Bolle Ganga Narsaiah' }, 'needs_confirmation', 'GAGAN MAN POWER CONSULTANTS'],
  [{ owner: 'Mallesh' }, 'need_more_info', null],
  [{ owner: 'Seedi Kavitha' }, 'needs_confirmation', 'GTM INTERNATIONAL'],
  [{ agency: 'Vision Tours and Travels', district: 'Hyderabad' }, 'confirmed_in_list', 'M/s VISION TOURS AND TRAVELS'],
] as Array<[Row, string, string | null]>) {
  test(`agent cases that failed on 18 oct calls ${JSON.stringify(query)}`, async () => {
    const r = (await client.post('/check-agent', { json: query })).json();
    assert.equal(r.match, match);
    assert.equal(r.candidates.length ? r.candidates[0].agency : null, first);
  });
}

const section = (page: string, start: string, end = '</section>') => {
  const s = page.slice(page.indexOf(start));
  return s.slice(0, s.indexOf(end));
};

test('home explains the repeat agent check and who pays', async () => {
  const page = (await client.get('/')).text;
  const at = (s: string) => page.indexOf(s);
  assert.ok(at('id="how"') < at('id="repeat-agent"') && at('id="repeat-agent"') < at('id="who-pays"') && at('id="who-pays"') < at('id="numbers"'));
  assert.ok(page.includes('Example. Made-up names and number.') && page.includes('98480 XXXXX') && page.includes('DID NOT PAY'));
  assert.ok(page.includes('Never paid by recruiting agents. Never sells worker data.') && page.includes('G.O. 205, 16 Sep 2024') && !page.includes('uniindia'));
  assert.ok(at('id="why"') < at('id="how"') && at('id="how"') < at('id="watch"'));
  assert.ok(at('</header>') < at('id="why"') && at('id="why"') < at('id="watch"'));
  const strip = page.slice(at('id="why"'), at('id="watch"'));
  assert.equal(strip.split('target="_blank" rel="noopener"').length - 1, 6);
  assert.ok(strip.includes('Rajya Sabha Q. 2319, Mar 2026'));
});

test('home has the case network diagram', async () => {
  const page = (await client.get('/')).text;
  const sec = page.slice(page.indexOf('id="repeat-agent"'), page.indexOf('id="who"'));
  const diagram = sec.slice(sec.indexOf('id="case-network"'), sec.indexOf('<div class="hear">'));
  assert.ok(diagram.includes('class="cn"'));
  for (const t of ['Same number', 'Worker 1 · Jagtial', 'CRITICAL', 'Worker 2 · Nizamabad', 'HIGH', 'Callers 3 &amp; 4',
    'Phone 98480 XXXXX', 'UPI ****@ybl', 'Caller 5 · warned before paying', 'DID NOT PAY']) assert.ok(diagram.includes(t), t);
  for (const banned of ['fraud', 'safe', 'criminal', 'genuine', 'employer', 'agent name', 'promise']) assert.ok(!diagram.toLowerCase().includes(banned), banned);
});

test('architecture diagram shows only what is built', async () => {
  const page = (await client.get('/')).text;
  const how = page.slice(page.indexOf('id="how"'), page.indexOf('id="watch"'));
  const arch = how.slice(how.indexOf('id="architecture"'));
  for (const t of ['Bolna voice agent', 'Sarvam saaras:v3', 'FastAPI on Vercel', 'Supabase', '₹35,400', 'Visit visa for a job',
    'Number seen in other cases', 'CRITICAL', 'Telugu warning on the call', 'ready to send', 'English case packet',
    'A human caseworker decides and acts', 'Saathi Check-in agent']) assert.ok(arch.includes(t), t);
  for (const banned of ['safe', 'blacklist', 'syndicate', 'fraud', 'criminal', 'genuine', 'score', 'tomcom', 'police', 'embassy', 'embassies']) {
    assert.ok(!arch.toLowerCase().includes(banned), banned);
  }
});

test('real call player and honest call counter', async () => {
  const page = (await client.get('/')).text;
  const hear = page.slice(page.indexOf('id="hear"'), page.indexOf('id="story"'));
  assert.ok(hear.includes('src="/gs_call_help_line.mp3"') && hear.includes('hidden=true'));
  assert.ok(hear.includes('నా పాస్‌పోర్ట్ పోయింది') && hear.includes('my passport was gone') && hear.includes('the caller is a team member') && hear.includes('alerting the Indian Embassy'));
  const w = await mem.insert('workers', { case_id: 'GS-AAAAAA', worker_name: 'A', worker_phone: '+919876543210', is_demo: false });
  const d = await mem.insert('workers', { case_id: 'GS-BBBBBB', worker_name: 'D', worker_phone: '+919000000001', is_demo: true });
  for (const [cid, wid, num, answered] of [['c1', w.id, '+919876543210', true], ['c2', w.id, '+919123456780', true],
    ['c3', w.id, '+919123456780', false], ['c4', d.id, '+919000000001', true]] as Array<[string, string, string, boolean]>) {
    await mem.upsert('calls', { id: cid, worker_id: wid, answered, raw: { user_number: num } });
  }
  assert.ok((await client.get('/')).text.includes('<b>2</b> calls answered so far (includes the team'));
  process.env.GS_TEAM_PHONES = '98765 43210';
  assert.ok((await client.get('/')).text.includes('<b>2</b> calls answered, <b>1</b> from 1 person outside the team'));
});

test("counter says plainly when all calls are the team's", async () => {
  const w = await mem.insert('workers', { case_id: 'GS-CCCCCC', worker_name: 'A', worker_phone: '+919876543210', is_demo: false });
  await mem.upsert('calls', { id: 't1', worker_id: w.id, answered: true, raw: { user_number: '+919876543210' } });
  process.env.GS_TEAM_PHONES = '+91 98765 43210';
  assert.ok((await client.get('/')).text.replaceAll('&#x27;', "'").includes("all from the team's test phone. Calls from families start with the pilot."));
});

test('call clip file is in public', () => {
  const clip = new URL('public/gs_call_help_line.mp3', REPO);
  assert.ok(existsSync(clip)); const size = statSync(clip).size; assert.ok(size > 100_000 && size < 1_000_000);
});

test('dashboard district filter and overdue clock', async () => {
  for (const [name, phone, district] of [['Rajanna', '9000000021', 'Jagtial'], ['Mallesh', '9000000022', 'Nizamabad']]) {
    await register({ worker_name: name, worker_phone: phone, family_phone: '9000000020', home_district: district });
  }
  const page = (await client.get('/dashboard', { params: { district: 'Jagtial' }, auth: AUTH })).text;
  assert.ok(page.includes('Rajanna') && !page.includes('Mallesh') && page.includes('All home districts'));
  const w = (await mem.get('workers', { worker_name: 'Rajanna' }))!;
  await mem.insert('escalations', { worker_id: w.id, level: 'critical', reasons: [], status: 'open',
    created_at: isoUtc(new Date(Date.now() - 9 * 24 * 3600_000)) });
  assert.ok((await client.get('/dashboard', { auth: AUTH })).text.includes('OVERDUE · Alert open 9 days · no caseworker action yet'));
  assert.ok((await client.get(`/dashboard/case/${w.case_id}`, { auth: AUTH })).text.includes('OVERDUE'));
  assert.ok(cases.caseClock(w, await mem.select('escalations'), new Date())!.overdue);
});

test('prajavani notes section', async () => {
  const page = (await client.get('/')).text;
  assert.ok(page.indexOf('id="who"') < page.indexOf('id="heard"') && page.indexOf('id="heard"') < page.indexOf('id="who-pays"'));
  const sec = page.slice(page.indexOf('id="heard"'), page.indexOf('id="who-pays"'));
  assert.ok(sec.includes('reportedly') && !sec.includes('<img'));
});

test('weekly alerts page', async () => {
  assert.equal((await client.get('/dashboard/alerts')).status, 401);
  const page = (await client.get('/dashboard/alerts', { auth: AUTH })).text;
  assert.ok(page.includes('Weekly scam alert') && page.includes('Goes to <b>0</b>'));
  const r = await client.post('/api/alerts', { auth: AUTH, json: { message: 'గల్ఫ్ సాథి హెచ్చరిక', channel: 'voice' } });
  assert.equal(r.status, 400); assert.ok(r.json().detail.includes('nobody'));
});

test('demo is public without password', async () => {
  assert.equal((await client.get('/demo')).status, 200);
  const out = (await client.post('/api/demo/run')).json();
  const c = await client.get(`/dashboard/case/${out.yadaiah}`, { headers: { Accept: 'text/html' } });
  assert.equal(c.status, 200); assert.ok(c.text.includes('DEMO') && c.text.includes('herding goats'));
  assert.ok(c.text.includes('Demo view, open to everyone') && !c.text.includes('/dashboard/new'));
  for (const sub of ['packet.txt', 'proof-of-work', 'petition']) assert.equal((await client.get(`/dashboard/case/${out.yadaiah}/${sub}`)).status, 200);
  assert.equal((await client.post(`/api/cases/${out.yadaiah}`, { json: {} })).status, 401);
  for (const path of ['/dashboard', '/dashboard/agents', '/dashboard/alerts', '/dashboard/new', `/dashboard/case/${out.yadaiah}/edit`]) {
    assert.equal((await client.get(path)).status, 401, path);
  }
});

test('real case stays private', async () => {
  const cid = (await register({ worker_name: 'Real', worker_phone: '+919812345678', family_phone: '+919812345679' })).json().case_id;
  for (const sub of ['', '/packet.txt', '/proof-of-work', '/petition']) {
    const r = await client.get(`/dashboard/case/${cid}${sub}`);
    assert.equal(r.status, 401, sub); assert.ok(!r.text.includes('+919812345678'));
  }
  assert.equal((await client.get('/dashboard/case/GS-NOPE')).status, 401);
  assert.equal((await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).status, 200);
});

test('public demo case never links a real case', async () => {
  const out = (await client.post('/api/demo/run')).json();
  const yad = (await mem.get('workers', { case_id: out.yadaiah }))!;
  const real = (await register({ worker_name: 'Real', worker_phone: '+919812345678', family_phone: '+919812345679', sub_agent_phone: yad.sub_agent_phone })).json();
  assert.ok(!(await client.get(`/dashboard/case/${out.yadaiah}`)).text.includes(real.case_id));
  assert.ok((await client.get(`/dashboard/case/${out.yadaiah}`, { auth: AUTH })).text.includes(real.case_id));
});

test('public demo reuses a recent story', async () => {
  const first = (await client.post('/api/demo/run')).json();
  const again = (await client.post('/api/demo/run')).json();
  assert.equal(again.yadaiah, first.yadaiah); assert.ok(again.reused);
  assert.equal((await mem.select('workers')).filter((w) => w.is_demo).length, 3);
});

const form = (o: Record<string, string>) => ({ body: new URLSearchParams(o).toString(), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });

test('login form sets a cookie', async () => {
  const bad = await client.post('/login', form({ password: 'nope', next: '/dashboard' }));
  assert.equal(bad.status, 401); assert.ok(bad.text.includes('Wrong password'));
  const good = await client.post('/login', form({ password: 'pw-123', next: '/dashboard/agents' }));
  assert.equal(good.status, 303); assert.equal(good.headers.get('location'), '/dashboard/agents');
  const setCookie = good.headers.get('set-cookie')!;
  assert.ok(!setCookie.includes('pw-123'));
  const cookie = setCookie.split(';')[0];
  assert.equal((await client.get('/dashboard', { headers: { Cookie: cookie } })).status, 200);
  const out = await client.get('/logout', { headers: { Cookie: cookie } });
  assert.ok(out.headers.get('set-cookie')!.startsWith('gs_team=;'));
  assert.equal((await client.get('/dashboard')).status, 401);
});

test('login never sends you to another site', async () => {
  const r = await client.post('/login', form({ password: 'pw-123', next: '//evil.example' }));
  assert.equal(r.headers.get('location'), '/dashboard');
});

test('curl head on public pages', async () => {
  for (const path of ['/', '/demo', '/login']) assert.equal((await client.head(path)).status, 200, path);
});

test('home started timeline', async () => {
  delete process.env.GS_PILOT_WHATSAPP;
  const page = (await client.get('/')).text;
  const a = page.indexOf('id="watch"'), b = page.indexOf('id="hear"');
  const sec = section(page, 'id="started"');
  assert.ok(a < page.indexOf('id="started"') && page.indexOf('id="started"') < b);
  const labels = ['Listened', 'Built', 'Demoed', 'Next: pilot'].map((x) => sec.indexOf(`<b>${x}</b>`));
  assert.deepEqual(labels, [...labels].sort((x, y) => x - y));
  assert.equal(sec.split('class="done"').length - 1, 3); assert.equal(sec.split('class="next"').length - 1, 1);
  assert.ok(sec.includes('starting with Jagtial') && !sec.includes('lang="te"'));
  for (const banned of ['approved', 'government pilot', 'committee', 'panel', 'fraud', 'genuine', 'rescue', 'safe', 'trusted']) assert.ok(!sec.toLowerCase().includes(banned), banned);
  assert.ok(!page.includes('Join the pilot'));
});

test('join the pilot button needs a number', async () => {
  process.env.GS_PILOT_WHATSAPP = '+91 98765 43210';
  assert.ok((await client.get('/')).text.includes('href="https://wa.me/919876543210"'));
  process.env.GS_PILOT_WHATSAPP = 'javascript:alert(1)';
  const page = (await client.get('/')).text;
  assert.ok(!page.includes('Join the pilot') && !page.includes('javascript:alert'));
});

test('started section has the prajavani photo and links the public post', async () => {
  delete process.env.GS_PILOT_WHATSAPP;
  const sec = section((await client.get('/')).text, 'id="started"');
  assert.ok(sec.includes('src="/gs_prajavani.webp"') && sec.includes('alt="A family meeting the Pravasi Prajavani desk'));
  assert.ok(sec.includes('Pravasi Prajavani, Praja Bhavan, Hyderabad.') && !sec.includes('AI-generated'));
  assert.ok(sec.includes('Pilot area: Jagtial district, Telangana. For families of Gulf workers.'));
  for (const banned of ['approved', 'government pilot', 'committee', 'panel', 'free', 'praised', 'endorsed', 'vinod', 'reddy']) assert.ok(!sec.toLowerCase().includes(banned), banned);
  assert.ok(sec.includes('src="/gs_pitch_wide.webp"') && sec.includes('https://www.facebook.com/share/v/1bkhsPZopf/'));
  assert.ok(sec.includes('from a public Facebook post, Nov 2026'));
  assert.equal(sec.split('<img').length - 1, 2); assert.equal(sec.split('alt="').length - 1, 2);
  for (const img of ['gs_prajavani.webp', 'gs_pitch_wide.webp']) assert.ok(statSync(new URL(`public/${img}`, REPO)).size < 250_000);
});

// --- pilot: outcome, intake, go-live card ---------------------------------------------

const realCase = async (extra: Row = {}) => {
  const r = await register({ worker_name: 'Real', worker_phone: '+919812345678', family_phone: '+919812345679', ...extra });
  assert.equal(r.status, 200, r.text);
  return r.json().case_id as string;
};

test('outcome is saved and shown', async () => {
  const cid = await realCase();
  assert.equal((await client.post(`/api/cases/${cid}/outcome`, { json: { outcome: 'solved' } })).status, 401);
  assert.equal((await client.post(`/api/cases/${cid}/outcome`, { auth: AUTH, json: { outcome: 'won' } })).status, 400);
  assert.equal((await client.post(`/api/cases/${cid}/outcome`, { auth: AUTH, json: { outcome: 'solved', amount_recovered: '-5' } })).status, 400);
  const before = (await mem.get('workers', { case_id: cid }))!;
  const r = await client.post(`/api/cases/${cid}/outcome`, { auth: AUTH, json: { outcome: 'solved', problem: 'unpaid_wages',
    amount_recovered: '2,00,000', note: '3 months paid' } });
  assert.deepEqual(r.json(), { ok: true, outcome: 'solved' });
  const w = (await mem.get('workers', { case_id: cid }))!;
  assert.equal(w.amount_recovered, 200000); assert.ok(w.outcome_at); assert.equal(w.status, before.status);
  assert.equal(w.next_call_at ?? null, before.next_call_at ?? null);
  const page = (await client.get(`/dashboard/case/${cid}`, { auth: AUTH })).text;
  assert.ok(page.includes('Recorded: Solved · ₹2,00,000 recovered'));
  const postCall = page.slice(page.indexOf("/outcome'")).slice(0, 200);
  assert.ok(!postCall.includes('{{') && postCall.includes('{problem:'));
  const listing = (await client.get('/dashboard', { auth: AUTH })).text;
  assert.ok(listing.includes('Money recovered (recorded by caseworkers)') && listing.includes('₹2,00,000'));
  await client.post(`/api/cases/${cid}/outcome`, { auth: AUTH, json: { outcome: '' } });
  assert.equal((await mem.get('workers', { case_id: cid }))!.outcome, null);
  assert.ok(!(await client.get('/dashboard', { auth: AUTH })).text.includes('Money recovered'));
});

test('outcome totals leave out demo cases', () => {
  const rows = [
    { outcome: 'solved', amount_recovered: 100, created_at: '2026-11-01T00:00:00+00:00', outcome_at: '2026-11-05T00:00:00+00:00' },
    { outcome: 'partly_solved', amount_recovered: 50, created_at: '2026-11-01T00:00:00+00:00', outcome_at: '2026-11-11T00:00:00+00:00' },
    { outcome: 'not_solved', created_at: '2026-11-01T00:00:00+00:00', outcome_at: '2026-11-21T00:00:00+00:00' },
    { outcome: 'solved', amount_recovered: 999, is_demo: true, created_at: '2026-11-01T00:00:00+00:00', outcome_at: '2026-11-02T00:00:00+00:00' },
    { outcome: null },
  ];
  assert.deepEqual(cases.outcomeTotals(rows), { closed: 3, solved: 2, recovered: 150, median_days: 10 });
});

test('public demo case has no outcome form', async () => {
  const out = (await client.post('/api/demo/run')).json();
  assert.ok(!(await client.get(`/dashboard/case/${out.yadaiah}`)).text.includes('Save outcome'));
  assert.ok((await client.get(`/dashboard/case/${out.yadaiah}`, { auth: AUTH })).text.includes('Save outcome'));
});

test('intake opens a case from the family', async () => {
  const placed: unknown[] = [];
  bolna.hooks.placeCall = (...a) => { placed.push(a); return ok; };
  assert.equal((await client.get('/dashboard/intake')).status, 401);
  assert.ok((await client.get('/dashboard/intake', { auth: AUTH })).text.includes('Did the family agree?'));
  const body = { consent: 'yes', family_phone: '98765 43210', family_name: 'Lakshmi', family_relation: 'wife',
    worker_name: 'Ravi', dest_country: 'Saudi Arabia', dest_city: 'Riyadh', problem: 'unpaid_wages',
    months_unpaid: '3', home_district: 'Jagtial', notes: 'No salary since August' };
  assert.equal((await client.post('/api/intake', { json: body })).status, 401);
  assert.equal((await client.post('/api/intake', { auth: AUTH, json: { ...body, consent: 'no' } })).status, 400);
  assert.equal((await client.post('/api/intake', { auth: AUTH, json: { ...body, family_phone: '' } })).status, 400);
  assert.equal((await client.post('/api/intake', { auth: AUTH, json: { ...body, problem: 'x' } })).status, 400);
  const out = (await client.post('/api/intake', { auth: AUTH, json: body })).json();
  assert.ok(out.new_case); assert.equal(out.risk_level, 'high');
  const w = (await mem.get('workers', { case_id: out.case_id }))!;
  assert.equal(w.source, 'prajavani'); assert.equal(w.family_phone, '+919876543210'); assert.equal(w.worker_name, 'Ravi');
  assert.equal(w.dest_country, 'Saudi Arabia'); assert.equal(w.outcome_problem, 'unpaid_wages'); assert.equal(w.status, 'abroad');
  assert.equal(w.call_consent, 'yes'); assert.ok(!w.consent_notice_at);
  assert.deepEqual(placed, []);
  assert.ok((await client.get(`/dashboard/case/${out.case_id}`, { auth: AUTH })).text.includes('Entered by a caseworker at intake (no call)'));
  const again = (await client.post('/api/intake', { auth: AUTH, json: body })).json();
  assert.equal(again.case_id, out.case_id); assert.ok(!again.new_case);
});

test('go live card is for the team only', async () => {
  delete process.env.GS_PILOT_WHATSAPP;
  const listing = (await client.get('/dashboard', { auth: AUTH })).text;
  assert.ok(listing.includes('Pilot go-live check:') && listing.includes('CHECK BY HAND') && listing.includes('Set GS_PILOT_WHATSAPP'));
  for (const path of ['/', '/demo', '/login']) assert.ok(!(await client.get(path)).text.includes('Pilot go-live check'));
});

test('health db probe columns are all text', () => {
  const schema = readFileSync(new URL('supabase/schema.sql', REPO), 'utf8');
  for (const col of api.NEW_WORKER_COLUMNS) {
    const m = new RegExp(`alter table workers add column if not exists ${col}\\s+(\\w+)`).exec(schema);
    assert.ok(m, `${col} is not added in schema.sql`);
    assert.equal(m![1], 'text', `${col} is ${m![1]}`);
  }
});

test('helpline number shows only when set', async () => {
  delete process.env.GS_HELPLINE_NUMBER;
  let page = (await client.get('/')).text;
  assert.ok(!page.includes('Call Saathi</h2>') && !page.includes('href="tel:'));
  process.env.GS_HELPLINE_NUMBER = '+91 80659 52403';
  page = (await client.get('/')).text;
  assert.ok(page.includes('href="tel:+918065952403"') && page.includes('+91 80659 52403') && page.includes('తెలుగులో మాట్లాడండి'));
  process.env.GS_HELPLINE_NUMBER = 'tel:evil';
  assert.ok(!(await client.get('/')).text.includes('href="tel:'));
  process.env.GS_HELPLINE_NUMBER = '9715501234567';
  page = (await client.get('/')).text;
  assert.ok(page.includes('href="tel:+9715501234567"') && page.includes('+971550123456'));
  for (const banned of ['safe', 'genuine', 'rescue', 'trusted', 'fraud']) assert.ok(!noHref(page).includes(banned), banned);
});

test('go live card lists the helpline number', async () => {
  delete process.env.GS_HELPLINE_NUMBER;
  const page = (await client.get('/dashboard', { auth: AUTH })).text;
  assert.ok(page.includes('Help-line number shown on the site') && page.includes('Set GS_HELPLINE_NUMBER'));
});
