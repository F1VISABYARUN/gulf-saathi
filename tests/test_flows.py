import pytest

from gulf_saathi import checkin, config, notify
from gulf_saathi.agents import AgentRegistry
from gulf_saathi.engine import Engine, Session
from gulf_saathi.offer import analyze_text, parse_amount
from gulf_saathi.store import Store


@pytest.fixture
def registry():
    return AgentRegistry.from_csv(config.ROOT / "data" / "agents_sample.csv")


@pytest.fixture
def store():
    notify.sent.clear()
    return Store()


@pytest.fixture
def engine(registry, store):
    return Engine(registry, store)


def text(reply):
    return " ".join(t for t, _ in reply.say)


# --- Agent lookup ---------------------------------------------------------

@pytest.mark.parametrize("query", ["Golconda Overseas", "గోల్కొండ ఓవర్సీస్", "गोलकोंडा", "گولکنڈہ اوورسیز"])
def test_flagged_agent_found_in_any_script(registry, query):
    m = registry.lookup(query)
    assert m.agent.name == "Golconda Demo Overseas"
    assert m.agent.status == "flagged"


def test_licence_number_lookup(registry):
    assert registry.lookup("my agent licence is 1002").agent.name == "Kakatiya Demo Recruiters"


def test_unknown_agent(registry):
    assert registry.lookup("Sai Ram Travels").kind == "none"


# --- Inbound flows --------------------------------------------------------

def test_demo_flagged_agent_warns_in_telugu(engine, store):
    s = Session(caller="+919000000001")
    engine.start_inbound(s)
    engine.handle(s, digits="1")  # Telugu
    r = engine.handle(s, digits="1")  # agent check
    assert r.expect == "speech"
    r = engine.handle(s, speech="గోల్కొండ ఓవర్సీస్")
    assert "జాగ్రత్త" in text(r)
    assert store.recent_lookups()[0]["status"] == "flagged"


def test_spoken_menu_choice(engine):
    s = Session()
    engine.start_inbound(s)
    engine.handle(s, speech="తెలుగు")  # Telugu script picks Telugu
    assert s.lang == "te" and s.step == "menu"
    engine.handle(s, speech="ఒకటి")
    assert s.step == "agent_name"


def test_probable_match_asks_to_confirm(engine):
    s = Session(lang="hi", step="agent_name")
    r = engine.handle(s, speech="golkonda")
    if s.step == "agent_confirm":
        r = engine.handle(s, digits="1")
    assert "सावधान" in text(r)


def test_offer_with_red_flags(engine):
    s = Session(lang="te", step="menu")
    engine.handle(s, digits="2")
    engine.handle(s, digits="2")  # no contract
    engine.handle(s, digits="2")  # visit visa
    engine.handle(s, digits="80000")
    engine.handle(s, digits="1")  # gulf
    r = engine.handle(s, digits="1")  # passport kept
    t = text(r)
    assert "4 ప్రమాద" in t
    assert "80,000" in t


def test_clean_offer(engine):
    s = Session(lang="ur", step="menu")
    for d in ["2", "1", "1", "25000", "1"]:
        engine.handle(s, digits=d)
    r = engine.handle(s, digits="2")
    assert "کوئی بڑا خطرے کا نشان نہیں" in text(r)


def test_invalid_input_hangs_up_after_retries(engine):
    s = Session(lang="te", step="menu")
    assert engine.handle(s, digits="7").expect == "digit"
    assert engine.handle(s, digits="7").expect == "digit"
    assert engine.handle(s, digits="7").expect is None


def test_registration_and_family_callback(engine, store):
    s = Session(caller="+919000000002", lang="te", step="menu")
    engine.handle(s, digits="3")
    engine.handle(s, digits="1")  # UAE
    assert engine.handle(s, digits="12345").expect == "digits"  # too short, reprompt
    engine.handle(s, digits="9876543210")
    r = engine.handle(s, digits="1")
    assert r.expect is None
    w = store.worker_by_phone("+919000000002")
    assert w["country"] == "UAE" and w["family_phone"] == "+919876543210"

    s = Session(caller="+919000000003", lang="hi", step="menu")
    engine.handle(s, digits="4")
    engine.handle(s, digits="1")
    engine.handle(s, digits="1")
    assert store.open_callbacks()[0]["topic"] == "ex_gratia"


# --- Weekly check-in ------------------------------------------------------

def _worker(store):
    return store.upsert_worker("+971500000001", "te", "UAE", "+919876543210")


def test_checkin_all_ok(engine, store):
    wid = _worker(store)
    s = Session()
    engine.start_checkin(s, wid)
    for d in ["1", "1"]:
        engine.handle(s, digits=d)
    engine.handle(s, digits="1")
    assert store.open_escalations() == []


def test_checkin_unpaid_escalates_and_sms_family(engine, store):
    wid = _worker(store)
    s = Session()
    engine.start_checkin(s, wid)
    engine.handle(s, digits="2")  # not paid
    engine.handle(s, speech="అవును")  # has passport (spoken yes)
    engine.handle(s, digits="1")
    esc = store.open_escalations()
    assert len(esc) == 1 and "wages" in esc[0]["reason"]
    assert notify.sent[-1]["to"] == "+919876543210"


def test_missed_calls_escalate(store):
    wid = _worker(store)
    assert checkin.run_due(store, base_url="http://x") == 1
    assert checkin.run_due(store, base_url="http://x") == 0  # not due again this week
    checkin.handle_call_status(store, wid, "no-answer")
    assert store.open_escalations() == []
    checkin.handle_call_status(store, wid, "busy")
    assert "missed" in store.open_escalations()[0]["reason"]


def test_hangup_before_answering_counts_as_missed(engine, store):
    wid = _worker(store)
    store.mark_called(wid)
    checkin.handle_call_status(store, wid, "completed")
    assert store.worker(wid)["missed"] == 1


# --- Offer text analysis --------------------------------------------------

def test_parse_amount():
    assert parse_amount("fee 1.5 lakh only") == 150000
    assert parse_amount("₹80,000 advance, call 9876543210") == 80000
    assert parse_amount("60 వేలు కట్టాలి") == 60000


def test_forwarded_offer_text():
    msg = ("Urgent! Dubai helper job on visit visa, salary 1500 AED. "
           "Fee 1 lakh via Google Pay. Submit passport at office today only.")
    a, flags = analyze_text(msg)
    assert a.fee_inr == 100000
    for f in ["flag_visit_visa", "flag_passport_kept", "flag_no_contract", "flag_fee_high",
              "flag_personal_payment", "flag_pressure"]:
        assert f in flags


def test_russia_offer():
    _, flags = analyze_text("Russia army helper job, contract provided, fee 25000")
    assert flags == ["flag_non_gulf"]


def test_fmt_rupees():
    from gulf_saathi.engine import fmt_rupees
    assert [fmt_rupees(n) for n in (500, 30000, 150000, 10000000)] == ["500", "30,000", "1,50,000", "1,00,00,000"]


def test_names_spoken_in_caller_script(engine):
    s = Session(lang="te", step="agent_name")
    assert "గోల్కొండ ఓవర్సీస్" in text(engine.handle(s, speech="Golconda Overseas"))
