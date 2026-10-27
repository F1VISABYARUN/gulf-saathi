import re
from fastapi.testclient import TestClient

from gulf_saathi.api import app

client = TestClient(app)


def test_health_reports_agents_loaded():
    assert client.get("/health").json()["licensed_agents_loaded"] == 2447


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
    h = client.get("/health").json()
    assert h["storage"] == "memory" and h["dashboard"] is True and h["bolna_checkin_calls"] is False
    assert client.get("/health/db").json() == {"storage": "memory", "ok": True,
                                                "tables": {t: "ok" for t in ("workers", "calls", "checkins", "escalations", "contact_reports",
                                                                              "workers (new columns)")}}


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
    assert "Workers registered" in home and "Pre-departure red flags" in home

    # "Call now" accepts a briefing (Bolna is off in tests, so it reports that).
    r = client.post(f"/api/cases/{case_id}/call", auth=AUTH, json={"kind": "briefing"})
    assert r.status_code == 502
    assert "Briefing: not done yet" in client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    client.post("/tools/record-checkin", json={"case_id": case_id, "call_kind": "briefing", "briefing_understood": "yes"})
    page = client.get(f"/dashboard/case/{case_id}", auth=AUTH).text
    assert "Briefing: done" in page and "(understood)" in page and "Understood the briefing" in page


def test_home_page_is_public_and_shows_totals_only(mem):
    client.post("/api/workers", auth=AUTH, json={"worker_name": "Secret Name", "worker_phone": "9876543210",
                                                 "family_phone": "9123456780"})
    page = client.get("/").text
    assert "Get a call from Saathi" in page and "Aadujeevitham" in page
    assert "Hindi" not in page and "8 Apr 2026" in page and "not sent yet" in page
    assert page.count("BUILT, BEING TESTED") == 4  # only "before paying" is marked as working on real calls
    assert 'src="/gulf-saathi-demo.mp4"' in page and "autoplay" not in page
    assert "Prototype demo · demo data · real Bolna test calls" in page
    assert page.count("AI-generated illustration<") == 4 and "Najeeb Muhammad" in page  # one caption per photo
    for img in ("gs_hero_airport.webp", "gs_desert_goats.webp", "gs_family_sms.webp", "gs_caseworker.webp", "gs_dashboard.webp"):
        assert f"/{img}" in page
    assert "Lok Sabha USQ 2190, 31 Jul 2026, Annex I" in page and "118 action-taken reports" in page
    assert "3,647 Indian women were sent home from Oman" in page and 'id="why"' not in page  # old block gone, Oman kept
    assert "Rs " not in page and "₹35,400" in page and "Demo dashboard" in page
    assert "Secret Name" not in page and "9876543210" not in page
    words = re.sub(r'href="[^"]*"', "", page).lower()  # source URLs are not our wording
    for banned in ("fraud", "genuine", "government-ready", "rescue", "safe", "trusted"):
        assert banned not in words
    assert page.count("<img") == page.count('alt="')


def test_demo_call_needs_the_code(mem, monkeypatch):
    calls = []
    monkeypatch.setattr(api.bolna, "place_call",
                        lambda phone, data, scheduled_at=None, agent_id="": calls.append((phone, agent_id)) or
                        {"ok": True, "execution_id": "e1", "error": None})
    monkeypatch.delenv("GS_DEMO_CODE", raising=False)
    assert client.post("/api/demo-call", json={"phone": "9876543210", "code": "x"}).status_code == 503
    monkeypatch.setenv("GS_DEMO_CODE", "judge-2026")
    monkeypatch.setenv("BOLNA_AGENT_ID", "agent-1")
    api._last_demo_call.clear()
    assert client.post("/api/demo-call", json={"phone": "9876543210", "code": "nope"}).status_code == 403
    assert client.post("/api/demo-call", json={"phone": "+971501112222", "code": "judge-2026"}).status_code == 400
    assert client.post("/api/demo-call", json={"phone": "98765 43210", "code": "judge-2026"}).status_code == 200
    assert calls == [("+919876543210", "agent-1")]
    assert client.post("/api/demo-call", json={"phone": "9876543210", "code": "judge-2026"}).status_code == 429


def test_demo_story_pages(mem):
    assert client.get("/demo").status_code == 401
    assert client.post("/api/demo/run").status_code == 401
    out = client.post("/api/demo/run", auth=AUTH).json()
    case = client.get(f"/dashboard/case/{out['yadaiah']}", auth=AUTH).text
    assert "DEMO" in case and "Promise vs reality" in case and "herding goats" in case
    assert "Seen in 2 cases" in case and "not a finding of fraud" in case
    agents = client.get("/dashboard/agents", auth=AUTH).text
    assert "Saathi Intelligence" in agents and "DEMO DATA" in agents
    ramesh = client.get(f"/dashboard/case/{out['ramesh']}", auth=AUTH).text
    assert "do not travel until" in ramesh


def test_report_problem_tool(mem):
    r = client.post("/tools/report-problem", json={"caller_phone": "+971501112222", "needs_help": "yes",
                                                   "case_id": "%(case_id)s"}).json()
    assert r["ok"] and r["risk_level"] == "critical" and r["new_case"]


def test_passwords_ignore_spaces_pasted_into_vercel(mem, monkeypatch):
    monkeypatch.setenv("GS_DASHBOARD_PASSWORD", " pw-123\n")
    assert client.get("/dashboard", auth=("x", "pw-123")).status_code == 200
    monkeypatch.setenv("GS_DEMO_CODE", "judge-2026 \n")
    monkeypatch.setenv("BOLNA_AGENT_ID", "agent-1")
    monkeypatch.setattr(api.bolna, "place_call", lambda *a, **k: {"ok": True, "execution_id": "e", "error": None})
    api._last_demo_call.clear()
    assert client.post("/api/demo-call", json={"phone": "9876543210", "code": "judge-2026"}).status_code == 200


def test_demo_cases_are_never_called(mem, monkeypatch):
    calls = []
    monkeypatch.setattr(api.bolna, "place_call", lambda *a, **k: calls.append(a) or {"ok": True, "execution_id": "e", "error": None})
    out = client.post("/api/demo/run", auth=AUTH).json()
    r = client.post(f"/api/cases/{out['yadaiah']}/call", auth=AUTH, json={"kind": "weekly"})
    assert r.status_code == 502 and "demo" in r.json()["detail"].lower() and calls == []
    page = client.get(f"/dashboard/case/{out['yadaiah']}", auth=AUTH).text
    assert "never calls demo numbers" in page
    assert "RED FLAGS" in client.get(f"/dashboard/case/{out['ramesh']}", auth=AUTH).text


def test_case_page_offers_an_embassy_alert_when_at_risk(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "Mallaiah", "worker_phone": "9876543210",
                                                     "family_phone": "9123456780", "dest_country": "UAE"})
    cid = r.json()["case_id"]
    assert "Alert the Indian Embassy now" not in client.get(f"/dashboard/case/{cid}", auth=AUTH).text
    from gulf_saathi import cases
    cases.record_checkin(mem, {"case_id": cid, "call_kind": "arrival", "pickup_status": "other_person",
                               "current_city": "Al Ain", "landmark": "near a big mosque"}, api.now())
    page = client.get(f"/dashboard/case/{cid}", auth=AUTH).text
    assert "Alert the Indian Embassy now" in page and "Al Ain, near a big mosque" in page and "+919876543210" in page


def test_check_contact_endpoint(mem):
    client.post("/api/workers", auth=AUTH, json={"worker_name": "A", "worker_phone": "9876543210",
                                                 "family_phone": "9123456780", "sub_agent_phone": "9848012345"})
    r = client.post("/check-contact", json={"phone": "+91 98480 12345", "payment": "%(payment)s"}).json()
    assert r["found"] and r["cases"] == 1 and "A" not in r["instruction"].split()
    assert client.get("/check-contact", params={"phone": "9000011111"}).json()["found"] is False


def test_contact_reports_saved_by_post_not_by_browser_get(mem):
    client.get("/check-contact", params={"phone": "9848012345"})
    assert mem.select("contact_reports") == []
    client.post("/check-contact", json={"phone": "98480 12345", "amount": "100000", "caller_phone": "+919000000001",
                                        "district": "Jagtial", "visa_type": "%(visa_type)s"})
    rep = mem.select("contact_reports")
    assert len(rep) == 1 and rep[0]["phone"] == "+919848012345" and rep[0]["amount_asked"] == 100000
    assert "Agent numbers reported on calls" in client.get("/dashboard/agents", auth=AUTH).text


def test_petition_page_and_status(mem):
    cid = client.post("/api/workers", auth=AUTH, json={"worker_name": "Ravi", "worker_phone": "9876543210",
                                                       "family_phone": "9123456780", "dest_country": "Oman"}).json()["case_id"]
    assert client.get(f"/dashboard/case/{cid}/petition").status_code == 401
    page = client.get(f"/dashboard/case/{cid}/petition", auth=AUTH).text
    assert "Pravasi Prajavani" in page and "ప్రవాసీ ప్రజావాణి" in page and "Print" in page
    assert client.post(f"/api/cases/{cid}/petition", auth=AUTH, json={"status": "nope"}).status_code == 400
    assert client.post(f"/api/cases/{cid}/petition", auth=AUTH, json={"status": "submitted", "ref": "A1"}).json()["ok"]
    assert "handed in" in client.get(f"/dashboard/case/{cid}", auth=AUTH).text


def test_death_report_from_the_dashboard(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "Rajanna", "worker_phone": "9876543210",
                                                     "family_phone": "9123456780", "family_name": "Lakshmi",
                                                     "dest_country": "Saudi Arabia", "dest_city": "Riyadh"})
    cid = r.json()["case_id"]
    page = client.get(f"/dashboard/case/{cid}", auth=AUTH).text
    assert "Record a death report" in page and "Death reported" not in page
    assert client.get(f"/dashboard/case/{cid}/death", auth=AUTH).status_code == 404
    assert client.post(f"/api/cases/{cid}/death", json={}).status_code == 401
    client.post(f"/api/cases/{cid}/death", auth=AUTH, json={"reported_by": "employer", "place": "King Saud hospital"})
    page = client.get(f"/dashboard/case/{cid}", auth=AUTH).text
    assert "Death reported" in page and "Tell the Indian Embassy about the death" in page and "King Saud hospital" in page
    assert "A death was reported" in page  # call buttons disabled
    papers = client.get(f"/dashboard/case/{cid}/death", auth=AUTH).text
    assert "Lakshmi" in papers and "G.O. 216" in papers and "తెలంగాణ" in papers
    assert client.post(f"/api/cases/{cid}/death-status", auth=AUTH,
                       json={"remains": "papers_signed", "ex_gratia": "applied"}).json()["remains_status"] == "papers_signed"
    assert client.post(f"/api/cases/{cid}/death-status", auth=AUTH, json={"remains": "x", "ex_gratia": "applied"}).status_code == 400
    client.post(f"/api/cases/{cid}/death-clear", auth=AUTH)
    assert "Record a death report" in client.get(f"/dashboard/case/{cid}", auth=AUTH).text


def test_find_a_case_by_phone_or_employer(mem):
    for name, phone, employer in (("Rajanna", "9876543210", "Al Safi Farms"), ("Mallesh", "9000011111", "Noor Cleaning")):
        client.post("/api/workers", auth=AUTH, json={"worker_name": name, "worker_phone": phone,
                                                     "family_phone": "9123456780", "employer_name": employer})
    page = client.get("/dashboard", params={"q": "98765 43210"}, auth=AUTH).text
    assert "Rajanna" in page and "Mallesh" not in page
    page = client.get("/dashboard", params={"q": "noor"}, auth=AUTH).text
    assert "Mallesh" in page and "Rajanna" not in page
    assert "No case matches" in client.get("/dashboard", params={"q": "zzz"}, auth=AUTH).text


def test_register_form_has_gender_and_age(mem):
    page = client.get("/dashboard/new", auth=AUTH).text
    assert 'name="worker_gender"' in page and 'name="worker_age"' in page
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "Saraswathi", "worker_phone": "9876543210",
                                                     "family_phone": "9123456780", "worker_gender": "woman",
                                                     "worker_age": "26", "job_title": "Housemaid", "visa_type": "tourist"})
    page = client.get(f"/dashboard/case/{r.json()['case_id']}", auth=AUTH).text
    assert "Woman going for housework on a tourist visa" in page and "do not travel" in page


def test_proof_of_work_page(mem):
    r = client.post("/api/workers", auth=AUTH, json={"worker_name": "Mallesh", "worker_phone": "9876543210",
                                                     "family_phone": "9123456780", "employer_name": "Noor Cleaning"})
    cid = r.json()["case_id"]
    assert "Proof of work" in client.get(f"/dashboard/case/{cid}", auth=AUTH).text
    assert client.get(f"/dashboard/case/{cid}/proof-of-work").status_code == 401
    page = client.get(f"/dashboard/case/{cid}/proof-of-work", auth=AUTH).text
    assert "Record of contact and work: Mallesh" in page and "Noor Cleaning" in page and "No calls answered yet" in page


@pytest.mark.parametrize("q, match, first", [
    ({"owner": "Bolle Ganga Narsaiah"}, "needs_confirmation", "GAGAN MAN POWER CONSULTANTS"),
    ({"owner": "Mallesh"}, "need_more_info", None),                      # one name: ask for more, never a verdict
    ({"owner": "Seedi Kavitha"}, "needs_confirmation", "GTM INTERNATIONAL"),  # "do you mean Cheeti Kavitha?"
    ({"agency": "Vision Tours and Travels", "district": "Hyderabad"}, "confirmed_in_list", "M/s VISION TOURS AND TRAVELS"),
])
def test_agent_cases_that_failed_on_18_oct_calls(q, match, first):
    r = client.post("/check-agent", json=q).json()
    assert r["match"] == match
    assert (r["candidates"][0]["agency"] if r["candidates"] else None) == first


def test_home_explains_the_repeat_agent_check_and_who_pays(mem):
    page = client.get("/").text
    assert page.index('id="how"') < page.index('id="repeat-agent"') < page.index('id="who-pays"') < page.index('id="numbers"')
    assert "Example. Made-up names and number." in page and "98480 XXXXX" in page and "DID NOT PAY" in page
    assert "Proposed model, not yet in place." in page
    # every number in "why this matters, and who pays" links to its source, in a new tab
    section = page[page.index('id="who-pays"'):page.index('id="numbers"')]
    assert section.count('target="_blank" rel="noopener"') == 6  # four stat cards, the Oman line and its backup
    assert "Rajya Sabha Q. 2319, Mar 2026" in section


def test_home_has_the_case_network_diagram(mem):
    page = client.get("/").text
    section = page[page.index('id="repeat-agent"'):page.index('id="who"')]
    diagram = section[section.index('id="case-network"'):section.index('<ol class="flow">')]  # above the five cards
    assert diagram.count('<svg class="net') == 2  # wide for desktop, tall for phones
    for text in ("Same number", "Worker 1 · Jagtial", "CRITICAL", "Worker 2 · Nizamabad", "HIGH", "Callers 3 &amp; 4",
                 "Phone 98480 XXXXX", "UPI ****@ybl", "Caller 5 · warned before paying",
                 "links cases only by exact phone numbers or payment accounts"):
        assert text in diagram
    for banned in ("fraud", "safe", "criminal", "genuine", "employer", "agent name", "promise"):
        assert banned not in diagram.lower()


def test_architecture_diagram_shows_only_what_is_built(mem):
    page = client.get("/").text
    how = page[page.index('id="how"'):page.index('id="repeat-agent"')]
    arch = how[how.index('id="architecture"'):]
    for text in ("Bolna voice agent", "Sarvam saaras:v3", "FastAPI on Vercel", "Supabase", "₹35,400",
                 "Visit or tourist visa", "Same phone or payment account", "CRITICAL", "Telugu warning on the call",
                 "sending not switched on yet", "English case packet", "A human caseworker decides and acts",
                 "Saathi Check-in agent", "Planned, not built", "Built and tested. Roadmap items are marked."):
        assert text in arch, text
    for banned in ("safe", "blacklist", "syndicate", "fraud", "criminal", "genuine", "score",
                   "tomcom", "police", "embassy", "embassies"):
        assert banned not in arch.lower(), banned
