"""Golden pages for the TypeScript port: build cases with the Python code, render every dashboard page,
and save the inputs and the HTML to ts/test/golden/pages.json.

    PYTHONPATH=. python ts/scripts/make_page_golden.py
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["GS_AUTO_CALLS"] = "1"
from gulf_saathi import alerts, bolna, cases, dashboard, signals, sms  # noqa: E402
from gulf_saathi.db import MemoryStore  # noqa: E402
from gulf_saathi.matcher import LicensedList  # noqa: E402

NOW = datetime(2026, 10, 21, 6, 0, tzinfo=timezone.utc)
n = [0]


def fake_call(phone, user_data, scheduled_at=None, agent_id=""):
    n[0] += 1
    return {"ok": True, "execution_id": f"exec-{n[0]}", "error": None}


bolna.place_call = fake_call
sms.send_sms = lambda to, text: "demo: not sent"
store, lic = MemoryStore(), LicensedList.load()
Y = {"worker_name": "Yadaiah <b>", "worker_name_te": "యాదయ్య", "worker_phone": "98765 43210", "family_name": "Lakshmi",
     "family_relation": "wife", "family_phone": "9123456780", "employer_name": "Al Noor Cleaning LLC",
     "employer_phone": "+971 50 123 4567", "sponsor_name": "Hamad", "sponsor_id": "784-1990-1234567-1",
     "dest_country": "UAE", "dest_city": "Dubai", "job_title": "Cleaner", "contract_salary": "1500",
     "salary_currency": "AED", "agent_name": "Gagan Manpower", "agent_owner": "Bolle Ganga Narsaiah",
     "agent_district": "Jagtial", "payments": "50000; 30000", "departure_date": "2026-10-24", "flight_no": "EK 527",
     "arrival_call_at": "2026-10-25T09:30", "home_district": "jagtial", "sub_agent_phone": "98480 12345",
     "promise_words": "salary 1,500 riyal & food", "promise_by": "Ramu", "call_consent": "yes", "alerts_opt_in": "yes"}
a = cases.register_worker(store, lic, Y, NOW)["worker"]
b = cases.register_worker(store, lic, {**Y, "worker_phone": "9000000011", "worker_name_te": "", "code_phrase": "",
                                       "agent_name": "Golconda Overseas", "agent_owner": "", "visa_type": "visit",
                                       "worker_gender": "woman", "worker_age": "27", "job_title": "Housemaid",
                                       "arrival_call_at": "", "home_district": "Nizamabad"}, NOW)["worker"]
c = cases.register_worker(store, lic, {**Y, "worker_phone": "9000000012", "arrival_call_at": ""}, NOW)["worker"]
cases.record_checkin(store, {"case_id": a["case_id"], "call_kind": "arrival", "pickup_status": "other_person",
                             "current_job": "herding goats", "current_city": "Al Kharj", "passport_with_worker": "no",
                             "notes": "scared <script>"}, NOW)
cases.process_call_record(store, {"id": "exec-1", "status": "completed", "conversation_duration": 40.5,
                                  "transcript": "assistant: నమస్కారం\nuser: అవును",
                                  "telephony_data": {"recording_url": "https://api.bolna.ai/r/exec-1"},
                                  "context_details": {"recipient_data": {"case_id": a["case_id"], "call_kind": "arrival"}}},
                          NOW + timedelta(hours=1))
cases.record_checkin(store, {"case_id": b["case_id"], "call_kind": "briefing", "briefing_understood": "no"}, NOW)
cases.record_checkin(store, {"case_id": c["case_id"], "call_kind": "weekly", "papers_problem": "absconding case"}, NOW)
cases.update_petition(store, store.get("workers", id=c["id"]), "submitted", "PPV-1", NOW + timedelta(days=1))
cases.update_outcome(store, store.get("workers", id=c["id"]), {"outcome": "solved", "problem": "unpaid_wages",
                                                                "amount_recovered": "120000", "note": "paid"}, NOW + timedelta(days=9))
d = cases.report_problem(store, {"caller_phone": "9123456780", "caller_relation": "wife", "worker_died": "yes",
                                 "current_city": "Dubai", "informed_by": "roommate"}, NOW + timedelta(days=2))
dead = store.get("workers", case_id=d["case_id"])
later = NOW + timedelta(days=10)
workers = store.select("workers")
open_alerts = store.select("escalations", {"status": "open"})
status = {"storage": "memory", "bolna": True, "sms": "demo"}
status_off = {"storage": "supabase", "bolna": False, "sms": "plivo"}
clocks = {w["id"]: cases.case_clock(w, open_alerts, later) for w in workers}
live = [["Supabase connected", "ok", ""], ["Bolna key", "off", "Set BOLNA_API_KEY"], ["Telugu default", "hand", "Check in Bolna"]]
totals = cases.summary_counts(workers, cases.briefed_worker_ids(store))
outcomes = cases.outcome_totals(workers)
sigs = signals.repeated_signals(workers)
store.insert("contact_reports", {"phone": "+919848012345", "amount_asked": 150000, "caller_phone": "+919000000001",
                                 "caller_district": "jagtial", "reporter": "family", "visa_type": "visit", "is_demo": False})
reported = signals.reported_contacts(store.select("contact_reports"), workers)
pages = []


def add(name, args, html):
    pages.append({"name": name, "args": args, "html": html})


add("list", [workers, status, totals, "", clocks, "", outcomes, live],
    dashboard.render_list(workers, status, totals, "", clocks, "", outcomes, live))
add("list_q", [workers, status_off, None, "dubai 9876", {}, "Jagtial", None, None],
    dashboard.render_list(workers, status_off, None, "dubai 9876", {}, "Jagtial", None, None))
add("list_empty", [[], status, None, "nobody", {}, "", None, None], dashboard.render_list([], status, None, "nobody"))
add("agents", [cases.agent_stats(workers), sigs, reported], dashboard.render_agents(cases.agent_stats(workers), sigs, reported))
add("agents_empty", [[], None, None], dashboard.render_agents([]))
add("form", [None, None], dashboard.render_form())
for w in store.select("workers"):
    add("form_edit", [w, w["case_id"]], dashboard.render_form(w, w["case_id"]))
    ev = cases.timeline(store, w)
    alert = cases.embassy_alert(store, w, later)
    clock = cases.case_clock(w, open_alerts, later)
    sg = signals.signals_for_case(w, workers)
    for st, pub in ((status, False), (status_off, True)):
        add("case", [w, ev, st, sg, alert, clock, pub], dashboard.render_case(w, ev, st, sg, alert, clock, public=pub))
    add("proof", [w, cases.proof_of_work(store, w, later)], dashboard.render_proof_of_work(w, cases.proof_of_work(store, w, later)))
    add("petition", [w, cases.prajavani_petition(store, w, later), True],
        dashboard.render_petition(w, cases.prajavani_petition(store, w, later), public=True))
add("death", [dead, cases.death_packet(store, dead, later)], dashboard.render_death_packet(dead, cases.death_packet(store, dead, later)))
add("intake", [], dashboard.render_intake())
hist = [store.insert("scam_alerts", {"created_at": NOW.isoformat(), "message": "గల్ఫ్ <x>", "channel": "voice",
                                     "recipients": 2, "sent": 1, "prepared": 0, "failed": 1})]
add("alerts", [alerts.recipients(workers), alerts.TEMPLATES, alerts.suggestions([{"created_at": NOW.isoformat(), "visa_type": "visit"}], NOW), hist, status],
    dashboard.render_alerts(alerts.recipients(workers), alerts.TEMPLATES, [{"template": "fee", "text": "1 caller"}], hist, status))
pages[-1]["args"][2] = [{"template": "fee", "text": "1 caller"}]
add("alerts_none", [[], alerts.TEMPLATES, [], [], status_off], dashboard.render_alerts([], alerts.TEMPLATES, [], [], status_off))
from gulf_saathi import site  # noqa: E402
os.environ["GS_HELPLINE_NUMBER"] = "918065952403"
os.environ["GS_PILOT_WHATSAPP"] = "919999999999"
for counts, on in (({"calls": {"answered": 5, "outside_team": 0}}, True),
                   ({"calls": {"answered": 5, "outside_team": 2, "outside_callers": 1}}, False), ({}, True)):
    add("site_home", [counts, on], site.render_home(counts, on))
add("site_demo", [], site.render_demo())
add("site_login", ["/dashboard/case/GS-X<y>", "Wrong password"], site.render_login("/dashboard/case/GS-X<y>", "Wrong password"))
out = Path(__file__).resolve().parents[1] / "test" / "golden" / "pages.json"
out.write_text(json.dumps(pages, ensure_ascii=False, default=str), encoding="utf-8")
print(out, len(pages))
