from fastapi.testclient import TestClient

from gulf_saathi.api import app

client = TestClient(app)


def test_health_reports_agents_loaded():
    assert client.get("/").json()["licensed_agents_loaded"] == 2447


def test_check_agent_post():
    r = client.post("/check-agent", json={"owner": "Seedi Kavitha"}).json()
    assert r["match"] == "needs_confirmation" and r["candidates"][0]["agency"] == "GTM INTERNATIONAL"
    assert client.post("/check-agent", json={"query": "చెల్లా మల్లేశం జగిత్యాల్"}).json()["match"] == "confirmed_in_list"
    assert client.post("/check-agent", json={"agency": "Golconda Overseas"}).json()["match"] == "not_found"


def test_check_agent_tolerates_missing_fields_from_bolna():
    body = {"agency": "Gagan Manpower", "owner": None, "district": {"$var": "district"},
            "licence_no": "%(licence_no)s", "query": "unknown"}
    r = client.post("/check-agent", json=body)
    assert r.status_code == 200
    assert r.json()["candidates"][0]["agency"] == "GAGAN MAN POWER CONSULTANTS"


def test_check_agent_from_browser_link():
    r = client.get("/check-agent", params={"owner": "బొల్లె గంగా నరసయ్య"}).json()
    assert r["candidates"][0]["agency"] == "GAGAN MAN POWER CONSULTANTS"


# --- dashboard and Bolna-facing endpoints -------------------------------------------

import pytest  # noqa: E402

from gulf_saathi import api, sms  # noqa: E402
from gulf_saathi.db import MemoryStore  # noqa: E402

AUTH = ("anyone", "pw-123")


@pytest.fixture
def mem(monkeypatch):
    monkeypatch.setattr(api, "STORE", MemoryStore())
    monkeypatch.setenv("GS_DASHBOARD_PASSWORD", "pw-123")
    monkeypatch.delenv("BOLNA_API_KEY", raising=False)
    monkeypatch.delenv("GS_WEBHOOK_TOKEN", raising=False)
    monkeypatch.setattr(sms, "send_sms", lambda to, text: "demo: not sent")
    return api.STORE


def test_dashboard_needs_password(mem, monkeypatch):
    assert client.get("/dashboard").status_code == 401
    assert client.get("/dashboard").headers["www-authenticate"].startswith("Basic")
    assert client.get("/dashboard", auth=("x", "wrong")).status_code == 401
    assert client.get("/dashboard", auth=AUTH).status_code == 200
    assert client.post("/api/workers", json={}).status_code == 401
    monkeypatch.delenv("GS_DASHBOARD_PASSWORD")
    assert client.get("/dashboard", auth=AUTH).status_code == 503  # off until a password is set


def test_register_view_call_and_packet(mem):
    r = client.post("/api/workers", auth=AUTH, json={
        "worker_name": "<script>alert(1)</script>", "worker_phone": "9876543210", "family_phone": "9123456780",
        "employer_name": "Al Noor", "agent_name": "Golconda Overseas", "payments": "80000"})
    assert r.status_code == 200, r.text
    case_id = r.json()["case_id"]

    page = client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert(1)" not in page
    assert "not_found" in page and "OVER the Rs 35,400 limit" in page
    assert case_id in client.get("/dashboard", auth=AUTH).text

    # Bolna isn't configured in tests: "Call now" reports that instead of pretending.
    r = client.post(f"/api/cases/{case_id}/call", auth=AUTH, json={"kind": "arrival"})
    assert r.status_code == 502 and "not configured" in r.json()["detail"]
    assert client.post(f"/api/cases/{case_id}/call", auth=AUTH, json={"kind": "bogus"}).status_code == 400

    # The check-in agent reports a wrong pickup during the call.
    r = client.post("/tools/record-checkin", json={"case_id": case_id, "call_kind": "arrival",
                                                     "pickup_status": "other_person", "months_unpaid": "%(months_unpaid)s"}).json()
    assert r["risk_level"] == "critical" and r["escalated"]
    assert "CRITICAL" in client.get(f"/dashboard/case/{case_id}", auth=AUTH).text

    packet = client.get(f"/dashboard/case/{case_id}/packet.txt", auth=AUTH)
    assert "attachment" in packet.headers["content-disposition"]
    assert "GULF SAATHI CASE PACKET" in packet.text and "Al Noor" in packet.text

    esc_id = mem.select("escalations")[0]["id"]
    assert client.post(f"/api/escalations/{esc_id}/resolve", auth=AUTH).json() == {"ok": True}
    assert client.post("/api/escalations/nope/resolve", auth=AUTH).status_code == 404


def test_register_rejects_bad_input(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "A"})
    assert r.status_code == 400 and "required" in r.json()["detail"]


def test_record_checkin_tool_checks_token(mem, monkeypatch):
    monkeypatch.setenv("GS_WEBHOOK_TOKEN", "t0k")
    assert client.post("/tools/record-checkin", json={"case_id": "GS-X"}).status_code == 401
    r = client.post("/tools/record-checkin?token=t0k", json={"case_id": "GS-X"}).json()
    assert r["ok"] is False


def test_health_shows_config_and_db(mem):
    h = client.get("/").json()
    assert h["storage"] == "memory" and h["dashboard"] is True and h["bolna_checkin_calls"] is False
    assert client.get("/health/db").json() == {"storage": "memory", "ok": True,
                                                "tables": {t: "ok" for t in ("workers", "calls", "checkins", "escalations")}}


def test_case_page_notices_edit_and_book_arrival(mem):
    r = client.post("/api/workers", auth=AUTH, json={
        "worker_name": "MALLAIAH", "worker_phone": "9491750870", "family_phone": "9441808262",
        "payments": "500000", "arrival_call_at": "2026-10-30T16:27"})
    case_id = r.json()["case_id"]
    page = client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    assert "is not booked" in page and "Book arrival call" in page          # Bolna off: nothing booked
    assert "Next call: —" in page                                            # and no booked time shown
    assert "family SMS will use the English name" in page
    assert f'/dashboard/case/{case_id}/edit' in page

    # Booking without Bolna reports why.
    r = client.post(f"/api/cases/{case_id}/book-arrival", auth=AUTH)
    assert r.status_code == 502 and "not configured" in r.json()["detail"]

    # The edit page is the form, filled in.
    edit = client.get(f"/dashboard/case/{case_id}/edit", auth=AUTH).text
    assert 'value="+919491750870"' in edit and 'value="500000"' in edit and 'value="2026-10-30T16:27"' in edit
    assert "Save changes" in edit

    r = client.post(f"/api/cases/{case_id}", auth=AUTH, json={
        "worker_name": "MALLAIAH", "worker_name_te": "మల్లయ్య", "worker_phone": "8341820870",
        "family_phone": "9441808262", "payments": "500000", "arrival_call_at": "2026-10-30T16:27",
        "code_phrase": "అమ్మ బాగుందా"})
    assert r.json() == {"case_id": case_id}
    page = client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    assert "+918341820870" in page and "English name" not in page

    bad = client.post(f"/api/cases/{case_id}", auth=AUTH, json={
        "worker_name": "M", "worker_phone": "8341820870", "family_phone": "9441808262", "code_phrase": "ANNA"})
    assert bad.status_code == 400 and "too easy" in bad.json()["detail"]
    assert client.post(f"/api/cases/{case_id}", json={}).status_code == 401
    assert client.get("/dashboard/case/GS-NOPE/edit", auth=AUTH).status_code == 404


def test_old_case_with_weak_code_phrase_shows_warning(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "M", "worker_phone": "9491750870",
                                                      "family_phone": "9441808262"})
    case_id = r.json()["case_id"]
    mem.update("workers", {"case_id": case_id}, {"code_phrase": "ANNA"})  # saved before the rule existed
    page = client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    assert 'Danger code phrase "ANNA" is too easy to say by accident' in page


def test_book_arrival_without_a_time(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "M", "worker_phone": "9491750870",
                                                      "family_phone": "9441808262"})
    r = client.post(f"/api/cases/{r.json()['case_id']}/book-arrival", auth=AUTH)
    assert r.status_code == 400 and "no arrival-day call time" in r.json()["detail"]


def test_state_view_agents_page_and_briefing(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "M", "worker_phone": "9491750870",
                                                      "family_phone": "9441808262", "agent_name": "<b>Fake</b> Overseas",
                                                      "payments": "300000"})
    case_id = r.json()["case_id"]
    assert client.get("/dashboard/agents").status_code == 401
    agents = client.get("/dashboard/agents", auth=AUTH).text
    assert "&lt;B&gt;FAKE&lt;/B&gt; OVERSEAS" in agents and "<b>FAKE" not in agents
    assert "not found in licensed list" in agents and case_id in agents

    home = client.get("/dashboard", auth=AUTH).text
    assert "Workers registered" in home and "Agent or fee red flags" in home

    # "Call now" accepts a briefing (Bolna is off in tests, so it reports that).
    r = client.post(f"/api/cases/{case_id}/call", auth=AUTH, json={"kind": "briefing"})
    assert r.status_code == 502
    assert "Briefing: not done yet" in client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    client.post("/tools/record-checkin", json={"case_id": case_id, "call_kind": "briefing", "briefing_understood": "yes"})
    page = client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    assert "Briefing: done" in page and "(understood)" in page and "Understood the briefing" in page
