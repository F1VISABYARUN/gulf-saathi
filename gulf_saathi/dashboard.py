"""Server-rendered dashboard pages. Plain HTML, no build step.

Every value from the database goes through esc(), since names, transcripts
and notes come from callers.
"""
from __future__ import annotations

from html import escape

from .cases import (CODE_PHRASE_HELP, promise_said, EX_GRATIA_STATUSES, GENDERS, IST, REMAINS_STATUSES, code_phrase_ok, fmt_ist,
                    parse_ts, reason_text)
from .fees import fmt_rupees
from .promise import STOP_FLAGS, VISA_TYPES, predeparture_checks, promise_rows

BADGE = {"critical": "#b42318", "high": "#c4320a", "medium": "#a15c07", "ok": "#067647"}
PICKUP = {"employer": "Registered employer", "other_person": "Someone else", "nobody": "Nobody came",
          "not_arrived": "Not arrived yet"}
ANSWER_LABELS = [
    ("pickup_status", "Who picked them up"), ("pickup_person", "Person at pickup"),
    ("current_location", "Where they are now"), ("current_job", "Work they are doing now"),
    ("current_city", "City they are in now"), ("landmark", "Nearby place"), ("home_district", "Home village / district"),
    ("agent_name", "Agent (as said)"), ("agent_phone", "Agent phone (as said)"), ("salary_received", "Salary received"),
    ("salary_amount", "Salary amount received"), ("papers_problem", "Papers problem (visa / iqama / absconding)"),
    ("months_unpaid", "Months unpaid"), ("passport_with_worker", "Passport with worker"),
    ("food_ok", "Food and room OK"), ("threatened", "Threats or violence"),
    ("movement_restricted", "Stopped from going out"), ("employer_changed", "Moved to another employer / house"),
    ("needs_help", "Asked for help"),
    ("code_phrase_used", "Said the danger phrase"), ("briefing_understood", "Understood the briefing"),
    ("notes", "Notes"),
]


def esc(v) -> str:
    return escape("" if v is None else str(v))


def badge(level: str) -> str:
    level = level or "ok"
    return f'<span class="badge" style="background:{BADGE.get(level, "#475467")}">{esc(level.upper())}</span>'


def page(title: str, body: str, refresh: int | None = None) -> str:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>{esc(title)} · Gulf Saathi</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {{ --ink:#101828; --muted:#475467; --line:#e4e7ec; --bg:#f9fafb; --card:#fff; --accent:#1d4ed8; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Telugu","Nirmala UI",sans-serif; color:var(--ink); background:var(--bg); }}
header {{ background:#0b1f3a; color:#fff; padding:12px 16px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
header a {{ color:#fff; text-decoration:none; font-weight:600; }}
header .sp {{ flex:1; }}
main {{ max-width:1100px; margin:0 auto; padding:16px; }}
h1 {{ font-size:22px; margin:8px 0 16px; }} h2 {{ font-size:17px; margin:0 0 12px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:16px; }}
.badge {{ color:#fff; border-radius:999px; padding:2px 10px; font-size:12px; font-weight:700; letter-spacing:.03em; white-space:nowrap; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
.wrap {{ overflow-x:auto; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:4px 24px; }}
.kv {{ padding:4px 0; }} .kv b {{ display:block; font-size:12px; color:var(--muted); font-weight:600; }}
.muted {{ color:var(--muted); }} a {{ color:var(--accent); }}
.btn {{ display:inline-block; border:1px solid var(--accent); background:var(--accent); color:#fff; border-radius:8px; padding:8px 14px; font:inherit; cursor:pointer; text-decoration:none; }}
.btn.secondary {{ background:#fff; color:var(--accent); }}
.btn:disabled {{ opacity:.5; cursor:wait; }}
.ev {{ border-left:3px solid var(--line); padding:4px 0 12px 12px; margin-left:4px; }}
.ev.alert {{ border-color:#b42318; }}
pre {{ white-space:pre-wrap; background:var(--bg); padding:10px; border-radius:8px; font:13px/1.5 inherit; }}
form label {{ display:block; font-size:13px; font-weight:600; margin-top:10px; }}
form input, form textarea {{ width:100%; padding:8px; border:1px solid #d0d5dd; border-radius:8px; font:inherit; }}
fieldset {{ border:1px solid var(--line); border-radius:10px; margin:0 0 16px; padding:8px 16px 16px; }}
legend {{ font-weight:700; padding:0 6px; }}
#msg {{ margin-top:12px; font-weight:600; }}
.nowrap {{ white-space:nowrap; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:16px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.tile b {{ display:block; font-size:26px; line-height:1.2; }} .tile span {{ font-size:13px; color:var(--muted); }}
.tile.warn b {{ color:#b42318; }}
.flag {{ color:#b42318; font-size:13px; font-weight:600; }}
.sms {{ background:#fef3f2; border:1px solid #fecdca; border-radius:8px; padding:10px; }}
.sms.info {{ background:#f0f9ff; border-color:#b9e6fe; }}
.stop {{ background:#b42318; color:#fff; border-radius:8px; padding:10px 14px; font-weight:700; margin:8px 0; }}
.demo {{ background:#fef0c7; color:#93370d; border-radius:999px; padding:1px 8px; font-size:11px; font-weight:700; letter-spacing:.04em; }}
.v-conflict {{ color:#b42318; font-weight:700; }} .v-match {{ color:#067647; }} .v-unknown {{ color:var(--muted); }}
select {{ width:100%; padding:8px; border:1px solid #d0d5dd; border-radius:8px; font:inherit; background:#fff; }}
</style></head><body>
<header><a href="/">Gulf Saathi</a><a href="/dashboard">Cases</a><a href="/dashboard/agents">Agents</a><a href="/demo">Demo story</a><span class="sp"></span><a href="/dashboard/new">+ Register worker</a></header>
<main>{body}</main>
<script>
async function post(url, body, btn, okText) {{
  if (btn) btn.disabled = true;
  const msg = document.getElementById('msg');
  try {{
    const r = await fetch(url, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(body||{{}})}});
    const j = await r.json().catch(() => ({{}}));
    if (!r.ok) throw new Error(j.detail || r.status);
    if (msg) msg.textContent = okText || 'Done';
    return j;
  }} catch (e) {{ if (msg) msg.textContent = 'Failed: ' + e.message; if (btn) btn.disabled = false; }}
}}
</script></body></html>"""


def predeparture_flags(w: dict) -> list[str]:
    """Problems found at registration, before the worker flies."""
    return [f["text"] for f in predeparture_checks(w)]


def case_badge(w: dict) -> str:
    """Risk badge. A worker still in India with no risk yet but with red flags shows
    RED FLAGS, not a green OK next to a "do not travel" warning."""
    if (w.get("risk_level") or "ok") == "ok" and w.get("status") == "registered" and predeparture_checks(w):
        return '<span class="badge" style="background:#b42318">RED FLAGS</span>'
    return badge(w.get("risk_level"))


def demo_tag(w: dict) -> str:
    return ' <span class="demo">DEMO</span>' if w.get("is_demo") else ""


def signals_table(signals: list[dict], intro: bool = True) -> str:
    """The same phone number, payment account or sponsor in several cases. A reason
    to look, never a finding."""
    if not signals:
        return "<p class='muted'>No phone number, payment account or sponsor appears in more than one case.</p>"
    rows = []
    for g in signals:
        cases = " ".join(f'<a class="nowrap" href="/dashboard/case/{esc(c)}">{esc(c)}</a>' for c in g["cases"])
        weak = '' if g.get('strong', True) else ' <span class="muted" style="font-size:12px">(weak: company names can repeat)</span>'
        where = f'<div class="muted" style="font-size:12px">Agent districts: {esc(", ".join(g["districts"]))}</div>' if g.get('districts') else ''
        rows.append(f"""<tr><td>{esc(g['label'])}{weak}{' <span class="demo">DEMO DATA</span>' if g['demo'] else ''}</td>
<td><b>{esc(g['value'])}</b></td><td>Seen in {len(g['cases'])} cases<div class="muted" style="font-size:12px">{cases}</div>{where}</td>
<td>{esc(g['at_risk']) if g['at_risk'] else '<span class="muted">0</span>'}</td>
<td>{esc(g['flagged']) if g['flagged'] else '<span class="muted">0</span>'}</td></tr>""")
    note = ("<p class='muted'>Seen in more than one case: needs a person to review. This is not a finding of fraud "
            "against anyone. Names are not matched, only phone numbers, payment accounts and sponsor IDs.</p>") if intro else ""
    return note + f"""<div class="wrap"><table><thead><tr><th>What</th><th>Value</th><th>Cases</th><th>At risk now</th>
<th>Pre-departure red flags</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


def promise_table(w: dict, latest_answers: dict) -> str:
    out = []
    word = {"conflict": "Does not match", "match": "Matches", "unknown": "Not enough to compare"}
    for r in promise_rows(w, latest_answers):
        cell = lambda v: esc(v) if v not in (None, "") else "<span class='muted'>—</span>"
        out.append(f"<tr><td class='muted'>{esc(r['what'])}</td><td>{cell(r['promised'])}</td><td>{cell(r['papers'])}</td>"
                   f"<td>{cell(r['now'])}</td><td class='v-{r['verdict']}'>{word[r['verdict']]}</td></tr>")
    return ("<div class='wrap'><table><thead><tr><th></th><th>Agent promised</th><th>Visa papers say</th>"
            "<th>Worker says now</th><th>Check</th></tr></thead><tbody>" + "".join(out) + "</tbody></table></div>"
            "<p class='muted' style='font-size:13px'>\"Visa papers\" is what a helper typed from the visa. "
            "\"Now\" is from the latest arrival, weekly or help call. Fixed word lists decide the match; the AI only writes down what was said.</p>")


def tiles(totals: dict) -> str:
    items = [("registered", "Workers registered", False), ("in_india", "Still in India", False),
             ("abroad", "Abroad", False), ("briefed", "Pre-departure briefing done", False),
             ("at_risk", "At risk now (HIGH or CRITICAL)", True), ("red_flags", "Pre-departure red flags", True)]
    return '<div class="tiles">' + "".join(
        f'<div class="tile{" warn" if warn and totals.get(k) else ""}"><b>{esc(totals.get(k, 0))}</b><span>{esc(label)}</span></div>'
        for k, label, warn in items) + "</div>"


def search_workers(workers: list[dict], q: str) -> list[dict]:
    """Find a case by name, phone digits, case number, employer, sponsor, place or notes.
    For the embassy or a volunteer asking "whose family is this?"."""
    q = " ".join((q or "").lower().split())
    if not q:
        return workers
    digits = "".join(ch for ch in q if ch.isdigit())
    keys = ("case_id", "worker_name", "worker_name_te", "employer_name", "sponsor_name", "sponsor_id", "dest_city",
            "dest_country", "agent_name", "family_name", "notes")
    out = []
    for w in workers:
        text = " ".join(str(w.get(k) or "") for k in keys).lower()
        phones = "".join(str(w.get(k) or "") for k in ("worker_phone", "family_phone", "employer_phone"))
        if all(word in text for word in q.split()) or (len(digits) >= 6 and digits in phones):
            out.append(w)
    return out


def render_list(workers: list[dict], status: dict, totals: dict | None = None, q: str = "") -> str:
    shown = search_workers(workers, q)
    search = f"""<form method="get" action="/dashboard" class="card" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
<input name="q" value="{esc(q)}" placeholder="Find a case: name, phone, employer, sponsor, city" style="flex:1;min-width:220px">
<button class="btn" type="submit">Find</button>{' <a href="/dashboard">Show all</a>' if q else ''}
<span class="muted" style="font-size:13px;flex-basis:100%">For the embassy or a volunteer asking whose family a worker is.</span></form>"""
    workers_all, workers = workers, shown
    rows = []
    order = {"critical": 0, "high": 1, "medium": 2, "ok": 3}
    # Most serious first; within a level, most recently updated first.
    by_recent = sorted(workers, key=lambda w: w.get("updated_at") or "", reverse=True)
    for w in sorted(by_recent, key=lambda w: order.get(w.get("risk_level"), 3)):
        rows.append(f"""<tr>
<td>{case_badge(w)}</td>
<td class="nowrap"><a href="/dashboard/case/{esc(w['case_id'])}"><b>{esc(w['case_id'])}</b></a></td>
<td>{esc(w['worker_name'])}{demo_tag(w)}<div class="muted">{esc(w.get('worker_phone'))}</div>{''.join(f'<div class="flag">{esc(f)}</div>' for f in predeparture_flags(w))}</td>
<td>{esc(w.get('dest_city'))}{', ' if w.get('dest_city') and w.get('dest_country') else ''}{esc(w.get('dest_country'))}</td>
<td>{esc(w.get('employer_name'))}</td>
<td>{esc(w.get('status'))}</td>
<td>{esc(fmt_ist(w.get('last_contact_at')))}</td>
<td>{esc(w.get('missed_checkins') or 0)}</td>
<td>{esc(fmt_ist(w.get('next_call_at')))}</td></tr>""")
    empty = (f"<p class='muted'>No case matches \"{esc(q)}\".</p>" if q else
             "<p class='muted'>No workers yet. <a href='/dashboard/new'>Register the first one</a>.</p>")
    table = (empty if not rows else
             f"""<div class="wrap"><table><thead><tr><th>Risk</th><th>Case</th><th>Worker</th><th>Destination</th>
<th>Employer</th><th>Status</th><th>Last contact</th><th>Missed</th><th>Next call</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>""")
    counts = {lvl: sum(1 for w in workers_all if (w.get("risk_level") or "ok") == lvl) for lvl in order}
    summary = " &nbsp; ".join(f"{badge(l)} {counts[l]}" for l in order)
    return page("Cases", f"""<h1>Cases</h1>{tiles(totals) if totals else ""}
<div class="card">{summary}<div class="muted" style="margin-top:8px">{status_line(status)} · refreshes every 15 seconds</div></div>
{search}<div class="card">{table}</div>
<script>
setInterval(() => {{ if (!document.querySelector('input:focus')) location.reload(); }}, 15000);
</script>""")


def reported_table(rows: list[dict]) -> str:
    if not rows:
        return "<p class='muted'>No agent numbers reported on calls yet.</p>"
    out = []
    for g in rows:
        amt = f"Rs {fmt_rupees(int(g['max_amount']))}" if g.get("max_amount") else "—"
        out.append(f"""<tr><td>{esc(g['kind'])}</td><td><b>{esc(g['value'])}</b></td>
<td>{esc(g['callers'])} caller(s){f'<div class="muted" style="font-size:12px">{esc(g["family_reports"])} from families</div>' if g['family_reports'] else ''}</td>
<td>{esc(', '.join(g['districts'])) or '<span class="muted">—</span>'}</td>
<td>{esc(g['over_limit']) or '<span class="muted">0</span>'}<div class="muted" style="font-size:12px">highest asked: {esc(amt)}</div></td>
<td>{esc(g['visit_visa']) or '<span class="muted">0</span>'}</td>
<td>{esc(g['cases'])} case(s){f' · <span class="flag">{esc(g["at_risk"])} at risk</span>' if g['at_risk'] else ''}</td>
<td class="nowrap">{esc(g['first_seen'])} → {esc(g['last_seen'])}</td></tr>""")
    return f"""<div class="wrap"><table><thead><tr><th>What</th><th>Value</th><th>Reported by</th><th>Caller districts</th>
<th>Asked over limit</th><th>Visit visa offered</th><th>Linked cases</th><th>Seen</th></tr></thead><tbody>{''.join(out)}</tbody></table></div>"""


def render_agents(stats: list[dict], signals: list[dict] | None = None, reported: list[dict] | None = None) -> str:
    rows = []
    for g in stats:
        listed = ('<span class="muted">in licensed list</span>' if g["licensed"] else
                  '<span class="flag">not found in licensed list</span>' if g["not_in_list"] else
                  '<span class="muted">not confirmed</span>')
        cases = " ".join(f'<a class="nowrap" href="/dashboard/case/{esc(c)}">{esc(c)}</a>' for c in g["case_ids"])
        risk = (f'{badge("critical")} {g["critical"]} ' if g["critical"] else "") + \
               (f'{badge("high")} {g["at_risk"] - g["critical"]}' if g["at_risk"] - g["critical"] else "")
        rows.append(f"""<tr><td><b>{esc(g['agent'])}</b><div>{listed}</div></td>
<td>{esc(g['cases'])}<div class="muted" style="font-size:12px">{cases}</div></td>
<td>{risk or '<span class="muted">—</span>'}</td>
<td>{esc(g['over_cap']) if g['over_cap'] else '<span class="muted">—</span>'}</td>
<td>{esc(', '.join(g['districts'])) or '<span class="muted">—</span>'}</td>
<td>{'<br>'.join(esc(e) for e in g['employers']) or '<span class="muted">—</span>'}</td></tr>""")
    table = ("<p class='muted'>No agents recorded yet.</p>" if not rows else
             f"""<div class="wrap"><table><thead><tr><th>Agent</th><th>Workers</th><th>At risk now</th>
<th>Paid over limit</th><th>District</th><th>Employers abroad</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>""")
    return page("Agents", f"""<h1>Agents behind our cases</h1>
<p class="muted">Every recruiting agent named in a Saathi case, riskiest first: how many of their workers are in trouble now,
how many paid over the Rs 35,400 limit, and which employers abroad they sent people to. This describes our cases, not a
finding about any agent.</p>
<div class="card">{table}</div>
<h2>Saathi Intelligence: repeated across cases</h2>
<p class="muted">Exact matches on agent phones, payment accounts, sponsor IDs and employer phones (strong), and employer
name plus country (weak). A link is a lead for a trained investigator, not proof. Workers checking a number on a call hear
only a count, never names or case numbers, and never from demo data.</p>
<div class="card">{signals_table(signals or [])}</div>
<h2>Agent numbers reported on calls</h2>
<p class="muted">Every agent phone or payment account a worker or family told Saathi, even if they never registered a case.
Counted once per caller. Who owns a number can only be found by the telecom company or the police: share these with the police
cyber cell or in an eMigrate complaint, never publicly.</p>
<div class="card">{reported_table(reported or [])}</div>""")


def status_line(status: dict) -> str:
    parts = [f"Storage: {esc(status['storage'])}", f"Bolna calls: {'on' if status['bolna'] else 'NOT configured'}",
             f"SMS: {esc(status['sms'])}"]
    return " · ".join(parts)


FIELDS = [
    ("Worker", [("worker_name", "Name (English) *", "Yadaiah"), ("worker_name_te", "Name in Telugu (for the family SMS)", "యాదయ్య"),
                ("worker_phone", "Worker phone *", "98765 43210"), ("code_phrase", "Danger code phrase", "అమ్మ బాగుందా"),
                ("worker_gender", "Woman or man", ""), ("worker_age", "Age", "34")]),
    ("Family", [("family_name", "Family member name", "Lakshmi"), ("family_relation", "Relation", "wife"),
                ("family_phone", "Family phone *", "91234 56780")]),
    ("Employer and sponsor", [("employer_name", "Employer / company", "Al Noor Cleaning LLC"),
                              ("employer_phone", "Employer phone (with country code)", "+971 50 123 4567"),
                              ("sponsor_name", "Sponsor (kafeel) name", ""), ("sponsor_id", "Sponsor ID", ""),
                              ("dest_country", "Country", "UAE"), ("dest_city", "City", "Dubai"),
                              ("job_title", "Job the agent promised", "Cleaner"), ("contract_salary", "Contract salary", "1500"),
                              ("salary_currency", "Currency", "AED")]),
    ("Recruiting agent", [("agent_name", "Agency name", "Gagan Manpower"), ("agent_owner", "Owner name", "Bolle Ganga Narsaiah"),
                          ("agent_district", "Agent's district", "Jagtial"), ("agent_licence", "Licence / RA number", ""),
                          ("sub_agent_name", "Village sub-agent name", ""),
                          ("sub_agent_phone", "Village sub-agent phone", "98480 12345"),
                          ("payments", "Every payment to the agent, separated by ;", "50000; 30000"),
                          ("payment_to", "Money paid to (UPI ID / account / phone)", "agent@upi"),
                          ("promise_by", "Who made the verbal promise", "sub-agent Ramu"),
                          ("promise_words", "What they said, in their own words (not what the papers say)",
                           "salary 1,500 riyal, cleaning job, free food"),
                          ("promise_date", "When they said it", "10 Oct 2026"),
                          ("contract_before_payment", "Got the full written contract before paying?", ""),
                          ("call_consent", "Worker agreed to recorded Saathi calls?", "")]),
    ("Visa papers (type exactly what the visa says)", [("visa_type", "Visa type", ""),
                                                       ("visa_job", "Job written on the visa", "Agricultural worker")]),
    ("Travel", [("departure_date", "Departure date", ""), ("flight_no", "Flight", "EK 527"),
                ("arrival_call_at", "Arrival-day call (India time)", "")]),
]


def _form_value(name: str, values: dict):
    """A stored value as the form field expects it."""
    v = values.get(name)
    if v in (None, ""):
        return ""
    if name == "payments":
        return "; ".join(str(x) for x in v) if isinstance(v, list) else v
    if name == "arrival_call_at":
        dt = parse_ts(v)
        return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M") if dt else ""
    if name == "contract_salary" and isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def render_form(values: dict | None = None, case_id: str | None = None) -> str:
    """Registration form; with values and a case ID it edits that case instead."""
    values = values or {}
    sets = []
    for legend, fields in FIELDS:
        inputs = []
        for name, label, ph in fields:
            if name in ("visa_type", "worker_gender", "contract_before_payment", "call_consent"):
                current = _form_value(name, values)
                choices = {"visa_type": VISA_TYPES, "worker_gender": GENDERS}.get(name, ("yes", "no"))
                opts = "".join(f'<option value="{t}"{" selected" if current == t else ""}>{t}</option>'
                               for t in ("", *choices))
                inputs.append(f'<div><label for="{name}">{esc(label)}</label><select id="{name}" name="{name}">{opts}</select></div>')
                continue
            kind = "date" if name == "departure_date" else "datetime-local" if name == "arrival_call_at" else "text"
            hint = f'<div class="muted" style="font-size:12px">{esc(CODE_PHRASE_HELP)}</div>' if name == "code_phrase" else ""
            inputs.append(f'<div><label for="{name}">{esc(label)}</label>'
                          f'<input id="{name}" name="{name}" type="{kind}" value="{esc(_form_value(name, values))}" '
                          f'placeholder="{esc("e.g. " + ph if ph else "")}">{hint}</div>')
        sets.append(f'<fieldset><legend>{esc(legend)}</legend><div class="grid">{"".join(inputs)}</div></fieldset>')
    if case_id:
        title, intro, url, button, done = (
            f"Edit {case_id}", f"Correct the details of case {esc(case_id)}. The case number, timeline and alerts stay as they are.",
            f"/api/cases/{esc(case_id)}", "Save changes", "Saved")
    else:
        title, intro, url, button, done = (
            "Register a worker before departure",
            "This is the evidence trail. If the worker goes missing, the family and embassy start from these names and numbers. "
            "If an arrival-day call time is set, Saathi books that call with Bolna.",
            "/api/workers", "Register", "Registered")
    return page(title, f"""<h1>{esc(title)}</h1>
<p class="muted">{intro}</p>
<form id="f" class="card" onsubmit="return false">{''.join(sets)}
<label for="notes">Notes</label><textarea id="notes" name="notes" rows="3">{esc(values.get('notes'))}</textarea>
<p><button class="btn" id="go" type="submit">{button}</button></p><div id="msg"></div></form>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  const data = Object.fromEntries(new FormData(e.target).entries());
  const j = await post('{url}', data, document.getElementById('go'), '{done}');
  if (j && j.case_id) location.href = '/dashboard/case/' + j.case_id;
}});
</script>""")


def render_new() -> str:
    return render_form()


def _answers_table(answers: dict) -> str:
    rows = []
    for key, label in ANSWER_LABELS:
        v = answers.get(key)
        if v in (None, ""):
            continue
        if key == "pickup_status":
            v = PICKUP.get(v, v)
        elif isinstance(v, bool):
            v = "Yes" if v else "No"
        rows.append(f"<tr><td class='muted'>{esc(label)}</td><td><b>{esc(v)}</b></td></tr>")
    return f"<table>{''.join(rows)}</table>" if rows else "<span class='muted'>No answers recorded</span>"


def render_case(w: dict, events: list[dict], status: dict, signals: list[dict] | None = None,
                alert: dict | None = None) -> str:
    kv = lambda label, value: f'<div class="kv"><b>{esc(label)}</b>{esc(value) if value not in (None, "") else "<span class=muted>—</span>"}</div>'
    reasons = "".join(f"<li>{esc(reason_text(r))}</li>" for r in (w.get("risk_reasons") or []))
    fee = ""
    if w.get("amount_paid_total"):
        over = w.get("fee_status") == "over_cap"
        fee = f"Rs {fmt_rupees(int(w['amount_paid_total']))} ({'OVER' if over else 'within'} the Rs 35,400 limit)"
    salary = w.get("contract_salary")
    if isinstance(salary, float) and salary.is_integer():
        salary = int(salary)
    checks = predeparture_checks(w)
    flags = "".join(f'<p class="flag">{esc(f["text"])}</p>' for f in checks)
    if w.get("status") == "registered" and any(f["code"] in STOP_FLAGS for f in checks):
        flags = ('<div class="stop">Tell the worker: do not pay the agent any more money and do not travel until this '
                 'is sorted out.</div>') + flags
    # Latest answers from a call made after arrival, for the "worker says now" column.
    latest = next((e["checkin"].get("answers") or {} for e in events
                   if e["type"] == "checkin" and e["checkin"].get("kind") in ("arrival", "weekly", "help")), {})
    candidates = (w.get("agent_check_detail") or {}).get("candidates") or []
    matched = "; ".join(f"{c['agency']} ({c['owner']}, {c['district']})" for c in candidates)

    evs = []
    for e in events:
        when = esc(fmt_ist(e["at"]))
        if e["type"] == "registered":
            evs.append(f'<div class="ev"><b>{when}</b> · Registered before departure</div>')
        elif e["type"] == "call":
            c = e["call"]
            state = "answered" if c.get("answered") else "MISSED" if c.get("missed") else (c.get("status") or "")
            when_call = fmt_ist(c.get("scheduled_at")) if c.get("status") == "scheduled" else None
            rec = f' · <a href="{esc(c["recording_url"])}" target="_blank" rel="noopener">Recording</a>' if c.get("recording_url") else ""
            tr = f"<details><summary>Transcript</summary><pre>{esc(c['transcript'])}</pre></details>" if c.get("transcript") else ""
            dur = f" · {int(c['duration_seconds'])}s" if c.get("duration_seconds") else ""
            booked = f" for {esc(when_call)}" if when_call else ""
            evs.append(f'<div class="ev"><b>{when}</b> · {esc((c.get("kind") or "call").title())} call · {esc(state)}{booked}{dur}{rec}{tr}</div>')
        elif e["type"] == "checkin":
            ch = e["checkin"]
            evs.append(f'<div class="ev"><b>{when}</b> · Answers from {esc(ch.get("kind"))} call {badge(ch.get("risk_level"))}'
                       f'{_answers_table(ch.get("answers") or {})}</div>')
        else:
            es = e["escalation"]
            rs = "; ".join(reason_text(r) for r in es.get("reasons") or [])
            action = (f'<button class="btn secondary" onclick="post(\'/api/escalations/{esc(es["id"])}/resolve\', {{}}, this, '
                      f'\'Marked resolved\').then(() => location.reload())">Mark resolved</button>' if es.get("status") == "open"
                      else f'<span class="muted">Resolved {esc(fmt_ist(es.get("resolved_at")))}</span>')
            evs.append(f'<div class="ev alert"><b>{when}</b> · ALERT {badge(es["level"])} {esc(rs)}'
                       f'<div class="sms" style="margin:8px 0"><b>Family SMS</b> ({esc(es.get("sms_status"))}):<br>{esc(es.get("family_sms"))}</div>'
                       f'{action}</div>')

    calls_disabled = ("disabled title='A death was reported: Saathi does not call this number'" if w.get("death_reported_at") else
                      "disabled title='Demo case: Saathi never calls demo numbers'" if w.get("is_demo") else
                      "" if status["bolna"] else "disabled title='Bolna is not configured'")
    case_id = esc(w["case_id"])

    briefings = [e["checkin"] for e in events if e["type"] == "checkin" and e["checkin"].get("kind") == "briefing"]
    if briefings:
        understood = (briefings[0].get("answers") or {}).get("briefing_understood")
        briefing = (f"Briefing: done {esc(fmt_ist(briefings[0]['created_at']))}"
                    + {True: " (understood)", False: " (did NOT understand: repeat it)"}.get(understood, ""))
    else:
        briefing = "Briefing: not done yet"

    # Things the caseworker should fix or do, shown above everything else.
    notices = []
    arrival_at = w.get("arrival_call_at")
    arrival_booked = any(e["type"] == "call" and e["call"].get("kind") == "arrival" for e in events)
    if arrival_at and not arrival_booked:
        why = "" if status["bolna"] else " Bolna is not set up yet (BOLNA_CHECKIN_AGENT_ID)."
        notices.append(f'<p class="flag">Arrival-day call for {esc(fmt_ist(arrival_at))} is not booked.{esc(why)} '
                       f'<button class="btn secondary" {calls_disabled} onclick="post(\'/api/cases/{case_id}/book-arrival\', {{}}, this, '
                       f'\'Booked\').then(j => j && location.reload())">Book arrival call</button></p>')
    if not code_phrase_ok(w.get("code_phrase")):
        notices.append(f'<p class="flag">Danger code phrase "{esc(w.get("code_phrase"))}" is too easy to say by accident. '
                       f'{esc(CODE_PHRASE_HELP)}. <a href="/dashboard/case/{case_id}/edit">Edit details</a></p>')
    if not w.get("worker_name_te"):
        notices.append(f'<p class="muted">The family SMS will use the English name. Add the name in Telugu: '
                       f'<a href="/dashboard/case/{case_id}/edit">Edit details</a></p>')
    welcome = (f'<div class="sms info" style="margin-top:12px"><b>Welcome SMS to family</b> ({esc(w.get("welcome_sms_status"))}):'
               f'<br>{esc(w["welcome_sms"])}</div>' if w.get("welcome_sms") else "")
    sig = (f'<div class="card"><h2>Repeated across cases</h2>{signals_table(signals)}</div>' if signals else "")
    embassy = ""
    dead = bool(w.get("death_reported_at"))
    if alert and (dead or w.get("risk_level") in ("high", "critical")):
        from urllib.parse import quote
        mailto = f"mailto:?subject={quote(alert['subject'])}&body={quote(alert['body'])}"
        heading, why = (("Tell the Indian Embassy about the death", "Saathi told the family a caseworker will inform the embassy.")
                        if dead else ("Alert the Indian Embassy now", "Saathi told the worker a caseworker will take the case to the embassy."))
        embassy = f"""<div class="card" style="border-color:#b42318"><h2>{heading}</h2>
<p class="muted">{why} Send this to the Indian Embassy or Consulate in
{esc(w.get('dest_country') or 'that country')} (community welfare email or helpline) and register it on MADAD. Saathi cannot send it by itself.</p>
<pre id="alert">{esc(alert['subject'])}\n\n{esc(alert['body'])}</pre>
<p><button class="btn" onclick="navigator.clipboard.writeText(document.getElementById('alert').innerText).then(() => this.textContent = 'Copied')">Copy alert</button>
<a class="btn secondary" href="{esc(mailto)}">Open in email</a>
<a class="btn secondary" href="https://madad.gov.in" target="_blank" rel="noopener">Open MADAD</a></p></div>"""
    death = death_card(w) if dead else ""
    record_death = "" if dead else f"""<details class="card"><summary><b>Record a death report</b>
<span class="muted">(if the employer, embassy or a volunteer tells you the worker died)</span></summary>
<form onsubmit="return false"><div class="grid">
<div><label for="d_by">Who reported it</label><input id="d_by" placeholder="e.g. employer, embassy, friend in Riyadh"></div>
<div><label for="d_from">They heard it from</label><input id="d_from" placeholder="name and phone, if known"></div>
<div><label for="d_place">Where</label><input id="d_place" placeholder="city, hospital"></div>
<div><label for="d_when">When</label><input id="d_when" placeholder="date"></div></div>
<label for="d_notes">What was said</label><textarea id="d_notes" rows="2"></textarea>
<p class="muted">This stops Saathi's calls to this number and opens a CRITICAL alert. The family is NOT sent an SMS:
a person must tell them.</p>
<p><button class="btn" onclick="post('/api/cases/{case_id}/death', {{reported_by: d_by.value, informed_by: d_from.value,
place: d_place.value, when: d_when.value, notes: d_notes.value}}, this, 'Recorded').then(j => j && location.reload())">Record death report</button></p>
</form></details>"""
    return page(w["case_id"], f"""<h1>{case_id} · {esc(w['worker_name'])}{demo_tag(w)} {case_badge(w)}</h1>
{death}
<div class="card">
  {f'<ul>{reasons}</ul>' if reasons else '<p class="muted">No current risk signals.</p>'}{flags}{''.join(notices)}
  <p>
    <button class="btn" {calls_disabled} onclick="post('/api/cases/{case_id}/call', {{kind:'arrival'}}, this, 'Arrival call requested')">Call now: arrival check</button>
    <button class="btn" {calls_disabled} onclick="post('/api/cases/{case_id}/call', {{kind:'weekly'}}, this, 'Weekly check-in call requested')">Call now: weekly check-in</button>
    <button class="btn" {calls_disabled} onclick="post('/api/cases/{case_id}/call', {{kind:'briefing'}}, this, 'Briefing call requested')">Call now: pre-departure briefing</button>
    <a class="btn secondary" href="/dashboard/case/{case_id}/packet.txt">Download English case packet</a>
    <a class="btn secondary" href="/dashboard/case/{case_id}/proof-of-work" target="_blank">Proof of work</a>
    <a class="btn secondary" href="/dashboard/case/{case_id}/edit">Edit details</a>
  </p><div id="msg"></div>
  <div class="muted">Status: {esc(w.get('status'))} · Last contact: {esc(fmt_ist(w.get('last_contact_at')))} ·
  Missed in a row: {esc(w.get('missed_checkins') or 0)} · Next call: {esc(fmt_ist(w.get('next_call_at')))} · {briefing} · refreshes every 20 seconds</div>
</div>
{embassy}
<div class="card"><h2>Pravasi Prajavani petition</h2>
<p class="muted">For families who cannot travel to Hyderabad: Saathi fills the petition from this case; a caseworker hands it in for them.
The caller hears the status when they call Saathi again.</p>
<p><a class="btn secondary" href="/dashboard/case/{case_id}/petition" target="_blank">Open petition (Telugu + English)</a></p>
<form onsubmit="return false" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
<label style="margin:0">Status<select id="pst">{''.join(f'<option value="{x}"{" selected" if w.get("petition_status") == x else ""}>{x}</option>' for x in ("prepared", "submitted", "acknowledged", "closed"))}</select></label>
<label style="margin:0">Reference no.<input id="pref" value="{esc(w.get('petition_ref'))}" placeholder="from the counter"></label>
<button class="btn" onclick="post('/api/cases/{case_id}/petition', {{status: document.getElementById('pst').value, ref: document.getElementById('pref').value}}, this, 'Saved').then(j => j && location.reload())">Save status</button>
</form>
<div class="muted" style="margin-top:6px">{esc(('Status: ' + w['petition_status'] + (' · handed in ' + fmt_ist(w.get('petition_submitted_at')) if w.get('petition_submitted_at') else '') + (' · ref ' + w['petition_ref'] if w.get('petition_ref') else '')) if w.get('petition_status') else 'Not prepared yet.')}</div>
</div>
<div class="card"><h2>Promise vs reality</h2>{promise_table(w, latest)}</div>
{sig}
<div class="card"><h2>Pre-departure trail</h2><div class="grid">
  {kv('Worker phone', w.get('worker_phone'))}{kv('Family', ' · '.join(x for x in [w.get('family_name'), w.get('family_relation'), w.get('family_phone')] if x))}
  {kv('Employer', w.get('employer_name'))}{kv('Employer phone', w.get('employer_phone'))}
  {kv('Sponsor (kafeel)', w.get('sponsor_name'))}{kv('Sponsor ID', w.get('sponsor_id'))}
  {kv('Destination', ', '.join(x for x in [w.get('dest_city'), w.get('dest_country')] if x))}{kv('Job', w.get('job_title'))}
  {kv('Contract salary', f"{salary or ''} {w.get('salary_currency') or ''}".strip())}
  {kv('Departure', ' · '.join(x for x in [w.get('departure_date'), w.get('flight_no')] if x))}
  {kv('Agency', w.get('agent_name'))}{kv('Agent owner', w.get('agent_owner'))}
  {kv('Licence check (MEA list)', w.get('agent_check'))}{kv('Closest list entries', matched)}
  {kv('Paid to agent', fee)}{kv('Money paid to', w.get('payment_to'))}
  {kv('Village sub-agent', ' · '.join(x for x in [w.get('sub_agent_name'), w.get('sub_agent_phone')] if x))}
  {kv('Visa type (papers)', w.get('visa_type'))}{kv('Job on visa (papers)', w.get('visa_job'))}
  {kv('Verbal promise (not on paper)', promise_said(w))}{kv('Recorded calls', ' · '.join(x for x in [('agreed at registration: ' + w['call_consent']) if w.get('call_consent') else '', ('notice played on a call ' + fmt_ist(w['consent_notice_at'])) if w.get('consent_notice_at') else ''] if x))}{kv('Full contract before paying', w.get('contract_before_payment'))}
  {kv('Danger code phrase', w.get('code_phrase'))}
</div>{welcome}</div>
<div class="card"><h2>Timeline</h2>{''.join(evs)}</div>
{record_death}
<script>
// Refresh every 20 seconds, but never while someone is typing or reading an opened section.
setInterval(() => {{ if (!document.querySelector('details[open], input:focus, textarea:focus, select:focus')) location.reload(); }}, 20000);
</script>""")



def death_card(w: dict) -> str:
    case_id = esc(w["case_id"])
    opts = lambda values, current: "".join(f'<option value="{x}"{" selected" if current == x else ""}>{x.replace("_", " ")}</option>'
                                           for x in values)
    return f"""<div class="card" style="border-color:#101828;border-width:2px"><h2>Death reported</h2>
<p><b>{esc(fmt_ist(w.get('death_reported_at')))}</b> · {esc(w.get('death_note') or 'no details yet')}</p>
<p class="muted">Not confirmed until the embassy or employer confirms it. Saathi has stopped calling this number and has not
texted the family. If a call was booked with Bolna before this, cancel it in Bolna's call history: Saathi ignores its
result, but cannot stop it ringing. Help the family with the steps in the support papers.</p>
<p><a class="btn" href="/dashboard/case/{case_id}/death" target="_blank">Open family support papers (Telugu + English)</a></p>
<form onsubmit="return false" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
<label style="margin:0">Body<select id="rst">{opts(REMAINS_STATUSES, w.get('remains_status'))}</select></label>
<label style="margin:0">Telangana ex-gratia<select id="egst">{opts(EX_GRATIA_STATUSES, w.get('ex_gratia_status'))}</select></label>
<button class="btn" onclick="post('/api/cases/{case_id}/death-status', {{remains: rst.value, ex_gratia: egst.value}}, this, 'Saved').then(j => j && location.reload())">Save</button>
<button class="btn secondary" onclick="confirm('Clear the death report? Only if it was a mistake.') && post('/api/cases/{case_id}/death-clear', {{}}, this, 'Cleared').then(j => j && location.reload())">It was a mistake: clear</button>
</form></div>"""


def render_death_packet(w: dict, pkt: dict) -> str:
    """Printable papers for a family after a death: Telugu steps first, then the English facts."""
    te, en = pkt["telugu"], pkt["english"]
    li = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)
    body = f"""<p class="noprint"><button class="btn" onclick="window.print()">Print / save as PDF</button>
<a class="btn secondary" href="/dashboard/case/{esc(w['case_id'])}">Back to case</a></p>
<p class="noprint muted">For the family and the caseworker. The Telugu is machine-drafted: have a Telugu speaker read it
first. Saathi does not make the NOC or consent form: the embassy gives its own, which the next of kin signs.</p>
<div class="card petition">
<p><b>{esc(te['title'])}</b></p><p>{esc(te['opening'])}</p><ol>{li(te['steps'])}</ol>
<hr>
<p><b>{esc(en['title'])}</b></p>
<p><b>Facts</b></p><ul>{li(en['facts'])}</ul>
<p><b>Steps</b></p><ol>{li(en['steps'])}</ol>
<p>{esc(en['status'])}</p>
<p class="muted">{esc(en['note'])}</p>
</div>
<style>@media print {{ header, .noprint {{ display:none }} .card {{ border:0 }} body {{ background:#fff }} }}
.petition p, .petition li {{ margin:6px 0 }}</style>"""
    return page(f"Family support {w['case_id']}", body)


def render_proof_of_work(w: dict, rec: dict) -> str:
    """Printable dated record: the worker's defence against a false absconding report."""
    li = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)
    rows = "".join(f"<tr><td class='nowrap'>{esc(r['when'])}</td><td>{esc(r['kind'])}</td><td>{esc(r['where'])}</td>"
                   f"<td>{esc(r['work'])}</td><td>{esc(r['pay'])}</td><td>{esc(r['passport'])}</td><td>{esc(r['said'])}</td></tr>"
                   for r in rec["rows"]) or "<tr><td colspan='7' class='muted'>No calls answered yet.</td></tr>"
    body = f"""<p class="noprint"><button class="btn" onclick="window.print()">Print / save as PDF</button>
<a class="btn secondary" href="/dashboard/case/{esc(w['case_id'])}">Back to case</a></p>
<p class="noprint muted">If the employer files a false absconding report, this dated record shows the worker was in contact,
where they said they were working, and when pay stopped. Give it to the embassy with the call recordings.</p>
<div class="card petition"><p><b>{esc(rec['title'])}</b></p><ul>{li(rec['summary'])}</ul>
<div class="wrap"><table><thead><tr><th>Date</th><th>Call</th><th>Where</th><th>Work</th><th>Salary</th><th>Passport with worker</th>
<th>What the worker reported</th></tr></thead><tbody>{rows}</tbody></table></div>
{f"<p><b>Call recordings</b></p><ul>{li(rec['recordings'])}</ul>" if rec['recordings'] else ''}
<p class="muted">{esc(rec['note'])}</p></div>
<style>@media print {{ header, .noprint {{ display:none }} .card {{ border:0 }} body {{ background:#fff }} }}
.petition p, .petition li {{ margin:6px 0 }}</style>"""
    return page(f"Proof of work {w['case_id']}", body)


def render_petition(w: dict, pet: dict) -> str:
    """Printable Pravasi Prajavani petition, Telugu first, then English."""
    te, en = pet["telugu"], pet["english"]
    li = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)
    body = f"""<p class="noprint"><button class="btn" onclick="window.print()">Print / save as PDF</button>
<a class="btn secondary" href="/dashboard/case/{esc(w['case_id'])}">Back to case</a></p>
<p class="noprint muted">Saathi fills this in from the case. A caseworker hands it in at Pravasi Prajavani (Praja Bhavan,
Hyderabad) for the family, so they do not have to travel. The Telugu is machine-drafted: have a Telugu speaker read it first.
Check every fact with the family before signing.</p>
<div class="card petition">
<p>{esc(te['to'])}</p><p><b>{esc(te['subject'])}</b></p>
{''.join(f'<p>{esc(x)}</p>' for x in te['body'])}
<p>{esc(te['petitioner'])}</p><p>సంతకం: ______________ &nbsp; తేదీ: ______________</p>
<hr>
<p>{esc(en['to'])}</p><p><b>{esc(en['subject'])}</b></p>
<p><b>Facts</b></p><ul>{li(en['facts'])}</ul>
<p><b>What the worker reported</b></p><ul>{li(en['problems'])}</ul>
{f"<p><b>Timeline</b></p><ul>{li(en['timeline'])}</ul>" if en['timeline'] else ''}
<p><b>Request</b></p><ol>{li(en['requests'])}</ol>
<p class="muted">{esc(en['note'])}</p>
<p>{esc(en['petitioner'])}</p><p>Signature: ______________ &nbsp; Date: ______________</p>
</div>
<style>@media print {{ header, .noprint {{ display:none }} .card {{ border:0 }} body {{ background:#fff }} }}
.petition p, .petition li {{ margin:6px 0 }}</style>"""
    return page(f"Petition {w['case_id']}", body)
