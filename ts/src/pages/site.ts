// Public pages: the home page (with "Get a call from Saathi") and the demo story. Port of gulf_saathi/site.py.
//
// The home page shows only totals, never a name or number. Every value from the database still goes
// through esc(). Images are served from public/. The fixed text and CSS come from tables/pages.json,
// exported from the Python module, so both versions say exactly the same.
import { esc } from '../py.js';
import { PAGES } from './text.js';

const S = PAGES.site;
type Row = Record<string, any>;

/** The Saathi help-line number, from GS_HELPLINE_NUMBER (digits, with country code), as [tel: link, how
 * it is shown]. Empty until it is set: the number is only published once a test call has been answered
 * by the right agent, and it stays out of the public repository. */
export function helpline(): [string, string] {
  const digits = (process.env.GS_HELPLINE_NUMBER ?? '').replace(/[\s+()-]/gu, '');
  if (!/^\d{10,15}$/.test(digits)) return ['', ''];
  const shown = digits.startsWith('91') && digits.length === 12 ? `+91 ${digits.slice(2, 7)} ${digits.slice(7)}` : '+' + digits;
  return [`tel:+${digits}`, shown];
}

/** WhatsApp link for "Join the pilot", from GS_PILOT_WHATSAPP (digits only, with country code). Empty
 * until it is set, so the page never shows a dead button. */
export function pilotLink(): string {
  const digits = (process.env.GS_PILOT_WHATSAPP ?? '').replace(/[\s+()-]/gu, '');
  return /^\d{10,15}$/.test(digits) ? `https://wa.me/${digits}` : '';
}

const AI_PHOTO: string = S.AI_PHOTO;
const PITCH_POST: string = S.PITCH_POST;

/** Python's str() of a float: 35.0 stays "35.0". */
const floatStr = (n: number) => (Number.isInteger(n) ? `${n}.0` : String(n));

/** The made-up Gangadhar example as a small network: reports on the left, the exact number they share in
 * the middle, the next caller on the right. */
export function caseNetwork(): string {
  const rows = [['Worker 1 · Jagtial', 'CRITICAL', 'bad'], ['Worker 2 · Nizamabad', 'HIGH', 'bad'],
    ['Callers 3 & 4', '₹1.5 lakh asked · visit visa offered', '']];
  const left = rows.map(([name, tag, cls]) => `<li class="cn-row ${cls}"><b>${esc(name)}</b><span>${esc(tag)}</span></li>`).join('');
  return `<div class="cn">
  <ul class="cn-in">${left}</ul>
  <div class="cn-arrow" aria-hidden="true"></div>
  <div class="cn-hub"><div class="k">Same number</div>
    <div class="id">Phone 98480 XXXXX</div><div class="id">UPI ****@ybl</div>
    <div class="cnt">2 cases · 2 reports</div></div>
  <div class="cn-arrow" aria-hidden="true"></div>
  <div class="cn-out"><div class="k">Next caller</div><b>Caller 5 · warned before paying</b>
    <span class="pill">DID NOT PAY</span></div>
</div>`;
}

export function architecture(): string {
  const stages: string[] = [];
  for (const [title, boxes] of S.ARCH_STAGES as Array<[string, string[] | null]>) {
    let inner: string;
    if (boxes === null) {
      inner = (S.RISK_LEVELS as string[][]).map(([name, cls]) => `<span class="lv ${cls}">${esc(name)}</span>`).join('');
      inner = `<div class="levels">${inner}</div>`;
    } else {
      const small = boxes.length > 2 ? ' small' : '';
      inner = boxes.map((b) => `<div class="ab${small}">${esc(b)}</div>`).join('');
    }
    const human = title === 'Then' ? ' human' : '';
    stages.push(`<li class="stage${human}"><div class="sh">${esc(title)}</div>${inner}</li>`);
  }
  return `<div class="arch" id="architecture">
  <h3>How it is built</h3>
  <ol class="stages">${stages.join('')}</ol>
  <div class="loop" aria-hidden="true"></div>
  <p class="looplabel">↺ Arrival-day and weekly check-in calls (Saathi Check-in agent)</p>
</div>`;
}

function page(title: string, body: string, description = ''): string {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title><meta name="description" content="${esc(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Anek+Telugu:wght@600;700&family=Noto+Sans+Telugu:wght@400;700&display=swap" onload="this.onload=null;this.rel='stylesheet'"><noscript><link href="https://fonts.googleapis.com/css2?family=Anek+Telugu:wght@600;700&family=Noto+Sans+Telugu:wght@400;700&display=swap" rel="stylesheet"></noscript><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='16' fill='%23a8501c'/%3E%3C/svg%3E">
<style>${S.STYLE}</style></head><body>
<div class="wrap"><nav><b>Gulf Saathi · గల్ఫ్ సాథి</b><span class="sp"></span>
<span class="links"><a href="/#how">How it works</a><a href="/#call">Get a call</a><a href="/demo">Demo story</a><a href="/login">Team login</a></span></nav></div>
${body}
<footer><div class="wrap">Built for the Bolna Buildathon 2026. Saathi records every Gulf job promise before the worker
pays, checks on them after they land, and turns trouble into a ready case file for the people who can act.</div></footer>
</body></html>`;
}

export function renderHome(counts: Row, demoCallsOn: boolean): string {
  const steps = (S.STEPS as string[][]).map(([en, te, text]) => `<li><h3>${esc(en)}</h3><div class="t">${esc(te)}</div><p>${esc(text)}</p></li>`).join('');
  const bubble = `<div class="bubble">${S.PHONE_ICON}<p class="te" lang="te">${esc(S.WARNING_TE)}</p>` +
    `<p class="en">"${esc(S.WARNING_EN)}"</p></div>`;
  const stats = (S.STATS as string[][]).map(([n, text, src, url]) => `<div class="num"><b>${esc(n)}</b><p>${esc(text)}</p><div class="src">Source: ` +
    `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(src)}</a></div></div>`).join('');
  const clip = (S.CALL_CLIP as Array<[number, string, string, string]>).map(([t, who, te, en]) =>
    `<li data-t="${floatStr(t)}"><b>${esc(who)}</b><span class="te" lang="te">${esc(te)}</span><span class="en">${esc(en)}</span></li>`).join('');
  const [tel, shown] = helpline();
  const helplineHtml = tel ? `<h2>Call Saathi</h2><p>Call <a class="tel" href="${esc(tel)}"><b>${esc(shown)}</b></a> and speak in Telugu. ` +
    "Ask Saathi to check an agent's name or a fee, or tell it what is wrong.</p>" +
    '<p class="te" lang="te">తెలుగులో మాట్లాడండి.</p><hr style="border:0;border-top:1px solid #4b5a68;margin:18px 0">' : '';
  const started = (S.STARTED as string[][]).map(([label, text, state]) =>
    `<li class="${state}"><b>${esc(label)}</b><span class="tag">${state === 'done' ? 'Done' : 'Next'}</span><p>${esc(text)}</p></li>`).join('');
  const link = pilotLink();
  const pilotBtn = link ? `<p><a class="btn" href="${esc(link)}" target="_blank" rel="noopener">Join the pilot</a></p>` : '';
  const calls: Row = counts.calls || {};
  let traction: string;
  if (calls.outside_team === 0) {
    traction = `Live system: <b>${esc(calls.answered)}</b> calls answered so far, all from the team's test phone. ` +
      'Calls from families start with the pilot.';
  } else if (calls.outside_team !== undefined && calls.outside_team !== null) {
    traction = `Live system: <b>${esc(calls.answered)}</b> calls answered, <b>${esc(calls.outside_team)}</b> ` +
      `from ${esc(calls.outside_callers)} ${calls.outside_callers === 1 ? 'person' : 'people'} outside the team.`;
  } else if (Object.keys(calls).length) {
    traction = `Live system: <b>${esc(calls.answered ?? 0)}</b> calls answered so far (includes the team's test calls).`;
  } else {
    traction = '';
  }
  const callForm = demoCallsOn ? `<form id="cf" onsubmit="return false">
  <label for="phone">Your phone number</label><input id="phone" name="phone" inputmode="tel" placeholder="98765 43210" required>
  <label for="code">Demo code (from the Gulf Saathi team)</label><input id="code" name="code" autocomplete="off" required>
  <p style="margin-top:14px"><button class="btn" id="go" type="submit">Get a call from Saathi</button></p>
  <div id="msg" aria-live="polite"></div></form>
<script>
document.getElementById('cf').addEventListener('submit', async (e) => {
  const btn = document.getElementById('go'), msg = document.getElementById('msg');
  btn.disabled = true; msg.textContent = 'Asking Saathi to call…';
  try {
    const r = await fetch('/api/demo-call', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(Object.fromEntries(new FormData(e.target).entries()))});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.status);
    msg.textContent = 'Saathi is calling you now. Say “తెలుగు” when it answers.';
  } catch (err) { msg.textContent = 'Could not start the call: ' + err.message; btn.disabled = false; }
});
</script>`
    : '<p><b>Demo calls are switched off right now.</b> Ask the Gulf Saathi team to turn them on.</p>';
  return page('Gulf Saathi', `
<header class="big"><img src="/gs_hero_airport.webp" srcset="/gs_hero_airport-640.webp 640w, /gs_hero_airport-960.webp 960w, /gs_hero_airport.webp 1376w" sizes="(max-width:640px) 100vw, 50vw" width="1376" height="768" fetchpriority="high" alt="A worker at the airport on the phone, his mother and wife beside him">
<p class="cap">${AI_PHOTO}</p><div class="wrap"><div class="txt">
  <h1>A trapped worker's only evidence is a selfie video. Saathi records the evidence before the trap.</h1>
  <p class="te">మీ గల్ఫ్ ప్రయాణంలో ప్రతి అడుగులో తోడుగా సాథి.</p>
  <p>A Telugu phone call that checks the agent, the fee and the visa before he pays, then calls him on arrival day and
  each week, and flags trouble to a caseworker.</p>
  <a class="btn" href="#watch">Watch the demo</a> <a class="btn ghost" href="#hear">Hear a real call</a><br>
  <span class="badge">Voice by Bolna · Telugu speech by Sarvam</span>
</div></div></header>

<section id="why"><div class="wrap">
  <div class="stats">${stats}</div>
  <p class="src" style="margin-top:12px">Also: 3,647 Indian women were sent home from Oman, 2021–25.
  Source: <a href="https://www.mea.gov.in/rajya-sabha.htm?dtl/40875/QUESTION+NO+2319+INDIAN+WOMEN+RESCUED+AND+REPATRIATED"
  target="_blank" rel="noopener">Rajya Sabha Q. 2319, Mar 2026</a>
  (also reported by <a href="https://timesofindia.indiatimes.com/city/chandigarh/over-10k-women-rescued-from-7-gulf-countries-in-5-yrs-rs-told/articleshow/129519566.cms"
  target="_blank" rel="noopener">Times of India, 13 Mar 2026</a>)</p>
</div></section>

<section id="how"><div class="wrap">
  <h2>How it works</h2>
  <p class="lede">One phone number, in Telugu, at every step of the journey. No app, no reading needed.</p>
  <ol class="timeline">${steps}</ol>
  <p class="honest" style="margin-top:18px">The AI only writes down what was said. Fixed rules decide the risk level.</p>
  <details class="more"><summary>Show how it is built</summary>${architecture()}</details>
</div></section>

<section id="watch"><div class="wrap video">
  <h2>Watch the demo</h2>
  <video controls playsinline preload="metadata" poster="/gulf-saathi-poster-960.jpg">
    <source src="/gulf-saathi-demo.mp4" type="video/mp4"
      onerror="document.getElementById('watch').hidden=true">
  </video>
  <p class="honest">Demo video · real Bolna calls</p>
</div></section>

<section id="started"><div class="wrap">
  <h2>How Gulf Saathi started</h2>
  <div class="pics">
  <figure><img src="/gs_prajavani.webp" srcset="/gs_prajavani-800.webp 800w, /gs_prajavani.webp 1600w" sizes="(max-width:700px) 100vw, 420px" alt="A family meeting the Pravasi Prajavani desk at Praja Bhavan, Hyderabad"
    width="1600" height="714" loading="lazy"><figcaption>Pravasi Prajavani, Praja Bhavan, Hyderabad.</figcaption></figure>
  <figure><a href="${PITCH_POST}" target="_blank" rel="noopener"><img src="/gs_pitch_wide.webp" srcset="/gs_pitch_wide-800.webp 800w, /gs_pitch_wide.webp 1600w" sizes="(max-width:700px) 100vw, 660px"
    alt="Left: the founder of Gulf Saathi explaining it. Right: the Pravasi Prajavani desk."
    width="1600" height="448" loading="lazy"></a>
    <figcaption>Explaining Gulf Saathi at Pravasi Prajavani, from a public Facebook post, Nov 2026.
    <a href="${PITCH_POST}" target="_blank" rel="noopener">Watch the post</a></figcaption></figure>
  </div>
  <ol class="tl" id="tl" aria-label="How it started, swipe sideways">${started}</ol>
  <p class="area">Pilot area: Jagtial district, Telangana. For families of Gulf workers.</p>
  ${pilotBtn}
</div></section>

<section id="hear"><div class="wrap">
  <h2>Hear a real call</h2>
  <p class="lede">A test call: a worker in Dubai says his passport is gone. Saathi notes it, registers the case as urgent and reads out
  the case number. Tap a line to jump to it.</p>
  <div class="player"><audio id="callaudio" controls preload="metadata">
    <source src="/gs_call_help_line.mp3" type="audio/mpeg" onerror="document.getElementById('hear').hidden=true"></audio>
  <ol class="caps" id="caps">${clip}</ol></div>
  <p class="src">Real Bolna call, 21 Oct 2026, 42 seconds; the caller is a team member.</p>
  ${traction ? `<p class="src">${traction}</p>` : ''}
</div></section>
<script>
(() => {
  const a = document.getElementById('callaudio'), items = [...document.querySelectorAll('#caps li')];
  if (!a) return;
  a.addEventListener('timeupdate', () => {
    let cur = null;
    items.forEach(li => { if (a.currentTime >= +li.dataset.t) cur = li; });
    items.forEach(li => li.classList.toggle('on', li === cur));
  });
  items.forEach(li => li.addEventListener('click', () => { a.currentTime = +li.dataset.t; a.play(); }));
})();
</script>

<section id="story"><div class="wrap story">
  <figure style="margin:0"><img src="/gs_desert_goats.webp" srcset="/gs_desert_goats-640.webp 640w, /gs_desert_goats.webp 1376w" sizes="(max-width:820px) 100vw, 460px" width="1376" height="768" alt="A worker alone in the desert with goats, looking at his phone" loading="lazy">
  <figcaption class="cap">${AI_PHOTO}</figcaption></figure>
  <div>
    <h2>Inspired by Aadujeevitham</h2>
    <p>In the film, based on the real story of Najeeb Muhammad, a man is promised a Gulf job and ends up herding goats in the desert, alone.</p>
    <div class="vs">
      <div class="without"><h3>Without Saathi</h3><ul>
        <li>Pays the agent in cash, no record</li><li>A stranger picks him up</li>
        <li>The family learns from a video, too late</li></ul></div>
      <div class="with"><h3>With Saathi</h3><ul>
        <li>Wrong visa flagged before he flies</li><li>Arrival call: wrong pickup = CRITICAL</li>
        <li>"Herding goats" is not the promised job = HIGH</li></ul></div>
    </div>
    <p><a class="more-link" href="/demo">Run this story on the demo →</a> <span class="src">(no password)</span></p>
  </div>
</div></section>

<section id="repeat-agent"><div class="wrap">
  <h2>How Saathi catches a repeat scam agent</h2>
  <p class="lede">Sub-agents cheat family after family with the same phone number or UPI account. Each family complains
  alone. Saathi connects the reports and warns the next family before they pay.</p>
  <span class="label">Example. Made-up names and number.</span>
  <div class="netbox" id="case-network">${caseNetwork()}
</div>
  <div class="hear"><div class="hl">What caller 5 hears (roughly)</div>${bubble}</div>
  <p class="honest" style="margin-top:10px">Callers hear only a count, never names. Proven on a real Bolna call; the
  multi-caller flow is tested in code.</p>
</div></section>

<section id="who"><div class="wrap">
  <h2>Who it helps</h2>
  <div class="who">
    <article><img src="/gs_family_sms.webp" srcset="/gs_family_sms-600.webp 600w, /gs_family_sms.webp 1200w" sizes="(max-width:640px) 100vw, 340px" width="1200" height="896" alt="A mother at home reading a message on her phone" loading="lazy">
      <div class="in"><p class="cap" style="margin:0 0 8px">${AI_PHOTO}</p><h3>Family</h3>
      <p>A Telugu SMS is ready for the family the moment something is wrong.</p></div></article>
    <article><img src="/gs_caseworker.webp" srcset="/gs_caseworker-600.webp 600w, /gs_caseworker.webp 1200w" sizes="(max-width:640px) 100vw, 340px" width="1200" height="896" alt="A caseworker with a headset at a laptop" loading="lazy">
      <div class="in"><p class="cap" style="margin:0 0 8px">${AI_PHOTO}</p><h3>Volunteers and caseworkers</h3>
      <p>A ready case: who, where, which agent, what was promised.</p></div></article>
    <article><div class="plain"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5h17l9 9v13"/><path d="M29 5v9h9"/><path d="M12 5v38h16"/><path d="M18 20h12M18 27h8"/><path d="M38 31l-7 3v5c0 4 3 6.5 7 8 4-1.5 7-4 7-8v-5z"/><path d="M35 39.5l2.2 2.2 4-4.2"/></svg><span>Police · TOMCOM · State</span></div>
      <div class="in"><h3><span class="mini"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5h17l9 9v13"/><path d="M29 5v9h9"/><path d="M12 5v38h16"/><path d="M18 20h12M18 27h8"/><path d="M38 31l-7 3v5c0 4 3 6.5 7 8 4-1.5 7-4 7-8v-5z"/><path d="M35 39.5l2.2 2.2 4-4.2"/></svg></span>Government</h3>
      <p>An evidence trail for every case, built one call at a time.</p></div></article>
  </div>
</div></section>

<section id="heard"><div class="wrap">
  <h2>What we heard at Pravasi Prajavani</h2>
  <p class="src">On 30 October 2026 we sat in on Pravasi Prajavani, the Gulf workers' grievance desk at Praja Bhavan,
  Hyderabad.</p>
  <div class="vs heard">
    <div class="today"><h3>Today</h3><ul>
      <li>No simple Telugu phone line the worker knows to call</li>
      <li>Help starts only when the family finds out and travels to Hyderabad</li>
      <li>Officials spend weeks collecting the employer, visa, agent and route before the embassy can act</li>
      <li>Workers can't check what the agent tells them</li></ul>
      <p class="end">Often weeks to start a case</p></div>
    <div class="with"><h3>With Saathi</h3><ul>
      <li>The agent's promise is recorded in Telugu before the worker pays</li>
      <li>The route, visa, employer, fees and document details are recorded from day one</li>
      <li>Weekly check-in calls, and a Telugu help line (being opened)</li>
      <li>The desk gets a ready case file</li></ul>
      <p class="end">Case file ready from the first call</p></div>
  </div>
  <p class="hl" style="margin:16px 0 8px">Cases we heard about</p>
  <ul class="pills"><li>Route changed without telling the worker</li><li>Told to wait in a third country</li>
    <li>A recruit reportedly sent to Russia</li></ul>
  <p class="src" style="margin-top:14px">Officials also asked for regular scam warnings to workers and families. Saathi now
  sends weekly scam alerts to workers and families who agree: as a voice call or SMS.</p>
</div></section>

<section id="who-pays"><div class="wrap">
  <h2>Who pays</h2>
  <p class="lede">Paid for by those who already spend money on Gulf-worker welfare.</p>
  <ol class="payers">
    <li><h3>Telangana government</h3><p>About 15 lakh Telangana people work in the Gulf. The state already pays ₹5 lakh
    ex-gratia per Gulf death (G.O. 205, 16 Sep 2024) and runs Pravasi Prajavani. Saathi gives its desk early warning and a ready case file,
    sorted by district.</p></li>
    <li><h3>Other states</h3><p>Andhra Pradesh's Konaseema district built a migration help desk. In March 2026 the Chief
    Minister reportedly directed that it be scaled statewide. Saathi is the Telugu phone line that desk doesn't have.
    Next: Kerala, Uttar Pradesh, Bihar.</p></li>
    <li><h3>Gulf employers</h3><p>Companies that must prove fair recruitment can show every promise their workers heard
    was recorded.</p></li>
  </ol>
  <p class="never-line">Never paid by recruiting agents. Never sells worker data.</p>
  <p class="src">15 lakh: <a href="https://www.thehindu.com/news/national/telangana/telangana-families-worry-about-gulf-migrant-workers-amid-west-asia-tensions/article70692242.ece"
  target="_blank" rel="noopener">The Hindu, Mar 2026</a>. Konaseema:
  <a href="https://www.thehansindia.com/andhra-pradesh/naidu-praises-7-dist-collectors-1055738" target="_blank"
  rel="noopener">The Hans India, 12 Mar 2026</a>.</p>
</div></section>

<section id="numbers"><div class="wrap">
  <h2>Caseworker view</h2>
  <div class="shotwrap"><div class="shotbox"><img src="/gs_dashboard.webp" width="1602" height="385" alt="The caseworker dashboard showing a made-up demo case marked CRITICAL, with its red flags" loading="lazy"></div>
  <p class="cap">Screenshot with a made-up demo case.</p></div>
  <p style="margin-top:14px"><a class="btn ghost" href="/demo">Open the demo (no password)</a> <a class="btn ghost" href="/login">Team login</a></p>
</div></section>

<section id="call"><div class="wrap"><div class="callbox">
  ${helplineHtml}
  <h2>Get a call from Saathi</h2>
  <p>Saathi will call your phone in Telugu. Ask it to check an agent's name or a fee. Indian numbers only for now.</p>
  ${callForm}
</div></div></section>
`, `Gulf Saathi: a Telugu voice line that checks agents, fees, visas, and calls workers on arrival day and every week.`);
}

export function renderDemo(): string {
  const people = (S.DEMO_PEOPLE as Row[]).map((p) => `<article class="person">
  <h3>${esc(p.name)} <span class="demo-note" style="font-size:11px;padding:1px 8px">DEMO</span></h3>
  <p class="te">${esc(p.te)}</p><p class="who">${esc(p.who)}</p>
  <dl>${(p.facts as string[][]).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
  <p class="catch">What Saathi catches</p>
  <ul>${(p.caught as string[]).map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
  <a class="btn ghost" id="open-${esc(p.key)}" href="#" aria-disabled="true">Run the story first</a>
</article>`).join('');
  const steps = (S.DEMO_STEPS as string[][]).map(([t, d]) => `<li><b>${esc(t)}</b>${esc(d)}</li>`).join('');
  const look = (S.DEMO_LOOK as string[][]).map(([t, d]) => `<li><b>${esc(t)}</b>: ${esc(d)}</li>`).join('');
  return page('Gulf Saathi demo story', `<style>${S.DEMO_STYLE}</style>
<div class="wrap hero">
  <h1>The demo story</h1>
  <p class="te">యాదయ్య కథ</p>
  <p>Three made-up workers, from the first call to the case file. No password needed.</p>
  <p><span class="demo-note">Example. Made-up names and numbers. No real call or SMS is made.</span></p>
  <p style="margin-top:14px"><button class="btn" id="run">Run the story</button></p>
  <div id="msg" aria-live="polite"></div>
</div>
<section><div class="wrap">
  <h2>The three workers</h2>
  <div class="people">${people}</div>
</div></section>
<section><div class="wrap">
  <h2>What happens, step by step</h2>
  <ol class="tl">${steps}</ol>
</div></section>
<section><div class="wrap">
  <h2>What to look at on each case page</h2>
  <ul class="look">${look}</ul>
</div></section>
<script>
document.getElementById('run').addEventListener('click', async (e) => {
  const msg = document.getElementById('msg'); e.target.disabled = true; msg.textContent = 'Creating the demo cases…';
  try {
    const r = await fetch('/api/demo/run', {method:'POST'});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.status);
    for (const k of ['yadaiah', 'ramesh', 'saraswathi']) {
      const a = document.getElementById('open-' + k);
      a.href = '/dashboard/case/' + j[k]; a.textContent = 'Open case ' + j[k]; a.className = 'btn';
      a.removeAttribute('aria-disabled');
    }
    msg.textContent = 'Ready. Open any case below.';
    e.target.textContent = 'Story ready';
    document.querySelector('.people').scrollIntoView({behavior:'smooth'});
  } catch (err) { msg.textContent = 'Failed: ' + err.message; e.target.disabled = false; }
});
</script>
`, `Run the Yadaiah demo story on Gulf Saathi. No password needed.`);
}

/** Team login. Real cases hold phone numbers, so they stay behind a password; the demo story is open to
 * everyone. */
export function renderLogin(nextPath = '/dashboard', error = ''): string {
  const err = error ? `<p role="alert" style="color:#fda29b;font-weight:700">${esc(error)}</p>` : '';
  return page('Gulf Saathi team login', `
<div class="wrap hero">
  <h1>See the demo</h1>
  <p>No password needed. Three made-up cases show what Saathi catches, from the first call to the case file.</p>
  <p><a class="btn" href="/demo">Open the demo (no password)</a></p>
</div>
<section><div class="wrap"><div class="callbox" style="max-width:480px">
  <h2>Team login</h2>
  <p>For Gulf Saathi caseworkers. Real cases hold workers' and families' phone numbers.</p>
  <form method="post" action="/login">
    <input type="hidden" name="next" value="${esc(nextPath)}">
    <label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required>
    ${err}
    <p style="margin-top:14px"><button class="btn" type="submit">Log in</button></p>
  </form>
</div></div></section>
`, `Gulf Saathi: open the demo without a password, or log in as the team.`);
}
