"""Public pages: the home page (with "Get a call from Saathi") and the demo story.

The home page shows only totals, never a name or number. Every value from the
database still goes through esc().
"""
from __future__ import annotations

from .dashboard import esc

GATES = [
    ("Agent", "ఏజెంట్", "Is this agent in the government licensed list? Saathi checks the MEA eMigrate active list "
     "(8 Apr 2026) by name, owner, district or licence number.", "live"),
    ("Job", "ఉద్యోగం", "The job the agent promises is written into the case, so it can be compared with the visa and with the work done abroad.",
     "live"),
    ("Payment", "డబ్బు", "Every payment is added up and compared with the legal service-fee limit (Rs 30,000 + 18% GST). Who the money went to is recorded.",
     "live"),
    ("Visa", "వీసా", "A visit or tourist visa for a job, or a visa naming a different job, is flagged: do not pay more or travel until it is sorted out.",
     "live"),
    ("Contract", "ఒప్పందం", "A short pre-departure briefing call explains contract, passport and receipts in Telugu, then checks they understood.",
     "testing"),
    ("Airport", "విమానాశ్రయం", "On arrival day Saathi calls: did the registered employer pick you up, or someone else?",
     "testing"),
    ("Workplace", "పని చోటు", "Every week: salary, passport, food, threats, freedom to go out, and is this the job and city you were promised?",
     "testing"),
]

STYLE = """
:root{--ink:#1f1a14;--muted:#5e554a;--line:#e8dfd2;--bg:#fbf7f1;--card:#fff;--sand:#f3e7d3;--accent:#b4541a;--accent-ink:#fff;--deep:#24323f;--ok:#067647;--warn:#b42318}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ink:#f3ede4;--muted:#b9ad9c;--line:#3a332b;--bg:#17130f;--card:#211c17;--sand:#2b241c;--accent:#e07a3c;--accent-ink:#17130f;--deep:#0f151b;--ok:#4cc38a;--warn:#f97066}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Telugu","Nirmala UI",sans-serif}
a{color:var(--accent)}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px}
nav{display:flex;gap:16px;align-items:center;padding:14px 0;flex-wrap:wrap}
nav b{font-size:18px;letter-spacing:.01em} nav .sp{flex:1} nav a{text-decoration:none;font-weight:600}
.hero{padding:40px 0 32px}
.hero h1{font-size:clamp(30px,6vw,52px);line-height:1.1;margin:0 0 12px;letter-spacing:-.02em}
.hero .te{font-size:clamp(20px,3.5vw,28px);color:var(--accent);font-weight:700;margin:0 0 16px}
.hero p{font-size:18px;max-width:640px;color:var(--muted);margin:0 0 20px}
.btn{display:inline-block;background:var(--accent);color:var(--accent-ink);border:0;border-radius:10px;padding:12px 18px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer}
.btn.ghost{background:transparent;color:var(--accent);border:2px solid var(--accent)}
.btn:disabled{opacity:.5;cursor:wait}
section{padding:32px 0;border-top:1px solid var(--line)}
h2{font-size:26px;margin:0 0 8px;letter-spacing:-.01em} .lede{color:var(--muted);max-width:720px;margin:0 0 20px}
.gates{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;counter-reset:g}
.gate{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;position:relative}
.gate:before{counter-increment:g;content:counter(g);position:absolute;top:14px;right:16px;font-weight:800;font-size:28px;color:var(--sand)}
.gate h3{margin:0;font-size:18px} .gate .t{color:var(--accent);font-weight:700;font-size:15px} .gate p{margin:8px 0 0;color:var(--muted);font-size:15px}
.story{background:var(--sand);border-radius:16px;padding:20px}
.story p{margin:0 0 10px}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.step{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.step b{display:block;margin-bottom:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.tile b{display:block;font-size:30px;line-height:1.1} .tile span{color:var(--muted);font-size:14px}
.tag{display:inline-block;background:#fef0c7;color:#93370d;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;letter-spacing:.04em}
.callbox{background:var(--deep);color:#fff;border-radius:16px;padding:20px}
.callbox h2{color:#fff} .callbox p{color:#d6dde4}
.callbox label{display:block;font-weight:600;margin:10px 0 4px;font-size:14px}
.callbox input{width:100%;max-width:360px;padding:10px 12px;border-radius:10px;border:1px solid #4b5a68;background:#0f151b;color:#fff;font:inherit}
#msg{margin-top:12px;font-weight:700;min-height:1.6em}
.honest{font-size:14px;color:var(--muted)}
.gate .st{display:inline-block;margin-top:10px;font-size:12px;font-weight:700;letter-spacing:.04em;border-radius:999px;padding:2px 10px}
.gate .st.live{background:#d1fadf;color:#05603a} .gate .st.testing{background:#fef0c7;color:#93370d}
.honest li{margin-bottom:4px}
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
It never says an agent is safe or genuine. Inspired by Aadujeevitham (The Goat Life).</div></footer>
</body></html>"""


def render_home(counts: dict, demo_calls_on: bool) -> str:
    label = {"live": "WORKING ON REAL CALLS", "testing": "BUILT, BEING TESTED"}
    gates = "".join(f'<div class="gate"><h3>{esc(en)}</h3><div class="t">{esc(te)}</div><p>{esc(text)}</p>'
                    f'<span class="st {st}">{label[st]}</span></div>' for en, te, text, st in GATES)
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
<div class="wrap hero">
  <h1>A Telugu voice that checks every step of the Gulf journey.</h1>
  <p class="te">మీ గల్ఫ్ ప్రయాణంలో ప్రతి అడుగులో తోడుగా సాథి.</p>
  <p>Workers from Telangana are cheated at one step nobody watches: an unlicensed agent, an illegal fee, a visit visa,
  a different job, a stranger at the airport. Gulf Saathi is a phone call in Telugu that checks each step, and tells the family
  when something goes wrong.</p>
  <a class="btn" href="#call">Get a call from Saathi</a> <a class="btn ghost" href="/demo">See the demo story</a>
</div>

<section id="problem"><div class="wrap">
  <h2>Seven gates, one cheat</h2>
  <p class="lede">Agent → Job → Payment → Visa → Contract → Airport → Workplace. Different offices watch different gates.
  A cheat only needs one gate nobody watches. Saathi watches all seven, in Telugu, by phone, with no app and no reading needed.</p>
  <div class="gates">{gates}</div>
</div></section>

<section id="story"><div class="wrap story">
  <h2>Inspired by Aadujeevitham</h2>
  <p>In the film, a man is promised a job in the Gulf and ends up herding goats in the desert, alone, with no way to tell anyone.</p>
  <p><b>With Saathi:</b> before he flies, the visa job ("agricultural worker") does not match the promised job ("cleaner"), so Saathi
  says: do not pay more, do not travel until this is sorted out. If he flies anyway, Saathi calls on arrival day and every week.
  When he says "herding goats", fixed rules mark it CRITICAL, a Telugu SMS for his family is prepared (demo: shown on the dashboard, not sent yet),
  and so is a complaint-ready packet.</p>
  <p><a href="/demo">Run this story on the demo →</a></p>
</div></section>

<section id="how"><div class="wrap">
  <h2>How Saathi works</h2>
  <div class="steps">
    <div class="step"><b>1. Before paying</b>The worker calls Saathi. "Is this agent in the government licensed list?" "Is this fee legal?" Answers in Telugu.</div>
    <div class="step"><b>2. Before flying</b>A helper registers the worker: promised job, visa, payments, family number. Red flags show at once. One Telugu SMS for the family with the case number (demo: shown on the dashboard, not sent yet).</div>
    <div class="step"><b>3. Arrival day and every week</b>Saathi calls the worker: who picked you up, salary, passport, and is this the job and city you were promised?</div>
    <div class="step"><b>4. When something is wrong</b>A Telugu SMS for the family (demo: shown on the dashboard, not sent yet). A caseworker sees it on the dashboard and has a complaint-ready packet in English.</div>
    <div class="step"><b>5. Patterns</b>The same village agent's phone or payment account in several cases is shown as "seen in N cases, needs review". Never as a verdict.</div>
    <div class="step"><b>6. Help line</b>A worker abroad can call the same Saathi number and report a problem. The same rules apply.</div>
  </div>
  <p class="honest" style="margin-top:16px">The voice AI only writes down what the worker said. Fixed rules, which anyone can read, decide the risk level.
  Nothing is decided by the AI's opinion.</p>
</div></section>

<section id="numbers"><div class="wrap">
  <h2>Live totals</h2>
  <div class="tiles">{tiles}</div>
  {demo_note}
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
  <p>This creates two made-up demo cases and walks through what Saathi catches. They are marked DEMO everywhere.
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
    add('Agents and repeated signals', '/dashboard/agents');
  } catch (err) { msg.textContent = 'Failed: ' + err.message; e.target.disabled = false; }
});
</script>
""", "Run the Yadaiah demo story on Gulf Saathi.")
