import pytest
from fastapi.testclient import TestClient

from gulf_saathi import config
from gulf_saathi.api import app
from gulf_saathi.fees import check_fee, fmt_rupees, parse_amounts

client = TestClient(app)


def test_cap_is_30000_plus_18_percent_gst():
    assert config.FEE_CAP_INR == 35400


@pytest.mark.parametrize("n, spoken", [(500, "500"), (30000, "30,000"), (150000, "1,50,000"), (10000000, "1,00,00,000")])
def test_indian_digit_grouping(n, spoken):
    assert fmt_rupees(n) == spoken


@pytest.mark.parametrize("text, amounts", [
    ("10000; 25000", [10000, 25000]),
    ("10,000 and 25,000", [10000, 25000]),
    ("10000,25000", [10000, 25000]),  # two payments, not one huge number
    ("80,000", [80000]),
    ("1,50,000", [150000]),
    ("5 lakh", [500000]),
    ("1.5 lakh and 60 వేలు", [150000, 60000]),
    ("call 9876543210, pay 20000", [20000]),  # phone numbers are not payments
    ("2 months, 5000 rupees", [5000]),
    ("", []),
])
def test_parse_amounts(text, amounts):
    assert parse_amounts(text) == amounts


def test_all_payments_are_added_before_comparing():
    # Each payment is under the cap; together they are not. This is the case a model
    # adding in its head is most likely to get wrong.
    r = check_fee("20000; 20000")
    assert r["total"] == 40000 and r["status"] == "over_cap" and r["over_by"] == 4600


@pytest.mark.parametrize("payments, status, over", [
    ("30000", "within_cap", 0),
    ("35400", "within_cap", 0),  # exactly the cap is allowed
    ("35401", "over_cap", 1),
    ("500000", "over_cap", 464600),
    (["10000", "25000"], "within_cap", 0),
    ([10000, 30000], "over_cap", 4600),
    ("", "no_amount", 0),
    (None, "no_amount", 0),
])
def test_status(payments, status, over):
    r = check_fee(payments)
    assert r["status"] == status and r["over_by"] == over


def test_within_cap_never_endorses_the_agent():
    text = check_fee("20000")["instruction"].lower()
    assert "do not say the agent is honest or safe" in text
    assert "within the legal maximum" in text


def test_api_post_and_browser_link():
    r = client.post("/check-fee", json={"payments": "10000; 25000; 5000"}).json()
    assert r["total"] == 40000 and r["over_by_spoken"] == "4,600" and r["status"] == "over_cap"
    r = client.get("/check-fee", params={"payments": "5 lakh"}).json()
    assert r["total_spoken"] == "5,00,000" and r["status"] == "over_cap"


@pytest.mark.parametrize("payments", [None, "%(payments)s", {"$var": "payments"}, "none"])
def test_api_tolerates_unfilled_field_from_bolna(payments):
    r = client.post("/check-fee", json={"payments": payments})
    assert r.status_code == 200 and r.json()["status"] == "no_amount"
