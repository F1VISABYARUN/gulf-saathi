"""Public pages: the home page (with "Get a call from Saathi") and the demo story.

The home page shows only totals, never a name or number. Every value from the
database still goes through esc(). Images are served by Vercel from public/.
"""
from __future__ import annotations

from .dashboard import esc

# The journey, one step per call. "live" = working on real calls; "testing" = built, being tested.
STEPS = [
    ("Before paying", "డబ్బు ఇచ్చే ముందు",
     "Is this agent in the government licensed list? Saathi checks the MEA eMigrate active list (8 Apr 2026) "
     "by name, owner, district or licence number. Every payment is added up and compared with the legal limit: "
     "Rs 30,000 + 18% GST = Rs 35,400.", "live"),
    ("Before flying", "ప్రయాణానికి ముందు",
     "The promised job, visa type, every payment and the family's number are recorded. Red flags show at once: "
     "a visit visa, a visa naming a different job, a fee over the limit.", "live"),
    ("Arrival day", "చేరిన రోజు", "Saathi calls: did the registered employer pick you up, or someone else?", "testing"),
    ("Every week", "ప్రతి వారం",
     "Salary, passport, food, threats, freedom to go out, and is this the job and city you were promised? "
     "Two missed calls in a row raise an alert.", "testing"),
    ("When something is wrong", "సమస్య వస్తే",
     "A Telugu SMS for the family (prepared; sending is not switched on yet), the caseworker dashboard, and an "
     "English complaint-ready packet for a person to take to MADAD, the Indian Embassy or the police.", "testing"),
]

# Each number with where it comes from (checked by the team against the original documents).
NUMBERS = [
    ("476", "complaints against illegal agents in Telangana, 2021–25, and 0 prosecution sanctions.",
     "Lok Sabha unstarred question 2190, 31 Jul 2026"),
    ("72%", "of Telangana Gulf returnees borrowed money to migrate.", "IOM / CESS survey of 3,046 returnees"),
    ("3,647", "Indian women sent home from Oman, 2021–25.", "MEA reply in the Rajya Sabha, Mar 2026"),
]

AI_PHOTO = "AI-generated illustration"

STYLE = """
:root{--ink:#1d1a16;--muted:#5c544a;--line:#e6dccd;--bg:#f8f3ea;--card:#fffdf9;--sand:#efe2cc;--accent:#a8501c;--accent-ink:#fff;
--deep:#1f2328;--alert:#b42318;--ok:#067647}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ink:#f2ece3;--muted:#b8ad9e;--line:#3a332b;--bg:#16130f;
--card:#201b16;--sand:#2b241c;--accent:#e2834a;--accent-ink:#16130f;--deep:#0e1114;--alert:#f97066;--ok:#4cc38a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Telugu","Nirmala UI",sans-serif}
a{color:var(--accent)} img{max-width:100%;display:block}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
nav{display:flex;gap:16px;align-items:center;padding:14px 0;flex-wrap:wrap}
nav b{font-size:18px;letter-spacing:.01em} nav .sp{flex:1} nav a{text-decoration:none;font-weight:600}
.hero{padding:40px 0 32px}
.hero h1{font-size:clamp(30px,6vw,52px);line-height:1.1;margin:0 0 12px;letter-spacing:-.02em}
.hero .te{font-size:clamp(20px,3.5vw,28px);color:var(--accent);font-weight:700;margin:0 0 16px}
.hero p{font-size:18px;max-width:640px;color:var(--muted);margin:0 0 20px}
.big{position:relative;min-height:min(86vh,720px);display:flex;align-items:flex-end;color:#fff;background:#111 center/cover no-repeat}
.big:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(14,12,10,.93) 0%,rgba(14,12,10,.78) 45%,rgba(14,12,10,.15) 82%)}
.big .wrap{position:relative;width:100%;padding-top:72px;padding-bottom:56px}
.big h1{font-size:clamp(30px,5.2vw,54px);line-height:1.08;margin:0 0 14px;letter-spacing:-.02em;max-width:760px}
.big .te{font-size:clamp(19px,3vw,26px);color:#f0b27f;font-weight:700;margin:0 0 14px}
.big p{font-size:18px;max-width:600px;color:#e8e1d7;margin:0 0 22px}
.big .btn.ghost{color:#fff;border-color:#fff}
.badge{display:inline-block;margin-top:14px;font-size:13px;font-weight:700;letter-spacing:.03em;border:1px solid rgba(255,255,255,.45);border-radius:999px;padding:4px 12px;color:#f3ede4}
.cap{font-size:12px;color:var(--muted);margin:6px 0 0}
.big .cap{position:absolute;right:16px;bottom:10px;color:#d9d2c8}
@media (max-width:720px){.big:before{background:linear-gradient(180deg,rgba(14,12,10,.5) 0%,rgba(14,12,10,.92) 50%)}.big{min-height:auto}
.big .wrap{padding-top:180px}}
.btn{display:inline-block;background:var(--accent);color:var(--accent-ink);border:0;border-radius:10px;padding:13px 20px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer;margin:0 8px 8px 0}
.btn.ghost{background:transparent;color:var(--accent);border:2px solid var(--accent)}
.btn:disabled{opacity:.5;cursor:wait}
section{padding:48px 0;border-top:1px solid var(--line)}
h2{font-size:clamp(24px,3.6vw,32px);line-height:1.2;margin:0 0 10px;letter-spacing:-.01em} .lede{color:var(--muted);max-width:720px;margin:0 0 24px}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.num{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--alert);border-radius:12px;padding:18px}
.num b{display:block;font-size:44px;line-height:1;color:var(--alert);margin-bottom:8px} .num p{margin:0 0 10px}
.src{font-size:13px;color:var(--muted)}
.story{display:grid;grid-template-columns:5fr 6fr;gap:28px;align-items:start}
.story img{border-radius:14px;width:100%;aspect-ratio:16/10;object-fit:cover}
.vs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0}
.vs div{border-radius:12px;padding:16px;background:var(--card);border:1px solid var(--line)}
.vs h3{margin:0 0 8px;font-size:17px} .vs ul{margin:0;padding-left:18px} .vs li{margin-bottom:6px}
.vs .without{border-top:4px solid var(--alert)} .vs .with{border-top:4px solid var(--ok)}
@media (max-width:820px){.story,.vs{grid-template-columns:1fr}}
.timeline{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;counter-reset:s;list-style:none;padding:0;margin:0}
.timeline li{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:46px 14px 14px}
.timeline li:before{counter-increment:s;content:counter(s);position:absolute;top:12px;left:14px;width:26px;height:26px;border-radius:50%;
background:var(--deep);color:#fff;font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center}
.timeline h3{margin:0;font-size:17px} .timeline .t{color:var(--accent);font-weight:700;font-size:15px} .timeline p{margin:8px 0 10px;color:var(--muted);font-size:15px}
@media (max-width:900px){.timeline{grid-template-columns:1fr;border-left:3px solid var(--line);margin-left:12px;padding-left:20px}
.timeline li{padding-top:14px}.timeline li:before{left:-35px;top:14px}}
.st{display:inline-block;font-size:11px;font-weight:800;letter-spacing:.05em;border-radius:6px;padding:3px 8px}
.st.live{background:#d1fadf;color:#05603a} .st.testing{background:#fef0c7;color:#93370d}
.who{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.who article{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.who img{width:100%;aspect-ratio:4/3;object-fit:cover} .who .in{padding:12px 16px 16px} .who h3{margin:0 0 6px;font-size:18px} .who p{margin:0}
.who .plain{display:flex;align-items:center;justify-content:center;aspect-ratio:4/3;background:var(--deep);color:#f0b27f;font-size:22px;font-weight:800;text-align:center;padding:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.tile b{display:block;font-size:30px;line-height:1.1} .tile span{color:var(--muted);font-size:14px}
.shot{border-radius:12px;border:1px solid var(--line);margin:20px 0 8px;box-shadow:0 10px 30px rgba(0,0,0,.12)}
.tag{display:inline-block;background:#fef0c7;color:#93370d;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;letter-spacing:.04em}
.callbox{background:var(--deep);color:#fff;border-radius:16px;padding:22px}
.callbox h2{color:#fff} .callbox p{color:#d6dde4}
.callbox label{display:block;font-weight:600;margin:10px 0 4px;font-size:14px}
.callbox input{width:100%;max-width:360px;padding:11px 12px;border-radius:10px;border:1px solid #4b5a68;background:#0f151b;color:#fff;font:inherit}
#msg{margin-top:12px;font-weight:700;min-height:1.6em}
.honest{font-size:14px;color:var(--muted)} .honest li{margin-bottom:4px}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.step{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.step b{display:block;margin-bottom:4px}
.video{max-width:960px;margin:0 auto}
.video video{display:block;width:100%;aspect-ratio:16/9;background:#000;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.18)}
.video p{text-align:center;margin:10px 0 0}
footer{padding:24px 0 40px;color:var(--muted);font-size:14px;border-top:1px solid var(--line)}
"""


def _page(title: str, body: str, description: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;700&display=swap" rel="stylesheet">
<style>{STYLE}</style></head><body>
<div class="wrap"><nav><b>Gulf Saathi · గల్ఫ్ సాథి</b><span class="sp"></span>
<a href="/#how">How it works</a><a href="/#call">Get a call</a><a href="/demo">Demo story</a><a href="/dashboard">Caseworker login</a></nav></div>
{body}
<footer><div class="wrap">Gulf Saathi is a hackathon prototype for the Bolna Buildathon, not a government service.
It never files a complaint by itself: it prepares a complaint-ready packet that a person takes to MADAD, the Indian Embassy or eMigrate.
It never says an agent is safe or genuine. Inspired by Aadujeevitham (The Goat Life). Photos are AI-generated illustrations.<br>
<b>Voice by Bolna · Built for the Bolna Buildathon 2026</b></div></footer>
</body></html>"""


def render_home(counts: dict, demo_calls_on: bool) -> str:
    label = {"live": "WORKING ON REAL CALLS", "testing": "BUILT, BEING TESTED"}
    steps = "".join(f'<li><h3>{esc(en)}</h3><div class="t">{esc(te)}</div><p>{esc(text)}</p>'
                    f'<span class="st {st}">{label[st]}</span></li>' for en, te, text, st in STEPS)
    numbers = "".join(f'<div class="num"><b>{esc(n)}</b><p>{esc(text)}</p><div class="src">Source: {esc(src)}</div></div>'
                      for n, text, src in NUMBERS)
    demo_note = (f'<p class="honest"><span class="tag">INCLUDES DEMO DATA</span> {esc(counts["demo"])} of these cases are made-up '
                 "demo cases.</p>" if counts.get("demo") else
                 '<p class="honest">No real worker data is shown here, only totals.</p>')
    tiles = "".join(f'<div class="tile"><b>{esc(counts.get(k, 0))}</b><span>{esc(label)}</span></div>' for k, label in (
        ("registered", "Cases"), ("red_flags", "Pre-departure red flags"), ("abroad", "Abroad, getting calls"),
        ("at_risk", "At risk now (HIGH or CRITICAL)"), ("signals", "Repeated agent phones / accounts across cases")))
    call_form = ("""<form id="cf" onsubmit="return false">
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
</script>""" if demo_calls_on else
                 '<p><b>Demo calls are switched off right now.</b> Ask the Gulf Saathi team to turn them on.</p>')
    return _page("Gulf Saathi", f"""
<header class="big" style="background-image:url('/gs_hero_airport.webp')"><div class="wrap">
  <h1>A trapped worker's only evidence is a selfie video. Saathi records the evidence before the trap.</h1>
  <p class="te">మీ గల్ఫ్ ప్రయాణంలో ప్రతి అడుగులో తోడుగా సాథి.</p>
  <p>A Telugu phone call that checks the agent, the fee and the visa before he pays, then calls him on arrival day and
  every week, and alerts his family when something goes wrong.</p>
  <a class="btn" href="#call">Get a call from Saathi</a> <a class="btn ghost" href="#watch">Watch the demo</a><br>
  <span class="badge">Voice by Bolna · Telugu speech by Sarvam · Prototype</span>
</div><p class="cap">{AI_PHOTO}</p></header>

<section id="why"><div class="wrap">
  <h2>Why this matters</h2>
  <div class="nums">{numbers}</div>
</div></section>

<section id="watch"><div class="wrap video">
  <h2>Watch the demo</h2>
  <video controls playsinline preload="metadata" poster="/gulf-saathi-poster.jpg">
    <source src="/gulf-saathi-demo.mp4" type="video/mp4"
      onerror="document.getElementById('watch').hidden=true">
  </video>
  <p class="honest">Prototype demo · demo data · real Bolna test calls</p>
</div></section>

<section id="story"><div class="wrap story">
  <figure style="margin:0"><img src="/gs_desert_goats.webp" alt="A worker alone in the desert with goats, looking at his phone" loading="lazy">
  <figcaption class="cap">{AI_PHOTO}</figcaption></figure>
  <div>
    <h2>Inspired by Aadujeevitham</h2>
    <p>In the film, based on the real story of Najeeb Muhammad, a man is promised a Gulf job and ends up herding goats in the desert, alone.</p>
    <div class="vs">
      <div class="without"><h3>Without Saathi</h3><ul>
        <li>Paid the agent in cash</li><li>The visa says a different job</li><li>A stranger picks him up</li>
        <li>No one hears from him for months</li><li>The family sees a video when it is too late</li></ul></div>
      <div class="with"><h3>With Saathi</h3><ul>
        <li>Job mismatch flagged before he flies: "do not pay more, do not travel"</li>
        <li>Arrival call: wrong pickup = CRITICAL</li>
        <li>Weekly call: "herding goats" is not the promised job = HIGH</li>
        <li>Telugu SMS prepared for the family (demo: not sent yet)</li>
        <li>Complaint-ready packet in English</li></ul></div>
    </div>
    <p><a href="/demo">Run this story on the demo →</a></p>
  </div>
</div></section>

<section id="how"><div class="wrap">
  <h2>How it works</h2>
  <p class="lede">One phone number, in Telugu, at every step of the journey. No app, no reading needed.</p>
  <ol class="timeline">{steps}</ol>
  <p class="honest" style="margin-top:18px">The voice AI only writes down what the worker said. Fixed rules, which anyone can read, decide the risk level.
  Nothing is decided by the AI's opinion.</p>
</div></section>

<section id="who"><div class="wrap">
  <h2>Who it helps</h2>
  <div class="who">
    <article><img src="/gs_family_sms.webp" alt="A mother at home reading a message on her phone" loading="lazy">
      <div class="in"><p class="cap" style="margin:0 0 8px">{AI_PHOTO}</p><h3>Family</h3>
      <p>Hears in Telugu when something is wrong, not months later.</p></div></article>
    <article><img src="/gs_caseworker.webp" alt="A caseworker with a headset at a laptop" loading="lazy">
      <div class="in"><p class="cap" style="margin:0 0 8px">{AI_PHOTO}</p><h3>Volunteers and caseworkers</h3>
      <p>Get a ready case: who, where, which agent, what was promised, when contact stopped.</p></div></article>
    <article><div class="plain">Police · TOMCOM · State</div>
      <div class="in"><h3>Government</h3>
      <p>An evidence trail for police and TOMCOM, built one call at a time. A prototype, not a government service.</p></div></article>
  </div>
</div></section>

<section id="numbers"><div class="wrap">
  <h2>Demo dashboard</h2>
  <div class="tiles">{tiles}</div>
  {demo_note}
  <img class="shot" src="/gs_dashboard.webp" alt="The caseworker dashboard listing demo cases with CRITICAL and RED FLAGS badges" loading="lazy">
  <p class="cap">Screenshot of the caseworker view with made-up demo cases.</p>
  <p style="margin-top:14px"><a class="btn ghost" href="/dashboard">Open caseworker view</a></p>
</div></section>

<section id="call"><div class="wrap callbox">
  <h2>Get a call from Saathi</h2>
  <p>Saathi will call your phone in Telugu. Ask it to check an agent's name or a fee. Indian numbers only for now.</p>
  {call_form}
  <ul class="honest" style="color:#b9c4cf">
    <li>This prototype runs on a Bolna trial account, which may only be able to call numbers verified in that account.</li>
    <li>Calls to Gulf numbers have not been tested yet.</li>
    <li>When Saathi answers, say "తెలుగు".</li>
  </ul>
</div></section>
""", "Gulf Saathi: a Telugu voice line that checks agents, fees, visas, and calls workers on arrival day and every week.")


def render_demo() -> str:
    return _page("Gulf Saathi demo story", """
<div class="wrap hero">
  <h1>The demo story</h1>
  <p class="te">యాదయ్య కథ</p>
  <p>This creates three made-up demo cases and walks through what Saathi catches. They are marked DEMO everywhere.
  No real call and no real SMS is made for them.</p>
  <button class="btn" id="run">Run the story</button> <a class="btn ghost" href="/dashboard">Open the dashboard</a>
  <div id="msg" aria-live="polite"></div>
</div>
<section><div class="wrap"><div class="steps" id="steps">
  <div class="step"><b>1. Registered before flying</b>Yadaiah was promised a <b>cleaner</b> job in Riyadh. He paid the agent Rs 90,000 in two parts.</div>
  <div class="step"><b>2. Red flags at once</b>The agent is not found in the licensed list. Rs 90,000 is over the Rs 35,400 limit.
    The visa says <b>agricultural worker</b>, not cleaner: "do not pay more or travel until this is sorted out".</div>
  <div class="step"><b>3. Family SMS</b>One Telugu SMS for his wife with the case number (shown, not sent).</div>
  <div class="step"><b>4. Arrival-day call</b>A stranger picked him up. He says he is <b>herding goats</b> in Al Kharj, and his passport was taken.
    Fixed rules mark it CRITICAL.</div>
  <div class="step"><b>5. Family alert and packet</b>A Telugu alert SMS (shown, not sent) and an English complaint-ready packet.</div>
  <div class="step"><b>6. Seen in 2 cases</b>Ramesh paid the same village agent's phone and UPI ID, and has a visit visa.
    Shown as "seen in 2 cases, needs human review", not as fraud.</div>
  <div class="step"><b>7. A woman sent for housework</b>Saraswathi, 27, is going to Muscat as a <b>housemaid</b> on a
    <b>tourist visa</b>: the route used to get past emigration checks. Stopped before she flies.</div>
</div></div></section>
<script>
document.getElementById('run').addEventListener('click', async (e) => {
  const msg = document.getElementById('msg'); e.target.disabled = true; msg.textContent = 'Creating the demo cases…';
  try {
    const r = await fetch('/api/demo/run', {method:'POST'});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.status);
    msg.innerHTML = '';
    const add = (text, href) => { const a = document.createElement('a'); a.href = href; a.textContent = text;
      a.className = 'btn ghost'; a.style.margin = '12px 8px 0 0'; msg.appendChild(a); };
    add('Yadaiah\\'s case ' + j.yadaiah, '/dashboard/case/' + j.yadaiah);
    add('Ramesh\\'s case ' + j.ramesh, '/dashboard/case/' + j.ramesh);
    add('Saraswathi\\'s case ' + j.saraswathi, '/dashboard/case/' + j.saraswathi);
    add('Agents and repeated signals', '/dashboard/agents');
  } catch (err) { msg.textContent = 'Failed: ' + err.message; e.target.disabled = false; }
});
</script>
""", "Run the Yadaiah demo story on Gulf Saathi.")
