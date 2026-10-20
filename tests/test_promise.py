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
