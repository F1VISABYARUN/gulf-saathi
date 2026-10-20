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
