"""Add up everything a worker has paid or been asked to pay an agent, and compare
it with the legal cap.

The voice agent should never do this arithmetic itself: a language model adding
"10,000 then 25,000 then 5,000" in its head is exactly where a wrong "that's fine"
could come from.
"""
from __future__ import annotations

import re
from typing import Any

from . import config
from .offer import _AMOUNT, _UNITS

MIN_PAYMENT = 100  # smaller bare numbers are more likely days, ages or months than rupees


def fmt_rupees(n: int) -> str:
    """Indian digit grouping: 150000 -> 1,50,000."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *groups, tail])


def parse_amounts(text: str) -> list[int]:
    """Every rupee amount in the text: "10000; 25000", "80,000", "1.5 lakh", "60 వేలు"."""
    # "10000,25000" is two payments, not one number: a thousands comma is followed by
    # exactly 2 or 3 digits ("1,50,000"), never 4 or more.
    text = re.sub(r",(?=\d{4,})", "; ", text.lower())
    out = []
    for num, unit in _AMOUNT.findall(text):
        digits = re.sub(r"\D", "", num)
        if len(digits) >= 10:  # a phone number
            continue
        value = float(num.replace(",", ""))
        if unit:
            value *= _UNITS[unit]
        elif value < MIN_PAYMENT:
            continue
        out.append(int(round(value)))
    return out


def check_fee(payments: Any) -> dict:
    """`payments` is a list of amounts, or text containing amounts."""
    if isinstance(payments, (list, tuple)):
        amounts = [a for item in payments for a in parse_amounts(str(item))]
    else:
        amounts = parse_amounts(str(payments or ""))

    cap = config.FEE_CAP_INR
    total = sum(amounts)
    base = {"payments": amounts, "total": total, "cap": cap, "total_spoken": fmt_rupees(total), "cap_spoken": fmt_rupees(cap)}

    if not amounts:
        return {**base, "status": "no_amount", "over_by": 0, "over_by_spoken": "0",
                "instruction": "No rupee amount was understood. Ask the caller for the total amount in rupees, as digits."}
    if total > cap:
        over = total - cap
        return {**base, "status": "over_cap", "over_by": over, "over_by_spoken": fmt_rupees(over),
                "instruction": (f"The total of {fmt_rupees(total)} rupees is {fmt_rupees(over)} rupees more than the legal maximum of "
                                f"{fmt_rupees(cap)}. Tell the caller this is illegal overcharging. Payment must be digital or by bank "
                                "draft, with a receipt for every payment.")}
    return {**base, "status": "within_cap", "over_by": 0, "over_by_spoken": "0",
            "instruction": (f"The total of {fmt_rupees(total)} rupees is within the legal maximum of {fmt_rupees(cap)}. "
                            "Do not say the agent is honest or safe. Payment must still be digital or by bank draft, with a receipt "
                            "for every payment, and more payments later would count towards the same limit.")}
