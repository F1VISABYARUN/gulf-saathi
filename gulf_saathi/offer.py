"""Red-flag checks for a job offer, from IVR answers or a forwarded message."""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import config


@dataclass
class OfferAnswers:
    has_contract: bool | None = None
    visa: str | None = None  # "employment", "visit" or "unknown"
    fee_inr: int | None = None
    region: str | None = None  # "gulf" or "other"
    passport_kept: bool | None = None
    personal_payment: bool = False
    pressure: bool = False


def assess(a: OfferAnswers) -> list[str]:
    """Return prompt keys for each red flag, most serious first."""
    flags = []
    if a.visa == "visit":
        flags.append("flag_visit_visa")
    if a.passport_kept:
        flags.append("flag_passport_kept")
    if a.has_contract is False:
        flags.append("flag_no_contract")
    if a.fee_inr is not None and a.fee_inr > config.FEE_CAP_INR:
        flags.append("flag_fee_high")
    if a.region == "other":
        flags.append("flag_non_gulf")
    if a.visa == "unknown":
        flags.append("flag_visa_unknown")
    if a.personal_payment:
        flags.append("flag_personal_payment")
    if a.pressure:
        flags.append("flag_pressure")
    return flags


# --- Free-text analysis (forwarded WhatsApp offer, or transcribed speech) ---

_VISIT = ["visit visa", "tourist visa", "visit", "tourist", "విజిట్", "టూరిస్ట్", "विज़िट", "विजिट", "टूरिस्ट", "وزٹ", "ٹورسٹ"]
_EMPLOYMENT = ["employment visa", "work visa", "work permit", "job visa", "residence visa", "ఉద్యోగ వీసా", "वर्क वीज़ा", "वर्क परमिट", "ورک ویزا"]
_CONTRACT = ["contract", "offer letter", "agreement", "appointment letter", "కాంట్రాక్ట్", "ఒప్పందం", "कॉन्ट्रैक्ट", "अनुबंध", "करार", "کانٹریکٹ", "معاہدہ"]
_NON_GULF = [
    "russia", "europe", "poland", "serbia", "romania", "croatia", "armenia", "georgia", "belarus",
    "ukraine", "lithuania", "latvia", "hungary", "malta", "cyprus", "myanmar", "laos", "cambodia",
    "రష్యా", "యూరప్", "రష్యాలో", "रूस", "यूरोप", "روس", "یورپ",
]
_PASSPORT_KEPT = ["submit passport", "passport submit", "deposit passport", "passport deposit", "keep your passport",
                  "hand over passport", "original passport", "పాస్‌పోర్ట్ ఇవ్వాలి", "पासपोर्ट जमा", "پاسپورٹ جمع"]
_PERSONAL_PAY = ["google pay", "gpay", "phonepe", "phone pe", "paytm", "cash only", "only cash", "personal account", "upi"]
_PRESSURE = ["urgent", "today only", "limited seats", "last date today", "hurry", "అర్జెంట్", "ఈరోజే", "तुरंत", "आज ही", "فوری", "آج ہی"]

_UNITS = {
    "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "l": 100000,
    "లక్ష": 100000, "లక్షలు": 100000, "लाख": 100000, "لاکھ": 100000,
    "k": 1000, "thousand": 1000, "వేలు": 1000, "వేల": 1000, "हज़ार": 1000, "हजार": 1000, "ہزار": 1000,
}
_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)*)\s*(" + "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True)) + r")?(?![a-z])", re.I)


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def parse_amount(text: str) -> int | None:
    """Largest rupee amount mentioned, e.g. "1.5 lakh", "80,000", "60 వేలు"."""
    best = None
    for num, unit in _AMOUNT.findall(text):
        unit = unit.lower()
        if unit:
            value = float(num.replace(",", "")) * _UNITS[unit]
        else:
            value = float(num.replace(",", ""))
            # Bare small numbers are ages, days, hours; 10+ digits are phone numbers.
            if value < 1000 or len(re.sub(r"\D", "", num)) >= 10:
                continue
        best = max(best or 0, int(value))
    return best


def analyze_text(text: str) -> tuple[OfferAnswers, list[str]]:
    t = text.lower()
    a = OfferAnswers()
    if _has(t, _EMPLOYMENT):
        a.visa = "employment"
    elif _has(t, _VISIT):
        a.visa = "visit"
    a.has_contract = _has(t, _CONTRACT)
    a.fee_inr = parse_amount(t) if _has(t, ["fee", "charge", "pay", "₹", "rs", "inr", "రూపాయ", "रुपये", "रुपए", "روپے", "ఫీజు", "फीस", "فیس", "lakh", "లక్ష", "लाख"]) else None
    a.region = "other" if _has(t, _NON_GULF) else None
    a.passport_kept = _has(t, _PASSPORT_KEPT)
    a.personal_payment = _has(t, _PERSONAL_PAY)
    a.pressure = _has(t, _PRESSURE)
    return a, assess(a)
