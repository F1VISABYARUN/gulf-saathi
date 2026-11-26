// Gulf Saathi server: tools the Bolna voice agents call, Bolna's webhook, and the caseworker dashboard.
// Port of gulf_saathi/api.py (FastAPI) to Express, with the same URLs, answers and errors.
//
// Without SUPABASE_URL / SUPABASE_SERVICE_KEY it keeps data in memory only.
import { createHmac, timingSafeEqual } from 'node:crypto';
import type { AddressInfo } from 'node:net';
import express, { type NextFunction, type Request, type Response } from 'express';
import * as alerts from './alerts.js';
import * as bolna from './bolna.js';
import * as cases from './cases.js';
import { findDir } from './config.js';
import { MemoryStore, StoreError, SupabaseStore, TABLES, isoUtc, type Row, type Store } from './db.js';
import * as demo from './demo.js';
import { checkFee as computeFee } from './fees.js';
import { LicensedList } from './matcher.js';
import * as dashboard from './pages/dashboard.js';
import * as site from './pages/site.js';
import { pyStr, truthy } from './py.js';
import * as signals from './signals.js';
import * as sms from './sms.js';

export const licensed = LicensedList.load();
/** The store and clock the server uses; tests swap them. */
export const state: { store: Store; now: () => Date } = {
  store: SupabaseStore.fromEnv() ?? new MemoryStore(),
  now: () => new Date(),
};
const S = () => state.store;
const now = () => state.now();

/** FastAPI's HTTPException: answered as {"detail": ...} with the status. */
export class HttpError extends Error {
  constructor(public status: number, public detail: unknown) { super(String(detail)); }
}

class LoginNeeded extends Error {
  constructor(public off = false) { super('login needed'); }
}

// Bolna fills a request template from what its LLM extracted. A field the caller never mentioned can
// arrive as null, an unfilled placeholder such as {"$var": "district"} or "%(district)s", or "none".
export function blank(v: unknown): boolean {
  if (v === null || v === undefined || (typeof v === 'object' && !Array.isArray(v))) return true;
  const s = pyStr(v).trim();
  return !s || s.startsWith('%(') || ['none', 'null', 'unknown', 'n/a', 'na', '-'].includes(s.toLowerCase());
}

export function cleanToolArgs(data: Row): Row {
  return Object.fromEntries(Object.entries(data).map(([k, v]) => [k, blank(v) ? '' : typeof v === 'string' ? v.trim() : v]));
}

const same = (a: string, b: string) => {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
};

/** If GS_WEBHOOK_TOKEN is set, Bolna's URLs must end in ?token=<it>. */
function requireBolnaToken(req: Request) {
  const expected = process.env.GS_WEBHOOK_TOKEN ?? '';
  const token = typeof req.query.token === 'string' ? req.query.token : '';
  if (expected && !same(token, expected)) throw new HttpError(401, 'bad token');
}

export const COOKIE = 'gs_team';

// Spaces or a line break copied along with a value pasted into the host would otherwise make the right
// password fail.
const teamPassword = () => (process.env.GS_DASHBOARD_PASSWORD ?? '').trim();

/** What the login cookie holds: a keyed hash of the password, never the password. Changing the password
 * logs everyone out. */
export const cookieValue = (password: string) => createHmac('sha256', password).update('gulf-saathi team login').digest('hex');

function cookies(req: Request): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of (req.headers.cookie ?? '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim().replace(/^"(.*)"$/, '$1'));
  }
  return out;
}

/** Logged in through the form (cookie) or a password sent with Basic auth (curl). */
export function isTeam(req: Request): boolean {
  const expected = teamPassword();
  if (!expected) return false;
  if (same(cookies(req)[COOKIE] ?? '', cookieValue(expected))) return true;
  const auth = req.headers.authorization ?? '';
  if (auth.toLowerCase().startsWith('basic ')) {
    let given = '';
    try {
      const text = Buffer.from(auth.slice(6), 'base64').toString('utf8');
      if (!text.includes(':')) throw new Error('no colon');
      given = text.split(':').slice(1).join(':').trim();
    } catch { given = ''; }
    return same(given, expected);
  }
  return false;
}

const wantsHtml = (req: Request) => req.method === 'GET' && (req.headers.accept ?? '').includes('text/html');

/** The team pages show workers' and families' personal data. */
function requireDashboard(req: Request) {
  if (!teamPassword()) throw new LoginNeeded(true);
  if (!isTeam(req)) throw new LoginNeeded();
}

/** Only our own pages, so the login can't send someone to another site. */
export function safeNext(path: unknown): string {
  const p = pyStr(path ?? '');
  return p.startsWith('/') && !p.startsWith('//') && !p.includes('\\') ? p : '/dashboard';
}

const status = () => ({ storage: S().kind, bolna: bolna.configured(), sms: sms.provider() });

function jsonObject(req: Request): Row {
  const raw: Buffer = req.body instanceof Buffer ? req.body : Buffer.alloc(0);
  let data: unknown;
  try { data = JSON.parse(raw.toString('utf8')); } catch { throw new HttpError(400, 'body is not JSON'); }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) throw new HttpError(400, 'expected a JSON object');
  return data as Row;
}

/** A pydantic model body: a JSON object, else FastAPI's 422. */
function modelBody(req: Request): Row {
  const raw: Buffer = req.body instanceof Buffer ? req.body : Buffer.alloc(0);
  let data: unknown;
  try { data = JSON.parse(raw.toString('utf8')); } catch {
    throw new HttpError(422, [{ type: 'json_invalid', loc: ['body'], msg: 'JSON decode error' }]);
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    throw new HttpError(422, [{ type: 'model_attributes_type', loc: ['body'], msg: 'Input should be a valid dictionary or object to extract fields from' }]);
  }
  return data as Row;
}

const q = (req: Request, name: string) => {
  const v = req.query[name];
  return typeof v === 'string' ? v : Array.isArray(v) ? String(v[v.length - 1]) : '';
};
const fields = (data: Row, names: string[]) => Object.fromEntries(names.map((n) => [n, blank(data[n]) ? '' : pyStr(data[n]).trim()]));

const html = (res: Response, body: string, code = 200) => res.status(code).type('text/html; charset=utf-8').send(body);
type Handler = (req: Request, res: Response) => unknown | Promise<unknown>;
/** Run a handler; a returned object is sent as JSON, a string as HTML. */
const wrap = (h: Handler, guard?: (req: Request) => void) => async (req: Request, res: Response, next: NextFunction) => {
  try {
    guard?.(req);
    const out = await h(req, res);
    if (res.headersSent || out === undefined) return;
    if (typeof out === 'string') html(res, out);
    else res.json(out);
  } catch (e) { next(e); }
};
const team = requireDashboard;

export function demoAgentId(): string {
  return (process.env.BOLNA_AGENT_ID ?? '').trim();
}

export const lastDemoCall = new Map<string, Date>(); // per server instance only: a speed bump, not a guarantee

export const NEW_WORKER_COLUMNS = ['visa_job', 'visa_type', 'sub_agent_name', 'sub_agent_phone', 'payment_to',
  'welcome_sms', 'welcome_sms_status', 'source', 'reported_by', 'petition_status',
  'petition_ref', 'worker_gender', 'death_note', 'remains_status', 'ex_gratia_status',
  'promise_words', 'contract_before_payment', 'promise_by', 'promise_date', 'call_consent',
  'passport_type', 'emigration_clearance', 'pbby', 'pbby_nominee', 'home_district', 'home_mandal', 'alerts_opt_in',
  'exit_penalty', 'outcome', 'outcome_problem', 'outcome_note'];
// The check below filters every column on the text "x". That fails with a type error on number and date
// columns (amount_recovered, outcome_at), so only text columns belong in this list.

/** What the pilot needs switched on: [label, "ok" / "off" / "hand", what to do]. "hand" = the server
 * cannot know; a person has to try it. */
export function goLiveChecks(): Array<[string, string, string]> {
  const line = (label: string, ok: boolean, fix: string): [string, string, string] => [label, ok ? 'ok' : 'off', ok ? '' : fix];
  return [
    line('Database (Supabase)', S().kind === 'supabase', 'Set SUPABASE_URL and SUPABASE_SERVICE_KEY in Vercel.'),
    line('Bolna check-in calls', bolna.configured(), 'Set BOLNA_API_KEY and BOLNA_CHECKIN_AGENT_ID in Vercel.'),
    line('Bolna help-line agent', Boolean(demoAgentId()), 'Set BOLNA_AGENT_ID in Vercel.'),
    line('Bolna webhook token', Boolean((process.env.GS_WEBHOOK_TOKEN ?? '').trim()),
      'Set GS_WEBHOOK_TOKEN in Vercel and add ?token=... to the Bolna tool and webhook URLs.'),
    line('SMS to families', sms.provider() !== 'demo',
      'Not connected: alerts show as ready to send, so a caseworker phones the family.'),
    line('Team phones (so test calls are not counted)', cases.teamPhones().size > 0, 'Set GS_TEAM_PHONES in Vercel.'),
    line('Join the pilot button', Boolean(site.pilotLink()), 'Set GS_PILOT_WHATSAPP in Vercel (digits, with country code).'),
    line('Help-line number shown on the site', Boolean(site.helpline()[0]),
      'Set GS_HELPLINE_NUMBER in Vercel (digits, with country code), only after a test call is answered by the right agent.'),
    ['Incoming number answers in Telugu', 'hand', 'Call the Saathi number from your own phone.'],
    ['A call to a Gulf number connects', 'hand', 'Register a test case with a real Gulf number and press Call now.'],
  ];
}

async function workerOr404(caseId: string): Promise<Row> {
  const w = await S().get('workers', { case_id: caseId.trim().toUpperCase() });
  if (!w) throw new HttpError(404, 'case not found');
  return w;
}

/** A made-up demo case is open to everyone (read only); a real case needs the team login. */
async function viewable(caseId: string, req: Request): Promise<[Row, boolean]> {
  if (isTeam(req)) return [await workerOr404(caseId), false];
  const w = await S().get('workers', { case_id: caseId.trim().toUpperCase() });
  if (!(w && truthy(w.is_demo))) requireDashboard(req); // no hint whether a real case exists
  return [w!, true];
}

const caseError = (e: unknown) => { if (e instanceof cases.CaseError) throw new HttpError(400, e.message); throw e; };
const pyTupleRepr = (xs: string[]) => `(${xs.map((x) => `'${x}'`).join(', ')})`;

export function createApp() {
  const app = express();
  app.set('trust proxy', true);
  app.disable('x-powered-by');
  app.use(express.raw({ type: () => true, limit: '2mb' }));
  // Case pages, packets and tool answers hold personal data: no CDN or browser may keep a copy.
  app.use((req, res, next) => {
    if (/^\/(dashboard|api|tools|webhooks|check-|login|logout|health)/.test(req.path)) res.set('Cache-Control', 'no-store');
    next();
  });

  // --- public website ---------------------------------------------------------------

  // The home page is public and counts every case and call: build the counts at most once a minute.
  let homeCache: { at: number; counts: Row } | null = null;
  const home: Handler = async () => {
    let counts: Row;
    if (homeCache && Date.now() - homeCache.at < 60_000) {
      return site.renderHome(homeCache.counts, Boolean((process.env.GS_DEMO_CODE ?? '').trim() && demoAgentId()));
    }
    try {
      const workers = await S().select('workers', null, { order: 'updated_at' });
      counts = { ...cases.summaryCounts(workers, {}), demo: workers.filter((w) => truthy(w.is_demo)).length,
        signals: signals.repeatedSignals(workers).filter((x) => x.strong).length,
        calls: cases.callCounts(await S().select('calls'), workers, cases.teamPhones()) };
      if (process.env.NODE_ENV !== 'test') homeCache = { at: Date.now(), counts };
    } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      counts = {};
    }
    return site.renderHome(counts, Boolean((process.env.GS_DEMO_CODE ?? '').trim() && demoAgentId()));
  };
  app.get('/', wrap(home)); // Express answers HEAD from GET routes

  app.post('/api/demo-call', wrap(async (req) => {
    const data = jsonObject(req);
    const expected = (process.env.GS_DEMO_CODE ?? '').trim();
    if (!expected || !demoAgentId()) throw new HttpError(503, 'Demo calls are off (GS_DEMO_CODE / BOLNA_AGENT_ID not set).');
    if (!same(pyStr(truthy(data.code) ? data.code : '').trim(), expected)) throw new HttpError(403, 'Wrong demo code.');
    let phone: string;
    try { phone = cases.normalizePhone(data.phone); } catch (e) { caseError(e); throw e; }
    if (!phone.startsWith('+91')) throw new HttpError(400, 'Indian numbers only for now.');
    const last = lastDemoCall.get(phone);
    if (last && (now().getTime() - last.getTime()) / 1000 < 120) {
      throw new HttpError(429, 'Saathi called this number less than 2 minutes ago. Please wait.');
    }
    const res = await bolna.placeCall(phone, { source: 'website_demo' }, null, demoAgentId());
    if (!res.ok) throw new HttpError(502, res.error);
    lastDemoCall.set(phone, now());
    return { ok: true, execution_id: res.execution_id };
  }));

  /** Open to everyone: judges and visitors run the made-up story without a password. */
  app.get('/demo', wrap(() => site.renderDemo()));

  /** Creates made-up demo cases (is_demo). No real call or SMS. A story made in the last hour is shown
   * again instead of making new cases each click. */
  app.post('/api/demo/run', wrap(async () => {
    try {
      const recent = demo.recentStory(await S().select('workers'), now());
      return recent ?? await demo.runDemo(S(), licensed, now());
    } catch (e) {
      if (e instanceof StoreError) throw new HttpError(503, `Could not save the demo cases. Has supabase/schema.sql been run again? ${e.message}`);
      throw e;
    }
  }));

  // --- team login -----------------------------------------------------------------

  app.get('/login', wrap((req) => site.renderLogin(safeNext(q(req, 'next') || '/dashboard'))));

  app.post('/login', wrap((req, res) => {
    const form = new URLSearchParams((req.body instanceof Buffer ? req.body : Buffer.alloc(0)).toString('utf8'));
    const given = (form.get('password') ?? '').trim();
    const target = safeNext(form.has('next') ? form.get('next') : '/dashboard');
    const expected = teamPassword();
    if (!expected) throw new LoginNeeded(true);
    if (!same(given, expected)) return html(res, site.renderLogin(target, 'Wrong password.'), 401);
    res.cookie(COOKIE, cookieValue(expected), { maxAge: 7 * 24 * 3600 * 1000, httpOnly: true, secure: req.secure, sameSite: 'lax', path: '/' });
    res.redirect(303, target);
  }));

  app.get('/logout', wrap((_req, res) => {
    res.clearCookie(COOKIE, { path: '/' });
    res.redirect(303, '/');
  }));

  // --- health -------------------------------------------------------------------

  app.get('/health', wrap(() => ({
    service: 'gulf-saathi',
    licensed_agents_loaded: licensed.agents.length,
    storage: S().kind,
    bolna_checkin_calls: bolna.configured(),
    sms: sms.provider(),
    dashboard: Boolean(process.env.GS_DASHBOARD_PASSWORD),
    webhook_token: Boolean(process.env.GS_WEBHOOK_TOKEN),
    // "Get a call from Saathi" needs both. Shows only whether each is set, never the value.
    demo_calls: { GS_DEMO_CODE: Boolean((process.env.GS_DEMO_CODE ?? '').trim()), BOLNA_AGENT_ID: Boolean(demoAgentId()) },
  })));

  /** Can we read each table? Shows Supabase's error message, never data. */
  app.get('/health/db', wrap(async () => {
    const tables: Record<string, string> = {};
    for (const t of TABLES) {
      try { await S().select(t, null, { limit: 1 }); tables[t] = 'ok'; } catch (e) { tables[t] = String((e as Error).message).slice(0, 300); }
    }
    try {
      // Filtering on a column fails if it doesn't exist: catches a schema.sql not re-run.
      await S().select('workers', Object.fromEntries(NEW_WORKER_COLUMNS.map((c) => [c, 'x'])), { limit: 1 });
      tables['workers (new columns)'] = 'ok';
    } catch (e) {
      tables['workers (new columns)'] = 'missing: run supabase/schema.sql again. ' + String((e as Error).message).slice(0, 200);
    }
    return { storage: S().kind, ok: Object.values(tables).every((v) => v === 'ok'), tables };
  }));

  // --- tools for the Bolna voice agents --------------------------------------------

  const AGENT_FIELDS = ['agency', 'owner', 'district', 'licence_no', 'query'];
  /** Is this agent in the MEA licensed list? It never endorses an agent. */
  const checkAgent = (f: Row) => licensed.check(f.agency, f.owner, f.district, f.licence_no, f.query);
  app.get('/check-agent', wrap((req) => checkAgent(fields(Object.fromEntries(AGENT_FIELDS.map((n) => [n, q(req, n)])), AGENT_FIELDS))));
  app.post('/check-agent', wrap((req) => checkAgent(fields(modelBody(req), AGENT_FIELDS))));

  /** Add up every payment to the agent and compare with the legal cap. */
  app.get('/check-fee', wrap((req) => computeFee(q(req, 'payments'))));
  app.post('/check-fee', wrap((req) => {
    const v = modelBody(req).payments;
    return computeFee(Array.isArray(v) ? v : blank(v) ? '' : v ?? '');
  }));

  const CONTACT_FIELDS = ['phone', 'payment', 'amount', 'visa_type', 'agent_name', 'district', 'reporter', 'caller_phone', 'notes'];
  async function contactResult(c: Row): Promise<Row> {
    let workers: Row[], reports: Row[];
    try {
      workers = await S().select('workers', null, { order: 'updated_at' });
      reports = await S().select('contact_reports');
    } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      console.error('check_contact failed:', e.message);
      return { found: false, instruction: 'Say you could not check the number right now; do not pay more until ' +
        'the licence and a written contract are checked.' };
    }
    return signals.checkContact(workers, c.phone, c.payment, reports, c.caller_phone);
  }
  /** Same check from a browser link, e.g. /check-contact?phone=9848012345 (saves nothing). */
  app.get('/check-contact', wrap((req) => contactResult(fields({ phone: q(req, 'phone'), payment: q(req, 'payment') }, CONTACT_FIELDS))));
  /** Live on the call: has this agent phone or payment account come up before? Saves this report too. */
  app.post('/check-contact', wrap(async (req) => {
    const c = fields(modelBody(req), CONTACT_FIELDS);
    const out = await contactResult(c);
    try { await signals.recordContact(S(), c, isoUtc(now())); } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      console.error('contact report not saved:', e.message); // the answer matters more than saving it
    }
    return out;
  }));

  app.post('/tools/record-checkin', wrap(async (req) => {
    const data = jsonObject(req);
    try { return await cases.recordCheckin(S(), cleanToolArgs(data), now()); } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      console.error('record_checkin failed:', e.message);
      return { ok: false, instruction: 'The system is not available right now. Thank the caller, do not ' +
        'promise anything, and say Saathi will call back.' };
    }
  }, requireBolnaToken));

  app.post('/tools/report-problem', wrap(async (req) => {
    const data = jsonObject(req);
    try { return await cases.reportProblem(S(), cleanToolArgs(data), now()); } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      console.error('report_problem failed:', e.message);
      return { ok: false, instruction: 'The system is not available right now. If they are in danger, tell them ' +
        'to call the Indian Embassy. Say Saathi will call back.' };
    }
  }, requireBolnaToken));

  // --- Bolna webhook ----------------------------------------------------------------

  /** Bolna posts here several times per call. Saves the call; once it has ended, counts a miss or a
   * contact, raises alerts and books the next call. */
  app.post('/webhooks/bolna', wrap(async (req) => {
    const payload = jsonObject(req);
    if ((process.env.GS_LOG_WEBHOOK ?? '1') !== '0') { // contains phone numbers and transcripts
      console.warn('BOLNA_WEBHOOK_RAW', JSON.stringify(payload).slice(0, 20000));
    }
    try { return await cases.processCallRecord(S(), payload, now()); } catch (e) {
      if (!(e instanceof StoreError)) throw e;
      console.error('webhook not saved:', e.message);
      throw new HttpError(503, 'storage unavailable'); // lets Bolna retry
    }
  }, requireBolnaToken));

  // --- dashboard ----------------------------------------------------------------------

  app.get('/dashboard', wrap(async (req) => {
    const workers = await S().select('workers', null, { order: 'updated_at' });
    const totals = cases.summaryCounts(workers, await cases.briefedWorkerIds(S()));
    const open = await S().select('escalations', { status: 'open' });
    const clocks: Record<string, Row> = {};
    for (const w of workers) clocks[w.id] = cases.caseClock(w, open, now())!;
    return dashboard.renderList(workers, status(), totals, Array.from(q(req, 'q')).slice(0, 100).join(''), clocks,
      Array.from(q(req, 'district')).slice(0, 60).join(''), cases.outcomeTotals(workers), goLiveChecks());
  }, team));

  app.get('/dashboard/intake', wrap(() => dashboard.renderIntake(), team));

  /** A caseworker enters a family whose worker is already in trouble abroad. No call is placed. */
  app.post('/api/intake', wrap(async (req) => {
    const data = jsonObject(req);
    try { return await cases.intakeFamily(S(), data, now()); } catch (e) { return caseError(e); }
  }, team));

  app.get('/dashboard/agents', wrap(async () => {
    const workers = await S().select('workers', null, { order: 'updated_at' });
    const reported = signals.reportedContacts(await S().select('contact_reports'), workers);
    return dashboard.renderAgents(cases.agentStats(workers), signals.repeatedSignals(workers), reported);
  }, team));

  app.get('/dashboard/new', wrap(() => dashboard.renderNew(), team));

  app.get('/dashboard/case/:caseId', wrap(async (req) => {
    const [w, isPublic] = await viewable(req.params.caseId as string, req);
    let workers = await S().select('workers', null, { order: 'updated_at' });
    if (isPublic) workers = workers.filter((x) => truthy(x.is_demo)); // links to other demo cases only
    const sig = signals.signalsForCase(w, workers);
    const clock = cases.caseClock(w, await S().select('escalations', { worker_id: w.id, status: 'open' }), now());
    return dashboard.renderCase(w, await cases.timeline(S(), w), status(), sig, await cases.embassyAlert(S(), w, now()), clock, isPublic);
  }));

  app.get('/dashboard/case/:caseId/edit', wrap(async (req) => {
    const w = await workerOr404(req.params.caseId as string);
    return dashboard.renderForm(w, w.case_id);
  }, team));

  app.get('/dashboard/case/:caseId/packet.txt', wrap(async (req, res) => {
    const [w] = await viewable(req.params.caseId as string, req);
    res.status(200).type('text/plain; charset=utf-8')
      .set('Content-Disposition', `attachment; filename="${w.case_id}-case-packet.txt"`)
      .send(await cases.casePacket(S(), w, now()));
  }));

  app.get('/dashboard/case/:caseId/petition', wrap(async (req) => {
    const [w, isPublic] = await viewable(req.params.caseId as string, req);
    return dashboard.renderPetition(w, await cases.prajavaniPetition(S(), w, now()), isPublic);
  }));

  app.post('/api/cases/:caseId/petition', wrap(async (req) => {
    const data = jsonObject(req);
    const w = await cases.updatePetition(S(), await workerOr404(req.params.caseId as string), pyStr(data.status || ''),
      pyStr(data.ref || ''), now()).catch(caseError);
    return { ok: true, petition_status: w.petition_status };
  }, team));

  app.post('/api/cases/:caseId/outcome', wrap(async (req) => {
    const data = jsonObject(req);
    const w = await cases.updateOutcome(S(), await workerOr404(req.params.caseId as string), data, now()).catch(caseError);
    return { ok: true, outcome: w.outcome ?? null };
  }, team));

  app.get('/dashboard/case/:caseId/proof-of-work', wrap(async (req) => {
    const [w, isPublic] = await viewable(req.params.caseId as string, req);
    return dashboard.renderProofOfWork(w, await cases.proofOfWork(S(), w, now()), isPublic);
  }));

  app.get('/dashboard/case/:caseId/death', wrap(async (req) => {
    const [w, isPublic] = await viewable(req.params.caseId as string, req);
    if (!truthy(w.death_reported_at)) throw new HttpError(404, 'no death reported for this case');
    return dashboard.renderDeathPacket(w, cases.deathPacket(S(), w, now()), isPublic);
  }));

  /** A caseworker records a death they heard about from the employer, embassy or a volunteer. */
  app.post('/api/cases/:caseId/death', wrap(async (req) => {
    const worker = await workerOr404(req.params.caseId as string);
    const w = await cases.reportDeath(S(), worker, jsonObject(req), now());
    await cases.markAction(S(), w, now());
    return { ok: true, case_id: w.case_id };
  }, team));

  app.post('/api/cases/:caseId/death-status', wrap(async (req) => {
    const data = jsonObject(req);
    const w = await cases.updateDeathStatus(S(), await workerOr404(req.params.caseId as string), pyStr(data.remains || ''),
      pyStr(data.ex_gratia || ''), now()).catch(caseError);
    return { ok: true, remains_status: w.remains_status, ex_gratia_status: w.ex_gratia_status };
  }, team));

  app.post('/api/cases/:caseId/death-clear', wrap(async (req) => {
    await cases.clearDeath(S(), await workerOr404(req.params.caseId as string), now());
    return { ok: true };
  }, team));

  app.get('/dashboard/alerts', wrap(async () => {
    const workers = await S().select('workers', null, { order: 'updated_at' });
    const history = await S().select('scam_alerts', null, { order: 'created_at' });
    return dashboard.renderAlerts(alerts.recipients(workers), alerts.TEMPLATES,
      alerts.suggestions(await S().select('contact_reports'), now()), history, status());
  }, team));

  app.post('/api/alerts', wrap(async (req) => {
    const data = jsonObject(req);
    const row = await alerts.sendAlert(S(), await S().select('workers'), pyStr(data.message || ''),
      pyStr(data.channel || 'voice'), now()).catch(caseError);
    return { ok: true, recipients: row.recipients ?? null, sent: row.sent ?? null, prepared: row.prepared ?? null, failed: row.failed ?? null };
  }, team));

  app.post('/api/workers', wrap(async (req) => {
    const data = jsonObject(req);
    const out = await cases.registerWorker(S(), licensed, data, now()).catch(caseError);
    return { case_id: out.worker.case_id, arrival_call: out.arrival_call };
  }, team));

  app.post('/api/cases/:caseId', wrap(async (req) => {
    const data = jsonObject(req);
    const w = await cases.updateWorker(S(), licensed, await workerOr404(req.params.caseId as string), data, now()).catch(caseError);
    return { case_id: w.case_id };
  }, team));

  app.post('/api/cases/:caseId/book-arrival', wrap(async (req) => {
    const res = await cases.bookArrivalCall(S(), await workerOr404(req.params.caseId as string), now()).catch(caseError);
    if (!res.ok) throw new HttpError(502, res.error);
    return res;
  }, team));

  app.post('/api/cases/:caseId/call', wrap(async (req) => {
    const raw: Buffer = req.body instanceof Buffer ? req.body : Buffer.alloc(0);
    const body = raw.length ? jsonObject(req) : {};
    const kind = Object.hasOwn(body, 'kind') ? body.kind : 'weekly';
    if (!cases.CALL_KINDS.includes(kind)) throw new HttpError(400, `kind must be one of ${pyTupleRepr(cases.CALL_KINDS)}`);
    const w = await workerOr404(req.params.caseId as string);
    const res = await cases.scheduleCall(S(), w, kind, null, now());
    if (!res.ok) throw new HttpError(502, res.error);
    await cases.markAction(S(), w, now());
    return res;
  }, team));

  app.post('/api/escalations/:id/resolve', wrap(async (req) => {
    if (!(await cases.resolveEscalation(S(), req.params.id as string, now()))) throw new HttpError(404, 'alert not found');
    return { ok: true };
  }, team));

  // Images, audio and video: served by Vercel from public/ on the old deployment; here by the server.
  app.use(express.static(findDir('public'), { index: false, maxAge: '1d' }));

  app.use((_req: Request, res: Response) => { res.status(404).json({ detail: 'Not Found' }); });

  // Errors, answered the way FastAPI does.
  app.use((err: unknown, req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof LoginNeeded) {
      if (err.off) return res.status(503).json({ detail: 'Dashboard is off: set GS_DASHBOARD_PASSWORD in Vercel and redeploy.' });
      // A login form, not the browser's password pop-up or raw JSON.
      if (wantsHtml(req)) return html(res, site.renderLogin(safeNext(req.path)), 401);
      return res.status(401).json({ detail: 'Team login needed' });
    }
    if (err instanceof HttpError) return res.status(err.status).json({ detail: err.detail });
    console.error(err);
    return res.status(500).type('text/plain; charset=utf-8').send('Internal Server Error');
  });
  return app;
}

/** Start the app on a free port, for tests. */
export async function listenForTests(): Promise<{ base: string; close: () => Promise<void> }> {
  const server = createApp().listen(0);
  await new Promise((r) => server.once('listening', r));
  const { port } = server.address() as AddressInfo;
  return { base: `http://127.0.0.1:${port}`, close: () => new Promise((r) => server.close(() => r())) };
}
