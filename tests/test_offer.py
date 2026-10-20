from gulf_saathi.offer import analyze_text, parse_amount


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


def test_fee_flag_uses_cap_including_gst():
    # 35,000 is under the 35,400 total cap; 36,000 is over it.
    assert "flag_fee_high" not in analyze_text("contract given, fee 35000")[1]
    assert "flag_fee_high" in analyze_text("contract given, fee 36000")[1]
