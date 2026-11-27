// Server-rendered dashboard pages. Port of gulf_saathi/dashboard.py. Plain HTML, no build step.
//
// Every value from the database goes through esc(), since names, transcripts and notes come from
// callers. Fixed labels and lists come from tables/pages.json, exported from the Python module.
import { codePhraseOk, fmtIst, parseTs, promiseSaid, reasonText, strftimeIst } from '../cases.js';
import { fmtRupees } from '../fees.js';
import { predepartureChecks, promiseRows, STOP_FLAGS } from '../promise.js';
import { esc, orStr, pyInt, pySorted, pyStr, pyTitle, squash, truthy } from '../py.js';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PAGES } from './text.js';

const D = PAGES.dashboard;

// The dashboard stylesheet (built from src/styles/dashboard.css with shadcn/ui classes). Its hash in the
// link makes browsers and the CDN fetch the new file after a change.
const HERE = dirname(fileURLToPath(import.meta.url));
export const CSS_PATH = join(HERE, '..', 'styles', 'dashboard.built.css');
const CSS_VERSION = existsSync(CSS_PATH) ? createHash('sha1').update(readFileSync(CSS_PATH)).digest('hex').slice(0, 10) : 'dev';
type Row = Record<string, any>;
const BADGE: Record<string, string> = D.BADGE;
const OUTCOME_LABELS: Record<string, string> = D.OUTCOME_LABELS;
const OUTCOMES: string[] = D.OUTCOMES;
const OUTCOME_PROBLEMS: string[] = D.OUTCOME_PROBLEMS;
const blank = (v: unknown) => v === null || v === undefined || v === '';
const joinIf = (xs: unknown[], sep: string) => xs.filter(truthy).map(pyStr).join(sep);
const label = (k: string) => (Object.hasOwn(OUTCOME_LABELS, k) ? OUTCOME_LABELS[k] : k);

/** Python's urllib.parse.quote(s): like encodeURIComponent, but "/" stays and !'()* are escaped. */
export function pyQuote(s: string): string {
  return encodeURIComponent(s).replace(/[!'()*]/g, (c) => '%' + c.charCodeAt(0).toString(16).toUpperCase()).replace(/%2F/g, '/');
}

export function badge(level: unknown): string {
  const l = truthy(level) ? String(level) : 'ok';
  return `<span class="badge" style="background:${Object.hasOwn(BADGE, l) ? BADGE[l] : '#475467'}">${esc(l.toUpperCase())}</span>`;
}

/** public: a demo case shown without the team login (other nav, a note on top). */
const ICON: Record<string, string> = {
  cases: '<path d="M4 4h16v16H4z"/><path d="M4 9h16"/><path d="M9 9v11"/>',
  agents: '<circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-7 7-7s7 3 7 7"/><path d="M17 11h5M19.5 8.5v5"/>',
  alerts: '<path d="M3 11l15-6v14L3 13z"/><path d="M7 13v5h3"/>',
  demo: '<path d="M8 5l11 7-11 7z"/>',
  intake: '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  add: '<path d="M12 5v14M5 12h14"/>',
  out: '<path d="M15 4h4v16h-4"/><path d="M10 8l-4 4 4 4"/><path d="M6 12h10"/>',
};
const svg = (name: string, cls = 'size-4') =>
  `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name]}</svg>`;

const TEAM_LINKS: Array<[string, string, string, string]> = [
  ['/dashboard', 'cases', 'Cases', ''], ['/dashboard/agents', 'agents', 'Agents', ''],
  ['/dashboard/alerts', 'alerts', 'Weekly alerts', ''], ['/demo', 'demo', 'Demo story', ''],
];
const TEAM_ACTIONS: Array<[string, string, string, string]> = [
  ['/dashboard/intake', 'intake', 'Family in trouble', 'outline'], ['/dashboard/new', 'add', 'Register worker', 'primary'],
  ['/logout', 'out', 'Log out', ''],
];

/** The page frame: a slim icon rail (shadcn sidebar-07) and the content panel (SidebarInset).
 * public: a demo case shown without the team login (no team links, a note on top). */
export function page(title: string, body: string, refresh: number | null = null, isPublic = false, flush = false): string {
  const meta = refresh ? `<meta http-equiv="refresh" content="${refresh}">` : '';
  if (isPublic) body = D.PUBLIC_NOTE + body;
  const railLink = ([href, icon, text, kind]: [string, string, string, string]) =>
    `<a class="rail-btn${kind ? ' ' + kind : ''}" href="${href}" title="${text}" aria-label="${text}">${svg(icon)}</a>`;
  const rail = isPublic
    ? `<a class="rail-btn" href="/demo" title="Demo story" aria-label="Demo story">${svg('demo')}</a>`
    : TEAM_LINKS.map(railLink).join('');
  const railEnd = isPublic ? '' : TEAM_ACTIONS.map(railLink).join('');
  const mobile = isPublic ? D.PUBLIC_NAV
    : [...TEAM_LINKS, ...TEAM_ACTIONS].map(([href, , text]) => `<a href="${href}">${text}</a>`).join('');
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
${meta}<title>${esc(title)} · Gulf Saathi</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Telugu:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/dashboard.css?v=${CSS_VERSION}"></head><body>
<div class="shell">
<aside class="rail"><a class="rail-brand" href="/" title="Gulf Saathi home">GS</a><nav class="rail-nav">${rail}</nav><nav class="rail-nav mt-auto">${railEnd}</nav></aside>
<div class="inset"><header class="mobile-bar"><a class="font-semibold" href="/">Gulf Saathi</a><span class="mobile-nav">${mobile}</span></header>
<main class="${flush ? 'flush' : ''}">${body}</main></div></div>
<script>
async function post(url, body, btn, okText) {
  if (btn) btn.disabled = true;
  const msg = document.getElementById('msg');
  try {
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.status);
    if (msg) msg.textContent = okText || 'Done';
    return j;
  } catch (e) { if (msg) msg.textContent = 'Failed: ' + e.message; if (btn) btn.disabled = false; }
}
document.querySelectorAll('.rail-btn').forEach(a => { if (a.getAttribute('href') === location.pathname) a.setAttribute('aria-current', 'page'); });
</script></body></html>`;
}

/** Problems found at registration, before the worker flies. */
export const predepartureFlags = (w: Row): string[] => predepartureChecks(w).map((f) => f.text);

/** Risk badge. A worker still in India with no risk yet but with red flags shows RED FLAGS, not a green
 * OK next to a "do not travel" warning. */
export function caseBadge(w: Row): string {
  if ((w.risk_level || 'ok') === 'ok' && w.status === 'registered' && predepartureChecks(w).length) {
    return '<span class="badge" style="background:#b42318">RED FLAGS</span>';
  }
  return badge(w.risk_level);
}

/** At most two red flags in the case list; the case page shows them all. */
const flagList = (fs: string[]) => fs.slice(0, 2).map((f) => `<div class="flag">${esc(f)}</div>`).join('') +
  (fs.length > 2 ? `<div class="more">+${fs.length - 2} more on the case page</div>` : '');

export const demoTag = (w: Row) => (truthy(w.is_demo) ? ' <span class="demo">DEMO</span>' : '');

/** The same phone number, payment account or sponsor in several cases. A reason to look, never a finding. */
export function signalsTable(signals: Row[], intro = true): string {
  if (!signals.length) return "<p class='muted'>No phone number, payment account or sponsor appears in more than one case.</p>";
  const rows: string[] = [];
  for (const g of signals) {
    const cases = (g.cases as string[]).map((c) => `<a class="nowrap" href="/dashboard/case/${esc(c)}">${esc(c)}</a>`).join(' ');
    const weak = (Object.hasOwn(g, 'strong') ? g.strong : true) ? '' : ' <span class="muted" style="font-size:12px">(weak: company names can repeat)</span>';
    const where = truthy(g.districts) ? `<div class="muted" style="font-size:12px">Agent districts: ${esc(g.districts.join(', '))}</div>` : '';
    rows.push(`<tr><td>${esc(g.label)}${weak}${truthy(g.demo) ? ' <span class="demo">DEMO DATA</span>' : ''}</td>
<td><b>${esc(g.value)}</b></td><td>Seen in ${g.cases.length} cases<div class="muted" style="font-size:12px">${cases}</div>${where}</td>
<td>${truthy(g.at_risk) ? esc(g.at_risk) : '<span class="muted">0</span>'}</td>
<td>${truthy(g.flagged) ? esc(g.flagged) : '<span class="muted">0</span>'}</td></tr>`);
  }
  const note = intro ? "<p class='muted'>Seen in more than one case: needs a person to review. This is not a finding of fraud against anyone. Names are not matched, only phone numbers, payment accounts and sponsor IDs.</p>" : '';
  return note + `<div class="wrap"><table><thead><tr><th>What</th><th>Value</th><th>Cases</th><th>At risk now</th>
<th>Pre-departure red flags</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

export function promiseTable(w: Row, latestAnswers: Row): string {
  const word: Record<string, string> = { conflict: 'Does not match', match: 'Matches', unknown: 'Not enough to compare' };
  const cell = (v: unknown) => (blank(v) ? "<span class='muted'>—</span>" : esc(v));
  const out = promiseRows(w, latestAnswers).map((r) => `<tr><td class='muted'>${esc(r.what)}</td><td>${cell(r.promised)}</td><td>${cell(r.papers)}</td><td>${cell(r.now)}</td><td class='v-${r.verdict}'>${word[r.verdict]}</td></tr>`);
  return "<div class='wrap'><table><thead><tr><th></th><th>Agent promised</th><th>Visa papers say</th><th>Worker says now</th><th>Check</th></tr></thead><tbody>" +
    out.join('') + "</tbody></table></div><p class='muted' style='font-size:13px'>\"Visa papers\" is what a helper typed from the visa. \"Now\" is from the latest arrival, weekly or help call. Fixed word lists decide the match; the AI only writes down what was said.</p>";
}

export function tiles(totals: Row): string {
  const items: Array<[string, string, boolean]> = [['registered', 'Workers registered', false], ['in_india', 'Still in India', false],
    ['abroad', 'Abroad', false], ['briefed', 'Pre-departure briefing done', false],
    ['at_risk', 'At risk now (HIGH or CRITICAL)', true], ['red_flags', 'Pre-departure red flags', true]];
  return '<div class="tiles">' + items.map(([k, lab, warn]) =>
    `<div class="tile${warn && truthy(totals[k]) ? ' warn' : ''}"><b>${esc(Object.hasOwn(totals, k) ? totals[k] : 0)}</b><span>${esc(lab)}</span></div>`).join('') + '</div>';
}

function options(values: string[], current: unknown, blankText = ''): string {
  const first = blankText ? `<option value="">${esc(blankText)}</option>` : '';
  return first + values.map((v) => `<option value="${esc(v)}"${v === current ? ' selected' : ''}>${esc(label(v))}</option>`).join('');
}

/** How cases ended. Numbers are what caseworkers recorded; demo cases are left out. */
export function outcomeTiles(t: Row | null | undefined): string {
  if (!truthy(t) || !truthy(t!.closed)) return '';
  const days = t!.median_days === null || t!.median_days === undefined ? '—' : t!.median_days;
  const items: Array<[unknown, string]> = [[t!.closed, 'Cases with an outcome'], [t!.solved, 'Solved or partly solved'],
    ['₹' + fmtRupees(t!.recovered), 'Money recovered (recorded by caseworkers)'], [days, 'Median days to an outcome']];
  return '<div class="tiles">' + items.map(([n, lab]) => `<div class="tile"><b>${esc(n)}</b><span>${esc(lab)}</span></div>`).join('') + '</div>';
}

/** Team only: is everything the pilot needs switched on? */
export function goLiveCard(checks: Array<[string, string, string]> | null | undefined): string {
  if (!checks || !checks.length) return '';
  const auto = checks.filter((c) => c[1] !== 'hand');
  const ready = auto.filter((c) => c[1] === 'ok').length;
  const mark: Record<string, string> = { ok: '<b style="color:#067647">ON</b>', off: '<b style="color:#b42318">OFF</b>', hand: '<b style="color:#93370d">CHECK BY HAND</b>' };
  const rows = checks.map(([lab, state, fix]) => `<tr><td>${esc(lab)}</td><td class="nowrap">${mark[state]}</td><td class="muted">${esc(fix)}</td></tr>`).join('');
  return `<details class="card"><summary><b>Pilot go-live check: ${ready} of ${auto.length} switched on</b></summary><div class="wrap"><table><tbody>${rows}</tbody></table></div></details>`;
}

/** Short form for a family whose worker is already in trouble abroad. */
export function renderIntake(): string {
  return page('Family in trouble', `<h1>Family in trouble</h1>
<p class="muted">For a family whose worker is already abroad and has a problem. Saathi opens the case and applies its usual rules.
No call is placed. Read the consent line to the family first.</p>
<form onsubmit="return false" class="card" id="intake">
<fieldset><legend>Consent</legend>
<p class="sms info" lang="te">"మీ వివరాలు, మీ కుటుంబ సభ్యుడి వివరాలు గల్ఫ్ సాథి కేసులో ఉంచుతాం. సహాయం చేసే అధికారులకు మాత్రమే చూపిస్తాం. మీరు ఎప్పుడైనా ఆపమని చెప్పవచ్చు. సరేనా?"</p>
<p class="muted">"We will keep your details and your family member's details in a Gulf Saathi case. We show them only to the officials who help. You can ask us to stop at any time. Is that okay?"</p>
<label>Did the family agree? *<select id="consent"><option value="">Choose</option><option value="yes">Yes</option><option value="no">No</option></select></label>
</fieldset>
<fieldset><legend>Family</legend>
<label>Family member's name<input id="family_name"></label>
<label>Family phone *<input id="family_phone" inputmode="tel" placeholder="98765 43210"></label>
<label>Relation to the worker<input id="family_relation" placeholder="wife, mother, brother"></label>
<label>Home village / district<input id="home_district" placeholder="Jagtial"></label>
</fieldset>
<fieldset><legend>Worker abroad</legend>
<label>Worker's name<input id="worker_name"></label>
<label>Worker's phone abroad (if the family has it)<input id="worker_phone" inputmode="tel" placeholder="+966 5x xxx xxxx"></label>
<label>Country<input id="dest_country" placeholder="Saudi Arabia"></label>
<label>City<input id="dest_city" placeholder="Riyadh"></label>
<label>Employer or sponsor (if known)<input id="employer_name"></label>
<label>Agent who sent them (if known)<input id="agent_name"></label>
</fieldset>
<fieldset><legend>Problem</legend>
<label>Main problem *<select id="problem">${options(OUTCOME_PROBLEMS, '', 'Choose')}</select></label>
<label>Months of salary not paid<input id="months_unpaid" inputmode="numeric" placeholder="3"></label>
<label>Is the passport with the worker?<select id="passport_with_worker"><option value="">Not known</option><option value="yes">Yes</option><option value="no">No</option></select></label>
<label>Is the worker being threatened or hurt now?<select id="threatened"><option value="">Not known</option><option value="yes">Yes</option><option value="no">No</option></select></label>
<label>What the family said<textarea id="notes" rows="3"></textarea></label>
</fieldset>
<button class="btn" id="save">Open the case</button><div id="msg"></div></form>
<script>
document.getElementById('save').addEventListener('click', async (e) => {
  const body = {};
  document.querySelectorAll('#intake input, #intake select, #intake textarea').forEach(el => body[el.id] = el.value);
  const j = await post('/api/intake', body, e.target, 'Case opened');
  if (j && j.case_id) location.href = '/dashboard/case/' + j.case_id;
});
</script>`);
}

/** Find a case by name, phone digits, case number, employer, sponsor, place or notes. For the embassy or
 * a volunteer asking "whose family is this?". */
export function searchWorkers(workers: Row[], query: string): Row[] {
  const q = squash((query || '').toLowerCase());
  if (!q) return workers;
  const digits = Array.from(q).filter((ch) => /\p{Nd}/u.test(ch)).join('');
  const keys = ['case_id', 'worker_name', 'worker_name_te', 'employer_name', 'sponsor_name', 'sponsor_id', 'dest_city',
    'dest_country', 'agent_name', 'family_name', 'notes'];
  const words = q.split(' ');
  return workers.filter((w) => {
    const text = keys.map((k) => orStr(w[k])).join(' ').toLowerCase();
    const phones = ['worker_phone', 'family_phone', 'employer_phone'].map((k) => orStr(w[k])).join('');
    return words.every((word) => text.includes(word)) || (Array.from(digits).length >= 6 && phones.includes(digits));
  });
}

/** 'Alert open 12 days · last action 9 days ago', red when nobody has acted for a week. */
export function clockBadge(clock: Row | null | undefined): string {
  if (!truthy(clock)) return '';
  const c = clock!;
  const last = c.last_action_days === null || c.last_action_days === undefined ? 'no caseworker action yet' : `last action ${c.last_action_days} days ago`;
  const style = c.overdue ? 'background:#b42318;color:#fff' : 'background:#f2f4f7;color:#344054';
  return `<div class="clock" style="${style};display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;margin-top:4px">${c.overdue ? 'OVERDUE · ' : ''}Alert open ${c.open_days} days · ${esc(last)}</div>`;
}

/** One short line: the first risk reason, else the first red flag. */
function problemLine(w: Row): string {
  const rs = (truthy(w.risk_reasons) ? w.risk_reasons : []) as Row[];
  if (rs.length) return reasonText(rs[0]) + (rs.length > 1 ? ` (+${rs.length - 1} more)` : '');
  const fs = predepartureFlags(w);
  return fs.length ? fs[0] + (fs.length > 1 ? ` (+${fs.length - 1} more)` : '') : '';
}

const RISK_DOT: Record<string, string> = { critical: 'bg-red-600', high: 'bg-orange-500', medium: 'bg-amber-500', ok: 'bg-green-600' };

/** "● Critical", or "● Red flags" for a worker still in India with red flags and no risk yet. */
function riskCell(w: Row): string {
  const level = truthy(w.risk_level) ? String(w.risk_level) : 'ok';
  if (level === 'ok' && w.status === 'registered' && predepartureChecks(w).length) {
    return '<span class="inline-flex items-center gap-1.5 whitespace-nowrap"><span class="size-2 rounded-full bg-red-600"></span>Red flags</span>';
  }
  return `<span class="inline-flex items-center gap-1.5 whitespace-nowrap"><span class="size-2 rounded-full ${RISK_DOT[level] ?? 'bg-zinc-400'}"></span>${esc(pyTitle(level))}</span>`;
}

const STATUS_TEXT: Record<string, string> = { registered: 'In India', abroad: 'Abroad', death_reported: 'Death reported' };

/** A small summary card (shadcn dashboard-01 SectionCards). */
const statCard = (label: string, value: unknown, foot: string, warn = false) =>
  `<div class="stat"><div class="stat-label">${esc(label)}</div><div class="stat-value${warn ? ' text-destructive' : ''}">${esc(value)}</div><div class="stat-foot">${foot}</div></div>`;

export function renderList(workersAll: Row[], status: Row, totals: Row | null = null, q = '', clocks: Record<string, Row> = {},
  district = '', outcomes: Row | null = null, live: Array<[string, string, string]> | null = null, risk = '', statusFilter = ''): string {
  const districts = pySorted(new Set(workersAll.filter((w) => truthy(w.home_district)).map((w) => pyTitle(squash(String(w.home_district))))));
  let shown = searchWorkers(workersAll, q);
  if (district) shown = shown.filter((w) => pyTitle(squash(orStr(w.home_district))) === district);
  if (risk === 'red_flags') shown = shown.filter((w) => w.status === 'registered' && predepartureChecks(w).length);
  else if (risk === 'at_risk') shown = shown.filter((w) => w.risk_level === 'high' || w.risk_level === 'critical');
  else if (risk === 'overdue') shown = shown.filter((w) => (clocks[w.id] ?? {}).overdue);
  else if (risk) shown = shown.filter((w) => (w.risk_level || 'ok') === risk);
  if (statusFilter) shown = shown.filter((w) => w.status === statusFilter);
  const opt = (value: string, text: string, current: string) => `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(text)}</option>`;
  const toolbar = `<form method="get" action="/dashboard" class="toolbar">
<input name="q" value="${esc(q)}" placeholder="Filter cases: name, phone, employer, sponsor, city" class="toolbar-search">
<select name="risk" class="toolbar-select">${opt('', 'Risk: all', risk)}${opt('at_risk', 'At risk (high, critical)', risk)}${opt('overdue', 'Overdue alerts', risk)}${opt('red_flags', 'Red flags, in India', risk)}${opt('critical', 'Critical', risk)}${opt('high', 'High', risk)}${opt('medium', 'Medium', risk)}${opt('ok', 'OK', risk)}</select>
<select name="status" class="toolbar-select">${opt('', 'Status: all', statusFilter)}${opt('registered', 'In India', statusFilter)}${opt('abroad', 'Abroad', statusFilter)}${opt('death_reported', 'Death reported', statusFilter)}</select>
<select name="district" class="toolbar-select"><option value="">All home districts</option>${districts.map((d) => opt(d, d, district)).join('')}</select>
<button class="btn" type="submit">Filter</button>${q || district || risk || statusFilter ? '<a class="text-sm text-muted-foreground" href="/dashboard">Reset ✕</a>' : ''}
</form>`;
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, ok: 3 };
  // Most serious first; overdue cases first within a level; then most recently updated.
  const byRecent = pySorted(shown, (w) => w.updated_at || '', true);
  const rows = pySorted(byRecent, (w) => [Object.hasOwn(order, w.risk_level) ? order[w.risk_level] : 3, !(clocks[w.id] ?? {}).overdue]).map((w) => {
    const city = truthy(w.dest_city) ? w.dest_city : w.dest_country;
    const problem = problemLine(w);
    return `<tr class="cursor-pointer" onclick="if(!event.target.closest('a'))location.href='/dashboard/case/${esc(w.case_id)}'">
<td class="whitespace-nowrap"><a href="/dashboard/case/${esc(w.case_id)}"><b>${esc(w.case_id)}</b></a></td>
<td class="whitespace-nowrap">${truthy(city) ? `<span class="tag mr-1.5">${esc(city)}</span>` : ''}${esc(w.worker_name)}${demoTag(w)}</td>
<td class="max-w-[22rem]"><div class="truncate" title="${esc(problem)}">${problem ? esc(problem) : '<span class="muted">—</span>'}</div></td>
<td>${riskCell(w)}</td>
<td class="whitespace-nowrap">${esc(Object.hasOwn(STATUS_TEXT, w.status) ? STATUS_TEXT[w.status] : w.status)}</td>
<td>${clockBadge(clocks[w.id] ?? null) || '<span class="muted">—</span>'}</td>
<td class="whitespace-nowrap text-muted-foreground">${esc(fmtIst(w.last_contact_at))}</td></tr>`;
  });
  const empty = q ? `<p class='muted p-4'>No case matches "${esc(q)}".</p>` : "<p class='muted p-4'>No workers yet. <a href='/dashboard/new'>Register the first one</a>.</p>";
  const table = !rows.length ? empty : `<div class="wrap"><table><thead><tr><th>Case</th><th>Worker</th><th>Problem</th><th>Risk</th><th>Status</th><th>Alert open</th><th>Last contact</th></tr></thead>
<tbody>${rows.join('')}</tbody></table></div>`;
  let cards = '';
  if (truthy(totals)) {
    const t = totals!;
    const overdue = workersAll.filter((w) => (clocks[w.id] ?? {}).overdue).length;
    const fourth = truthy(outcomes) && truthy(outcomes!.closed)
      ? statCard('Money recovered (recorded by caseworkers)', '₹' + fmtRupees(outcomes!.recovered), `${esc(outcomes!.solved)} of ${esc(outcomes!.closed)} closed cases solved`)
      : statCard('Pre-departure briefing done', t.briefed ?? 0, 'calls before the worker flies');
    cards = `<div class="stats">${statCard('At risk now (HIGH or CRITICAL)', t.at_risk ?? 0, `${overdue} overdue: 7+ days with no caseworker action`, truthy(t.at_risk))}
${statCard('Workers registered', t.registered ?? 0, `${esc(t.abroad ?? 0)} abroad · ${esc(t.in_india ?? 0)} still in India`)}
${statCard('Pre-departure red flags', t.red_flags ?? 0, 'in India: told not to pay or travel until sorted', truthy(t.red_flags))}
${fourth}</div>`;
  }
  return page('Cases', `<div class="page-head"><div><h1>Cases</h1><p class="muted m-0">Most serious first. For the embassy or a volunteer asking whose family a worker is, search by name or phone.</p></div>
<div class="flex flex-wrap gap-2"><a class="btn secondary" href="/dashboard/intake">+ Family in trouble</a><a class="btn" href="/dashboard/new">+ Register worker</a></div></div>
${cards}${toolbar}
<div class="table-card">${table}</div>
<div class="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span>${rows.length} of ${workersAll.length} case(s)</span><span>${statusLine(status)} · refreshes every 15 seconds</span></div>
${goLiveCard(live)}
<script>
setInterval(() => { if (!document.querySelector('input:focus, select:focus, details[open]')) location.reload(); }, 15000);
</script>`);
}

export function reportedTable(rows: Row[]): string {
  if (!rows.length) return "<p class='muted'>No agent numbers reported on calls yet.</p>";
  const out: string[] = [];
  for (const g of rows) {
    const amt = truthy(g.max_amount) ? `Rs ${fmtRupees(pyInt(g.max_amount))}` : '—';
    out.push(`<tr><td>${esc(g.kind)}</td><td><b>${esc(g.value)}</b></td>
<td>${esc(g.callers)} caller(s)${truthy(g.family_reports) ? `<div class="muted" style="font-size:12px">${esc(g.family_reports)} from families</div>` : ''}</td>
<td>${esc(g.districts.join(', ')) || '<span class="muted">—</span>'}</td>
<td>${esc(g.over_limit) || '<span class="muted">0</span>'}<div class="muted" style="font-size:12px">highest asked: ${esc(amt)}</div></td>
<td>${esc(g.visit_visa) || '<span class="muted">0</span>'}</td>
<td>${esc(g.cases)} case(s)${truthy(g.at_risk) ? ` · <span class="flag">${esc(g.at_risk)} at risk</span>` : ''}</td>
<td class="nowrap">${esc(g.first_seen)} → ${esc(g.last_seen)}</td></tr>`);
  }
  return `<div class="wrap"><table><thead><tr><th>What</th><th>Value</th><th>Reported by</th><th>Caller districts</th>
<th>Asked over limit</th><th>Visit visa offered</th><th>Linked cases</th><th>Seen</th></tr></thead><tbody>${out.join('')}</tbody></table></div>`;
}

export function renderAgents(stats: Row[], signals: Row[] | null = null, reported: Row[] | null = null): string {
  const rows: string[] = [];
  for (const g of stats) {
    const listed = g.licensed ? '<span class="muted">in licensed list</span>'
      : truthy(g.not_in_list) ? '<span class="flag">not found in licensed list</span>' : '<span class="muted">not confirmed</span>';
    const cases = (g.case_ids as string[]).map((c) => `<a class="nowrap" href="/dashboard/case/${esc(c)}">${esc(c)}</a>`).join(' ');
    const risk = (truthy(g.critical) ? `${badge('critical')} ${g.critical} ` : '') +
      (g.at_risk - g.critical ? `${badge('high')} ${g.at_risk - g.critical}` : '');
    rows.push(`<tr><td><b>${esc(g.agent)}</b><div>${listed}</div></td>
<td>${esc(g.cases)}<div class="muted" style="font-size:12px">${cases}</div></td>
<td>${risk || '<span class="muted">—</span>'}</td>
<td>${truthy(g.over_cap) ? esc(g.over_cap) : '<span class="muted">—</span>'}</td>
<td>${esc(g.districts.join(', ')) || '<span class="muted">—</span>'}</td>
<td>${g.employers.map(esc).join('<br>') || '<span class="muted">—</span>'}</td></tr>`);
  }
  const table = !rows.length ? "<p class='muted'>No agents recorded yet.</p>" : `<div class="wrap"><table><thead><tr><th>Agent</th><th>Workers</th><th>At risk now</th>
<th>Paid over limit</th><th>District</th><th>Employers abroad</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  return page('Agents', `<h1>Agents behind our cases</h1>
<p class="muted">Every recruiting agent named in a Saathi case, riskiest first: how many of their workers are in trouble now,
how many paid over the Rs 35,400 limit, and which employers abroad they sent people to. This describes our cases, not a
finding about any agent.</p>
<div class="card">${table}</div>
<h2>Saathi Intelligence: repeated across cases</h2>
<p class="muted">Exact matches on agent phones, payment accounts, sponsor IDs and employer phones (strong), and employer
name plus country (weak). A link is a lead for a trained investigator, not proof. Workers checking a number on a call hear
only a count, never names or case numbers, and never from demo data.</p>
<div class="card">${signalsTable(signals ?? [])}</div>
<h2>Agent numbers reported on calls</h2>
<p class="muted">Every agent phone or payment account a worker or family told Saathi, even if they never registered a case.
Counted once per caller. Who owns a number can only be found by the telecom company or the police: share these with the police
cyber cell or in an eMigrate complaint, never publicly.</p>
<div class="card">${reportedTable(reported ?? [])}</div>`);
}

export function statusLine(status: Row): string {
  return [`Storage: ${esc(status.storage)}`, `Bolna calls: ${truthy(status.bolna) ? 'on' : 'NOT configured'}`, `SMS: ${esc(status.sms)}`].join(' · ');
}

/** A stored value as the form field expects it. */
function formValue(name: string, values: Row): unknown {
  const v = values[name];
  if (blank(v)) return '';
  if (name === 'payments') return Array.isArray(v) ? v.map(pyStr).join('; ') : v;
  if (name === 'arrival_call_at') {
    const dt = parseTs(v);
    return dt ? strftimeIst(dt, '%Y-%m-%dT%H:%M') : '';
  }
  return v;
}

const SELECTS = ['visa_type', 'worker_gender', 'contract_before_payment', 'call_consent', 'alerts_opt_in', 'passport_type',
  'emigration_clearance', 'pbby'];

/** Registration form; with values and a case ID it edits that case instead. */
export function renderForm(values: Row | null = null, caseId: string | null = null): string {
  values = values ?? {};
  const sets: string[] = [];
  for (const [legend, fields] of D.FIELDS as Array<[string, Array<[string, string, string]>]>) {
    const inputs: string[] = [];
    for (const [name, lab, ph] of fields) {
      if (SELECTS.includes(name)) {
        const current = formValue(name, values);
        const choices: string[] = ({ visa_type: D.VISA_TYPES, worker_gender: D.GENDERS, passport_type: D.PASSPORT_TYPES } as Row)[name] ?? ['yes', 'no'];
        const opts = ['', ...choices].map((t) => `<option value="${t}"${current === t ? ' selected' : ''}>${t}</option>`).join('');
        inputs.push(`<div><label for="${name}">${esc(lab)}</label><select id="${name}" name="${name}">${opts}</select></div>`);
        continue;
      }
      const kind = name === 'departure_date' ? 'date' : name === 'arrival_call_at' ? 'datetime-local' : 'text';
      const hint = name === 'code_phrase' ? `<div class="muted" style="font-size:12px">${esc(D.CODE_PHRASE_HELP)}</div>` : '';
      inputs.push(`<div><label for="${name}">${esc(lab)}</label><input id="${name}" name="${name}" type="${kind}" value="${esc(formValue(name, values))}" placeholder="${esc(ph ? 'e.g. ' + ph : '')}">${hint}</div>`);
    }
    sets.push(`<fieldset><legend>${esc(legend)}</legend><div class="grid">${inputs.join('')}</div></fieldset>`);
  }
  let title: string, intro: string, url: string, button: string, done: string;
  if (caseId) {
    [title, intro, url, button, done] = [`Edit ${caseId}`, `Correct the details of case ${esc(caseId)}. The case number, timeline and alerts stay as they are.`,
      `/api/cases/${esc(caseId)}`, 'Save changes', 'Saved'];
  } else {
    [title, intro, url, button, done] = ['Register a worker before departure',
      'This is the evidence trail. If the worker goes missing, the family and embassy start from these names and numbers. If an arrival-day call time is set, Saathi books that call with Bolna.',
      '/api/workers', 'Register', 'Registered'];
  }
  return page(title, `<h1>${esc(title)}</h1>
<p class="muted">${intro}</p>
<form id="f" class="card" onsubmit="return false">${sets.join('')}
<label for="notes">Notes</label><textarea id="notes" name="notes" rows="3">${esc(values.notes)}</textarea>
<p><button class="btn" id="go" type="submit">${button}</button></p><div id="msg"></div></form>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  const data = Object.fromEntries(new FormData(e.target).entries());
  const j = await post('${url}', data, document.getElementById('go'), '${done}');
  if (j && j.case_id) location.href = '/dashboard/case/' + j.case_id;
});
</script>`);
}

export const renderNew = () => renderForm();

function answersTable(answers: Row): string {
  const rows: string[] = [];
  for (const [key, lab] of D.ANSWER_LABELS as string[][]) {
    let v = answers[key];
    if (blank(v)) continue;
    if (key === 'pickup_status') v = Object.hasOwn(D.PICKUP, v) ? D.PICKUP[v] : v;
    else if (typeof v === 'boolean') v = v ? 'Yes' : 'No';
    rows.push(`<tr><td class='muted'>${esc(lab)}</td><td><b>${esc(v)}</b></td></tr>`);
  }
  return rows.length ? `<table>${rows.join('')}</table>` : "<span class='muted'>No answers recorded</span>";
}

/** The case list on the left of the inbox (shadcn mail layout). The caller passes only cases this
 * viewer may see: demo cases on a public demo page. */
function inboxList(cases: Row[], current: string, clocks: Record<string, Row>): string {
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, ok: 3 };
  const sorted = pySorted(pySorted(cases, (x) => x.updated_at || '', true), (x) => [Object.hasOwn(order, x.risk_level) ? order[x.risk_level] : 3]);
  const atRisk = (x: Row) => x.risk_level === 'high' || x.risk_level === 'critical';
  const flagged = (x: Row) => x.status === 'registered' && predepartureChecks(x).length > 0;
  const items = sorted.map((x) => {
    const city = truthy(x.dest_city) ? x.dest_city : x.dest_country;
    const tags = [atRisk(x) ? 'risk' : '', flagged(x) ? 'flags' : '', (clocks[x.id] ?? {}).overdue ? 'overdue' : ''].filter(Boolean).join(' ');
    return `<a class="inbox-item${x.case_id === current ? ' active' : ''}" href="/dashboard/case/${esc(x.case_id)}" data-tags="${tags}" data-text="${esc(orStr(x.worker_name).toLowerCase() + ' ' + orStr(x.case_id).toLowerCase() + ' ' + orStr(x.worker_phone) + ' ' + orStr(city).toLowerCase())}">
<div class="flex items-center gap-2"><span class="font-semibold">${esc(x.worker_name)}</span>${demoTag(x)}<span class="ml-auto shrink-0 text-xs text-muted-foreground">${esc(fmtIst(x.updated_at).split(',')[0])}</span></div>
<div class="text-xs text-muted-foreground">${esc(x.case_id)}${truthy(city) ? ' · ' + esc(city) : ''}${x.status === 'registered' ? ' · in India' : ''}</div>
<div class="mt-1.5 line-clamp-2 text-sm text-muted-foreground">${esc(problemLine(x)) || 'No problem reported'}</div>
<div class="mt-2 flex flex-wrap gap-1">${caseBadge(x)}</div></a>`;
  }).join('');
  const n = (f: (x: Row) => unknown) => cases.filter(f).length;
  return `<section class="inbox-list"><div class="inbox-head"><span class="text-lg font-semibold">Cases</span></div>
<div class="flex flex-wrap gap-1 px-3 pt-3" id="chips"><button class="chip active" data-f="">All ${cases.length}</button><button class="chip" data-f="risk">At risk ${n(atRisk)}</button><button class="chip" data-f="flags">Red flags ${n(flagged)}</button><button class="chip" data-f="overdue">Overdue ${n((x) => (clocks[x.id] ?? {}).overdue)}</button></div>
<div class="p-3"><input id="inbox-q" placeholder="Search name, phone, case number"></div>
<div class="inbox-items" id="inbox-items">${items}</div></section>`;
}

const INBOX_SCRIPT = `<script>
(() => {
  let f = '', q = '';
  const apply = () => document.querySelectorAll('#inbox-items .inbox-item').forEach(a => {
    a.style.display = (!f || a.dataset.tags.split(' ').includes(f)) && (!q || a.dataset.text.includes(q)) ? '' : 'none';
  });
  document.querySelectorAll('#chips .chip').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('#chips .chip').forEach(x => x.classList.toggle('active', x === b)); f = b.dataset.f; apply();
  }));
  const s = document.getElementById('inbox-q'); if (s) s.addEventListener('input', () => { q = s.value.toLowerCase().trim(); apply(); });
  const tabs = [...document.querySelectorAll('[data-tab]')];
  const show = (id) => { tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === id));
    document.querySelectorAll('[data-panel]').forEach(p => p.hidden = p.dataset.panel !== id); };
  tabs.forEach(t => t.addEventListener('click', () => { show(t.dataset.tab); history.replaceState(null, '', '#' + t.dataset.tab); }));
  const start = location.hash.slice(1); show(tabs.some(t => t.dataset.tab === start) ? start : 'overview');
})();
</script>`;

export function renderCase(w: Row, events: Row[], status: Row, signals: Row[] | null = null, alert: { subject: string; body: string } | null = null,
  clock: Row | null = null, isPublic = false, inbox: Row[] | null = null, inboxClocks: Record<string, Row> = {}): string {
  const kv = (lab: string, value: unknown) => `<div class="kv"><b>${esc(lab)}</b>${blank(value) ? '<span class=muted>—</span>' : esc(value)}</div>`;
  const reasons = ((truthy(w.risk_reasons) ? w.risk_reasons : []) as Row[]).map((r) => `<li>${esc(reasonText(r))}</li>`).join('');
  let fee = '';
  if (truthy(w.amount_paid_total)) {
    const over = w.fee_status === 'over_cap';
    fee = `Rs ${fmtRupees(pyInt(w.amount_paid_total))} (${over ? 'OVER' : 'within'} the Rs 35,400 limit)`;
  }
  const salary = w.contract_salary ?? null;
  const checks = predepartureChecks(w);
  let flags = checks.map((f) => `<p class="flag">${esc(f.text)}</p>`).join('');
  if (w.status === 'registered' && checks.some((f) => STOP_FLAGS.has(f.code))) {
    flags = '<div class="stop">Tell the worker: do not pay the agent any more money and do not travel until this is sorted out.</div>' + flags;
  }
  // Latest answers from a call made after arrival, for the "worker says now" column.
  const latestEv = events.find((e) => e.type === 'checkin' && ['arrival', 'weekly', 'help'].includes(e.checkin.kind));
  const latest: Row = latestEv ? (truthy(latestEv.checkin.answers) ? latestEv.checkin.answers : {}) : {};
  const detail: Row = truthy(w.agent_check_detail) ? w.agent_check_detail : {};
  const candidates: Row[] = truthy(detail.candidates) ? detail.candidates : [];
  const matched = candidates.map((c) => `${pyStr(c.agency)} (${pyStr(c.owner)}, ${pyStr(c.district)})`).join('; ');

  const evs: string[] = [];
  for (const e of events) {
    const when = esc(fmtIst(e.at));
    if (e.type === 'registered') {
      evs.push(`<div class="ev"><b>${when}</b> · Registered before departure</div>`);
    } else if (e.type === 'call') {
      const c = e.call;
      const state = truthy(c.answered) ? 'answered' : truthy(c.missed) ? 'MISSED' : orStr(c.status);
      const whenCall = c.status === 'scheduled' ? fmtIst(c.scheduled_at) : null;
      const rec = truthy(c.recording_url) ? ` · <a href="${esc(c.recording_url)}" target="_blank" rel="noopener">Recording</a>` : '';
      const tr = truthy(c.transcript) ? `<details><summary>Transcript</summary><pre>${esc(c.transcript)}</pre></details>` : '';
      const dur = truthy(c.duration_seconds) ? ` · ${pyInt(c.duration_seconds)}s` : '';
      const booked = whenCall ? ` for ${esc(whenCall)}` : '';
      evs.push(`<div class="ev"><b>${when}</b> · ${esc(pyTitle(pyStr(c.kind || 'call')))} call · ${esc(state)}${booked}${dur}${rec}${tr}</div>`);
    } else if (e.type === 'checkin') {
      const ch = e.checkin;
      evs.push(`<div class="ev"><b>${when}</b> · Answers from ${esc(ch.kind)} call ${badge(ch.risk_level)}${answersTable(truthy(ch.answers) ? ch.answers : {})}</div>`);
    } else {
      const es = e.escalation;
      const rs = ((truthy(es.reasons) ? es.reasons : []) as Row[]).map((r) => reasonText(r)).join('; ');
      const action = es.status === 'open' ? `<button class="btn secondary" onclick="post('/api/escalations/${esc(es.id)}/resolve', {}, this, 'Marked resolved').then(() => location.reload())">Mark resolved</button>`
        : `<span class="muted">Resolved ${esc(fmtIst(es.resolved_at))}</span>`;
      evs.push(`<div class="ev alert"><b>${when}</b> · ALERT ${badge(es.level)} ${esc(rs)}<div class="sms" style="margin:8px 0"><b>Family SMS</b> (${esc(es.sms_status)}):<br>${esc(es.family_sms)}</div>${action}</div>`);
    }
  }

  const callsDisabled = truthy(w.death_reported_at) ? "disabled title='A death was reported: Saathi does not call this number'"
    : truthy(w.is_demo) ? "disabled title='Demo case: Saathi never calls demo numbers'"
    : truthy(status.bolna) ? '' : "disabled title='Bolna is not configured'";
  const caseId = esc(w.case_id);

  const briefings = events.filter((e) => e.type === 'checkin' && e.checkin.kind === 'briefing').map((e) => e.checkin);
  let briefing: string;
  if (briefings.length) {
    const understood = (truthy(briefings[0].answers) ? briefings[0].answers : {}).briefing_understood;
    briefing = `Briefing: done ${esc(fmtIst(briefings[0].created_at))}` +
      (understood === true ? ' (understood)' : understood === false ? ' (did NOT understand: repeat it)' : '');
  } else {
    briefing = 'Briefing: not done yet';
  }

  // Things the caseworker should fix or do, shown above everything else.
  const notices: string[] = [];
  const arrivalAt = w.arrival_call_at;
  const arrivalBooked = events.some((e) => e.type === 'call' && e.call.kind === 'arrival');
  if (truthy(arrivalAt) && !arrivalBooked) {
    const why = truthy(status.bolna) ? '' : ' Bolna is not set up yet (BOLNA_CHECKIN_AGENT_ID).';
    notices.push(`<p class="flag">Arrival-day call for ${esc(fmtIst(arrivalAt))} is not booked.${esc(why)} <button class="btn secondary" ${callsDisabled} onclick="post('/api/cases/${caseId}/book-arrival', {}, this, 'Booked').then(j => j && location.reload())">Book arrival call</button></p>`);
  }
  if (!codePhraseOk(w.code_phrase)) {
    notices.push(`<p class="flag">Danger code phrase "${esc(w.code_phrase)}" is too easy to say by accident. ${esc(D.CODE_PHRASE_HELP)}. <a href="/dashboard/case/${caseId}/edit">Edit details</a></p>`);
  }
  if (!truthy(w.worker_name_te)) {
    notices.push(`<p class="muted">The family SMS will use the English name. Add the name in Telugu: <a href="/dashboard/case/${caseId}/edit">Edit details</a></p>`);
  }
  const welcome = truthy(w.welcome_sms) ? `<div class="sms info" style="margin-top:12px"><b>Welcome SMS to family</b> (${esc(w.welcome_sms_status)}):<br>${esc(w.welcome_sms)}</div>` : '';
  const sig = signals && signals.length ? `<div class="card"><h2>Repeated across cases</h2>${signalsTable(signals)}</div>` : '';
  let embassy = '';
  const dead = truthy(w.death_reported_at);
  if (alert && (dead || w.risk_level === 'high' || w.risk_level === 'critical')) {
    const mailto = `mailto:?subject=${pyQuote(alert.subject)}&body=${pyQuote(alert.body)}`;
    const [heading, why] = dead ? ['Tell the Indian Embassy about the death', 'Saathi told the family a caseworker will inform the embassy.']
      : ['Alert the Indian Embassy now', 'Saathi told the worker a caseworker will take the case to the embassy.'];
    embassy = `<div class="card" style="border-color:#b42318"><h2>${heading}</h2>
<p class="muted">${why} Send this to the Indian Embassy or Consulate in
${esc(w.dest_country || 'that country')} (community welfare email or helpline) and register it on MADAD. Saathi cannot send it by itself.</p>
<pre id="alert">${esc(alert.subject)}

${esc(alert.body)}</pre>
<p><button class="btn" onclick="navigator.clipboard.writeText(document.getElementById('alert').innerText).then(() => this.textContent = 'Copied')">Copy alert</button>
<a class="btn secondary" href="${esc(mailto)}">Open in email</a>
<a class="btn secondary" href="https://madad.gov.in" target="_blank" rel="noopener">Open MADAD</a></p></div>`;
  }
  const death = dead ? deathCard(w) : '';
  const recordDeath = dead ? '' : `<details class="card"><summary><b>Record a death report</b>
<span class="muted">(if the employer, embassy or a volunteer tells you the worker died)</span></summary>
<form onsubmit="return false"><div class="grid">
<div><label for="d_by">Who reported it</label><input id="d_by" placeholder="e.g. employer, embassy, friend in Riyadh"></div>
<div><label for="d_from">They heard it from</label><input id="d_from" placeholder="name and phone, if known"></div>
<div><label for="d_place">Where</label><input id="d_place" placeholder="city, hospital"></div>
<div><label for="d_when">When</label><input id="d_when" placeholder="date"></div></div>
<label for="d_notes">What was said</label><textarea id="d_notes" rows="2"></textarea>
<p class="muted">This stops Saathi's calls to this number and opens a CRITICAL alert. The family is NOT sent an SMS:
a person must tell them.</p>
<p><button class="btn" onclick="post('/api/cases/${caseId}/death', {reported_by: d_by.value, informed_by: d_from.value,
place: d_place.value, when: d_when.value, notes: d_notes.value}, this, 'Recorded').then(j => j && location.reload())">Record death report</button></p>
</form></details>`;
  let recorded = '';
  if (truthy(w.outcome)) {
    const money = truthy(w.amount_recovered) ? ` · ₹${fmtRupees(pyInt(w.amount_recovered))} recovered` : '';
    recorded = `Recorded: ${label(w.outcome)}${money} · ${fmtIst(w.outcome_at)}`;
  }
  const outcomeCard = isPublic ? '' : `<div class="card"><h2>Outcome</h2>
<p class="muted">How this case ended. It does not stop Saathi's calls. Leave "Outcome" empty while the case is still open.</p>
<form onsubmit="return false" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
<label style="margin:0">Problem<select id="oprob">${options(OUTCOME_PROBLEMS, w.outcome_problem, 'Not set')}</select></label>
<label style="margin:0">Outcome<select id="oout">${options(OUTCOMES, w.outcome, 'Still open')}</select></label>
<label style="margin:0">Money recovered (₹)<input id="oamt" inputmode="numeric" value="${esc(w.amount_recovered ?? '')}" placeholder="200000"></label>
<label style="margin:0;flex:1;min-width:200px">Note<input id="onote" value="${esc(w.outcome_note)}" placeholder="what happened"></label>
<button class="btn" onclick="post('/api/cases/${esc(w.case_id)}/outcome', {problem: oprob.value, outcome: oout.value, amount_recovered: oamt.value, note: onote.value}, this, 'Saved').then(j => j && location.reload())">Save outcome</button>
</form><div class="muted" style="margin-top:6px">${recorded ? esc(recorded) : 'No outcome recorded yet.'}</div></div>`;
  const nowJob = latest.current_job || latest.current_location;
  const jobClash = truthy(nowJob) && promiseRows(w, latest)[0].verdict === 'conflict';
  const overCap = w.fee_status === 'over_cap';
  const summary = `<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
<div class="stat"><div class="stat-label">Promised</div><div class="text-base font-semibold">${esc(joinIf([w.job_title, w.dest_city || w.dest_country], ', ') || '—')}</div></div>
<div class="stat"><div class="stat-label">Worker says now</div><div class="text-base font-semibold${jobClash ? ' text-destructive' : ''}">${esc(joinIf([nowJob, latest.current_city], ', ') || '—')}</div></div>
<div class="stat"><div class="stat-label">Paid to agent</div><div class="text-base font-semibold${overCap ? ' text-destructive' : ''}">${truthy(w.amount_paid_total) ? 'Rs ' + esc(fmtRupees(pyInt(w.amount_paid_total))) : '—'}</div><div class="stat-foot">legal limit Rs 35,400</div></div></div>`;
  const tab = (id: string, text: string) => `<button class="tab" data-tab="${id}">${text}</button>`;
  const tabs = `<div class="tabs">${tab('overview', 'Overview')}${tab('timeline', 'Timeline')}${tab('promise', 'Promise vs reality')}${tab('details', 'Details')}${tab('petition', 'Petition')}${isPublic ? '' : tab('outcome', 'Outcome')}</div>`;
  const detailPane = `
<div class="case-head"><a class="lg:hidden text-sm" href="/dashboard">← Cases</a><span class="text-sm text-muted-foreground">${caseId}</span><span class="text-muted-foreground">/</span><span class="text-sm font-medium">${esc(w.worker_name)}</span>
<div class="ml-auto flex flex-wrap justify-end gap-2"><a class="btn secondary sm" href="/dashboard/case/${caseId}/packet.txt">Download English case packet</a>
<a class="btn secondary sm" href="/dashboard/case/${caseId}/proof-of-work" target="_blank">Proof of work</a>
${isPublic ? '' : `<a class="btn secondary sm" href="/dashboard/case/${caseId}/edit">Edit details</a>`}${embassy ? '<button class="btn sm" data-tab="overview" onclick="document.getElementById(\'embassy\').scrollIntoView({behavior:\'smooth\'})">Alert embassy</button>' : ''}</div></div>
<div class="case-body">
<div class="flex flex-wrap items-center gap-3"><div class="avatar">${esc(Array.from(orStr(w.worker_name))[0] || '?')}</div>
<div class="min-w-0"><h1 class="m-0 text-xl font-semibold">${caseId} · ${esc(w.worker_name)}${truthy(w.worker_name_te) ? ` <span class="text-base font-normal text-muted-foreground">· ${esc(w.worker_name_te)}</span>` : ''}${demoTag(w)}</h1>
<div class="text-sm text-muted-foreground">${esc(w.worker_phone)} · Family: ${esc(joinIf([w.family_name, w.family_relation, w.family_phone], ' · ') || '—')}</div></div>
<div class="ml-auto flex flex-col items-end gap-1">${caseBadge(w)}${clockBadge(clock)}</div></div>
${death}
${summary}
${flags || notices.length ? `<div>${flags}${notices.join('')}</div>` : ''}
${tabs}
<div data-panel="overview">
<div class="card">
  ${reasons ? `<ul>${reasons}</ul>` : '<p class="muted">No current risk signals.</p>'}
  <p>
    <button class="btn" ${callsDisabled} onclick="post('/api/cases/${caseId}/call', {kind:'arrival'}, this, 'Arrival call requested')">Call now: arrival check</button>
    <button class="btn" ${callsDisabled} onclick="post('/api/cases/${caseId}/call', {kind:'weekly'}, this, 'Weekly check-in call requested')">Call now: weekly check-in</button>
    <button class="btn" ${callsDisabled} onclick="post('/api/cases/${caseId}/call', {kind:'briefing'}, this, 'Briefing call requested')">Call now: pre-departure briefing</button>
  </p><div id="msg"></div>
  <div class="muted">Status: ${esc(w.status)} · Last contact: ${esc(fmtIst(w.last_contact_at))} ·
  Missed in a row: ${esc(truthy(w.missed_checkins) ? w.missed_checkins : 0)} · Next call: ${esc(fmtIst(w.next_call_at))} · ${briefing} · refreshes every 20 seconds</div>
</div>
${embassy ? embassy.replace('<div class="card" style="border-color:#b42318">', '<div class="card alert-card" id="embassy">') : ''}
${isPublic ? '' : recordDeath}
</div>
<div data-panel="timeline"><div class="card"><h2>Timeline</h2>${evs.join('')}</div></div>
<div data-panel="promise"><div class="card"><h2>Promise vs reality</h2>${promiseTable(w, latest)}</div>${sig}</div>
<div data-panel="details"><div class="card"><h2>Pre-departure trail</h2><div class="grid">
  ${kv('Worker phone', w.worker_phone)}${kv('Family', joinIf([w.family_name, w.family_relation, w.family_phone], ' · '))}
  ${kv('Employer', w.employer_name)}${kv('Employer phone', w.employer_phone)}
  ${kv('Sponsor (kafeel)', w.sponsor_name)}${kv('Sponsor ID', w.sponsor_id)}
  ${kv('Destination', joinIf([w.dest_city, w.dest_country], ', '))}${kv('Job', w.job_title)}
  ${kv('Contract salary', `${orStr(salary)} ${orStr(w.salary_currency)}`.trim())}
  ${kv('Departure', joinIf([w.departure_date, w.flight_no], ' · '))}
  ${kv('Agency', w.agent_name)}${kv('Agent owner', w.agent_owner)}
  ${kv('Licence check (MEA list)', w.agent_check)}${kv('Closest list entries', matched)}
  ${kv('Paid to agent', fee)}${kv('Money paid to', w.payment_to)}
  ${kv('Village sub-agent', joinIf([w.sub_agent_name, w.sub_agent_phone], ' · '))}
  ${kv('Visa type (papers)', w.visa_type)}${kv('Job on visa (papers)', w.visa_job)}
  ${kv('Verbal promise (not on paper)', promiseSaid(w))}${kv('Penalty to leave / cancel visa', w.exit_penalty)}${kv('Recorded calls', joinIf([truthy(w.call_consent) ? 'agreed at registration: ' + w.call_consent : '', truthy(w.consent_notice_at) ? 'notice played on a call ' + fmtIst(w.consent_notice_at) : ''], ' · '))}${kv('Full contract before paying', w.contract_before_payment)}
  ${kv('Home', joinIf([w.home_mandal, w.home_district], ', '))}
  ${kv('Passport type', orStr(w.passport_type).toUpperCase())}${kv('Emigration clearance (eMigrate)', w.emigration_clearance)}
  ${kv('PBBY insurance', joinIf([w.pbby, truthy(w.pbby_nominee) ? 'nominee: ' + w.pbby_nominee : ''], ' · '))}
  ${kv('Danger code phrase', w.code_phrase)}
</div>${welcome}</div></div>
<div data-panel="petition"><div class="card"><h2>Pravasi Prajavani petition</h2>
<p class="muted">For families who cannot travel to Hyderabad: Saathi fills the petition from this case; a caseworker hands it in for them.
The caller hears the status when they call Saathi again.</p>
<p><a class="btn secondary" href="/dashboard/case/${caseId}/petition" target="_blank">Open petition (Telugu + English)</a></p>
<form onsubmit="return false" class="flex flex-wrap items-end gap-2">
<label style="margin:0">Status<select id="pst">${['prepared', 'submitted', 'acknowledged', 'closed'].map((x) => `<option value="${x}"${w.petition_status === x ? ' selected' : ''}>${x}</option>`).join('')}</select></label>
<label style="margin:0">Reference no.<input id="pref" value="${esc(w.petition_ref)}" placeholder="from the counter"></label>
<button class="btn" onclick="post('/api/cases/${caseId}/petition', {status: document.getElementById('pst').value, ref: document.getElementById('pref').value}, this, 'Saved').then(j => j && location.reload())">Save status</button>
</form>
<div class="muted" style="margin-top:6px">${esc(truthy(w.petition_status) ? 'Status: ' + w.petition_status + (truthy(w.petition_submitted_at) ? ' · handed in ' + fmtIst(w.petition_submitted_at) : '') + (truthy(w.petition_ref) ? ' · ref ' + w.petition_ref : '') : 'Not prepared yet.')}</div>
</div></div>
${isPublic ? '' : `<div data-panel="outcome">${outcomeCard}</div>`}
</div>`;
  const list = inbox ? inboxList(inbox, w.case_id, inboxClocks) : '';
  return page(w.case_id, `<div class="inbox${list ? '' : ' single'}">${list}<section class="case-pane">${detailPane}</section></div>
${INBOX_SCRIPT}
<script>
// Refresh every 20 seconds, but never while someone is typing or reading an opened section.
setInterval(() => { if (!document.querySelector('details[open], input:focus, textarea:focus, select:focus')) location.reload(); }, 20000);
</script>`, null, isPublic, true);
}

export function deathCard(w: Row): string {
  const caseId = esc(w.case_id);
  const opts = (values: string[], current: unknown) => values.map((x) => `<option value="${x}"${current === x ? ' selected' : ''}>${x.replaceAll('_', ' ')}</option>`).join('');
  return `<div class="card" style="border-color:#101828;border-width:2px"><h2>Death reported</h2>
<p><b>${esc(fmtIst(w.death_reported_at))}</b> · ${esc(w.death_note || 'no details yet')}</p>
<p class="muted">Not confirmed until the embassy or employer confirms it. Saathi has stopped calling this number and has not
texted the family. If a call was booked with Bolna before this, cancel it in Bolna's call history: Saathi ignores its
result, but cannot stop it ringing. Help the family with the steps in the support papers.</p>
<p><a class="btn" href="/dashboard/case/${caseId}/death" target="_blank">Open family support papers (Telugu + English)</a></p>
<form onsubmit="return false" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
<label style="margin:0">Body<select id="rst">${opts(D.REMAINS_STATUSES, w.remains_status)}</select></label>
<label style="margin:0">Telangana ex-gratia<select id="egst">${opts(D.EX_GRATIA_STATUSES, w.ex_gratia_status)}</select></label>
<button class="btn" onclick="post('/api/cases/${caseId}/death-status', {remains: rst.value, ex_gratia: egst.value}, this, 'Saved').then(j => j && location.reload())">Save</button>
<button class="btn secondary" onclick="confirm('Clear the death report? Only if it was a mistake.') && post('/api/cases/${caseId}/death-clear', {}, this, 'Cleared').then(j => j && location.reload())">It was a mistake: clear</button>
</form></div>`;
}

const li = (xs: string[]) => xs.map((x) => `<li>${esc(x)}</li>`).join('');

/** Printable papers for a family after a death: Telugu steps first, then the English facts. */
export function renderDeathPacket(w: Row, pkt: Row, isPublic = false): string {
  const te = pkt.telugu, en = pkt.english;
  const body = `<p class="noprint"><button class="btn" onclick="window.print()">Print / save as PDF</button>
<a class="btn secondary" href="/dashboard/case/${esc(w.case_id)}">Back to case</a></p>
<p class="noprint muted">For the family and the caseworker. The Telugu is machine-drafted: have a Telugu speaker read it
first. Saathi does not make the NOC or consent form: the embassy gives its own, which the next of kin signs.</p>
<div class="card petition">
<p><b>${esc(te.title)}</b></p><p>${esc(te.opening)}</p><ol>${li(te.steps)}</ol>
<hr>
<p><b>${esc(en.title)}</b></p>
<p><b>Facts</b></p><ul>${li(en.facts)}</ul>
<p><b>Steps</b></p><ol>${li(en.steps)}</ol>
<p>${esc(en.status)}</p>
<p class="muted">${esc(en.note)}</p>
</div>
<style>@media print { header, .noprint { display:none } .card { border:0 } body { background:#fff } }
.petition p, .petition li { margin:6px 0 }</style>`;
  return page(`Family support ${pyStr(w.case_id)}`, body, null, isPublic);
}

/** Printable dated record: the worker's defence against a false absconding report. */
export function renderProofOfWork(w: Row, rec: Row, isPublic = false): string {
  const rows = (rec.rows as Row[]).map((r) => `<tr><td class='nowrap'>${esc(r.when)}</td><td>${esc(r.kind)}</td><td>${esc(r.where)}</td><td>${esc(r.work)}</td><td>${esc(r.pay)}</td><td>${esc(r.passport)}</td><td>${esc(r.said)}</td></tr>`).join('')
    || "<tr><td colspan='7' class='muted'>No calls answered yet.</td></tr>";
  const body = `<p class="noprint"><button class="btn" onclick="window.print()">Print / save as PDF</button>
<a class="btn secondary" href="/dashboard/case/${esc(w.case_id)}">Back to case</a></p>
<p class="noprint muted">If the employer files a false absconding report, this dated record shows the worker was in contact,
where they said they were working, and when pay stopped. Give it to the embassy with the call recordings.</p>
<div class="card petition"><p><b>${esc(rec.title)}</b></p><ul>${li(rec.summary)}</ul>
<div class="wrap"><table><thead><tr><th>Date</th><th>Call</th><th>Where</th><th>Work</th><th>Salary</th><th>Passport with worker</th>
<th>What the worker reported</th></tr></thead><tbody>${rows}</tbody></table></div>
${rec.recordings.length ? `<p><b>Call recordings</b></p><ul>${li(rec.recordings)}</ul>` : ''}
<p class="muted">${esc(rec.note)}</p></div>
<style>@media print { header, .noprint { display:none } .card { border:0 } body { background:#fff } }
.petition p, .petition li { margin:6px 0 }</style>`;
  return page(`Proof of work ${pyStr(w.case_id)}`, body, null, isPublic);
}

/** Weekly scam alert: pick or write one Telugu warning, send to everyone who opted in. */
export function renderAlerts(people: Row[], templates: Array<[string, string, string]>, hints: Row[], history: Row[], status: Row): string {
  const opts = templates.map(([, lab, text]) => `<option value="${esc(text)}">${esc(lab)}</option>`).join('');
  const hint = hints.map((h) => `<li>${esc(h.text)}</li>`).join('') || "<li class='muted'>No reports from callers this week.</li>";
  const rows = history.map((a) => `<tr><td class='nowrap'>${esc(fmtIst(a.created_at))}</td><td>${esc(a.channel)}</td><td>${esc(a.message)}</td><td>${esc(a.recipients)}</td><td>${esc(a.sent)} sent · ${esc(a.prepared)} prepared · ${esc(a.failed)} failed</td></tr>`).join('');
  const smsNote = status.sms !== 'demo' ? 'SMS is switched on.' : 'SMS is not switched on yet: an SMS alert is only prepared, not sent.';
  return page('Weekly alerts', `<h1>Weekly scam alert</h1>
<p class="muted">One short Telugu warning to every worker and family who agreed to alerts. Warn about a pattern, never a
person: a message with a phone number is refused.</p>
<div class="card"><h2>This week, callers reported</h2><ul>${hint}</ul></div>
<form class="card" onsubmit="return false">
<label for="tpl">Pick a warning</label><select id="tpl" onchange="msgtext.value=this.value"><option value="">Write my own</option>${opts}</select>
<label for="msgtext">Alert (Telugu, under 300 characters)</label><textarea id="msgtext" rows="3" maxlength="300"></textarea>
<label for="chan">Send as</label><select id="chan"><option value="voice">Voice call (Bolna, uses credits)</option><option value="sms">SMS</option></select>
<p class="muted">Goes to <b>${people.length}</b> number(s) that opted in. ${esc(smsNote)}</p>
<p><button class="btn" onclick="confirm('Send this alert to ${people.length} number(s)?') && post('/api/alerts', {message: msgtext.value, channel: chan.value}, this, 'Sent').then(j => j && location.reload())">Send alert</button></p>
<div id="msg"></div></form>
<div class="card"><h2>Sent alerts</h2>${rows ? '<div class="wrap"><table><thead><tr><th>When</th><th>How</th><th>Alert</th><th>To</th><th>Result</th></tr></thead><tbody>' + rows + '</tbody></table></div>' : '<p class="muted">None yet.</p>'}</div>`);
}

/** Printable Pravasi Prajavani petition, Telugu first, then English. */
export function renderPetition(w: Row, pet: Row, isPublic = false): string {
  const te = pet.telugu, en = pet.english;
  const body = `<p class="noprint"><button class="btn" onclick="window.print()">Print / save as PDF</button>
<a class="btn secondary" href="/dashboard/case/${esc(w.case_id)}">Back to case</a></p>
<p class="noprint muted">Saathi fills this in from the case. A caseworker hands it in at Pravasi Prajavani (Praja Bhavan,
Hyderabad) for the family, so they do not have to travel. The Telugu is machine-drafted: have a Telugu speaker read it first.
Check every fact with the family before signing.</p>
<div class="card petition">
<p>${esc(te.to)}</p><p><b>${esc(te.subject)}</b></p>
${te.body.map((x: string) => `<p>${esc(x)}</p>`).join('')}
<p>${esc(te.petitioner)}</p><p>సంతకం: ______________ &nbsp; తేదీ: ______________</p>
<hr>
<p>${esc(en.to)}</p><p><b>${esc(en.subject)}</b></p>
<p><b>Facts</b></p><ul>${li(en.facts)}</ul>
<p><b>What the worker reported</b></p><ul>${li(en.problems)}</ul>
${en.timeline.length ? `<p><b>Timeline</b></p><ul>${li(en.timeline)}</ul>` : ''}
<p><b>Request</b></p><ol>${li(en.requests)}</ol>
<p class="muted">${esc(en.note)}</p>
<p>${esc(en.petitioner)}</p><p>Signature: ______________ &nbsp; Date: ______________</p>
</div>
<style>@media print { header, .noprint { display:none } .card { border:0 } body { background:#fff } }
.petition p, .petition li { margin:6px 0 }</style>`;
  return page(`Petition ${pyStr(w.case_id)}`, body, null, isPublic);
}

/** Team login, in the layout of shadcn's login blocks: the form on the left, a photo on the right.
 * Real cases hold phone numbers, so they stay behind a password; the demo story is open to everyone. */
export function renderLogin(nextPath = '/dashboard', error = ''): string {
  const err = error ? `<p role="alert" class="m-0 text-sm font-medium text-destructive">${esc(error)}</p>` : '';
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Team login · Gulf Saathi</title><meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/dashboard.css?v=${CSS_VERSION}"></head><body class="bg-background">
<div class="grid min-h-svh lg:grid-cols-2">
  <div class="flex flex-col gap-4 p-6 md:p-10">
    <a class="flex items-center gap-2 font-medium no-underline" href="/"><span class="flex size-6 items-center justify-center rounded-md bg-primary text-[10px] font-bold text-primary-foreground">GS</span>Gulf Saathi</a>
    <div class="flex flex-1 items-center justify-center">
      <form method="post" action="/login" class="login-form">
        <input type="hidden" name="next" value="${esc(nextPath)}">
        <div class="flex flex-col items-center gap-2 text-center"><h1 class="m-0 text-2xl font-bold">Team login</h1>
          <p class="m-0 text-sm text-balance text-muted-foreground">For Gulf Saathi caseworkers. Real cases hold workers' and families' phone numbers.</p></div>
        <label for="password">Password<input id="password" name="password" type="password" autocomplete="current-password" required></label>
        ${err}
        <button class="btn w-full" type="submit">Log in</button>
        <div class="or"><span>Or</span></div>
        <a class="btn secondary w-full" href="/demo">Open the demo (no password)</a>
        <p class="m-0 text-center text-xs text-muted-foreground">The demo shows three made-up cases, from the first call to the case file.</p>
      </form>
    </div>
  </div>
  <div class="relative hidden bg-muted lg:block"><img src="/gs_caseworker.webp" alt="A caseworker with a headset at a laptop" class="absolute inset-0 h-full w-full object-cover"></div>
</div></body></html>`;
}
