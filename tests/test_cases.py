import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from gulf_saathi import bolna, cases, sms
from gulf_saathi.cases import CaseError, case_packet, process_call_record, record_checkin, register_worker
from gulf_saathi.db import MemoryStore, SupabaseStore
from gulf_saathi.matcher import LicensedList

NOW = datetime(2026, 10, 21, 6, 0, tzinfo=timezone.utc)  # 11:30 IST


@pytest.fixture(scope="module")
def licensed():
    return LicensedList.load()


@pytest.fixture
def placed(monkeypatch):
    """Stand-in for Bolna: records each requested call and returns an execution id."""
    calls = []

    def fake_place_call(phone, user_data, scheduled_at=None, agent_id=""):
        calls.append({"phone": phone, "user_data": user_data, "scheduled_at": scheduled_at})
        return {"ok": True, "execution_id": f"exec-{len(calls)}", "error": None}

    monkeypatch.setattr(bolna, "place_call", fake_place_call)
    return calls


@pytest.fixture
def texts(monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "send_sms", lambda to, text: sent.append((to, text)) or "demo: not sent")
    return sent


@pytest.fixture
def store():
    return MemoryStore()


YADAIAH = {
    "worker_name": "Yadaiah", "worker_name_te": "యాదయ్య", "worker_phone": "98765 43210",
    "family_name": "Lakshmi", "family_relation": "wife", "family_phone": "9123456780",
    "employer_name": "Al Noor Cleaning LLC", "employer_phone": "+971 50 123 4567",
    "sponsor_name": "Hamad", "sponsor_id": "784-1990-1234567-1",
    "dest_country": "UAE", "dest_city": "Dubai", "job_title": "Cleaner",
    "contract_salary": "1500", "salary_currency": "AED",
    "agent_name": "Gagan Manpower", "agent_owner": "Bolle Ganga Narsaiah", "agent_district": "Jagtial",
    "payments": "50000; 30000",
    "departure_date": "2026-10-24", "flight_no": "EK 527",
    "arrival_call_at": "2026-10-25T09:30",  # India time
}


def register(store, licensed, **overrides):
    # The welcome SMS has its own test; leaving it out keeps `texts` to alerts only.
    return register_worker(store, licensed, {**YADAIAH, **overrides}, NOW, send_welcome=False)


def payload(call_id, case_id, kind, status="completed", talked=True, extracted=None):
    return {
        "id": call_id, "status": status, "conversation_duration": 40 if talked else 0,
        "transcript": "assistant: నమస్కారం\nuser: అవును వచ్చాను" if talked else "assistant: నమస్కారం\n",
        "telephony_data": {"recording_url": f"https://api.bolna.ai/recordings/call/{call_id}", "to_number": "+919876543210"},
        "context_details": {"recipient_data": {"case_id": case_id, "call_kind": kind}},
        "extracted_data": extracted or {},
    }


# --- registration -----------------------------------------------------------------

def test_registration_builds_the_trail_and_books_the_arrival_call(store, licensed, placed):
    out = register(store, licensed)
    w = out["worker"]
    assert re.fullmatch(r"GS-[A-Z2-9]{6}", w["case_id"])
    assert w["worker_phone"] == "+919876543210" and w["family_phone"] == "+919123456780"
    assert w["employer_phone"] == "+971501234567"
    assert w["agent_check"] == "confirmed_in_list"  # agency + owner + district
    assert w["amount_paid_total"] == 80000 and w["fee_status"] == "over_cap"
    assert w["code_phrase"] == cases.DEFAULT_CODE_PHRASE

    # Arrival call booked with Bolna for 09:30 India time = 04:00 UTC.
    assert len(placed) == 1
    assert placed[0]["scheduled_at"] == datetime(2026, 10, 25, 4, 0, tzinfo=timezone.utc)
    assert placed[0]["user_data"]["case_id"] == w["case_id"]
    assert placed[0]["user_data"]["call_kind"] == "arrival"
    assert placed[0]["user_data"]["employer_name"] == "Al Noor Cleaning LLC"
    assert store.get("calls", id="exec-1")["status"] == "scheduled"
    assert w["next_call_at"] == "2026-10-25T04:00:00+00:00"


@pytest.mark.parametrize("bad, message", [
    ({"worker_name": ""}, "worker name"),
    ({"family_phone": ""}, "family phone"),
    ({"worker_phone": "12"}, "phone"),
    ({"departure_date": "24/10/2026"}, "YYYY-MM-DD"),
    ({"contract_salary": "fifteen hundred"}, "number"),
])
def test_registration_rejects_bad_input(store, licensed, placed, bad, message):
    with pytest.raises(CaseError, match=message):
        register(store, licensed, **bad)


def test_registration_works_without_bolna(store, licensed, monkeypatch):
    monkeypatch.delenv("BOLNA_API_KEY", raising=False)
    out = register(store, licensed)
    assert out["worker"]["case_id"]
    assert out["arrival_call"]["ok"] is False and "not configured" in out["arrival_call"]["error"]


# --- arrival call: the Najeeb moment -----------------------------------------------

def test_wrong_person_at_airport_is_critical(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    r = record_checkin(store, {"case_id": w["case_id"].lower(), "call_kind": "arrival",
                               "pickup_status": "other_person", "pickup_person": "a man named Faisal"}, NOW)
    assert r["risk_level"] == "critical" and r["escalated"]
    assert "Never promise rescue" in r["instruction"] and "alerting the Indian Embassy in UAE" in r["instruction"]
    assert "call the embassy themselves" in r["instruction"]  # forbidden, not suggested
    assert "Al Noor Cleaning LLC" in r["instruction"]  # don't go with anyone else

    w = store.get("workers", id=w["id"])
    assert w["risk_level"] == "critical" and w["status"] == "abroad"

    # The family SMS is Telugu only: apart from the case number, no Latin letters.
    to, text = texts[0]
    assert to == "+919123456780"
    assert "యాదయ్య" in text and "అత్యవసరం" in text
    assert not re.search(r"[A-Za-z]", text.replace(w["case_id"], ""))


def test_code_phrase_keeps_the_call_quiet(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    r = record_checkin(store, {"case_id": w["case_id"], "code_phrase_used": "yes"}, NOW)
    assert r["risk_level"] == "critical"
    assert "Do NOT mention" in r["instruction"]
    assert "నేరుగా అడగకండి" in texts[0][1]  # family told not to ask about it on the phone


def test_all_clear_checkin(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    r = record_checkin(store, {"case_id": w["case_id"], "call_kind": "arrival", "pickup_status": "employer",
                               "salary_received": "yes", "passport_with_worker": "అవును"}, NOW)
    assert r["risk_level"] == "ok" and not r["escalated"] and texts == []


def test_unknown_case_does_not_crash():
    r = record_checkin(MemoryStore(), {"case_id": "GS-NOPE"}, NOW)
    assert r["ok"] is False and "do not promise" in r["instruction"]


# --- weekly check-ins ------------------------------------------------------------

def test_unpaid_and_passport_taken_is_high_and_not_repeated(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    answers = {"case_id": w["case_id"], "salary_received": "no", "months_unpaid": "2 months",
               "passport_with_worker": "no", "food_ok": "yes"}
    r = record_checkin(store, answers, NOW)
    assert r["risk_level"] == "high" and r["escalated"]
    assert {x["code"] for x in store.get("workers", id=w["id"])["risk_reasons"]} == {"unpaid_2plus", "passport_taken"}

    # Same answers next week, alert still open: no second SMS.
    assert record_checkin(store, answers, NOW + timedelta(days=7))["escalated"] is False
    assert len(texts) == 1
    # A new, worse problem gets through.
    assert record_checkin(store, {**answers, "threatened": "yes"}, NOW + timedelta(days=8))["escalated"] is True
    assert len(texts) == 2


def test_one_month_unpaid_is_medium_without_sms(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    assert record_checkin(store, {"case_id": w["case_id"], "salary_received": "no"}, NOW)["risk_level"] == "medium"
    assert texts == []


# --- webhook: calls ending ------------------------------------------------------

def test_answered_arrival_call_books_weekly_call(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    r = process_call_record(store, payload("exec-1", w["case_id"], "arrival"), NOW)
    assert r["processed"] and not r["missed"]

    call = store.get("calls", id="exec-1")
    assert call["answered"] and call["recording_url"].endswith("exec-1") and "అవును" in call["transcript"]
    w = store.get("workers", id=w["id"])
    assert w["status"] == "abroad" and w["missed_checkins"] == 0
    # Next: weekly call 7 days later.
    assert placed[-1]["user_data"]["call_kind"] == "weekly"
    assert placed[-1]["scheduled_at"] == NOW + timedelta(days=7)


def test_two_missed_calls_raise_high_and_redelivery_is_ignored(store, licensed, placed, texts):
    w = register(store, licensed, arrival_call_at="")["worker"]
    store.update("workers", {"id": w["id"]}, {"status": "abroad"})

    process_call_record(store, payload("exec-a", w["case_id"], "weekly", "no-answer", talked=False), NOW)
    # Bolna sends several webhooks per call: the same call again must not count twice.
    process_call_record(store, payload("exec-a", w["case_id"], "weekly", "no-answer", talked=False), NOW)
    w1 = store.get("workers", id=w["id"])
    assert w1["missed_checkins"] == 1 and w1["risk_level"] == "medium" and texts == []
    assert placed[-1]["scheduled_at"] == NOW + timedelta(hours=24)  # retry tomorrow

    store.update("calls", {"worker_id": w["id"]}, {"status": "completed"})  # the retry call happened
    # "completed" but nobody spoke also counts as missed.
    r = process_call_record(store, payload("exec-b", w["case_id"], "weekly", "completed", talked=False), NOW + timedelta(days=1))
    assert r["missed"] and r["risk_level"] == "high" and r["escalated"]
    assert "వరుసగా 2 కాల్స్‌కు జవాబు రాలేదు" in texts[0][1]

    # Answering again resets the count; the open alert keeps the badge until resolved.
    store.update("calls", {"worker_id": w["id"]}, {"status": "completed"})
    process_call_record(store, payload("exec-c", w["case_id"], "weekly"), NOW + timedelta(days=2))
    w3 = store.get("workers", id=w["id"])
    assert w3["missed_checkins"] == 0 and w3["risk_level"] == "high"

    esc = store.select("escalations", {"worker_id": w["id"]})[0]
    cases.resolve_escalation(store, esc["id"], NOW + timedelta(days=2))
    assert store.get("workers", id=w["id"])["risk_level"] == "ok"


def test_no_second_booking_when_one_is_pending(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]  # arrival call pending for 25 Oct
    process_call_record(store, payload("exec-x", w["case_id"], "weekly"), NOW)
    assert len(placed) == 1  # only the arrival call


def test_empty_extraction_keeps_what_the_tool_recorded(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    record_checkin(store, {"case_id": w["case_id"], "salary_received": "no"}, NOW)  # medium
    process_call_record(store, payload("exec-1", w["case_id"], "weekly"), NOW)
    assert store.get("workers", id=w["id"])["risk_level"] == "medium"


def test_extracted_data_is_used_when_present(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    process_call_record(store, payload("exec-1", w["case_id"], "weekly", extracted={"passport_with_worker": "no"}), NOW)
    assert store.get("workers", id=w["id"])["risk_level"] == "high"


def test_call_from_the_agent_check_line_is_stored_not_processed(store, placed):
    p = payload("exec-z", "", "")
    p["context_details"] = {"recipient_data": {"timezone": "Asia/Kolkata"}}
    r = process_call_record(store, p, NOW)
    assert r == {"stored": True, "processed": False, "worker": None}
    assert store.get("calls", id="exec-z")["kind"] == "other"


# --- case packet -----------------------------------------------------------------

def test_case_packet_has_the_whole_trail(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    record_checkin(store, {"case_id": w["case_id"], "call_kind": "arrival", "pickup_status": "other_person"}, NOW)
    process_call_record(store, payload("exec-1", w["case_id"], "arrival"), NOW)
    text = case_packet(store, store.get("workers", id=w["id"]), NOW)
    for expected in [w["case_id"], "CRITICAL", "Al Noor Cleaning LLC", "784-1990-1234567-1", "Hamad", "Dubai",
                     "Gagan Manpower", "confirmed_in_list", "OVER the Rs 35,400 limit",
                     "someone other than the registered employer", "Recording: https://api.bolna.ai/recordings/call/exec-1",
                     "have not been independently verified", "madad.gov.in", "అవును"]:
        assert expected in text, expected
    assert "rescue" not in text.lower()


# --- outside services: exact requests ----------------------------------------------

def test_supabase_requests(monkeypatch):
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": "1"}])
        return httpx.Response(201, json=[json.loads(request.content)])

    s = SupabaseStore("https://abc.supabase.co/", "sb_secret_xyz")
    s.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert s.get("workers", case_id="GS-ABC234") == {"id": "1"}
    s.insert("workers", {"case_id": "GS-ABC234"})
    s.upsert("calls", {"id": "exec-1"})
    s.update("workers", {"id": "1"}, {"risk_level": "high"})

    get, ins, ups, upd = seen
    assert str(get.url).startswith("https://abc.supabase.co/rest/v1/workers?")
    assert get.url.params["case_id"] == "eq.GS-ABC234" and get.url.params["limit"] == "1"
    assert get.headers["apikey"] == "sb_secret_xyz" and "authorization" not in get.headers
    assert ins.headers["prefer"] == "return=representation"
    assert ups.url.params["on_conflict"] == "id" and "merge-duplicates" in ups.headers["prefer"]
    assert upd.method == "PATCH" and upd.url.params["id"] == "eq.1"

    legacy = SupabaseStore("https://abc.supabase.co", "eyJhbGciOi.legacy")
    assert legacy.headers["Authorization"] == "Bearer eyJhbGciOi.legacy"


def test_bolna_call_request(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"execution_id": "exec-99", "status": "queued"})

    monkeypatch.setenv("BOLNA_API_KEY", "bn-test")
    monkeypatch.setenv("BOLNA_CHECKIN_AGENT_ID", "agent-123")
    monkeypatch.setattr(bolna.httpx, "post", fake_post)
    when = datetime(2026, 10, 25, 4, 0, tzinfo=timezone.utc)
    r = bolna.place_call("+919876543210", {"case_id": "GS-ABC234", "n": None}, when)
    assert r == {"ok": True, "execution_id": "exec-99", "error": None}
    assert seen["url"] == "https://api.bolna.ai/call"
    assert seen["headers"]["Authorization"] == "Bearer bn-test"
    assert seen["json"] == {"agent_id": "agent-123", "recipient_phone_number": "+919876543210",
                            "user_data": {"case_id": "GS-ABC234", "n": ""},
                            "scheduled_at": "2026-10-25T04:00:00+00:00"}


def test_real_bolna_event_sequence_processes_once(store, licensed, placed, texts):
    # Order seen on a live call: initiated, ringing, in-progress, call-disconnected
    # (and possibly completed afterwards).
    w = register(store, licensed, arrival_call_at="")["worker"]
    for status in ("initiated", "ringing", "in-progress"):
        r = process_call_record(store, payload("exec-live", w["case_id"], "weekly", status, talked=False), NOW)
        assert r["processed"] is False
    assert store.get("workers", id=w["id"])["missed_checkins"] == 0  # ringing is not a miss

    r = process_call_record(store, payload("exec-live", w["case_id"], "weekly", "call-disconnected"), NOW)
    assert r["processed"] and not r["missed"]
    r = process_call_record(store, payload("exec-live", w["case_id"], "weekly", "completed"), NOW)
    assert r["processed"] is False
    assert len(placed) == 1 and placed[0]["user_data"]["call_kind"] == "weekly"  # next call booked once


# --- fixes from the first live registration ------------------------------------------

def test_failed_booking_does_not_show_a_booked_call(store, licensed, monkeypatch):
    monkeypatch.setattr(bolna, "place_call", lambda *a, **k: {"ok": False, "execution_id": None, "error": "Bolna not configured"})
    w = register(store, licensed)["worker"]
    assert w.get("next_call_at") is None
    assert not cases.arrival_call_booked(store, w)


def test_book_arrival_call_later(store, licensed, monkeypatch, placed):
    real_fake = bolna.place_call
    monkeypatch.setattr(bolna, "place_call", lambda *a, **k: {"ok": False, "execution_id": None, "error": "off"})
    w = register(store, licensed)["worker"]
    monkeypatch.setattr(bolna, "place_call", real_fake)  # Bolna set up afterwards

    res = cases.book_arrival_call(store, w, NOW)
    assert res["ok"] and cases.arrival_call_booked(store, w)
    assert placed[-1]["scheduled_at"] == datetime(2026, 10, 25, 4, 0, tzinfo=timezone.utc)
    assert store.get("workers", id=w["id"])["next_call_at"] == "2026-10-25T04:00:00+00:00"

    # If the arrival time has already passed, call now instead.
    res = cases.book_arrival_call(store, w, datetime(2026, 10, 26, tzinfo=timezone.utc))
    assert res["ok"] and placed[-1]["scheduled_at"] is None


def test_book_arrival_needs_a_time(store, licensed, placed):
    w = register(store, licensed, arrival_call_at="")["worker"]
    with pytest.raises(CaseError, match="no arrival-day call time"):
        cases.book_arrival_call(store, w, NOW)


@pytest.mark.parametrize("phrase, ok", [
    ("అమ్మ బాగుందా", True), ("Is Amma well?", True), ("ANNA", False), ("అన్నా", False),
    ("anna.", False), ("hello", False), ("", False), ("ok", False),
])
def test_code_phrase_rule(phrase, ok):
    assert cases.code_phrase_ok(phrase) is ok


def test_registration_rejects_a_weak_code_phrase(store, licensed, placed):
    with pytest.raises(CaseError, match="too easy to say by accident"):
        register(store, licensed, code_phrase="ANNA")


def test_edit_corrects_details_and_keeps_the_case(store, licensed, placed):
    w = register(store, licensed)["worker"]
    edited = cases.update_worker(store, licensed, w, {**YADAIAH, "worker_phone": "8341820870",
                                                      "agent_name": "Golconda Overseas", "agent_owner": "",
                                                      "payments": "20000"}, NOW + timedelta(hours=1))
    assert edited["case_id"] == w["case_id"] and edited["id"] == w["id"]
    assert edited["worker_phone"] == "+918341820870"
    assert edited["agent_check"] == "not_found" and edited["fee_status"] == "within_cap"  # checks re-run
    assert edited["status"] == "registered" and edited["risk_level"] == "ok"
    with pytest.raises(CaseError, match="too easy"):
        cases.update_worker(store, licensed, w, {**YADAIAH, "code_phrase": "anna"}, NOW)


def test_edit_clears_a_next_call_time_with_nothing_booked(store, licensed, placed):
    w = register(store, licensed, arrival_call_at="")["worker"]
    store.update("workers", {"id": w["id"]}, {"next_call_at": "2026-10-30T10:57:00+00:00"})  # stale, as on GS-W9HWSY
    assert cases.update_worker(store, licensed, w, YADAIAH, NOW)["next_call_at"] is None

    booked = register(store, licensed)["worker"]  # arrival call really booked for 25 Oct
    assert cases.update_worker(store, licensed, booked, YADAIAH, NOW)["next_call_at"] == "2026-10-25T04:00:00+00:00"


# --- CM's three points: state view and pre-departure briefing ------------------------

def test_summary_counts_and_agent_stats(store, licensed, placed, texts):
    a = register(store, licensed, arrival_call_at="", payments="20000")["worker"]  # licensed Gagan, fee ok
    b = register(store, licensed, arrival_call_at="", agent_name="Golconda Overseas", agent_owner="",
                 agent_district="jagtial", employer_name="Al Noor Cleaning LLC")["worker"]
    c = register(store, licensed, arrival_call_at="", agent_name="GOLCONDA  OVERSEAS", agent_owner="",
                 agent_district="Jagtial", employer_name="Desert Star", dest_city="Riyadh", dest_country="Saudi Arabia")["worker"]
    record_checkin(store, {"case_id": c["case_id"], "call_kind": "arrival", "pickup_status": "other_person"}, NOW)
    record_checkin(store, {"case_id": a["case_id"], "call_kind": "briefing", "briefing_understood": "yes"}, NOW)

    workers = store.select("workers")
    totals = cases.summary_counts(workers, cases.briefed_worker_ids(store))
    assert totals == {"registered": 3, "in_india": 2, "abroad": 1, "briefed": 1, "at_risk": 1, "red_flags": 2}

    stats = cases.agent_stats(workers)
    golconda, gagan = stats  # riskiest first
    assert golconda["agent"] == "GOLCONDA OVERSEAS"  # spacing and case don't split the group
    assert (golconda["cases"], golconda["not_in_list"], golconda["over_cap"], golconda["critical"]) == (2, 2, 2, 1)
    assert golconda["districts"] == ["Jagtial"]
    assert golconda["employers"] == ["Al Noor Cleaning LLC (Dubai, UAE)", "Desert Star (Riyadh, Saudi Arabia)"]
    assert gagan["agent"] == "GAGAN MAN POWER CONSULTANTS" and gagan["licensed"] and gagan["over_cap"] == 0


def test_briefing_is_recorded_without_touching_risk(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    record_checkin(store, {"case_id": w["case_id"], "salary_received": "no"}, NOW)  # medium
    r = record_checkin(store, {"case_id": w["case_id"], "call_kind": "briefing", "briefing_understood": "no"}, NOW)
    assert r["risk_level"] == "ok" and "land" in r["instruction"]
    assert store.get("workers", id=w["id"])["risk_level"] == "medium"  # unchanged
    assert cases.briefed_worker_ids(store)[w["id"]]["answers"]["briefing_understood"] is False


def test_danger_on_a_briefing_call_still_alerts(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    r = record_checkin(store, {"case_id": w["case_id"], "call_kind": "briefing", "threatened": "yes"}, NOW)
    assert r["risk_level"] == "critical" and r["escalated"] and len(texts) == 1


def test_missed_briefing_is_not_a_missed_checkin(store, licensed, placed, texts):
    w = register(store, licensed, arrival_call_at="")["worker"]
    r = process_call_record(store, payload("exec-br", w["case_id"], "briefing", "no-answer", talked=False), NOW)
    assert r["processed"] is False
    assert store.get("workers", id=w["id"])["missed_checkins"] == 0 and texts == [] and placed == []


# --- promise vs reality, welcome SMS, help line ---------------------------------------

def test_welcome_sms_once_at_registration(store, licensed, placed, texts):
    w = register_worker(store, licensed, YADAIAH, NOW)["worker"]
    assert len(texts) == 1 and texts[0][0] == "+919123456780"
    assert w["case_id"] in texts[0][1] and "యాదయ్య" in texts[0][1]
    assert not re.search(r"[A-Za-z]", texts[0][1].replace(w["case_id"], ""))  # Telugu only
    assert w["welcome_sms_status"] == "demo: not sent" and w["source"] == "dashboard" and w["is_demo"] is False


def test_different_work_on_arrival_is_flagged(store, licensed, placed, texts):
    w = register(store, licensed, visa_type="employment", visa_job="Cleaner")
    w = w["worker"]
    r = record_checkin(store, {"case_id": w["case_id"], "call_kind": "arrival", "pickup_status": "employer",
                               "current_job": "herding goats", "current_city": "Al Ain"}, NOW)
    assert r["risk_level"] == "high" and r["escalated"]
    codes = [x["code"] for x in store.get("workers", id=w["id"])["risk_reasons"]]
    assert codes == ["job_mismatch", "city_mismatch"]
    assert "herding goats" in cases.reason_text(store.get("workers", id=w["id"])["risk_reasons"][0])


def test_same_work_is_not_flagged(store, licensed, placed, texts):
    w = register(store, licensed)["worker"]
    r = record_checkin(store, {"case_id": w["case_id"], "call_kind": "weekly", "current_job": "cleaning offices",
                               "current_city": "Dubai Marina", "salary_received": "yes"}, NOW)
    assert r["risk_level"] == "ok" and texts == []


def test_visa_fields_and_red_flags(store, licensed, placed):
    w = register(store, licensed, visa_type="Visit", visa_job="Shepherd", sub_agent_phone="98480 12345")["worker"]
    assert w["visa_type"] == "visit" and w["sub_agent_phone"] == "+919848012345"
    assert cases.has_predeparture_flags(w)
    with pytest.raises(CaseError):
        register(store, licensed, visa_type="business")


def test_help_line_opens_a_case_and_alerts(store, licensed, placed, texts):
    r = cases.report_problem(store, {"caller_phone": "+971 50 111 2222", "caller_name": "Srinu",
                                     "family_phone": "9000012345", "threatened": "yes", "notes": "boss beats me"}, NOW)
    assert r["ok"] and r["new_case"] and r["risk_level"] == "critical" and r["escalated"]
    w = store.get("workers", case_id=r["case_id"])
    assert w["source"] == "help_call" and w["worker_phone"] == "+971501112222"
    assert texts and texts[0][0] == "+919000012345"
    assert store.select("checkins", {"worker_id": w["id"]})[0]["kind"] == "help"
    # Calling again finds the same case by phone.
    r2 = cases.report_problem(store, {"caller_phone": "971501112222", "months_unpaid": "3"}, NOW)
    assert r2["case_id"] == r["case_id"] and not r2["new_case"]


def test_help_line_needs_a_way_to_find_the_caller(store, placed, texts):
    r = cases.report_problem(store, {"needs_help": "yes"}, NOW)
    assert r["ok"] is False and "phone number" in r["instruction"]


def test_demo_story_never_calls_or_texts(store, licensed, placed, texts):
    from gulf_saathi.demo import run_demo
    from gulf_saathi.signals import repeated_signals
    out = run_demo(store, licensed, NOW)
    assert placed == [] and texts == []
    y = store.get("workers", case_id=out["yadaiah"])
    assert y["is_demo"] and y["risk_level"] == "critical"
    assert {"job_mismatch", "city_mismatch", "wrong_pickup", "passport_taken"} <= {r["code"] for r in y["risk_reasons"]}
    assert store.select("escalations")[0]["sms_status"] == "demo: not sent"
    sig = repeated_signals(store.select("workers"))
    assert sig and all(s["demo"] for s in sig) and set(sig[0]["cases"]) == {out["yadaiah"], out["ramesh"]}


# --- help line safety net (Bolna after-call extraction) -----------------------------

def _x(objective=None, subjective=None):
    return {"objective": objective, "subjective": subjective, "confidence": 0.9}


# Shape of extracted_data from the live call d5acc09e (21 Oct 2026, "Oman airport").
OMAN_EXTRACTION = {"help_check": {
    "notes": _x(subjective="The caller says someone took them in Oman, that they are being beaten, and asks for help."),
    "abroad": _x("yes"), "needs_help": _x("yes"), "threatened": _x("yes"),
    "caller_name": _x(subjective="not_said"), "current_job": _x(subjective="not_said"),
    "current_city": _x(subjective="Oman, at the airport"), "months_unpaid": _x(subjective="not_said"),
    "movement_restricted": _x("not_said"), "passport_with_worker": _x("not_said"),
}}


def gulf_line_call(call_id, extracted, number="+971501112222"):
    return {"id": call_id, "agent_id": "gulf-saathi", "status": "completed", "conversation_duration": 180,
            "transcript": "assistant: నమస్కారం\nuser: ఓమన్ ఎయిర్పోర్ట్ లో ఉన్నాను", "user_number": number,
            "telephony_data": {"recording_url": f"https://api.bolna.ai/recordings/call/{call_id}"},
            "context_details": {"recipient_data": {"timezone": "Asia/Kolkata"}}, "extracted_data": extracted}


def test_flatten_extraction_reads_bolna_categories():
    flat = cases.flatten_extraction(OMAN_EXTRACTION)
    assert flat["abroad"] == "yes" and flat["threatened"] == "yes" and flat["current_city"] == "Oman, at the airport"
    assert flat["caller_name"] == "" and flat["passport_with_worker"] == ""
    assert cases.flatten_extraction({"abroad": "yes"}) == {"abroad": "yes"}


def test_after_call_extraction_opens_a_help_case_when_the_live_ai_missed_it(store, placed, texts):
    out = process_call_record(store, gulf_line_call("x1", OMAN_EXTRACTION), NOW)
    assert out["processed"] and out["help"]["new_case"]
    w = store.get("workers", case_id=out["worker"])
    assert w["source"] == "help_call" and w["risk_level"] == "critical" and w["worker_phone"] == "+971501112222"
    assert {"threatened", "needs_help"} <= {r["code"] for r in w["risk_reasons"]}
    assert len(store.select("escalations")) == 1
    # Bolna delivers the same finished call again: nothing new.
    again = process_call_record(store, gulf_line_call("x1", OMAN_EXTRACTION), NOW)
    assert again["processed"] is False and len(store.select("escalations")) == 1
    assert placed == []  # never books calls for a help-line caller


def test_after_call_extraction_after_the_live_tool_sends_no_second_alert(store, texts):
    cases.report_problem(store, {"caller_phone": "+971501112222", "threatened": "yes", "needs_help": "yes"}, NOW)
    process_call_record(store, gulf_line_call("x2", OMAN_EXTRACTION), NOW)
    assert len(store.select("workers")) == 1 and len(store.select("escalations")) == 1


def test_a_caller_only_checking_an_agent_opens_no_case(store, texts):
    checking = {"help_check": {"abroad": _x("no"), "needs_help": _x("not_said"), "threatened": _x("not_said"),
                               "notes": _x(subjective="Asked whether an agent in Jagtial is licensed.")}}
    out = process_call_record(store, gulf_line_call("x3", checking, "+919000011111"), NOW)
    assert store.select("workers") == [] and not out.get("help")


def test_taken_by_a_stranger_is_critical_with_airport_advice(store, texts):
    r = cases.report_problem(store, {"caller_phone": "+96890001111", "taken_by_stranger": "yes"}, NOW)
    assert r["risk_level"] == "critical" and "airport help desk or airport police" in r["instruction"]
    assert "G S, " in r["instruction"]  # case number read letter by letter


def test_family_is_only_said_to_be_told_when_the_sms_went_out(store, monkeypatch):
    monkeypatch.setattr(sms, "send_sms", lambda to, text: "demo: not sent (no SMS provider configured)")
    r = cases.report_problem(store, {"caller_phone": "+971501112222", "family_phone": "9000012345",
                                     "threatened": "yes"}, NOW)
    assert "family has been sent a message" not in r["instruction"]
    monkeypatch.setattr(sms, "send_sms", lambda to, text: "sent")
    r = cases.report_problem(store, {"caller_phone": "+971502223333", "family_phone": "9000012346",
                                     "threatened": "yes"}, NOW)
    assert "Their family has been sent a message" in r["instruction"]


def test_help_line_keeps_trace_details_on_the_case(store, texts):
    r = cases.report_problem(store, {"caller_phone": "+971501112222", "needs_help": "yes", "caller_name": "Mallayya",
                                     "home_district": "Jagtial", "agent_name": "Rajesh", "agent_phone": "98480 12345",
                                     "landmark": "near a big mosque", "current_city": "Al Ain"}, NOW)
    w = store.get("workers", case_id=r["case_id"])
    assert w["worker_name"] == "Mallayya" and w["agent_name"] == "Rajesh" and w["sub_agent_phone"] == "+919848012345"
    assert "Home: Jagtial" in w["notes"] and "Near: near a big mosque" in w["notes"] and w["dest_city"] == "Al Ain"
    ans = store.select("checkins")[0]["answers"]
    assert ans["landmark"] == "near a big mosque" and ans["home_district"] == "Jagtial"


def test_arrival_call_scored_from_bolna_extraction_when_the_tool_was_missed(store, licensed, placed, texts):
    # The live AI never called record_checkin; the after-call "checkin" extraction still scores it.
    w = register(store, licensed)["worker"]
    extracted = {"checkin": {"pickup_status": _x("other_person"), "current_job": _x(subjective="herding goats"),
                             "current_city": _x(subjective="Al Kharj"), "threatened": _x("not_said")}}
    out = process_call_record(store, payload("a1", w["case_id"], "arrival", extracted=extracted), NOW)
    w = store.get("workers", id=w["id"])
    assert out["processed"] and w["risk_level"] == "critical"
    assert {"wrong_pickup", "job_mismatch", "city_mismatch"} <= {r["code"] for r in w["risk_reasons"]}


def test_extraction_arriving_with_completed_after_disconnect_is_scored(store, licensed, placed, texts):
    # Live order: "call-disconnected" (transcript, no extraction) then "completed" (with extraction).
    # The live AI never called record_checkin (Bolna attached no tools on 21 Oct).
    w = register(store, licensed)["worker"]
    first = process_call_record(store, payload("d1", w["case_id"], "arrival", "call-disconnected"), NOW)
    assert first["processed"] and store.get("workers", id=w["id"])["risk_level"] == "ok"
    extracted = {"help_check": {"taken_by_stranger": _x("yes"), "current_job": _x(subjective="herding sheep"),
                                "passport_with_worker": _x("no"), "abroad": _x("yes")}}
    late = process_call_record(store, payload("d1", w["case_id"], "arrival", "completed", extracted=extracted), NOW)
    w = store.get("workers", id=w["id"])
    assert late["late_extraction"] and w["risk_level"] == "critical"
    assert {"wrong_pickup", "job_mismatch", "passport_taken"} <= {r["code"] for r in w["risk_reasons"]}
    assert len(store.select("escalations")) == 1
    again = process_call_record(store, payload("d1", w["case_id"], "arrival", "completed", extracted=extracted), NOW)
    assert again["processed"] is False and len(store.select("escalations")) == 1
    assert len(placed) == 1  # only the arrival call booked at registration; nothing extra


def test_critical_answer_brings_saathi_back_within_hours(store, licensed, placed, texts):
    # Someone in danger is not left for a week: the next call comes within 3 hours.
    w = register(store, licensed, arrival_call_at="")["worker"]
    record_checkin(store, {"case_id": w["case_id"], "call_kind": "arrival", "pickup_status": "other_person"}, NOW)
    process_call_record(store, payload("c1", w["case_id"], "arrival"), NOW)
    assert placed[-1]["scheduled_at"] == NOW + timedelta(hours=3)
    w2 = register(store, licensed, arrival_call_at="", worker_phone="9876500000")["worker"]
    process_call_record(store, payload("c2", w2["case_id"], "weekly"), NOW)
    assert placed[-1]["scheduled_at"] == NOW + timedelta(days=7)
