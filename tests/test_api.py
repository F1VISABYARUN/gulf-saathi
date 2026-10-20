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
