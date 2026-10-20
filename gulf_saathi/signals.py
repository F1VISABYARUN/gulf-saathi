"""Repeated-risk signals: the same phone number, payment account or sponsor showing
up in more than one case.

A signal is a reason for a person to look, never a finding. Names are left out on
purpose: "Raju" or "Mohammed" would link strangers.
"""
from __future__ import annotations

import re

from .cases import CaseError, normalize_phone, rank
from .promise import predeparture_checks

# (field on the worker, label shown, kind of value)
ENTITY_FIELDS = (
    ("sub_agent_phone", "Village agent's phone", "phone"),
    ("payment_to", "Money paid to (UPI / account / number)", "text"),
    ("sponsor_id", "Sponsor ID", "text"),
    ("employer_phone", "Employer's phone", "phone"),
)


def _norm(value, kind: str) -> str | None:
    if not value:
        return None
    if kind == "phone":
        try:
            return normalize_phone(value)
        except CaseError:
            return None
    v = re.sub(r"\s+", "", str(value)).lower()
    return v or None


def repeated_signals(workers: list[dict], min_cases: int = 2) -> list[dict]:
    """Every value shared by at least `min_cases` cases, most worrying first."""
    seen: dict[tuple[str, str], list[dict]] = {}
    for w in workers:
        for field, label, kind in ENTITY_FIELDS:
            v = _norm(w.get(field), kind)
            if v:
                seen.setdefault((label, v), []).append(w)
    out = []
    for (label, value), ws in seen.items():
        if len(ws) < min_cases:
            continue
        out.append({
            "label": label, "value": value,
            "cases": [w["case_id"] for w in ws],
            "at_risk": sum(1 for w in ws if rank(w.get("risk_level")) >= rank("high")),
            "flagged": sum(1 for w in ws if predeparture_checks(w)),
            "demo": all(w.get("is_demo") for w in ws),
        })
    return sorted(out, key=lambda s: (-s["at_risk"], -s["flagged"], -len(s["cases"]), s["label"]))


def signals_for_case(worker: dict, workers: list[dict]) -> list[dict]:
    return [s for s in repeated_signals(workers) if worker["case_id"] in s["cases"]]
