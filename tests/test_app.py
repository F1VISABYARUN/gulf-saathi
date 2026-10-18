import os

os.environ["GS_DB"] = ":memory:"
os.environ["GS_ADMIN_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

from gulf_saathi.app import app  # noqa: E402

client = TestClient(app)


def test_inbound_call_twiml():
    r = client.post("/voice", data={"CallSid": "CA1", "From": "+919000000009"})
    assert r.status_code == 200
    assert "<Gather" in r.text and "te-IN" in r.text
    client.post("/voice/step", data={"CallSid": "CA1", "Digits": "1"})
    r = client.post("/voice/step", data={"CallSid": "CA1", "Digits": "1"})
    assert 'input="speech"' in r.text and "hints=" in r.text
    r = client.post("/voice/step", data={"CallSid": "CA1", "SpeechResult": "గోల్కొండ ఓవర్సీస్"})
    assert "జాగ్రత్త" in r.text


def test_offer_analyze_api():
    r = client.post("/offer/analyze", json={"text": "Visit visa job, fee 1 lakh, pay by GPay", "lang": "hi"})
    body = r.json()
    assert "flag_visit_visa" in body["flags"] and "1,00,000" in body["message"]


def test_admin_requires_token():
    assert client.get("/admin/escalations").status_code == 401
    assert client.get("/admin/escalations", headers={"X-Admin-Token": "test-token"}).status_code == 200
