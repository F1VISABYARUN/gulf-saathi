from gulf_saathi.promise import compare_jobs, compare_places, predeparture_checks, promise_rows
from gulf_saathi.signals import repeated_signals, signals_for_case


def test_jobs_compare_by_kind_of_work():
    assert compare_jobs("Cleaner", "Agricultural worker") == "conflict"
    assert compare_jobs("Cleaner", "cleaning in a hospital") == "match"
    assert compare_jobs("Cleaner", "మేకలు కాస్తున్నాను") == "conflict"  # "herding goats" in Telugu
    assert compare_jobs("House driver", "డ్రైవర్") == "match"
    assert compare_jobs("Cleaner", "") == "unknown"
    assert compare_jobs("Cleaner", "something else") == "unknown"  # unrecognised work never raises a flag


def test_places():
    assert compare_places("Riyadh", "near Riyadh") == "match"
    assert compare_places("Riyadh", "Al Kharj") == "conflict"
    assert compare_places("Riyadh", None) == "unknown"


def test_predeparture_checks():
    w = {"agent_check": "not_found", "fee_status": "over_cap", "amount_paid_total": 90000,
         "visa_type": "visit", "job_title": "Cleaner", "visa_job": "Shepherd"}
    codes = [f["code"] for f in predeparture_checks(w)]
    assert codes == ["agent_not_listed", "fee_over_cap", "visit_visa", "visa_job_mismatch"]
    assert predeparture_checks({"agent_check": "confirmed_in_list", "visa_type": "employment",
                                "job_title": "Cleaner", "visa_job": "Cleaner"}) == []


def test_promise_rows():
    rows = promise_rows({"job_title": "Cleaner", "visa_job": "Cleaner", "visa_type": "employment", "dest_city": "Riyadh"},
                        {"current_job": "herding goats", "current_city": "Al Kharj"})
    assert [r["verdict"] for r in rows] == ["conflict", "match", "conflict"]


def test_repeated_signals_never_match_names():
    ws = [
        {"case_id": "GS-A", "sub_agent_phone": "+919848012345", "sub_agent_name": "Raju", "risk_level": "critical"},
        {"case_id": "GS-B", "sub_agent_phone": "98480 12345", "sub_agent_name": "Raju", "risk_level": "ok",
         "visa_type": "visit", "is_demo": True},
        {"case_id": "GS-C", "sub_agent_name": "Raju", "payment_to": "x@upi"},
    ]
    s = repeated_signals(ws)
    assert len(s) == 1 and s[0]["cases"] == ["GS-A", "GS-B"] and s[0]["at_risk"] == 1 and s[0]["flagged"] == 1
    assert s[0]["demo"] is False  # one real case: not labelled demo
    assert signals_for_case(ws[2], ws) == []


# --- Saathi Intelligence ----------------------------------------------------------------

from gulf_saathi.signals import check_contact  # noqa: E402


def _w(cid, **kw):
    return {"case_id": cid, "risk_level": "ok", **kw}


def test_live_contact_check_warns_without_names_or_case_numbers():
    ws = [_w("GS-A", sub_agent_phone="+919848012345", risk_level="critical", agent_district="Jagtial"),
          _w("GS-B", payment_to="raju@upi", agent_district="Nizamabad"),
          _w("GS-C", sub_agent_phone="+919848012345", is_demo=True, risk_level="critical")]
    r = check_contact(ws, phone="98480 12345")
    assert r["found"] and r["cases"] == 1 and r["at_risk"] == 1  # the demo case never counts
    assert "do not pay any more money" in r["instruction"] and "GS-A" not in str(r)
    r = check_contact(ws, payment=" Raju@UPI ")
    assert r["cases"] == 1 and r["at_risk"] == 0 and "none reported a problem" in r["instruction"]
    r = check_contact(ws, phone="9000011111")
    assert not r["found"] and "does not mean the agent is safe" in r["instruction"]
    assert "Ask for the agent's phone number" in check_contact(ws)["instruction"]


def test_employer_names_link_only_with_country_and_are_weak():
    ws = [_w("GS-A", employer_name="Al Noor Cleaning LLC", dest_country="UAE"),
          _w("GS-B", employer_name="AL NOOR CLEANING", dest_country="UAE"),
          _w("GS-C", employer_name="Al Noor Cleaning", dest_country="Oman"),
          _w("GS-D", employer_name="Noor", dest_country="UAE"), _w("GS-E", employer_name="Noor", dest_country="UAE")]
    s = repeated_signals(ws)
    assert len(s) == 1 and set(s[0]["cases"]) == {"GS-A", "GS-B"} and s[0]["strong"] is False


def test_numbers_heard_on_calls_count_even_without_a_case():
    from gulf_saathi.db import MemoryStore
    from gulf_saathi.signals import record_contact, reported_contacts
    store = MemoryStore()
    for caller, amt, district in (("9000000001", "150000", "Jagtial"), ("9000000002", "90000", "Nizamabad"),
                                  ("9000000002", "90000", "Nizamabad"), ("9000000003", "30000", "Jagtial")):
        record_contact(store, {"phone": "98480 12345", "amount": amt, "district": district, "caller_phone": caller,
                               "visa_type": "visit" if caller.endswith("1") else ""}, "2026-10-22T10:00:00+00:00")
    assert record_contact(store, {"phone": ""}, "x") is None
    reports = store.select("contact_reports")
    r = check_contact([], phone="9848012345", reports=reports, caller_phone="9000000003")
    assert r["callers"] == 2 and r["callers_over_limit"] == 2 and r["callers_visit_visa"] == 1  # caller 3 not counted
    assert "asked for more than the legal limit" in r["instruction"] and "not proof" in r["instruction"]
    g = reported_contacts(reports, [])[0]
    assert g["callers"] == 3 and g["reports"] == 4 and g["over_limit"] == 3 and g["districts"] == ["Jagtial", "Nizamabad"]
