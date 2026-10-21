"""Must-pass cases for the agent matcher against the real 2,447-agent licensed list.

Includes the exact speech-to-text strings from the first live Bolna test calls.
"""
import pytest

from gulf_saathi.matcher import LicensedList

GAGAN = "GAGAN MAN POWER CONSULTANTS"
CMR = "CMR INTERNATIONAL MANPOWER CONSULTANCY"
GTM = "GTM INTERNATIONAL"


@pytest.fixture(scope="module")
def agents():
    return LicensedList.load()


def top(result):
    return result["candidates"][0]["agency"] if result["candidates"] else None


def test_full_list_loaded(agents):
    assert len(agents.agents) == 2447


# --- Real agents are found ------------------------------------------------

@pytest.mark.parametrize("kwargs, agency", [
    ({"owner": "Bolle Ganga Narsaiah"}, GAGAN),
    ({"query": "బొల్లె గంగా నరసయ్య"}, GAGAN),
    ({"agency": "Gagan Manpower"}, GAGAN),
    ({"query": "గగన్ మ్యాన్‌పవర్"}, GAGAN),
    ({"owner": "Chella Mallesham"}, CMR),
    ({"agency": "CMR International"}, CMR),
    ({"query": "సి ఎం ఆర్ ఇంటర్నేషనల్"}, CMR),
    ({"owner": "Cheeti Kavitha"}, GTM),
    ({"agency": "GTM International"}, GTM),
])
def test_real_agent_is_top_candidate(agents, kwargs, agency):
    r = agents.check(**kwargs)
    assert r["match"] in ("confirmed_in_list", "needs_confirmation")
    assert top(r) == agency


def test_gagan_manpower_is_not_gagan_overseas(agents):
    r = agents.check(agency="Gagan Manpower")
    assert top(r) == GAGAN
    assert r["match"] == "needs_confirmation"  # name alone never confirms


# --- Confirmation needs more than one piece of evidence -------------------

@pytest.mark.parametrize("kwargs, agency", [
    ({"agency": "Gagan Manpower", "owner": "Bolle Ganga Narsaiah"}, GAGAN),
    ({"agency": "Gagan Manpower", "district": "Jagtial"}, GAGAN),
    ({"agency": "Gagan Manpower", "district": "జగిత్యాల"}, GAGAN),
    ({"query": "గగన్ మ్యాన్‌పవర్ జగిత్యాల"}, GAGAN),
    ({"query": "చెల్లా మల్లేశం జగిత్యాల్"}, CMR),
    ({"licence_no": "RA5596427"}, GAGAN),
    ({"licence_no": "B-1293"}, GAGAN),
    ({"licence_no": "B-1293/TEL/PART/100/5/9657/2019"}, GAGAN),
])
def test_confirmed(agents, kwargs, agency):
    r = agents.check(**kwargs)
    assert r["match"] == "confirmed_in_list"
    assert top(r) == agency


@pytest.mark.parametrize("kwargs", [
    {"owner": "Bolle Ganga Narsaiah"},
    {"owner": "Cheeti Kavitha"},
    {"agency": "CMR International"},
])
def test_one_name_alone_only_needs_confirmation(agents, kwargs):
    assert agents.check(**kwargs)["match"] == "needs_confirmation"


def test_wrong_district_does_not_confirm(agents):
    r = agents.check(agency="Gagan Manpower", district="Nizamabad")
    assert r["match"] != "confirmed_in_list"


# --- Misheard names become candidates, never a wrong confirmation ---------

@pytest.mark.parametrize("kwargs, agency", [
    ({"owner": "Seedi Kavitha"}, GTM),
    ({"query": "సీది కవిత"}, GTM),  # from live call 1
    ({"query": "బొండె గంగా నరసయ్య"}, GAGAN),  # from live call 2
    ({"query": "చెల్లా మల్లేశ్వరం"}, CMR),  # from live call 1
])
def test_misheard_name_needs_confirmation(agents, kwargs, agency):
    r = agents.check(**kwargs)
    assert r["match"] == "needs_confirmation"
    assert top(r) == agency


def test_vision_tours_does_not_confirm_vision_overseas(agents):
    r = agents.check(agency="Vision Tours and Travels")
    assert r["match"] != "confirmed_in_list"
    assert top(r) == "M/s VISION TOURS AND TRAVELS"


def test_made_up_name_sharing_a_real_word_is_only_a_candidate(agents):
    # "Telangana" is the distinctive word of TOMCOM's own registration, so with no
    # district the line asks "did you mean TOMCOM?" instead of confirming or ignoring it.
    r = agents.check(query="Telangana Gulf Placements")
    assert r["match"] == "needs_confirmation"
    assert top(r) == "TELANGANA OVERSEAS MANPOWER COMPANY LIMITED"
    # Told it is in Nirmal (TOMCOM is Hyderabad), the weak match is dropped.
    assert agents.check(query="Telangana Gulf Placements Nirmal")["match"] == "not_found"


@pytest.mark.parametrize("kwargs", [
    {"query": "కవిత"}, {"owner": "Kavitha"}, {"query": "రామయ్య"}, {"owner": "Ramayya"}, {"owner": "Mallesh"},
    {"agency": "Gagan"}, {"query": "చెల్లా"},
])
def test_one_word_alone_asks_for_more_instead_of_listing_agents(agents, kwargs):
    # Live call: "రామయ్య" alone made the line read out agents from Kerala and Maharashtra.
    r = agents.check(**kwargs)
    assert r["match"] == "need_more_info"
    assert r["candidates"] == []


@pytest.mark.parametrize("kwargs", [
    {"query": "రామయ్య కరీంనగర్"}, {"agency": "రామయ్య", "district": "కరీంనగర్"},
    {"owner": "రామయ్య", "district": "కరీంనగర్"},
])
def test_weak_name_in_a_different_district_is_not_found(agents, kwargs):
    # Live call 3. Ramya Manpower (Nirmal) is a weak, wrong-district match: don't read it out.
    assert agents.check(**kwargs)["match"] == "not_found"


def test_one_word_plus_district_is_checked(agents):
    assert agents.check(owner="Mallesh", district="Nirmal")["match"] == "needs_confirmation"


def test_at_most_two_candidates_and_home_states_first(agents):
    r = agents.check(agency="Vision Tours and Travels")
    assert len(r["candidates"]) <= 2
    assert r["candidates"][0]["state"] == "Telangana"


# --- Made-up agents are not found -----------------------------------------

FAKES = [
    "Golconda Overseas", "Ramesh Travels Jagtial", "Charminar Gulf Jobs", "Kakatiya Dubai Manpower",
    "Godavari Overseas Nizamabad", "Sircilla Gulf Consultants", "Lakshmi Narasimha Travels Kamareddy",
    "Bathukamma Overseas", "Yadagiri Manpower Services", "Ramagundam Recruitment Agency",
    "Pochampally Recruiters", "Bhadradri Overseas Consultancy", "Warangal Fort Travels",
    "Moosi River Manpower", "Saudi Dream Jobs Jagtial", "Dubai Fast Visa Services", "Ankapur Overseas",
    "Metpally Gulf Agency", "Korutla Travels and Tours", "Armoor International Manpower",
    "Bodhan Desert Jobs", "Vemulawada Overseas", "Dharmapuri Gulf Consultants", "Raju Bhai Visa Agent",
    # Garbled live-call utterances (call 1 wrongly answered "Vision Tours is licensed" to the first)
    "విజన్ పేరు చిల్లా మల్లేష్ అంజే దేకి త్యాగు", "చెల్లా మలేషియన్ బైక్", "జగతి అల్లు",
]


@pytest.mark.parametrize("name", FAKES)
def test_made_up_agent_not_found(agents, name):
    assert agents.check(query=name)["match"] == "not_found"
    assert agents.check(agency=name)["match"] == "not_found"


@pytest.mark.parametrize("name", ["Overseas", "Manpower Consultants", "Gulf Travels"])
def test_generic_words_alone_find_nobody(agents, name):
    assert agents.check(agency=name)["match"] == "not_found"


@pytest.mark.parametrize("kwargs", [{}, {"agency": ""}, {"district": "నిజామాబాద్"}])
def test_no_name_asks_for_one_instead_of_saying_not_found(agents, kwargs):
    # Live call 4: the model sent only the district, and the line said "not found".
    assert agents.check(**kwargs)["match"] == "need_more_info"


def test_result_never_uses_endorsement_words(agents):
    for kwargs in ({"licence_no": "RA5596427"}, {"agency": "Gagan Manpower"}, {"agency": "Golconda Overseas"}):
        text = str(agents.check(**kwargs)).lower()
        for word in ("safe", "trusted", "genuine", "good agent"):
            assert word not in text


@pytest.mark.parametrize("kwargs", [
    {"owner": "Ramesh", "district": "Jagtial"},
    {"owner": "రమేష్", "district": "జగిత్యాల"},
    {"query": "రమేష్ జగిత్యాల"},
])
def test_one_first_name_never_reads_back_another_state(agents, kwargs):
    # Live call 21 Oct 2026: "Ramesh, Jagtial" was read back as a Chennai agency and
    # the caller said yes. With one name, the district must match.
    r = agents.check(**kwargs)
    assert r["match"] == "not_found" and r["candidates"] == []


def test_one_name_in_the_right_district_still_only_needs_confirmation(agents):
    r = agents.check(owner="Narsaiah", district="Jagtial")
    assert r["match"] == "needs_confirmation" and r["candidates"][0]["district"] == "Jagtial"


def test_one_name_with_extra_free_text_still_never_reads_another_state(agents):
    # Live call 21 Oct 09:07: owner "Ramesh" + district + a long free-text query
    # brought back RAMESH S of Chennai again.
    r = agents.check(owner="Ramesh", district="Nizamabad",
                     query="నిజామాబాద్‌లోని ఏజెంట్ రమేష్; వర్క్ వీసా వస్తే ఆయనే పంపిస్తానంటున్నారు")
    assert all(c["district"] != "Chennai" for c in r["candidates"])
