"""Server-rendered dashboard pages. Plain HTML, no build step.

Every value from the database goes through esc(), since names, transcripts
and notes come from callers.
"""
from __future__ import annotations

from html import escape

from .cases import CODE_PHRASE_HELP, IST, code_phrase_ok, fmt_ist, parse_ts, reason_text
from .fees import fmt_rupees
from .promise import STOP_FLAGS, VISA_TYPES, predeparture_checks, promise_rows

BADGE = {"critical": "#b42318", "high": "#c4320a", "medium": "#a15c07", "ok": "#067647"}
PICKUP = {"employer": "Registered employer", "other_person": "Someone else", "nobody": "Nobody came",
          "not_arrived": "Not arrived yet"}
ANSWER_LABELS = [
    ("pickup_status", "Who picked them up"), ("pickup_person", "Person at pickup"),
    ("current_location", "Where they are now"), ("current_job", "Work they are doing now"),
    ("current_city", "City they are in now"), ("salary_received", "Salary received"),
    ("months_unpaid", "Months unpaid"), ("passport_with_worker", "Passport with worker"),
    ("food_ok", "Food and room OK"), ("threatened", "Threats or violence"),
    ("movement_restricted", "Stopped from going out"), ("needs_help", "Asked for help"),
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
        rows.append(f"""<tr><td>{esc(g['label'])}{' <span class="demo">DEMO DATA</span>' if g['demo'] else ''}</td>
<td><b>{esc(g['value'])}</b></td><td>Seen in {len(g['cases'])} cases<div class="muted" style="font-size:12px">{cases}</div></td>
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


def render_list(workers: list[dict], status: dict, totals: dict | None = None) -> str:
    rows = []
    order = {"critical": 0, "high": 1, "medium": 2, "ok": 3}
    # Most serious first; within a level, most recently updated first.
    by_recent = sorted(workers, key=lambda w: w.get("updated_at") or "", reverse=True)
    for w in sorted(by_recent, key=lambda w: order.get(w.get("risk_level"), 3)):
        rows.append(f"""<tr>
<td>{badge(w.get('risk_level'))}</td>
<td class="nowrap"><a href="/dashboard/case/{esc(w['case_id'])}"><b>{esc(w['case_id'])}</b></a></td>
<td>{esc(w['worker_name'])}{demo_tag(w)}<div class="muted">{esc(w.get('worker_phone'))}</div>{''.join(f'<div class="flag">{esc(f)}</div>' for f in predeparture_flags(w))}</td>
<td>{esc(w.get('dest_city'))}{', ' if w.get('dest_city') and w.get('dest_country') else ''}{esc(w.get('dest_country'))}</td>
<td>{esc(w.get('employer_name'))}</td>
<td>{esc(w.get('status'))}</td>
<td>{esc(fmt_ist(w.get('last_contact_at')))}</td>
<td>{esc(w.get('missed_checkins') or 0)}</td>
<td>{esc(fmt_ist(w.get('next_call_at')))}</td></tr>""")
    table = ("<p class='muted'>No workers yet. <a href='/dashboard/new'>Register the first one</a>.</p>" if not rows else
             f"""<div class="wrap"><table><thead><tr><th>Risk</th><th>Case</th><th>Worker</th><th>Destination</th>
<th>Employer</th><th>Status</th><th>Last contact</th><th>Missed</th><th>Next call</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>""")
    counts = {lvl: sum(1 for w in workers if (w.get("risk_level") or "ok") == lvl) for lvl in order}
    summary = " &nbsp; ".join(f"{badge(l)} {counts[l]}" for l in order)
    return page("Cases", f"""<h1>Cases</h1>{tiles(totals) if totals else ""}
<div class="card">{summary}<div class="muted" style="margin-top:8px">{status_line(status)} · refreshes every 15 seconds</div></div>
<div class="card">{table}</div>""", refresh=15)


def render_agents(stats: list[dict], signals: list[dict] | None = None) -> str:
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
<h2>Repeated across cases</h2>
<div class="card">{signals_table(signals or [])}</div>""")


def status_line(status: dict) -> str:
    parts = [f"Storage: {esc(status['storage'])}", f"Bolna calls: {'on' if status['bolna'] else 'NOT configured'}",
             f"SMS: {esc(status['sms'])}"]
    return " · ".join(parts)


FIELDS = [
    ("Worker", [("worker_name", "Name (English) *", "Yadaiah"), ("worker_name_te", "Name in Telugu (for the family SMS)", "యాదయ్య"),
                ("worker_phone", "Worker phone *", "98765 43210"), ("code_phrase", "Danger code phrase", "అమ్మ బాగుందా")]),
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
                          ("payment_to", "Money paid to (UPI ID / account / phone)", "agent@upi")]),
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
            if name == "visa_type":
                current = _form_value(name, values)
                opts = "".join(f'<option value="{t}"{" selected" if current == t else ""}>{t}</option>'
                               for t in ("", *VISA_TYPES))
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


def render_case(w: dict, events: list[dict], status: dict, signals: list[dict] | None = None) -> str:
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

    calls_disabled = "" if status["bolna"] else "disabled title='Bolna is not configured'"
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
    return page(w["case_id"], f"""<h1>{case_id} · {esc(w['worker_name'])}{demo_tag(w)} {badge(w.get('risk_level'))}</h1>
<div class="card">
  {f'<ul>{reasons}</ul>' if reasons else '<p class="muted">No current risk signals.</p>'}{flags}{''.join(notices)}
  <p>
    <button class="btn" {calls_disabled} onclick="post('/api/cases/{case_id}/call', {{kind:'arrival'}}, this, 'Arrival call requested')">Call now: arrival check</button>
    <button class="btn" {calls_disabled} onclick="post('/api/cases/{case_id}/call', {{kind:'weekly'}}, this, 'Weekly check-in call requested')">Call now: weekly check-in</button>
    <button class="btn" {calls_disabled} onclick="post('/api/cases/{case_id}/call', {{kind:'briefing'}}, this, 'Briefing call requested')">Call now: pre-departure briefing</button>
    <a class="btn secondary" href="/dashboard/case/{case_id}/packet.txt">Download English case packet</a>
    <a class="btn secondary" href="/dashboard/case/{case_id}/edit">Edit details</a>
  </p><div id="msg"></div>
  <div class="muted">Status: {esc(w.get('status'))} · Last contact: {esc(fmt_ist(w.get('last_contact_at')))} ·
  Missed in a row: {esc(w.get('missed_checkins') or 0)} · Next call: {esc(fmt_ist(w.get('next_call_at')))} · {briefing} · refreshes every 20 seconds</div>
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
  {kv('Danger code phrase', w.get('code_phrase'))}
</div>{welcome}</div>
<div class="card"><h2>Timeline</h2>{''.join(evs)}</div>""", refresh=20)

