"""Public pages: the home page (with "Get a call from Saathi") and the demo story.

The home page shows only totals, never a name or number. Every value from the
database still goes through esc(). Images are served by Vercel from public/.
"""
from __future__ import annotations

from .dashboard import esc

# The journey, one step per call. "live" = working on real calls; "testing" = built, being tested.
STEPS = [
    ("Before paying", "డబ్బు ఇచ్చే ముందు",
     "Is the agent licensed? Checks 2,447 agents (MEA eMigrate, 8 Apr 2026). Adds up every payment against the "
     "₹35,400 legal limit.", "live"),
    ("Before flying", "ప్రయాణానికి ముందు",
     "Records the promised job, visa and payments. Flags a visit visa or a different job at once.", "testing"),
    ("Arrival day", "చేరిన రోజు", "Calls on landing: did the registered employer pick you up?", "testing"),
    ("Every week", "ప్రతి వారం",
     "Salary, passport, food, threats, same job and city? Two missed calls raise an alert.", "testing"),
    ("When something is wrong", "సమస్య వస్తే",
     "Caseworker dashboard, English complaint-ready packet, and a family SMS (sending not switched on yet).", "testing"),
]

AI_PHOTO = "AI-generated illustration"

PHONE_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><path d="M5 3h4l2 5-2.5 1.5a11 11 0 0 0 6 6L16 13l5 2v4a2 2 0 0 '
              '1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2z"/></svg>')

WARNING_TE = "ఈ నంబర్ మరో 2 సాథి కేసుల్లో వచ్చింది. ఇది రుజువు కాదు, కానీ కేస్‌వర్కర్ చూసే వరకు డబ్బు ఇవ్వకండి."
WARNING_EN = "This number came up in 2 other Saathi cases. It's not proof, but don't pay until a caseworker checks."

# (number, text, source label, link). Checked by the team against the sources.
STATS = [
    ("9.9 million", "Indians live in the six Gulf countries.", "MEA, Dec 2025",
     "https://www.mea.gov.in/population-of-overseas-indians"),
    ("1.5 million", "(nearly 15 lakh) of them are from Telangana.", "State NRI Advisory Committee, via UNI, Aug 2026",
     "https://www.uniindia.com/telangana-nri-panel-studies-philippines-migration-policy-for-gulf-workers/south/news/3947967.html"),
    ("72%", "of Telangana returnees borrowed money to migrate.", "IOM / CESS survey",
     "https://publications.iom.int/books/international-returnee-migrants-telangana-survey"),
    ("476", "complaints against illegal agents in Telangana, 2021–25: 118 action-taken reports, 0 prosecution sanctions.",
     "Lok Sabha USQ 2190, 31 Jul 2026, Annex I", "https://sansad.in/getFile/lsapps/loksabhaquestions/annex/188/AU2190_NjP8nJ.pdf"),
]

PAYERS = [
    ("State governments", "First customer",
     "Telangana pays ₹5 lakh per Gulf death (G.O. 205). Saathi gives a live district view and early warning, before it "
     "becomes a death. AP and Kerala next."),
    ("Licensed agents", "Opt-in",
     "They pay to have their workers checked on weekly. Saathi reports how the workers are doing and never vouches for an agent."),
    ("Partners", "Later", "Fair loans, insurance and remittances for monitored workers."),
]

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
.big{position:relative;min-height:min(86vh,720px);display:flex;align-items:flex-end;color:#fff;background:#14110e;overflow:hidden}
.big>img{position:absolute;top:0;right:0;width:50%;height:100%;object-fit:cover;object-position:20% center}
.big:before{content:"";position:absolute;inset:0;z-index:1;
background:linear-gradient(90deg,rgba(20,17,14,1) 0%,rgba(20,17,14,1) 50%,rgba(20,17,14,.55) 52%,rgba(20,17,14,0) 55%)}
.big .wrap{position:relative;z-index:2;width:100%;padding-top:72px;padding-bottom:56px}
.big .txt{max-width:min(480px,40vw)}
.big h1{font-size:clamp(28px,3.6vw,48px);line-height:1.1;margin:0 0 14px;letter-spacing:-.02em}
.big .te{font-size:clamp(18px,2.2vw,24px);color:#f0b27f;font-weight:700;margin:0 0 14px}
.big p{font-size:18px;color:#e8e1d7;margin:0 0 22px}
.big .btn.ghost{color:#fff;border-color:#fff}
.badge{display:inline-block;margin-top:14px;font-size:13px;font-weight:700;letter-spacing:.03em;border:1px solid rgba(255,255,255,.45);border-radius:999px;padding:4px 12px;color:#f3ede4}
.cap{font-size:12px;color:var(--muted);margin:6px 0 0}
.big .cap{position:absolute;z-index:2;right:16px;bottom:10px;color:#e8e1d7;text-shadow:0 1px 3px rgba(0,0,0,.7)}
@media (max-width:640px){.big{display:block;min-height:0;background:var(--deep)}
.big>img{position:static;width:100%;height:auto;aspect-ratio:4/3}.big:before{display:none}
.big .cap{position:static;color:#b8ad9e;text-shadow:none;padding:6px 16px 0;text-align:right}
.big .wrap{padding-top:18px;padding-bottom:32px}.big .txt{max-width:none}.big h1{font-size:30px}}
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
.vs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0;align-items:stretch}
.vs div{border-radius:12px;padding:16px;background:var(--card);border:1px solid var(--line)}
.vs h3{margin:0 0 8px;font-size:17px} .vs ul{margin:0;padding-left:18px} .vs li{margin-bottom:6px}
.vs .without{border-top:4px solid var(--alert)} .vs .with{border-top:4px solid var(--ok)}
@media (max-width:820px){.story,.vs{grid-template-columns:1fr}}
.timeline{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;counter-reset:s;list-style:none;padding:0;margin:0}
.timeline li{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:46px 14px 14px;display:flex;flex-direction:column}
.timeline li .st{margin-top:auto;align-self:flex-start}
.timeline li:before{counter-increment:s;content:counter(s);position:absolute;top:12px;left:14px;width:26px;height:26px;border-radius:50%;
background:var(--deep);color:#fff;font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center}
.timeline h3{margin:0;font-size:17px} .timeline .t{color:var(--accent);font-weight:700;font-size:15px} .timeline p{margin:8px 0 14px;color:var(--muted);font-size:15px}
@media (max-width:900px){.timeline{grid-template-columns:1fr;border-left:3px solid var(--line);margin-left:12px;padding-left:20px}
.timeline li{padding-top:14px}.timeline li:before{left:-35px;top:14px}}
.st{display:inline-block;font-size:10.5px;font-weight:800;letter-spacing:.02em;border-radius:6px;padding:3px 7px;white-space:nowrap}
.st.live{background:#d1fadf;color:#05603a} .st.testing{background:#fef0c7;color:#93370d}
.who{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.who article{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.who img{width:100%;aspect-ratio:4/3;object-fit:cover} .who .in{padding:12px 16px 16px} .who h3{margin:0 0 6px;font-size:18px} .who p{margin:0}
.who .plain{display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;aspect-ratio:4/3;background:var(--sand);color:var(--accent);font-weight:700;font-size:15px;letter-spacing:.03em}
.who .plain svg{width:84px;height:84px} .who .mini{display:none;width:28px;height:28px;color:var(--accent)}
@media (max-width:640px){.who .plain{display:none}.who .mini{display:inline-block;vertical-align:-6px;margin-right:6px}}
.tiles{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
@media (max-width:760px){.tiles{grid-template-columns:1fr 1fr}.tiles .tile:nth-child(5){grid-column:1/-1}}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.tile b{display:block;font-size:30px;line-height:1.1} .tile span{color:var(--muted);font-size:14px}
.shotbox{position:relative;max-height:320px;overflow:hidden;border-radius:12px;border:1px solid var(--line);margin:20px 0 8px;box-shadow:0 10px 30px rgba(0,0,0,.12)}
.shotbox:after{content:"";position:absolute;left:0;right:0;bottom:0;height:36px;background:linear-gradient(rgba(255,255,255,0),#fff)}
.shotbox img{width:100%}
@media (max-width:640px){.shotwrap{display:none}}
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
.label{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.04em;color:var(--muted);border:1px dashed var(--muted);border-radius:6px;padding:2px 8px;margin:0 0 10px}
.hear{max-width:560px;margin:4px 0 14px} .hl{font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
details.more{margin-top:22px}
details.more>summary{display:inline-block;cursor:pointer;list-style:none;font-weight:700;color:var(--accent);
border:2px solid var(--accent);border-radius:10px;padding:8px 14px}
details.more>summary::-webkit-details-marker{display:none}
details.more>summary:after{content:" ▾"} details.more[open]>summary:after{content:" ▴"}
details.more .arch{margin-top:14px}
.bubble{position:relative;background:#fff4dc;border:1px solid #f0cf8a;border-radius:12px;padding:12px 14px 12px 42px;color:#3d2a06}
.bubble svg{position:absolute;left:14px;top:14px;width:20px;height:20px;color:#a86a00}
.bubble .te{margin:0 0 6px;font-weight:700;font-size:15px;line-height:1.5;color:#3d2a06} .bubble .en{margin:0;font-size:14px;line-height:1.45;color:#5c4512}
.netbox{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:0 0 22px}
.cn{display:grid;grid-template-columns:1.15fr 36px 1fr 36px 1fr;align-items:center}
.cn-in{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.cn-row{display:flex;justify-content:space-between;align-items:center;gap:10px;background:var(--bg);border:1px solid var(--line);
border-left:4px solid var(--muted);border-radius:10px;padding:8px 12px;font-size:14px}
.cn-row span{font-size:12px;color:var(--muted);text-align:right}
.cn-row.bad{border-left-color:var(--alert)} .cn-row.bad span{color:var(--alert);font-weight:800;letter-spacing:.04em}
.cn-arrow{height:2px;background:var(--muted);position:relative;margin:0 6px;opacity:.7}
.cn-arrow:after{content:"";position:absolute;right:-2px;top:-5px;border:6px solid transparent;border-right:0;border-left:8px solid var(--muted)}
.cn-hub,.cn-out{border-radius:14px;padding:14px 16px;text-align:center}
.cn-hub{border:2px solid #d9a54a;background:rgba(217,165,74,.12)}
.cn-out{border:2px solid var(--ok);background:rgba(6,118,71,.08)}
.cn .k{font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.cn-hub .id{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:15px;font-weight:700;margin:2px 0}
.cn-hub .cnt{margin-top:8px;font-size:13px;color:var(--muted)}
.cn-out b{display:block;font-size:15px;margin-bottom:8px}
.cn-out .pill{display:inline-block;background:var(--ok);color:#fff;font-size:11px;font-weight:800;letter-spacing:.05em;border-radius:6px;padding:3px 8px}
@media (max-width:820px){.cn{grid-template-columns:1fr;gap:0}
.cn-arrow{width:2px;height:22px;margin:6px auto}
.cn-arrow:after{right:-5px;top:auto;bottom:-2px;border:6px solid transparent;border-bottom:0;border-top:8px solid var(--muted)}}
.arch{margin-top:28px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.arch h3{margin:0 0 12px;font-size:18px}
.stages{display:grid;grid-template-columns:1fr 1fr 1.35fr .85fr 1.15fr .9fr;gap:26px;list-style:none;margin:0;padding:0}
.stage{position:relative;display:flex;flex-direction:column;gap:8px}
.stage:not(:last-child):after{content:"→";position:absolute;right:-21px;top:40%;font-weight:900;font-size:20px;color:var(--ink)}
.sh{font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--accent)}
.ab{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:14px;line-height:1.35}
.ab.small{font-size:13px;padding:6px 8px}
.stage.human .ab{background:var(--deep);color:#fff;border-color:var(--deep);font-weight:700}
.levels{display:flex;flex-direction:column;gap:6px}
.lv{color:#fff;font-size:12px;font-weight:800;letter-spacing:.04em;border-radius:999px;padding:4px 10px;text-align:center}
.lv.ok{background:#067647} .lv.medium{background:#a15c07} .lv.high{background:#c4320a} .lv.critical{background:#b42318}
.loop{position:relative;height:24px;margin:10px 23% 0 7%;border:2px dashed var(--accent);border-top:0;border-radius:0 0 14px 14px}
.loop:before{content:"▲";position:absolute;left:-8px;top:-12px;font-size:13px;color:var(--accent)}
.looplabel{text-align:center;margin:6px 0 14px;font-size:14px;font-weight:600;color:var(--accent)}
.roadmap{border-top:2px dashed var(--line);padding-top:10px;margin:0;color:var(--muted);font-size:14px;opacity:.75}
@media (max-width:900px){.stages{grid-template-columns:1fr;gap:26px}
.stage:not(:last-child):after{content:"↓";right:auto;left:12px;top:auto;bottom:-25px}
.loop{display:none}.looplabel{text-align:left;border:2px dashed var(--accent);border-radius:10px;padding:8px 10px;margin-top:16px}}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.stats .num b{font-size:clamp(28px,2.6vw,36px);white-space:nowrap}
.big-label{font-size:14px;padding:4px 10px;border-width:2px}
@media (max-width:900px){.stats{grid-template-columns:1fr 1fr}} @media (max-width:520px){.stats{grid-template-columns:1fr}}
.pay{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:24px}
@media (max-width:820px){.pay{grid-template-columns:1fr}}
.pay article{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--accent);border-radius:12px;padding:16px}
.pay h3{margin:0 0 2px;font-size:18px} .pay .k{font-size:12px;font-weight:800;letter-spacing:.04em;color:var(--accent);text-transform:uppercase;margin-bottom:8px} .pay p{margin:0;color:var(--muted)}
footer{padding:24px 0 40px;color:var(--muted);font-size:14px;border-top:1px solid var(--line)}
"""


def case_network() -> str:
    """The made-up Gangadhar example as a small network: reports on the left, the exact
    number they share in the middle, the next caller on the right."""
    rows = [("Worker 1 · Jagtial", "CRITICAL", "bad"), ("Worker 2 · Nizamabad", "HIGH", "bad"),
            ("Callers 3 & 4", "₹1.5 lakh asked · visit visa offered", "")]
    left = "".join(f'<li class="cn-row {cls}"><b>{esc(name)}</b><span>{esc(tag)}</span></li>' for name, tag, cls in rows)
    return f"""<div class="cn">
  <ul class="cn-in">{left}</ul>
  <div class="cn-arrow" aria-hidden="true"></div>
  <div class="cn-hub"><div class="k">Same number</div>
    <div class="id">Phone 98480 XXXXX</div><div class="id">UPI ****@ybl</div>
    <div class="cnt">2 cases · 2 reports</div></div>
  <div class="cn-arrow" aria-hidden="true"></div>
  <div class="cn-out"><div class="k">Next caller</div><b>Caller 5 · warned before paying</b>
    <span class="pill">DID NOT PAY</span></div>
</div>"""


# What is built, stage by stage, left to right. Only what exists; the roadmap is separate.
ARCH_STAGES = [
    ("Call", ["Telugu call from worker or family", "Bolna voice agent · Sarvam saaras:v3 speech-to-text"]),
    ("Backend", ["FastAPI on Vercel", "Supabase case store"]),
    ("Fixed rules", ["Licensed agent?", "Fee over ₹35,400?", "Visit visa for a job?", "Number seen in other cases?"]),
    ("Risk level", None),
    ("Outputs", ["Telugu warning on the call", "Dashboard + English case packet", "Family SMS (not switched on yet)"]),
    ("Then", ["A human caseworker decides and acts"]),
]
RISK_LEVELS = (("OK", "ok"), ("MEDIUM", "medium"), ("HIGH", "high"), ("CRITICAL", "critical"))
ROADMAP = ["recognising a worker's Gulf or borrowed phone", "other Indian languages", "a state dashboard"]


def architecture() -> str:
    stages = []
    for title, boxes in ARCH_STAGES:
        if boxes is None:
            inner = "".join(f'<span class="lv {cls}">{esc(name)}</span>' for name, cls in RISK_LEVELS)
            inner = f'<div class="levels">{inner}</div>'
        else:
            small = " small" if len(boxes) > 2 else ""
            inner = "".join(f'<div class="ab{small}">{esc(b)}</div>' for b in boxes)
        human = " human" if title == "Then" else ""
        stages.append(f'<li class="stage{human}"><div class="sh">{esc(title)}</div>{inner}</li>')
    road = esc(" · ".join(ROADMAP))
    return f"""<div class="arch" id="architecture">
  <h3>How it is built</h3>
  <ol class="stages">{''.join(stages)}</ol>
  <div class="loop" aria-hidden="true"></div>
  <p class="looplabel">↺ Arrival-day and weekly check-in calls (Saathi Check-in agent)</p>
  <p class="roadmap"><b>Planned, not built:</b> {road}</p>
  <p class="src" style="margin:8px 0 0">Built and tested. Roadmap items are marked.</p>
</div>"""


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
It never files a complaint by itself: it prepares a complaint-ready packet that a person takes to MADAD, the Indian Embassy or the police.
It never vouches for an agent: it only says whether the agent is in the government licensed list. Inspired by Aadujeevitham (The Goat Life). Photos are AI-generated illustrations.<br>
<b>Voice by Bolna · Built for the Bolna Buildathon 2026</b></div></footer>
</body></html>"""


def render_home(counts: dict, demo_calls_on: bool) -> str:
    label = {"live": "WORKING ON REAL CALLS", "testing": "BUILT, BEING TESTED"}
    steps = "".join(f'<li><h3>{esc(en)}</h3><div class="t">{esc(te)}</div><p>{esc(text)}</p>'
                    f'<span class="st {st}">{label[st]}</span></li>' for en, te, text, st in STEPS)
    bubble = (f'<div class="bubble">{PHONE_ICON}<p class="te" lang="te">{esc(WARNING_TE)}</p>'
              f'<p class="en">"{esc(WARNING_EN)}"</p></div>')
    stats = "".join(f'<div class="num"><b>{esc(n)}</b><p>{esc(text)}</p><div class="src">Source: '
                    f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(src)}</a></div></div>'
                    for n, text, src, url in STATS)
    payers = "".join(f'<article><div class="k">{i}. {esc(k)}</div><h3>{esc(who)}</h3><p>{esc(text)}</p></article>'
                     for i, (who, k, text) in enumerate(PAYERS, 1))
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
<header class="big"><img src="/gs_hero_airport.webp" alt="A worker at the airport on the phone, his mother and wife beside him">
<p class="cap">{AI_PHOTO}</p><div class="wrap"><div class="txt">
  <h1>A trapped worker's only evidence is a selfie video. Saathi records the evidence before the trap.</h1>
  <p class="te">మీ గల్ఫ్ ప్రయాణంలో ప్రతి అడుగులో తోడుగా సాథి.</p>
  <p>A Telugu phone call that checks the agent, the fee and the visa before he pays, then calls him on arrival day and
  every week, and alerts his family when something goes wrong.</p>
  <a class="btn" href="#call">Get a call from Saathi</a> <a class="btn ghost" href="#watch">Watch the demo</a><br>
  <span class="badge">Voice by Bolna · Telugu speech by Sarvam · Prototype</span>
</div></div></header>

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
        <li>Pays the agent in cash, no record</li><li>A stranger picks him up</li>
        <li>The family learns from a video, too late</li></ul></div>
      <div class="with"><h3>With Saathi</h3><ul>
        <li>Wrong visa flagged before he flies</li><li>Arrival call: wrong pickup = CRITICAL</li>
        <li>Weekly calls catch "herding goats" = HIGH</li></ul></div>
    </div>
    <p><a href="/demo">Run this story on the demo →</a></p>
  </div>
</div></section>

<section id="how"><div class="wrap">
  <h2>How it works</h2>
  <p class="lede">One phone number, in Telugu, at every step of the journey. No app, no reading needed.</p>
  <ol class="timeline">{steps}</ol>
  <p class="honest" style="margin-top:18px">The AI only writes down what was said. Fixed rules decide the risk level.</p>
  <details class="more"><summary>Show how it is built</summary>{architecture()}</details>
</div></section>

<section id="repeat-agent"><div class="wrap">
  <h2>How Saathi catches a repeat scam agent</h2>
  <p class="lede">Sub-agents cheat family after family with the same phone number or UPI account. Each family complains
  alone. Saathi connects the reports and warns the next family before they pay.</p>
  <span class="label">Example. Made-up names and number.</span>
  <div class="netbox" id="case-network">{case_network()}
  <p class="src" style="margin:12px 0 0">Saathi links cases only by exact phone numbers or payment accounts. A link is a lead
  for a caseworker to review, not proof against anyone.</p></div>
  <div class="hear"><div class="hl">What caller 5 hears, live</div>{bubble}</div>
  <p class="honest" style="margin-top:10px">Callers hear only a count, never names. Proven on a real Bolna call; the
  multi-caller flow is tested in code.</p>
</div></section>

<section id="who"><div class="wrap">
  <h2>Who it helps</h2>
  <div class="who">
    <article><img src="/gs_family_sms.webp" alt="A mother at home reading a message on her phone" loading="lazy">
      <div class="in"><p class="cap" style="margin:0 0 8px">{AI_PHOTO}</p><h3>Family</h3>
      <p>Hears in Telugu when something is wrong, not months later.</p></div></article>
    <article><img src="/gs_caseworker.webp" alt="A caseworker with a headset at a laptop" loading="lazy">
      <div class="in"><p class="cap" style="margin:0 0 8px">{AI_PHOTO}</p><h3>Volunteers and caseworkers</h3>
      <p>A ready case: who, where, which agent, what was promised.</p></div></article>
    <article><div class="plain"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5h17l9 9v13"/><path d="M29 5v9h9"/><path d="M12 5v38h16"/><path d="M18 20h12M18 27h8"/><path d="M38 31l-7 3v5c0 4 3 6.5 7 8 4-1.5 7-4 7-8v-5z"/><path d="M35 39.5l2.2 2.2 4-4.2"/></svg><span>Police · TOMCOM · State</span></div>
      <div class="in"><h3><span class="mini"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5h17l9 9v13"/><path d="M29 5v9h9"/><path d="M12 5v38h16"/><path d="M18 20h12M18 27h8"/><path d="M38 31l-7 3v5c0 4 3 6.5 7 8 4-1.5 7-4 7-8v-5z"/><path d="M35 39.5l2.2 2.2 4-4.2"/></svg></span>Government</h3>
      <p>An evidence trail, built one call at a time. A prototype, not a government service.</p></div></article>
  </div>
</div></section>

<section id="who-pays"><div class="wrap">
  <h2>Why this matters, and who pays</h2>
  <div class="stats">{stats}</div>
  <p class="src" style="margin-top:12px">Also: 3,647 Indian women were sent home from Oman, 2021–25.
  Source: <a href="https://www.mea.gov.in/rajya-sabha.htm?dtl/40875/QUESTION+NO+2319+INDIAN+WOMEN+RESCUED+AND+REPATRIATED"
  target="_blank" rel="noopener">Rajya Sabha Q. 2319, Mar 2026</a>
  (also reported by <a href="https://timesofindia.indiatimes.com/city/chandigarh/over-10k-women-rescued-from-7-gulf-countries-in-5-yrs-rs-told/articleshow/129519566.cms"
  target="_blank" rel="noopener">Times of India, 13 Mar 2026</a>)</p>
  <details class="more"><summary>Show who pays</summary>
  <span class="label big-label" style="margin-top:16px">Proposed model, not yet in place.</span>
  <div class="pay" style="margin-top:4px">{payers}</div>
  <p class="lede" style="margin-top:18px">Telugu today. Built so new languages and routes (Nepal, Bangladesh) can be added.</p>
  </details>
</div></section>

<section id="numbers"><div class="wrap">
  <h2>Demo dashboard</h2>
  <div class="tiles">{tiles}</div>
  {demo_note}
  <div class="shotwrap"><div class="shotbox"><img src="/gs_dashboard.webp" alt="The caseworker dashboard showing a made-up demo case marked CRITICAL, with its red flags" loading="lazy"></div>
  <p class="cap">Screenshot of the caseworker view with made-up demo cases.</p></div>
  <p style="margin-top:14px"><a class="btn ghost" href="/dashboard">Open caseworker view</a></p>
</div></section>

<section id="call"><div class="wrap callbox">
  <h2>Get a call from Saathi</h2>
  <p>Saathi will call your phone in Telugu. Ask it to check an agent's name or a fee. Indian numbers only for now.</p>
  {call_form}
  <p class="honest" style="color:#b9c4cf">Say "తెలుగు" when Saathi answers. Calls are recorded to help your case; agent numbers
  you mention warn other callers as a count, never with your name. Trial account: may only call verified numbers; Gulf
  numbers not tested yet.</p>
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
