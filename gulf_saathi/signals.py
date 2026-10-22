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


def _contact_keys(phone: str = "", payment: str = "") -> tuple[str | None, str | None]:
    return (_norm(phone, "phone") if phone else None), (_norm(payment, "text") if payment else None)


def record_contact(store, data: dict, now_iso: str) -> dict | None:
    """Save an agent phone / payment account a caller told Saathi, with what the agent
    asked for. Every call adds to the picture, not only registered cases."""
    from .cases import as_int, normalize_phone
    phone, payment = _contact_keys(data.get("phone") or "", data.get("payment") or "")
    if not (phone or payment):
        return None
    try:
        caller = normalize_phone(data.get("caller_phone")) if data.get("caller_phone") else None
    except CaseError:
        caller = None
    text = lambda k, n=200: (str(data.get(k) or "").strip()[:n] or None)
    return store.insert("contact_reports", {
        "created_at": now_iso, "phone": phone, "payment": payment, "amount_asked": as_int(data.get("amount")),
        "visa_type": (text("visa_type", 20) or "").lower() or None, "agent_name": text("agent_name"),
        "caller_district": text("district", 60), "reporter": (text("reporter", 20) or "worker").lower(),
        "caller_phone": caller, "notes": text("notes", 500), "is_demo": False,
    })


def _reports_for(reports: list[dict], phone: str | None, payment: str | None, skip_caller: str | None) -> list[dict]:
    return [r for r in reports if ((phone and r.get("phone") == phone) or (payment and r.get("payment") == payment))
            and not (skip_caller and r.get("caller_phone") == skip_caller)]


def _over_cap(r: dict) -> bool:
    from .config import FEE_CAP_INR
    return bool(r.get("amount_asked")) and float(r["amount_asked"]) > FEE_CAP_INR


def check_contact(workers: list[dict], phone: str = "", payment: str = "", reports: list[dict] | None = None,
                  caller_phone: str = "") -> dict:
    """Live check during a call, before the worker pays: has this agent phone or
    payment account come up in other Saathi cases, or been reported by other callers?
    Returns counts only, never names or case details, and an instruction for the voice agent."""
    p, m = _contact_keys(phone, payment)
    if not (p or m):
        return {"found": False, "cases": 0, "at_risk": 0, "callers": 0,
                "instruction": "Ask for the agent's phone number (10 digits) or the UPI ID / account the money goes "
                               "to, read it back digit by digit to confirm, then check again."}
    keys = ([("phone", p, ("sub_agent_phone", "employer_phone"))] if p else []) + ([("payment", m, ("payment_to",))] if m else [])
    pool = [w for w in workers if include_demo() or not w.get("is_demo")]
    hits = {w["case_id"]: w for w in pool for _, value, fields in keys
            if any(_norm(w.get(f), "phone" if "phone" in f else "text") == value for f in fields)}
    ws = list(hits.values())
    at_risk = sum(1 for w in ws if rank(w.get("risk_level")) >= rank("high"))
    flagged = sum(1 for w in ws if predeparture_checks(w))
    try:
        me = normalize_phone(caller_phone) if caller_phone else None
    except CaseError:
        me = None
    rs = _reports_for(reports or [], p, m, me)
    callers = len({r.get("caller_phone") or r["id"] for r in rs})
    over = len({r.get("caller_phone") or r["id"] for r in rs if _over_cap(r)})
    visit = len({r.get("caller_phone") or r["id"] for r in rs if r.get("visa_type") in ("visit", "tourist")})
    if at_risk or flagged:
        say = (f"Say calmly: this number has come up in {len(ws)} other Saathi case(s); {at_risk} of those workers "
               f"reported serious problems after travelling" + (f" and {flagged} had red flags before travelling"
                                                                if flagged else "") +
               ". This is not proof against anyone, but please do not pay any more money until a Saathi caseworker "
               "has checked it. Never name the other workers or say the agent is a criminal.")
    elif over or visit:
        parts = ([f"{over} other caller(s) said this agent asked for more than the legal limit of 35,400 rupees"]
                 if over else []) + ([f"{visit} other caller(s) were offered a visit or tourist visa for a job"] if visit else [])
        say = ("Say calmly: " + "; ".join(parts) + ". This is not proof against anyone, but do not pay more than "
               "35,400 rupees, pay only digitally with a receipt, and never go on a visit visa for a job.")
    elif ws or callers:
        say = (f"Say: other people have asked Saathi about this number before ({len(ws)} case(s), {callers} other "
               "caller(s)), and none reported a problem so far. That is not a check of the agent: still check the "
               "licence and get a written contract.")
    else:
        say = ("Say: this number is not in any Saathi case yet. That does not mean the agent is safe: still check "
               "the licence, ask for an employment visa and a written contract, and pay only with a receipt.")
    return {"found": bool(ws or callers), "cases": len(ws), "at_risk": at_risk, "flagged": flagged,
            "callers": callers, "callers_over_limit": over, "callers_visit_visa": visit,
            "districts": len(_districts(ws) or {r.get("caller_district") for r in rs if r.get("caller_district")}),
            "instruction": say}


def reported_contacts(reports: list[dict], workers: list[dict]) -> list[dict]:
    """Numbers and accounts callers told Saathi about, grouped, most worrying first."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in reports:
        if r.get("is_demo") and not include_demo():
            continue
        for kind in ("phone", "payment"):
            if r.get(kind):
                groups.setdefault((kind, r[kind]), []).append(r)
    out = []
    for (kind, value), rs in groups.items():
        linked = check_contact(workers, **({"phone": value} if kind == "phone" else {"payment": value}))
        dates = sorted(str(r.get("created_at") or "") for r in rs)
        amounts = [float(r["amount_asked"]) for r in rs if r.get("amount_asked")]
        out.append({
            "kind": "Agent phone" if kind == "phone" else "Paid to (UPI / account)", "value": value,
            "callers": len({r.get("caller_phone") or r["id"] for r in rs}), "reports": len(rs),
            "over_limit": sum(1 for r in rs if _over_cap(r)),
            "visit_visa": sum(1 for r in rs if r.get("visa_type") in ("visit", "tourist")),
            "max_amount": max(amounts) if amounts else None,
            "districts": sorted({r["caller_district"].title() for r in rs if r.get("caller_district")}),
            "family_reports": sum(1 for r in rs if r.get("reporter") == "family"),
            "cases": linked["cases"], "at_risk": linked["at_risk"],
            "first_seen": dates[0][:10] if dates else "", "last_seen": dates[-1][:10] if dates else "",
        })
    return sorted(out, key=lambda g: (-g["at_risk"], -g["callers"], -g["over_limit"], g["value"]))
