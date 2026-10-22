"""Saathi Intelligence: the same phone number, payment account, sponsor or employer
showing up in more than one case.

A signal is a reason for a trained person to look, never a finding. Person names
are left out on purpose: "Raju" or "Mohammed" would link strangers. Employer names
are linked only together with the country, and marked weak: company names repeat.
"""
from __future__ import annotations

import os
import re

from .cases import CaseError, normalize_phone, rank
from .promise import predeparture_checks

# (field on the worker, label shown, kind of value, strong?)
ENTITY_FIELDS = (
    ("sub_agent_phone", "Village agent's phone", "phone", True),
    ("payment_to", "Money paid to (UPI / account / number)", "text", True),
    ("sponsor_id", "Sponsor ID", "text", True),
    ("employer_phone", "Employer's phone", "phone", True),
    ("employer_name", "Employer name (same country)", "company", False),
)

# Words that make two spellings of one company look different.
_COMPANY_NOISE = {"llc", "l.l.c", "co", "company", "est", "establishment", "trading", "services", "service",
                  "group", "the", "and", "&", "wll", "w.l.l", "spc", "fze", "fzco", "ltd", "limited", "pvt"}


def _norm(value, kind: str, worker: dict | None = None) -> str | None:
    if not value:
        return None
    if kind == "phone":
        try:
            return normalize_phone(value)
        except CaseError:
            return None
    if kind == "company":
        words = [w for w in re.findall(r"[a-z0-9]+", str(value).lower()) if w not in _COMPANY_NOISE]
        country = re.sub(r"[^a-z]", "", str((worker or {}).get("dest_country") or "").lower())
        if len(words) < 2 or not country:  # one word ("Noor") or no country links strangers
            return None
        return " ".join(words) + " / " + country
    v = re.sub(r"\s+", "", str(value)).lower()
    return v or None


def include_demo() -> bool:
    """Demo cases never feed warnings given to real callers, unless switched on for a demo."""
    return os.getenv("GS_SIGNALS_INCLUDE_DEMO", "0") == "1"


def _districts(ws: list[dict]) -> list[str]:
    return sorted({" ".join(str(w["agent_district"]).split()).title() for w in ws if w.get("agent_district")})


def repeated_signals(workers: list[dict], min_cases: int = 2) -> list[dict]:
    """Every value shared by at least `min_cases` cases, most worrying first."""
    seen: dict[tuple[str, str], tuple[bool, list[dict]]] = {}
    for w in workers:
        for field, label, kind, strong in ENTITY_FIELDS:
            v = _norm(w.get(field), kind, w)
            if v:
                seen.setdefault((label, v), (strong, []))[1].append(w)
    out = []
    for (label, value), (strong, ws) in seen.items():
        if len(ws) < min_cases:
            continue
        out.append({
            "label": label, "value": value, "strong": strong,
            "cases": [w["case_id"] for w in ws],
            "at_risk": sum(1 for w in ws if rank(w.get("risk_level")) >= rank("high")),
            "flagged": sum(1 for w in ws if predeparture_checks(w)),
            "districts": _districts(ws),
            "demo": all(w.get("is_demo") for w in ws),
        })
    return sorted(out, key=lambda s: (not s["strong"], -s["at_risk"], -s["flagged"], -len(s["cases"]), s["label"]))


def signals_for_case(worker: dict, workers: list[dict]) -> list[dict]:
    return [s for s in repeated_signals(workers) if worker["case_id"] in s["cases"]]


def check_contact(workers: list[dict], phone: str = "", payment: str = "") -> dict:
    """Live check during a call, before the worker pays: has this agent phone or
    payment account come up in other Saathi cases? Returns counts only, never names
    or case details, and an instruction for the voice agent."""
    keys = []
    p = _norm(phone, "phone") if phone else None
    if p:
        keys.append(("phone", p, ("sub_agent_phone", "employer_phone")))
    m = _norm(payment, "text") if payment else None
    if m:
        keys.append(("payment", m, ("payment_to",)))
    if not keys:
        return {"found": False, "cases": 0, "at_risk": 0,
                "instruction": "Ask for the agent's phone number (10 digits) or the UPI ID / account the money goes "
                               "to, then check again."}
    pool = [w for w in workers if include_demo() or not w.get("is_demo")]
    hits = {w["case_id"]: w for w in pool for _, value, fields in keys
            if any(_norm(w.get(f), "phone" if "phone" in f else "text") == value for f in fields)}
    ws = list(hits.values())
    at_risk = sum(1 for w in ws if rank(w.get("risk_level")) >= rank("high"))
    flagged = sum(1 for w in ws if predeparture_checks(w))
    if not ws:
        say = ("Say: this number is not in any Saathi case yet. That does not mean the agent is safe: still check "
               "the licence, ask for an employment visa and a written contract, and pay only with a receipt.")
    elif at_risk or flagged:
        say = (f"Say calmly: this number has come up in {len(ws)} other Saathi case(s); {at_risk} of those workers "
               f"reported serious problems after travelling" + (f" and {flagged} had red flags before travelling"
                                                                if flagged else "") +
               ". This is not proof against anyone, but please do not pay any more money until a Saathi caseworker "
               "has checked it. Never name the other workers or say the agent is a criminal.")
    else:
        say = (f"Say: this number has come up in {len(ws)} other Saathi case(s) and none has reported a problem so "
               "far. That is not a check of the agent: still check the licence and get a written contract.")
    return {"found": bool(ws), "cases": len(ws), "at_risk": at_risk, "flagged": flagged,
            "districts": len(_districts(ws)), "instruction": say}
