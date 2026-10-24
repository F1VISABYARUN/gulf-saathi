"""Promise vs reality: what the worker was promised (the case's job_title), what the papers say, and what
the worker says is happening now.

The voice AI only turns speech into words ("herding goats"). These fixed rules
decide whether two jobs are the same kind of work, so every flag can be explained.
"""
from __future__ import annotations

import re

# Kinds of work, with English and Telugu words that point to them. A job matching
# no category is "unknown" and never raises a flag on its own.
JOB_CATEGORIES = {
    "cleaning": ["cleaner", "cleaning", "housekeeping", "janitor", "sweeper", "క్లీనర్", "క్లీనింగ్", "శుభ్రం"],
    "farm and livestock": ["agricultur", "farm", "shepherd", "herder", "herding", "camel", "goat", "sheep", "cattle",
                           "livestock", "date palm", "వ్యవసాయ", "పొలం", "గొర్రె", "మేక", "ఒంటె", "పశువు", "గేదె", "ఆవు"],
    "driving": ["driver", "driving", "chauffeur", "డ్రైవర్", "డ్రైవింగ్"],
    "domestic work": ["domestic", "housemaid", "maid", "house worker", "household", "nanny", "babysit",
                      "ఇంటి పని", "పనిమనిషి"],
    "construction": ["mason", "construction", "labour", "labor", "scaffold", "steel fix", "shuttering",
                     "మేస్త్రి", "కూలి", "నిర్మాణ"],
    "electrical": ["electrician", "electrical", "ఎలక్ట్రీషియన్"],
    "plumbing": ["plumber", "plumbing", "ప్లంబర్"],
    "welding": ["welder", "welding", "వెల్డర్"],
    "carpentry": ["carpenter", "carpentry", "కార్పెంటర్", "వడ్రంగి"],
    "painting": ["painter", "painting", "పెయింటర్"],
    "cooking": ["cook", "chef", "kitchen", "వంట"],
    "security": ["security", "guard", "watchman", "సెక్యూరిటీ", "వాచ్‌మెన్"],
    "hotel and restaurant": ["waiter", "hotel", "restaurant", "room boy", "steward"],
    "sales": ["salesman", "sales", "cashier", "store keeper", "storekeeper"],
    "nursing and care": ["nurse", "nursing", "caregiver", "నర్సు"],
    "tailoring": ["tailor", "stitching", "దర్జీ"],
    "gardening": ["gardener", "garden", "landscap"],
}

VISA_TYPES = ("employment", "visit", "tourist", "unknown")


def job_categories(text: str | None) -> set[str]:
    t = (text or "").lower()
    return {cat for cat, words in JOB_CATEGORIES.items() if any(w in t for w in words)}


def compare_jobs(promised: str | None, other: str | None) -> str:
    """"match", "conflict", or "unknown" when either job is missing or unrecognised."""
    a, b = job_categories(promised), job_categories(other)
    if not a or not b:
        return "unknown"
    return "match" if a & b else "conflict"


def _norm_place(text: str | None) -> str:
    return re.sub(r"[^a-zఀ-౿]", "", (text or "").lower())


def compare_places(promised: str | None, now: str | None) -> str:
    a, b = _norm_place(promised), _norm_place(now)
    if not a or not b:
        return "unknown"
    return "match" if a in b or b in a else "conflict"


def is_woman_domestic(w: dict) -> bool:
    """A woman going for housework: the job most often hidden inside a private house abroad."""
    jobs = job_categories(w.get("job_title")) | job_categories(w.get("visa_job"))
    return w.get("worker_gender") == "woman" and "domestic work" in jobs


def predeparture_checks(w: dict) -> list[dict]:
    """Red flags found before the worker flies. Each has a code and plain English text."""
    flags = []
    if is_woman_domestic(w) and w.get("visa_type") in ("visit", "tourist"):
        # MEA has said agents send women on tourist visas so emigration checks don't stop them.
        flags.append({"code": "domestic_visit_visa",
                      "text": f"Woman going for housework on a {w['visa_type']} visa: the route used to get past "
                              "emigration checks. High risk of being sold between houses abroad"})
    elif is_woman_domestic(w):
        flags.append({"code": "domestic_woman",
                      "text": "Woman going for housework: with an ECR passport, only a state government recruiting "
                              "agency may send her, and the employer must be approved on eMigrate"})
    if w.get("worker_gender") == "woman" and w.get("worker_age") and int(w["worker_age"]) < 30:
        flags.append({"code": "woman_under_30",
                      "text": f"Woman aged {int(w['worker_age'])}: with an ECR passport, India does not give emigration "
                              "clearance to women under 30 for jobs in ECR countries (all Gulf countries)"})
    if w.get("agent_check") in ("not_found", "need_more_info"):
        flags.append({"code": "agent_not_listed", "text": "Agent not found in the licensed list"})
    if w.get("fee_status") == "over_cap" and w.get("amount_paid_total"):
        from .fees import fmt_rupees
        flags.append({"code": "fee_over_cap",
                      "text": f"Paid agent Rs {fmt_rupees(int(w['amount_paid_total']))}, over the Rs 35,400 limit"})
    if w.get("visa_type") in ("visit", "tourist"):
        flags.append({"code": "visit_visa",
                      "text": f"The visa on the papers is a {w['visa_type']} visa, not an employment visa"})
    if compare_jobs(w.get("job_title"), w.get("visa_job")) == "conflict":
        flags.append({"code": "visa_job_mismatch",
                      "text": f"Promised job \"{w.get('job_title')}\" but the visa says \"{w.get('visa_job')}\""})
    return flags


# Flags serious enough that the worker should not pay more or fly until they are resolved.
STOP_FLAGS = {"visit_visa", "visa_job_mismatch", "domestic_visit_visa"}


def promise_rows(w: dict, latest_answers: dict) -> list[dict]:
    """Rows for the promise-vs-reality table: promised, on papers, now, and the verdict."""
    now_job = latest_answers.get("current_job")
    now_city = latest_answers.get("current_city")
    papers_vs_promise = compare_jobs(w.get("job_title"), w.get("visa_job"))
    now_vs_promise = compare_jobs(w.get("job_title"), now_job)
    verdict = "conflict" if "conflict" in (papers_vs_promise, now_vs_promise) else \
        "match" if "match" in (papers_vs_promise, now_vs_promise) else "unknown"
    return [
        {"what": "Job", "promised": w.get("job_title"), "papers": w.get("visa_job"), "now": now_job,
         "verdict": verdict},
        {"what": "Visa type", "promised": "employment", "papers": w.get("visa_type"), "now": None,
         "verdict": "conflict" if w.get("visa_type") in ("visit", "tourist") else
         "match" if w.get("visa_type") == "employment" else "unknown"},
        {"what": "City", "promised": w.get("dest_city"), "papers": None, "now": now_city,
         "verdict": compare_places(w.get("dest_city"), now_city)},
        {"what": "Salary", "promised": _money(w.get("contract_salary"), w), "papers": None,
         "now": _money(latest_answers.get("salary_amount"), w), "verdict": compare_salary(w, latest_answers)},
    ]


def _money(v, w: dict) -> str | None:
    return f"{int(float(v))} {w.get('salary_currency') or ''}".strip() if v not in (None, "") else None


def compare_salary(w: dict, answers: dict) -> str:
    """Less than 90% of the contract is a conflict: the same rule the risk engine uses."""
    paid, promised = answers.get("salary_amount"), w.get("contract_salary")
    if not paid or not promised:
        return "unknown"
    return "conflict" if paid < float(promised) * 0.9 else "match"
