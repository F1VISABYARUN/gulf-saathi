"""Worker cases: registration, check-in answers, risk levels, family alerts,
call scheduling and the English case packet.

Everything here takes a store (db.MemoryStore or db.SupabaseStore) and the
current time, so the whole flow runs in tests without Supabase or Bolna.
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from . import bolna, promise, sms
from .calls import parse_call
from .fees import check_fee, fmt_rupees
from .matcher import LicensedList

IST = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving
CHECKIN_DAYS = int(os.getenv("GS_CHECKIN_DAYS", "7"))
RETRY_HOURS = {"arrival": 3, "weekly": 24}  # after a missed call
# After an answered call, how soon Saathi calls back, by the worker's risk now:
# a person in danger is not left for a week.
FOLLOW_UP = {"critical": timedelta(hours=3), "high": timedelta(days=1)}
# Never more than one automatic call to the same worker in this window, whatever
# else happens (a booking Bolna places at once instead of later must not loop).
AUTO_CALL_GAP = timedelta(hours=int(os.getenv("GS_AUTO_CALL_GAP_HOURS", "6")))


def auto_calls_on() -> bool:
    """Calls the server books by itself after a call ends (retries, follow-ups, next
    week). Off unless GS_AUTO_CALLS=1: on 22 Oct 2026 booked calls came at once and
    looped. "Call now" on the dashboard always works."""
    return os.getenv("GS_AUTO_CALLS", "0") == "1"


def _recent_call_other_than(store, worker_id: str, this_call: str, now: datetime) -> bool:
    """A call other than the one just ended was created in the last AUTO_CALL_GAP."""
    for c in store.select("calls", {"worker_id": worker_id}):
        if c["id"] == this_call or c.get("status") == "scheduled":
            continue  # booked for later and not yet happened
        made = parse_ts(c.get("created_at"))
        if made and now - made < AUTO_CALL_GAP:
            return True
    return False
DEFAULT_CODE_PHRASE = "అమ్మ బాగుందా"  # "Is Amma well?": says "I can't talk freely" without saying it
CHECKIN_KINDS = ("arrival", "weekly")  # calls that count towards misses and alerts
CALL_KINDS = (*CHECKIN_KINDS, "briefing")  # briefing: pre-departure, before the worker flies
# "help": the worker called the Gulf Saathi line themselves and asked for help. Not a
# scheduled call, so it is recorded as a check-in but never booked or counted as missed.
CHECKIN_RECORD_KINDS = (*CALL_KINDS, "help")

LEVELS = ("ok", "medium", "high", "critical")
GENDERS = ("woman", "man")

# code: (level, English for the dashboard and packet, Telugu for the family SMS)
REASONS = {
    "wrong_pickup": ("critical", "Picked up at the airport by someone other than the registered employer",
                     "విమానాశ్రయంలో నమోదైన యజమాని కాకుండా వేరే వ్యక్తి తీసుకెళ్లారు"),
    "no_pickup": ("critical", "Nobody came to pick the worker up at the airport",
                  "విమానాశ్రయంలో తీసుకెళ్లడానికి ఎవరూ రాలేదు"),
    "threatened": ("critical", "Reports threats or violence", "బెదిరింపులు లేదా హింస జరుగుతోందని చెప్పారు"),
    "movement_restricted": ("critical", "Not allowed to go out", "బయటకు వెళ్లనివ్వడం లేదని చెప్పారు"),
    "needs_help": ("critical", "Asked for urgent help", "వెంటనే సహాయం కావాలని అడిగారు"),
    "code_phrase": ("critical", "Said the agreed danger phrase: may not be able to speak freely",
                    "ముందే చెప్పుకున్న ప్రమాద సంకేతం చెప్పారు"),
    "death_reported": ("critical", "Death reported: {detail}", "మరణించినట్లు సమాచారం వచ్చింది"),
    "job_mismatch": ("high", "Doing different work from the job promised: {detail}",
                     "చెప్పిన ఉద్యోగం కాకుండా వేరే పని చేయిస్తున్నారు"),
    "employer_changed": ("high", "Moved to a different employer or house than the one registered",
                         "నమోదైన యజమాని కాకుండా వేరే ఇంటికి లేదా వేరే యజమాని దగ్గరకు పంపారు"),
    "missed_1_domestic": ("high", "Missed the last check-in call. She works inside a private house, so one missed "
                                  "call is a warning sign", "చివరి కాల్‌కు జవాబు రాలేదు; ఇంటి పనిలో ఉన్నందున ఇది ప్రమాద సంకేతం"),
    "passport_taken": ("high", "Passport is not with the worker", "పాస్‌పోర్ట్ వారి దగ్గర లేదు"),
    "unpaid_2plus": ("high", "Salary unpaid for {n} months", "{n} నెలలుగా జీతం రాలేదు"),
    "missed_2plus": ("high", "{n} check-in calls missed in a row", "వరుసగా {n} కాల్స్‌కు జవాబు రాలేదు"),
    "unpaid_1": ("medium", "Salary unpaid this month", "ఈ నెల జీతం రాలేదు"),
    "salary_short": ("high", "Paid less than the contract: {detail}", "ఒప్పందంలో చెప్పిన జీతం కంటే తక్కువ ఇస్తున్నారు"),
    "papers_problem": ("high", "Papers problem (risk of arrest; the agent's doing, not the worker's): {detail}",
                       "వీసా లేదా పత్రాల సమస్య ఉంది; అరెస్టు భయం ఉంది"),
    "city_mismatch": ("medium", "In a different city from the one promised: {detail}",
                      "చెప్పిన ఊరు కాకుండా వేరే చోట ఉన్నారు"),
    "food_not_ok": ("medium", "Problems with food or accommodation", "భోజనం లేదా వసతి సరిగా లేదు"),
    "missed_1": ("medium", "Missed the last check-in call", "చివరి కాల్‌కు జవాబు రాలేదు"),
}


class CaseError(ValueError):
    pass


# --- small helpers ------------------------------------------------------------

def rank(level: str | None) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_india_time(value) -> datetime | None:
    """A time typed on the dashboard ("2026-10-25T09:30") is India time."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise CaseError(f"not a date and time: {value}")
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def fmt_ist(value) -> str:
    dt = parse_ts(value)
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M IST") if dt else "—"


def normalize_phone(raw) -> str:
    """"98765 43210" -> "+919876543210". Numbers with a country code keep it."""
    s = re.sub(r"[^\d+]", "", str(raw or ""))
    if not s:
        return ""
    if s.startswith("00"):
        s = "+" + s[2:]
    digits = s.lstrip("+")
    if s.startswith("+"):
        out = "+" + digits
    elif len(digits) == 10:
        out = "+91" + digits
    elif len(digits) == 12 and digits.startswith("91"):
        out = "+" + digits
    else:
        out = "+" + digits
    if not 9 <= len(out) - 1 <= 15:
        raise CaseError(f"not a phone number: {raw}")
    return out


def new_case_id(store) -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: easy to read out on a call
    while True:
        cid = "GS-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not store.get("workers", case_id=cid):
            return cid


def reason_text(reason: dict, lang: str = "en") -> str:
    level, en, te = REASONS[reason["code"]]
    return (te if lang == "te" else en).format(n=reason.get("n", ""), detail=reason.get("detail", ""))


# --- answers and risk -----------------------------------------------------------

_YES = {"yes", "y", "true", "1", "haan", "ha", "avunu", "అవును", "ఔను", "ఉంది", "వచ్చింది", "అందింది"}
_NO = {"no", "n", "false", "0", "ledu", "లేదు", "కాదు", "raledu", "రాలేదు"}
_PICKUP = {
    "employer": "employer", "named_employer": "employer", "registered_employer": "employer",
    "other_person": "other_person", "other": "other_person", "someone_else": "other_person", "stranger": "other_person",
    "nobody": "nobody", "none": "nobody", "no_one": "nobody",
    "not_arrived": "not_arrived", "not_landed": "not_arrived",
}


def yes_no(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return True if s in _YES else False if s in _NO else None


def as_int(v) -> int | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None


def normalize_answers(raw: dict) -> dict:
    """Answers from the record_checkin tool or Bolna's extracted_data, cleaned up."""
    raw = {str(k).lower(): v for k, v in (raw or {}).items()}
    pickup = _PICKUP.get(str(raw.get("pickup_status") or "").strip().lower().replace(" ", "_"))
    if pickup is None and "picked_up_by_named_employer" in raw:  # field name in Hark's notes
        named = yes_no(raw["picked_up_by_named_employer"])
        pickup = {True: "employer", False: "other_person"}.get(named)
    if pickup is None and yes_no(raw.get("taken_by_stranger")):
        # Help line: "someone I don't know took me from the airport / is taking me now".
        pickup = "other_person"
    text = lambda k: "" if str(raw.get(k) or "").strip().lower() == "not_said" else str(raw.get(k) or "").strip()[:500]
    return {
        "pickup_status": pickup,
        "pickup_person": text("pickup_person"),
        "current_location": text("current_location"),
        "current_job": text("current_job"),
        "current_city": text("current_city"),
        "landmark": text("landmark"),
        "home_district": text("home_district"),
        "agent_name": text("agent_name"),
        "agent_phone": text("agent_phone"),
        "salary_received": yes_no(raw.get("salary_received")),
        "salary_amount": as_int(raw.get("salary_amount")) if text("salary_amount") else None,
        "papers_problem": "" if text("papers_problem").lower() in _NO | {"none", "fine", "ok"} else text("papers_problem"),
        "months_unpaid": as_int(raw.get("months_unpaid")),
        "passport_with_worker": yes_no(raw.get("passport_with_worker")),
        "food_ok": yes_no(raw.get("food_ok")),
        "threatened": yes_no(raw.get("threatened")),
        "movement_restricted": yes_no(raw.get("movement_restricted")),
        "employer_changed": yes_no(raw.get("employer_changed")),
        "needs_help": yes_no(raw.get("needs_help")),
        "code_phrase_used": yes_no(raw.get("code_phrase_used")),
        "briefing_understood": yes_no(raw.get("briefing_understood")),
        "notes": text("notes"),
    }


def assess(answers: dict, missed_in_row: int = 0, worker: dict | None = None) -> tuple[str, list[dict]]:
    """Fixed rules turn answers into a risk level. With the worker's case, also
    compares the work and city they describe now with what they were promised."""
    reasons = []
    if answers.get("pickup_status") == "other_person":
        reasons.append({"code": "wrong_pickup"})
    elif answers.get("pickup_status") == "nobody":
        reasons.append({"code": "no_pickup"})
    for key, code in (("threatened", "threatened"), ("movement_restricted", "movement_restricted"),
                      ("needs_help", "needs_help"), ("code_phrase_used", "code_phrase")):
        if answers.get(key) is True:
            reasons.append({"code": code})
    if worker and promise.compare_jobs(worker.get("job_title"), answers.get("current_job")) == "conflict":
        reasons.append({"code": "job_mismatch",
                        "detail": f'promised "{worker["job_title"]}", says "{answers["current_job"]}"'})
    if answers.get("employer_changed") is True:
        reasons.append({"code": "employer_changed"})
    if answers.get("passport_with_worker") is False:
        reasons.append({"code": "passport_taken"})
    months = answers.get("months_unpaid")
    if answers.get("salary_received") is False and not months:
        months = 1
    if months and months >= 2:
        reasons.append({"code": "unpaid_2plus", "n": months})
    elif months == 1:
        reasons.append({"code": "unpaid_1"})
    if worker and promise.compare_places(worker.get("dest_city"), answers.get("current_city")) == "conflict":
        reasons.append({"code": "city_mismatch",
                        "detail": f'promised "{worker["dest_city"]}", says "{answers["current_city"]}"'})
    paid, promised = answers.get("salary_amount"), (worker or {}).get("contract_salary")
    if worker and promise.compare_salary(worker, answers) == "conflict":
        cur = worker.get("salary_currency") or ""
        reasons.append({"code": "salary_short",
                        "detail": f"gets {paid} {cur}, contract says {int(float(promised))} {cur}".replace("  ", " ")})
    if answers.get("papers_problem"):
        reasons.append({"code": "papers_problem", "detail": answers["papers_problem"]})
    if answers.get("food_ok") is False:
        reasons.append({"code": "food_not_ok"})
    if missed_in_row >= 2:
        reasons.append({"code": "missed_2plus", "n": missed_in_row})
    elif missed_in_row == 1 and worker and promise.is_woman_domestic(worker):
        reasons.append({"code": "missed_1_domestic"})
    elif missed_in_row == 1:
        reasons.append({"code": "missed_1"})
    level = max((REASONS[r["code"]][0] for r in reasons), key=rank, default="ok")
    return level, reasons


def overall_level(store, worker_id: str, latest: str) -> str:
    """The badge: the latest assessment, but never lower than an alert nobody has resolved."""
    open_levels = [e["level"] for e in store.select("escalations", {"worker_id": worker_id, "status": "open"})]
    return max([latest, *open_levels], key=rank)


# --- family alert ---------------------------------------------------------------

def family_sms(worker: dict, level: str, reasons: list[dict]) -> str:
    """All Telugu (the case number is the only Latin text). Never promises rescue."""
    name = worker.get("worker_name_te") or worker["worker_name"]
    what = ", ".join(reason_text(r, "te") for r in reasons)
    parts = [("అత్యవసరం: " if level == "critical" else "") + f"గల్ఫ్ సాథీ: {name} గారి విషయంలో {what}."]
    if any(r["code"] == "code_phrase" for r in reasons):
        parts.append("దయచేసి వారికి ఫోన్ చేయండి, కానీ ఈ విషయం ఫోన్‌లో నేరుగా అడగకండి.")
    else:
        parts.append("దయచేసి వెంటనే వారికి ఫోన్ చేయండి.")
    parts.append(f"భారత రాయబార కార్యాలయానికి ఇవ్వడానికి ఫిర్యాదు వివరాలు సిద్ధం చేశాం. కేసు నంబర్ {worker['case_id']}.")
    return " ".join(parts)


def escalate(store, worker: dict, level: str, reasons: list[dict], now: datetime,
             notify_family: bool = True) -> dict | None:
    """Open an alert and text the family, unless an unresolved alert already covers
    the same problems. Repeating the same SMS every day would teach families to
    ignore it; a new kind of problem still gets through."""
    codes = {r["code"] for r in reasons}
    for e in store.select("escalations", {"worker_id": worker["id"], "status": "open"}):
        if rank(e["level"]) >= rank(level) and codes <= {r["code"] for r in e.get("reasons") or []}:
            return None
    if not notify_family:
        text, status = "", "not sent: a death is told to the family by a person, never by SMS"
    else:
        text = family_sms(worker, level, reasons)
        status = "demo: not sent" if worker.get("is_demo") else sms.send_sms(worker.get("family_phone") or "", text)
    return store.insert("escalations", {
        "worker_id": worker["id"], "level": level, "reasons": reasons,
        "family_sms": text, "sms_status": status, "status": "open", "created_at": iso(now),
    })


# --- registration -----------------------------------------------------------------

def _text(data: dict, key: str, limit: int = 200) -> str | None:
    v = str(data.get(key) or "").strip()
    return v[:limit] or None


# Everyday words make bad danger phrases: the worker would say them by accident.
# "Anna" (elder brother) is also how the voice agent itself talks.
_WEAK_PHRASES = {"anna", "annaa", "అన్న", "అన్నా", "amma", "అమ్మ", "hello", "హలో", "ok", "okay"}
CODE_PHRASE_HELP = "Use a short sentence the worker would never say by accident, e.g. " + DEFAULT_CODE_PHRASE


def code_phrase_ok(phrase: str | None) -> bool:
    p = (phrase or "").strip().strip(".!?,").lower()
    return len(p.split()) >= 2 and p not in _WEAK_PHRASES


def clean_case_fields(data: dict, licensed: LicensedList) -> dict:
    """Validate and normalise everything a caseworker types in, for registering or
    editing a case. Re-runs the agent and fee checks. Raises CaseError."""
    name = _text(data, "worker_name")
    if not name:
        raise CaseError("worker name is required")
    worker_phone = normalize_phone(data.get("worker_phone"))
    family_phone = normalize_phone(data.get("family_phone"))
    if not worker_phone or not family_phone:
        raise CaseError("worker phone and family phone are required")

    agent = {k: _text(data, k) for k in ("agent_name", "agent_owner", "agent_licence", "agent_district")}
    agent_check, agent_detail = None, {}
    if agent["agent_name"] or agent["agent_owner"] or agent["agent_licence"]:
        res = licensed.check(agent["agent_name"] or "", agent["agent_owner"] or "",
                             agent["agent_district"] or "", agent["agent_licence"] or "")
        agent_check = res["match"]
        agent_detail = {"candidates": res["candidates"], "reason": res["reason"]}

    fee = check_fee(data.get("payments") or "")
    departure = _text(data, "departure_date", 10)
    if departure:
        try:
            date.fromisoformat(departure)
        except ValueError:
            raise CaseError(f"departure date must be YYYY-MM-DD: {departure}")
    arrival_call_at = parse_india_time(data.get("arrival_call_at"))
    salary = data.get("contract_salary")
    try:
        salary = float(str(salary).replace(",", "")) if str(salary or "").strip() else None
    except ValueError:
        raise CaseError(f"salary must be a number: {salary}")
    visa_type = (_text(data, "visa_type", 20) or "").lower() or None
    if visa_type and visa_type not in promise.VISA_TYPES:
        raise CaseError(f"visa type must be one of {', '.join(promise.VISA_TYPES)}: {visa_type}")
    gender = (_text(data, "worker_gender", 10) or "").lower() or None
    if gender and gender not in GENDERS:
        raise CaseError(f"gender must be one of {', '.join(GENDERS)}: {gender}")
    age = as_int(data.get("worker_age")) if str(data.get("worker_age") or "").strip() else None
    if age is not None and not 14 <= age <= 90:
        raise CaseError(f"age must be a number of years: {data.get('worker_age')}")
    sub_agent_phone = normalize_phone(data.get("sub_agent_phone")) if data.get("sub_agent_phone") else None
    code_phrase = _text(data, "code_phrase") or DEFAULT_CODE_PHRASE
    if not code_phrase_ok(code_phrase):
        raise CaseError(f'danger code phrase "{code_phrase}" is too easy to say by accident. {CODE_PHRASE_HELP}')

    return {
        "worker_name": name, "worker_name_te": _text(data, "worker_name_te"), "worker_phone": worker_phone,
        "worker_gender": gender, "worker_age": age,
        "family_name": _text(data, "family_name"), "family_phone": family_phone,
        "family_relation": _text(data, "family_relation"),
        "employer_name": _text(data, "employer_name"),
        "employer_phone": normalize_phone(data.get("employer_phone")) if data.get("employer_phone") else None,
        "sponsor_name": _text(data, "sponsor_name"), "sponsor_id": _text(data, "sponsor_id"),
        "dest_country": _text(data, "dest_country"), "dest_city": _text(data, "dest_city"),
        "job_title": _text(data, "job_title"),
        "visa_job": _text(data, "visa_job"), "visa_type": visa_type,
        "contract_salary": salary, "salary_currency": _text(data, "salary_currency", 10),
        **agent, "agent_check": agent_check, "agent_check_detail": agent_detail,
        "sub_agent_name": _text(data, "sub_agent_name"), "sub_agent_phone": sub_agent_phone,
        "payment_to": _text(data, "payment_to"),
        "payments": fee["payments"], "amount_paid_total": fee["total"], "fee_status": fee["status"],
        "departure_date": departure, "flight_no": _text(data, "flight_no", 20),
        "arrival_call_at": iso(arrival_call_at) if arrival_call_at else None,
        "code_phrase": code_phrase,
        "notes": _text(data, "notes", 2000),
    }


def welcome_sms(worker: dict) -> str:
    """The one SMS the family gets at registration, so they know the number and the case."""
    name = worker.get("worker_name_te") or worker["worker_name"]
    return (f"గల్ఫ్ సాథీ: {name} గారి వివరాలు నమోదు చేశాం. కేసు నంబర్ {worker['case_id']}. "
            "వారు చేరిన రోజు, తర్వాత ప్రతి వారం సాథీ వారికి ఫోన్ చేస్తుంది. "
            "ఏదైనా సమస్య ఉంటే మీకు మెసేజ్ వస్తుంది. ఈ నంబర్ దాచుకోండి.")


def register_worker(store, licensed: LicensedList, data: dict, now: datetime, is_demo: bool = False,
                    send_welcome: bool = True) -> dict:
    """Create the pre-departure case and text the family once.
    Returns {"worker": ..., "arrival_call": ...}."""
    fields = clean_case_fields(data, licensed)
    worker = store.insert("workers", {
        "case_id": new_case_id(store), "created_at": iso(now), "updated_at": iso(now), **fields,
        "status": "registered", "risk_level": "ok", "risk_reasons": [], "missed_checkins": 0,
        "source": "demo" if is_demo else "dashboard", "is_demo": is_demo,
    })
    if send_welcome:
        text = welcome_sms(worker)
        status = "demo: not sent" if is_demo else sms.send_sms(worker["family_phone"], text)
        store.update("workers", {"id": worker["id"]}, {"welcome_sms": text, "welcome_sms_status": status})
    arrival_at = parse_ts(fields["arrival_call_at"])
    arrival = schedule_call(store, worker, "arrival", arrival_at, now) if arrival_at else None
    return {"worker": store.get("workers", id=worker["id"]), "arrival_call": arrival}


def update_worker(store, licensed: LicensedList, worker: dict, data: dict, now: datetime) -> dict:
    """Correct a case's details. The case ID, status, risk and timeline stay as they are.
    Does not book or move calls: the case page offers that."""
    fields = clean_case_fields(data, licensed)
    changes = {**fields, "updated_at": iso(now)}
    if not _other_booked_call(store, worker["id"], "", now):
        # Clears a "next call" time saved when booking had actually failed.
        changes["next_call_at"] = None
    store.update("workers", {"id": worker["id"]}, changes)
    return store.get("workers", id=worker["id"])


def arrival_call_booked(store, worker: dict) -> bool:
    return any(c.get("kind") == "arrival" for c in store.select("calls", {"worker_id": worker["id"]}))


def book_arrival_call(store, worker: dict, now: datetime) -> dict:
    """Book the arrival call that registration couldn't (e.g. Bolna wasn't set up yet).
    If its time has already passed, call now."""
    when = parse_ts(worker.get("arrival_call_at"))
    if not when:
        raise CaseError("no arrival-day call time is set for this case")
    return schedule_call(store, worker, "arrival", when if when > now + timedelta(minutes=1) else None, now)


# --- calls ------------------------------------------------------------------------

def call_user_data(worker: dict, kind: str) -> dict:
    """Variables the check-in agent's prompt can use ({{case_id}}, {{employer_name}}, ...)."""
    return {
        "case_id": worker["case_id"], "call_kind": kind,
        "worker_name": worker.get("worker_name_te") or worker["worker_name"],
        "employer_name": worker.get("employer_name") or "",
        "promised_job": worker.get("job_title") or "",
        "employer_phone": worker.get("employer_phone") or "",
        "sponsor_name": worker.get("sponsor_name") or "",
        "dest_city": worker.get("dest_city") or "", "dest_country": worker.get("dest_country") or "",
        "code_phrase": worker.get("code_phrase") or DEFAULT_CODE_PHRASE,
    }


def schedule_call(store, worker: dict, kind: str, when: datetime | None, now: datetime) -> dict:
    """Ask Bolna to call the worker at `when` (or now). Records the call so the
    webhook can match it and the dashboard can show it."""
    later = when is not None and when > now + timedelta(minutes=1)
    if worker.get("death_reported_at"):
        return {"ok": False, "execution_id": None, "kind": kind, "when": iso(now),
                "error": "A death was reported for this case: Saathi does not call this number. "
                         "If the report was a mistake, clear it on the case page."}
    if worker.get("is_demo"):
        # Demo numbers are made up but could belong to real people, and calls cost credits.
        return {"ok": False, "execution_id": None, "error": "Demo case: Saathi never calls demo numbers",
                "kind": kind, "when": iso(now)}
    res = bolna.place_call(worker["worker_phone"], call_user_data(worker, kind), when if later else None)
    if res["ok"] and later:
        # Only after Bolna accepted it: the dashboard must not show a call that isn't booked.
        store.update("workers", {"id": worker["id"]}, {"next_call_at": iso(when), "updated_at": iso(now)})
    if res["ok"] and res["execution_id"]:
        store.upsert("calls", {
            "id": res["execution_id"], "worker_id": worker["id"], "kind": kind,
            "status": "scheduled" if later else "queued",
            "scheduled_at": iso(when) if later else iso(now), "created_at": iso(now), "updated_at": iso(now),
        })
    return {**res, "kind": kind, "when": iso(when) if later else iso(now)}


def _trim_raw(payload: dict) -> dict:
    # Latency and billing details are large and not part of the evidence trail.
    return {k: v for k, v in payload.items() if k not in ("latency_data", "usage_breakdown", "cost_breakdown")}


def _find_worker(store, case_id: str, existing_call: dict | None, phone: str | None) -> dict | None:
    if case_id:
        w = store.get("workers", case_id=case_id)
        if w:
            return w
    if existing_call and existing_call.get("worker_id"):
        w = store.get("workers", id=existing_call["worker_id"])
        if w:
            return w
    if phone:
        try:
            return store.get("workers", worker_phone=normalize_phone(phone))
        except CaseError:
            return None
    return None


def _other_booked_call(store, worker_id: str, this_call: str, now: datetime) -> bool:
    """Is a different call already booked for this worker, not yet made?"""
    for c in store.select("calls", {"worker_id": worker_id}):
        when = parse_ts(c.get("scheduled_at"))
        if c["id"] != this_call and when and when > now + timedelta(minutes=30) and c.get("status") in ("scheduled", "queued"):
            return True
    return False


def process_call_record(store, payload: dict, now: datetime) -> dict:
    """Webhook: save the call, and once it has ended, count a miss or a contact,
    raise alerts and book the next call. Safe to receive many times per call."""
    c = parse_call(payload)
    if not c["call_id"]:
        return {"stored": False, "reason": "no call id"}
    rd = c["recipient_data"] or {}
    existing = store.get("calls", id=c["call_id"])
    worker = _find_worker(store, str(rd.get("case_id") or "").strip().upper(), existing, c["user_number"])
    kind = rd.get("call_kind") or (existing or {}).get("kind") or "other"

    row = {
        "id": c["call_id"], "worker_id": worker["id"] if worker else None, "kind": kind,
        "status": c["status"], "answered": c["answered"], "missed": c["missed"],
        "duration_seconds": c["duration_seconds"], "transcript": c["transcript"],
        "recording_url": c["recording_url"], "extracted": c["extracted"], "raw": _trim_raw(payload),
        "updated_at": iso(now),
    }
    if not existing:
        row["created_at"] = iso(now)
    store.upsert("calls", row)

    if c["terminal"] and kind not in CALL_KINDS and c["extracted"] and not (existing or {}).get("processed_at"):
        # A call to the Gulf Saathi line (Saathi didn't place it). Bolna's after-call
        # extraction is the safety net if the live voice AI missed report_problem.
        help_out = help_from_extraction(store, c, now)
        if help_out is not None:
            hw = store.get("workers", case_id=help_out["case_id"])
            store.update("calls", {"id": c["call_id"]}, {"processed_at": iso(now), "kind": "help", "worker_id": hw["id"]})
            return {"stored": True, "processed": True, "worker": hw["case_id"], "help": help_out}
    if (c["terminal"] and worker and kind in CHECKIN_KINDS and (existing or {}).get("processed_at")
            and c["extracted"] and not (existing or {}).get("extracted") and c["answered"]):
        # Bolna sends "call-disconnected" (processed above) before "completed", and only
        # "completed" carries the after-call extraction. Score it now: the safety net
        # for when the live voice AI never called record_checkin.
        return _apply_late_extraction(store, worker, kind, c, now)
    if worker and worker.get("death_reported_at"):
        # A call booked before the death was reported: keep the record, but never
        # count a miss, text the family or book another call.
        return {"stored": True, "processed": False, "worker": worker["case_id"], "death_reported": True}
    if not c["terminal"] or not worker or kind not in CHECKIN_KINDS or (existing or {}).get("processed_at"):
        return {"stored": True, "processed": False, "worker": worker["case_id"] if worker else None}
    store.update("calls", {"id": c["call_id"]}, {"processed_at": iso(now)})

    if c["missed"]:
        missed = int(worker.get("missed_checkins") or 0) + 1
        level, reasons = assess({}, missed_in_row=missed, worker=worker)
        changes = {"missed_checkins": missed}
        next_when = now + timedelta(hours=RETRY_HOURS[kind])
        next_kind = kind
    else:
        # Answers normally arrive during the call through record_checkin. Only use
        # Bolna's extracted_data if it actually has some, so an empty one doesn't
        # wipe what the tool recorded.
        answers = normalize_answers(flatten_extraction(c["extracted"]))
        has_answers = any(val not in (None, "") for val in answers.values())
        level, reasons = assess(answers, worker=worker) if has_answers else (None, [])
        changes = {"missed_checkins": 0, "last_contact_at": iso(now)}
        if kind == "arrival":
            changes["status"] = "abroad"
        next_kind = "weekly"

    escalation = escalate(store, worker, level, reasons, now) if level and rank(level) >= rank("high") else None
    changes["updated_at"] = iso(now)
    if level:
        changes.update({"risk_level": overall_level(store, worker["id"], level), "risk_reasons": reasons})
    store.update("workers", {"id": worker["id"]}, changes)
    worker = store.get("workers", id=worker["id"])

    if not c["missed"]:
        next_when = now + FOLLOW_UP.get(worker.get("risk_level"), timedelta(days=CHECKIN_DAYS))
    # Book the next call unless another one is already booked for later, automatic
    # calls are off, or this worker already had a call recently.
    next_call = None
    if (auto_calls_on() and not _other_booked_call(store, worker["id"], c["call_id"], now)
            and not _recent_call_other_than(store, worker["id"], c["call_id"], now)):
        next_call = schedule_call(store, worker, next_kind, next_when, now)
    return {"stored": True, "processed": True, "worker": worker["case_id"], "missed": c["missed"],
            "risk_level": worker["risk_level"], "escalated": bool(escalation), "next_call": next_call}


def _apply_late_extraction(store, worker: dict, kind: str, c: dict, now: datetime) -> dict:
    answers = normalize_answers(flatten_extraction(c["extracted"]))
    if not any(v not in (None, "") for v in answers.values()):
        return {"stored": True, "processed": False, "worker": worker["case_id"]}
    answers["notes"] = ("From the after-call summary. " + (answers.get("notes") or "")).strip()
    level, reasons = assess(answers, worker=worker)
    store.insert("checkins", {"worker_id": worker["id"], "kind": kind, "answers": answers,
                              "risk_level": level, "risk_reasons": reasons, "created_at": iso(now)})
    escalation = escalate(store, worker, level, reasons, now) if rank(level) >= rank("high") else None
    store.update("workers", {"id": worker["id"]}, {"risk_level": overall_level(store, worker["id"], level),
                                                   "risk_reasons": reasons, "updated_at": iso(now)})
    return {"stored": True, "processed": True, "worker": worker["case_id"], "late_extraction": True,
            "risk_level": level, "escalated": bool(escalation)}


def checkin_instruction(worker: dict, kind: str, level: str, codes: set, escalation: dict | None) -> str:
    """What the voice agent says after recording. Saathi acts for the worker: the
    team alerts the embassy; the worker is never told to go and find a number."""
    country = worker.get("dest_country") or "that country"
    family = ("Their family has been sent a message. " if escalation and escalation.get("sms_status") == "sent" else "")
    if "code_phrase" in codes:
        return ("IMPORTANT: the worker said the danger phrase and may not be able to talk freely. Do NOT mention "
                "danger, help, complaints, family or embassy. Chat normally for a few seconds and end the call politely.")
    if level == "critical":
        say = (f"Speak calmly and slowly. Say: you are not alone. Your case is registered as URGENT and the Saathi "
               f"team is alerting the Indian Embassy in {country} now, with your name, phone number and what you told "
               f"us. {family}")
        if codes & {"wrong_pickup", "no_pickup"}:
            employer = worker.get("employer_name") or "your registered employer"
            say += (f"Then: if you are still inside the airport, stay inside. Go to the airport help desk or airport "
                    f"police and tell them you are an Indian worker and need help. Do not go with anyone except "
                    f"{employer}. If you are already in a vehicle, stay calm, do not fight, and look for any sign, "
                    f"building or road name. ")
        else:
            say += ("Then: if you can, stay where there are other people. Keep your phone hidden and charged. ")
        back = ("say Saathi will call back within a few hours" if kind != "help" and auto_calls_on()
                else "say the team will try to reach them on this phone; keep it with you")
        say += (f"Ask ONE question: where are you now, any building, shop, mosque or road name? Then {back}. "
                "Never tell them to call the embassy themselves. Never promise rescue.")
        return say
    if level == "high":
        return (f"Say: you are not alone. Your problem is registered and a Saathi caseworker will take it up with the "
                f"Indian Embassy in {country}. {family}" + ("Saathi will call you again tomorrow. "
                                                    if kind != "help" and auto_calls_on() else "")
                + "Do not promise that the "
                "salary or passport will be recovered. Never tell them to call the embassy themselves.")
    if kind == "help":
        return ("Say: your problem is registered and a Saathi caseworker will look at it. Do not promise that anyone will come or that money will be recovered.")
    if kind == "briefing":
        return ("Thank them warmly. Say: Saathi will call on the day you land. If something feels wrong at the "
                "airport, stay inside near the help desk or airport police and ask them for help. Saathi will check on you.")
    if level == "medium":
        return "Say: noted. Saathi will keep checking on you. Tell Saathi on the next call if anything gets worse."
    return "Say: good, everything is noted as fine. Saathi will call again next week."


# Workers on a visit visa, an expired visa or a false "absconding" report fear the
# local police will arrest them, so they stay silent. Saathi is not the police.
PAPERS_FIRST = ("FIRST say gently: Saathi is not the police; we never give your details to the police in that country. "
                "This is the agent's wrongdoing, not yours. The Indian Embassy helps Indians go home even when their "
                "papers are not in order. Do not promise they will not be fined or sent back. Then: ")


def record_checkin(store, data: dict, now: datetime) -> dict:
    """Bolna tool, called by the check-in agent with the worker's answers during the
    call. Returns what the voice agent should say next."""
    case_id = str(data.get("case_id") or "").strip().upper()
    worker = store.get("workers", case_id=case_id) if case_id else None
    if not worker:
        return {"ok": False, "instruction": "The case was not found. Thank the caller, do not promise anything, "
                                            "and say Saathi will call back."}
    kind = str(data.get("call_kind") or "weekly").strip().lower()
    kind = kind if kind in CHECKIN_RECORD_KINDS else "weekly"
    answers = normalize_answers(data)
    # Danger answers count on any call, a briefing included.
    level, reasons = assess(answers, worker=worker)
    store.insert("checkins", {"worker_id": worker["id"], "kind": kind, "answers": answers,
                              "risk_level": level, "risk_reasons": reasons, "created_at": iso(now)})
    escalation = escalate(store, worker, level, reasons, now) if rank(level) >= rank("high") else None
    changes = {"last_contact_at": iso(now), "missed_checkins": 0, "updated_at": iso(now)}
    if kind != "briefing" or level != "ok":
        # A quiet briefing says nothing about safety abroad: leave the risk as it is.
        changes.update({"risk_reasons": reasons, "risk_level": overall_level(store, worker["id"], level)})
    if kind == "arrival":
        changes["status"] = "abroad"
    store.update("workers", {"id": worker["id"]}, changes)

    codes = {r["code"] for r in reasons}
    say = checkin_instruction(worker, kind, level, codes, escalation)
    if "papers_problem" in codes and "code_phrase" not in codes:
        say = PAPERS_FIRST + say
    return {"ok": True, "risk_level": level, "escalated": bool(escalation), "instruction": say}


def report_problem(store, data: dict, now: datetime) -> dict:
    """Bolna tool for the Gulf Saathi line: a worker abroad, or their family in India,
    calls with a problem. Finds the case by case number or phone, or opens a minimal
    help case, then records the answers like a check-in, so the same rules and alerts
    apply. A family caller is the case's family contact, never the worker."""
    relation = (_text(data, "caller_relation", 30) or "").lower()
    died = yes_no(data.get("worker_died")) is True
    if died and relation in ("", "self", "worker", "me", "not_said"):
        relation = "family"  # whoever reports a death is not the worker
    family = relation not in ("", "self", "worker", "me", "not_said")
    case_id = str(data.get("case_id") or "").strip().upper()
    worker = store.get("workers", case_id=case_id) if case_id else None
    phone = ""
    try:
        phone = normalize_phone(data.get("caller_phone"))
    except CaseError:
        pass
    abroad_phone = ""
    try:
        abroad_phone = normalize_phone(data.get("worker_phone")) if data.get("worker_phone") else ""
    except CaseError:
        pass
    if not worker and family:
        worker = ((abroad_phone and store.get("workers", worker_phone=abroad_phone))
                  or (phone and store.get("workers", family_phone=phone)) or None)
    elif not worker and phone:
        worker = store.get("workers", worker_phone=phone)
    opened = False
    if not worker:
        if not phone:
            return {"ok": False, "instruction": "Ask for their phone number with the country code, or their Saathi "
                                                 "case number, then call report_problem again."}
        if family:
            worker = store.insert("workers", {
                "case_id": new_case_id(store), "created_at": iso(now), "updated_at": iso(now),
                "worker_name": _text(data, "worker_name") or "Name not given (reported by family)",
                # The worker's own number if the family knows it; otherwise the family's, marked in notes.
                "worker_phone": abroad_phone or phone, "family_phone": phone, "family_relation": relation,
                "family_name": _text(data, "caller_name"), "dest_city": _text(data, "current_city"),
                "code_phrase": DEFAULT_CODE_PHRASE, "status": "abroad", "risk_level": "ok", "risk_reasons": [],
                "missed_checkins": 0, "source": "family_call", "reported_by": relation,
                "notes": "Opened from a family call to the Gulf Saathi line." +
                         ("" if abroad_phone else " Worker's own phone not known: the phone here is the family's."),
            })
        else:
            fam = ""
            try:
                fam = normalize_phone(data.get("family_phone"))
            except CaseError:
                pass
            worker = store.insert("workers", {
                "case_id": new_case_id(store), "created_at": iso(now), "updated_at": iso(now),
                "worker_name": _text(data, "caller_name") or "Caller (name not given)", "worker_phone": phone,
                "family_phone": fam or None, "dest_city": _text(data, "current_city"),
                "code_phrase": DEFAULT_CODE_PHRASE, "status": "abroad", "risk_level": "ok", "risk_reasons": [],
                "missed_checkins": 0, "source": "help_call", "reported_by": "self",
                "notes": "Opened from a call to the Gulf Saathi line.",
            })
        opened = True
    trace = dict(data)
    if family:  # the caller's name is the family member's, not the worker's
        trace["caller_name"] = data.get("worker_name") or ""
        if data.get("caller_name") and not worker.get("family_name"):
            store.update("workers", {"id": worker["id"]}, {"family_name": _text(data, "caller_name")})
    _save_trace(store, worker, trace, now)
    if died:
        worker = report_death(store, store.get("workers", id=worker["id"]), {
            "reported_by": relation, "informed_by": data.get("informed_by"), "place": data.get("current_city"),
            "notes": data.get("notes")}, now)
        say = death_instruction(worker) + (f" The case number is {spoken_case_id(worker['case_id'])}: read it slowly, "
                                           "one letter at a time, and ask them to keep it.")
        return {"ok": True, "risk_level": "critical", "escalated": True, "instruction": say,
                "case_id": worker["case_id"], "new_case": opened}
    out = record_checkin(store, {**data, "case_id": worker["case_id"], "call_kind": "help"}, now)
    if out["ok"] and family:
        out["instruction"] = family_instruction(store.get("workers", id=worker["id"]), relation, out["risk_level"])
    if out["ok"]:
        out["instruction"] += (f" The case number is {spoken_case_id(worker['case_id'])}: read it slowly, one "
                               "letter at a time, and ask them to keep it.")
        status = petition_line(store.get("workers", id=worker["id"]))
        if status and not opened:
            out["instruction"] += " " + status
    return {**out, "case_id": worker["case_id"], "new_case": opened}


def family_instruction(worker: dict, relation: str, level: str) -> str:
    """For a parent, wife or brother calling from India about someone abroad."""
    country = worker.get("dest_country") or worker.get("dest_city") or "that country"
    who = relation if relation not in ("family", "yes") else "family member"
    urgent = rank(level) >= rank("high")
    return ((f"Speak calmly and warmly to the {who}: you are not alone. " if urgent else f"Speak warmly to the {who}: ")
            + ("The case is registered as URGENT and the Saathi team is alerting the Indian Embassy in "
               f"{country} with these details. " if urgent else "The problem is registered and a Saathi caseworker "
               "will look at it. ")
            + "Saathi will prepare the Pravasi Prajavani petition for them, so they do not need to travel to "
              "Hyderabad; a Saathi caseworker will hand it in and contact them on this phone. Never promise rescue "
              "or that money will come back.")


PETITION_STATUSES = ("prepared", "submitted", "acknowledged", "closed")


def petition_line(worker: dict) -> str:
    """What the voice agent can tell a caller about their Pravasi Prajavani petition."""
    st = worker.get("petition_status")
    if st not in PETITION_STATUSES or st == "prepared":
        return ""
    when = fmt_ist(worker.get("petition_submitted_at")).split(",")[0] if worker.get("petition_submitted_at") else ""
    ref = f", reference {worker['petition_ref']}" if worker.get("petition_ref") else ""
    return f"Also tell them: their Pravasi Prajavani petition is {st}" + (f" (handed in {when}{ref})" if when else ref) + "."


def update_petition(store, worker: dict, status: str, ref: str, now: datetime) -> dict:
    if status not in PETITION_STATUSES:
        raise CaseError(f"status must be one of {', '.join(PETITION_STATUSES)}")
    changes = {"petition_status": status, "petition_ref": (ref or "").strip()[:100] or None, "updated_at": iso(now)}
    if status == "submitted" and not worker.get("petition_submitted_at"):
        changes["petition_submitted_at"] = iso(now)
    store.update("workers", {"id": worker["id"]}, changes)
    return store.get("workers", id=worker["id"])


# --- when a worker dies abroad ------------------------------------------------------
# The hard part for families is not the grief alone: bodies wait in mortuaries while
# volunteers search for the village, and illiterate parents face English papers.
# A Saathi case already links the worker, employer, sponsor and family from day zero.

REMAINS_STATUSES = ("reported", "embassy_informed", "family_decided", "papers_signed", "remains_home",
                    "buried_abroad", "closed")
EX_GRATIA_STATUSES = ("not_applied", "applied", "paid", "rejected")
# Telangana G.O. 216 (from news reports, not the G.O. text): Rs 5 lakh for families of
# workers who die in these countries, for deaths from 7 Dec 2023. Check before relying on it.
EX_GRATIA_PLACES = ("bahrain", "manama", "iraq", "kuwait", "oman", "muscat", "salalah", "qatar", "doha", "saudi",
                    "ksa", "riyadh", "jeddah", "dammam", "mecca", "makkah", "medina", "uae", "emirates", "dubai",
                    "abu dhabi", "sharjah", "ajman", "al ain", "fujairah", "ras al")


def ex_gratia_country(w: dict) -> bool | None:
    """Did the worker go to a country Telangana's ex-gratia covers? None if not known."""
    where = f"{w.get('dest_country') or ''} {w.get('dest_city') or ''}".lower().strip()
    if not where:
        return None
    return any(p in where for p in EX_GRATIA_PLACES)


def report_death(store, worker: dict, info: dict, now: datetime) -> dict:
    """Record that someone reported the worker's death. Stops Saathi calling the
    number, opens a CRITICAL alert for the embassy, and never texts the family:
    news like this must come from a person. A caseworker can clear it if it was wrong."""
    clean = lambda k, n=200: (str(info.get(k) or "").strip()[:n] if str(info.get(k) or "").strip().lower()
                              not in ("", "not_said") else "")
    parts = [f"reported by {clean('reported_by', 40)}" if clean("reported_by") else "",
             f"they heard it from {clean('informed_by')}" if clean("informed_by") else "",
             f"place: {clean('place')}" if clean("place") else "",
             f"when: {clean('when', 60)}" if clean("when") else "", clean("notes", 500)]
    new = "; ".join(p for p in parts if p)
    old = worker.get("death_note") or ""
    note = old if new in old else (f"{old} | {new}" if old else new)
    detail = clean("place") or (worker.get("dest_city") or worker.get("dest_country") or "place not known")
    reasons = [{"code": "death_reported", "detail": f"{detail}, as told by {clean('reported_by', 40) or 'a caller'}"}]
    escalate(store, worker, "critical", reasons, now, notify_family=False)
    store.update("workers", {"id": worker["id"]}, {
        "death_reported_at": worker.get("death_reported_at") or iso(now), "death_note": note[:2000] or None,
        "remains_status": worker.get("remains_status") or "reported",
        "ex_gratia_status": worker.get("ex_gratia_status") or "not_applied",
        "status": "death_reported", "next_call_at": None, "risk_level": "critical", "risk_reasons": reasons,
        "updated_at": iso(now)})
    return store.get("workers", id=worker["id"])


def clear_death(store, worker: dict, now: datetime) -> dict:
    """The report was a mistake (wrong person, a rumour). Calls can be made again."""
    note = ((worker.get("notes") or "") + f" Death report cleared as a mistake on {fmt_ist(now)}: "
            f"{worker.get('death_note') or ''}").strip()[:2000]
    store.update("workers", {"id": worker["id"]}, {
        "death_reported_at": None, "death_note": None, "remains_status": None, "ex_gratia_status": None,
        "status": "abroad", "notes": note, "updated_at": iso(now)})
    return store.get("workers", id=worker["id"])


def update_death_status(store, worker: dict, remains: str, ex_gratia: str, now: datetime) -> dict:
    if remains not in REMAINS_STATUSES:
        raise CaseError(f"remains status must be one of {', '.join(REMAINS_STATUSES)}")
    if ex_gratia not in EX_GRATIA_STATUSES:
        raise CaseError(f"ex-gratia status must be one of {', '.join(EX_GRATIA_STATUSES)}")
    store.update("workers", {"id": worker["id"]}, {"remains_status": remains, "ex_gratia_status": ex_gratia,
                                                   "updated_at": iso(now)})
    return store.get("workers", id=worker["id"])


def death_instruction(worker: dict) -> str:
    """What the voice agent says to a family member who reports a death."""
    country = worker.get("dest_country") or worker.get("dest_city") or "that country"
    support = ("Say: the Telangana government gives support money to families of workers who die in Gulf countries, "
               "and a Saathi caseworker will help them apply. Do not say an amount. "
               if ex_gratia_country(worker) else
               "Say: a Saathi caseworker will check what government support the family can get. ")
    return ("Speak slowly and gently. Say: I am very sorry. You are not alone; Saathi will stay with your family "
            f"through this. The Saathi team is informing the Indian Embassy in {country} with these details, so they "
            "can help with bringing them home and with the papers. " + support +
            "Then, only what they have not said yet, ONE question at a time: who told you, and that person's phone "
            "number; in which city it happened. Do not press for how it happened. Never promise when the body will "
            "come home or that money will come. Never ask for the passport number or bank details.")


def spoken_case_id(case_id: str) -> str:
    """"GS-W9HWSY" -> "G S, W 9 H W S Y", so the voice reads it letter by letter."""
    return "G S, " + " ".join(case_id[3:])


def _save_trace(store, worker: dict, data: dict, now: datetime) -> None:
    """Help line: keep what helps trace the caller (name, home, agent, nearby place)
    on the case. Fills empty fields only; never overwrites what a caseworker typed."""
    a = normalize_answers(data)
    changes = {}
    name = _text(data, "caller_name")
    if name and name.lower() != "not_said" and worker.get("worker_name", "").startswith("Caller ("):
        changes["worker_name"] = name
    if a["agent_name"] and not worker.get("agent_name"):
        changes["agent_name"] = a["agent_name"][:200]
    if a["agent_phone"] and not worker.get("sub_agent_phone"):
        try:
            changes["sub_agent_phone"] = normalize_phone(a["agent_phone"])
        except CaseError:
            pass
    if a["current_city"] and not worker.get("dest_city"):
        changes["dest_city"] = a["current_city"][:200]
    extra = [f"{label}: {a[k]}" for k, label in (("home_district", "Home"), ("landmark", "Near"))
             if a[k] and f"{label}: {a[k]}" not in (worker.get("notes") or "")]
    if extra:
        changes["notes"] = ((worker.get("notes") or "") + " " + ". ".join(extra) + ".").strip()[:2000]
    if changes:
        changes["updated_at"] = iso(now)
        store.update("workers", {"id": worker["id"]}, changes)
        worker.update(changes)


def flatten_extraction(extracted: dict) -> dict:
    """Bolna puts after-call extractions under a category, each with an `objective`
    (pre-defined answer) or `subjective` (free text) value:
    {"help_check": {"abroad": {"objective": "yes", ...}, "notes": {"subjective": "...", ...}}}
    Flat {"field": "value"} data is accepted too. "not_said" becomes empty."""
    out = {}

    def value(v):
        if isinstance(v, dict) and ("objective" in v or "subjective" in v):
            v = v.get("objective") if v.get("objective") not in (None, "") else v.get("subjective")
        return "" if v is None or str(v).strip().lower() == "not_said" else v

    for k, v in (extracted or {}).items():
        if isinstance(v, dict) and not ("objective" in v or "subjective" in v):
            for k2, v2 in v.items():
                out[str(k2).lower()] = value(v2)
        else:
            out[str(k).lower()] = value(v)
    return out


def help_from_extraction(store, c: dict, now: datetime) -> dict | None:
    """After a call to the Gulf Saathi line: if Bolna's extraction says the caller is
    abroad or in danger, open or update their help case, even if the live voice AI
    never called report_problem. None when there is nothing to act on."""
    ex = flatten_extraction(c.get("extracted") or {})
    a = normalize_answers(ex)
    # "Needs help" alone is not danger: someone checking an agent before paying also
    # asks for help (live call 22 Oct 2026). Act only when they are abroad or report
    # harm that only happens abroad.
    danger = (any(a.get(k) is True for k in ("threatened", "movement_restricted"))
              or a.get("passport_with_worker") is False or (a.get("months_unpaid") or 0) > 0
              or a.get("pickup_status") in ("other_person", "nobody") or bool(a.get("papers_problem")))
    died = yes_no(ex.get("worker_died")) is True  # reported by family in India: "abroad" may be no
    if not c.get("user_number") or (not died and (yes_no(ex.get("abroad")) is False
                                                  or not (yes_no(ex.get("abroad")) or danger))):
        return None
    data = {k: v for k, v in ex.items() if k != "case_id"}
    data["caller_phone"] = c["user_number"]
    data["notes"] = ("After-call summary: " + str(ex.get("notes") or "")).strip()
    out = report_problem(store, data, now)
    return out if out.get("ok") else None


def briefed_worker_ids(store) -> dict:
    """worker id -> the latest briefing check-in, for workers who had one."""
    out = {}
    for ch in store.select("checkins", order="created_at", desc=False):
        if ch.get("kind") == "briefing":
            out[ch["worker_id"]] = ch
    return out


def has_predeparture_flags(w: dict) -> bool:
    return bool(promise.predeparture_checks(w))


def summary_counts(workers: list[dict], briefed: dict) -> dict:
    """The numbers a state office asks for first."""
    return {
        "registered": len(workers),
        "in_india": sum(1 for w in workers if w.get("status") == "registered"),
        "abroad": sum(1 for w in workers if w.get("status") == "abroad"),
        "briefed": sum(1 for w in workers if w["id"] in briefed),
        "at_risk": sum(1 for w in workers if rank(w.get("risk_level")) >= rank("high")),
        "red_flags": sum(1 for w in workers if has_predeparture_flags(w)),
    }


def _agent_key(w: dict) -> str | None:
    detail = w.get("agent_check_detail") or {}
    if w.get("agent_check") == "confirmed_in_list" and detail.get("candidates"):
        return detail["candidates"][0]["agency"].upper()
    name = w.get("agent_name") or w.get("agent_owner")
    return " ".join(name.split()).upper() if name else None


def agent_stats(workers: list[dict]) -> list[dict]:
    """Per recruiting agent named in our cases: how its workers are doing. The
    evidence a state agent register would want; no claim about the agent itself."""
    groups: dict[str, dict] = {}
    for w in workers:
        key = _agent_key(w)
        if not key:
            continue
        g = groups.setdefault(key, {"agent": key, "licensed": False, "cases": 0, "not_in_list": 0, "over_cap": 0,
                                    "at_risk": 0, "critical": 0, "districts": set(), "employers": set(), "case_ids": []})
        g["cases"] += 1
        g["case_ids"].append(w["case_id"])
        g["licensed"] |= w.get("agent_check") == "confirmed_in_list"
        g["not_in_list"] += w.get("agent_check") in ("not_found", "need_more_info")
        g["over_cap"] += w.get("fee_status") == "over_cap"
        g["at_risk"] += rank(w.get("risk_level")) >= rank("high")
        g["critical"] += w.get("risk_level") == "critical"
        if w.get("agent_district"):
            g["districts"].add(" ".join(w["agent_district"].split()).title())
        if w.get("employer_name"):
            where = ", ".join(x for x in (w.get("dest_city"), w.get("dest_country")) if x)
            g["employers"].add(" ".join(w["employer_name"].split()) + (f" ({where})" if where else ""))
    out = [{**g, "districts": sorted(g["districts"]), "employers": sorted(g["employers"])} for g in groups.values()]
    return sorted(out, key=lambda g: (-g["critical"], -g["at_risk"], -g["not_in_list"], -g["over_cap"], -g["cases"], g["agent"]))


def resolve_escalation(store, escalation_id: str, now: datetime) -> dict | None:
    rows = store.update("escalations", {"id": escalation_id}, {"status": "resolved", "resolved_at": iso(now)})
    if not rows:
        return None
    w = store.get("workers", id=rows[0]["worker_id"])
    latest = store.select("checkins", {"worker_id": w["id"]}, limit=1)
    level = latest[0]["risk_level"] if latest else "ok"
    store.update("workers", {"id": w["id"]}, {"risk_level": overall_level(store, w["id"], level), "updated_at": iso(now)})
    return rows[0]


def embassy_alert(store, worker: dict, now: datetime) -> dict:
    """Short urgent message a caseworker sends to the Indian Embassy / Consulate (or
    MADAD) for a worker in danger: who, where, what they said, how to reach them."""
    w = worker
    if w.get("death_reported_at"):
        return _death_alert(w, now)
    latest = next((ch for ch in store.select("checkins", {"worker_id": w["id"]}, limit=5)), None)
    a = (latest or {}).get("answers") or {}
    where = ", ".join(x for x in [a.get("current_city"), a.get("landmark"), a.get("current_location")] if x) \
        or ", ".join(x for x in [w.get("dest_city"), w.get("dest_country")] if x) or "not known"
    lines = [
        f"URGENT: Indian worker may need help. Gulf Saathi case {w['case_id']}, {fmt_ist(now)}.",
        "",
        f"Name: {w['worker_name']}   Phone: {w['worker_phone']}",
        f"Where (as told on the call): {where}",
        f"Risk: {(w.get('risk_level') or 'ok').upper()}",
    ]
    lines += [f"  - {reason_text(r)}" for r in w.get("risk_reasons") or []]
    lines += [
        f"Employer: {w.get('employer_name') or 'not recorded'}   Sponsor: {w.get('sponsor_name') or 'not recorded'} "
        f"(ID {w.get('sponsor_id') or 'not recorded'})",
        f"Recruiting agent: {w.get('agent_name') or 'not recorded'}",
        f"Family in India: {w.get('family_phone') or 'not recorded'}",
    ]
    if a.get("notes"):
        lines.append(f"Worker said: {a['notes']}")
    papers = next((r for r in w.get("risk_reasons") or [] if r["code"] == "papers_problem"), None)
    if papers:
        agent = ", ".join(x for x in [w.get("agent_name"), w.get("sub_agent_phone")] if x) or "not known yet"
        lines += ["", f"Papers: {papers.get('detail')}. The worker is a victim of illegal recruitment (agent: {agent}). "
                      "May need an Emergency Certificate to return home. Please do not treat the worker as an offender."]
    lines += ["", "Reported by phone to Gulf Saathi (Telangana) and not independently verified. "
                  "Please contact the worker. Full case packet available on request."]
    body = "\n".join(lines)
    subject = f"URGENT: Indian worker in distress, {w.get('dest_country') or 'Gulf'}, case {w['case_id']}"
    return {"subject": subject, "body": body}


def proof_of_work(store, worker: dict, now: datetime) -> dict:
    """Dated record of every call: where the worker said they were, what work, whether
    pay came and the passport was with them. If the employer files a false absconding
    report, this shows the worker was in contact and working, and when pay stopped."""
    w = worker
    calls = sorted(store.select("calls", {"worker_id": w["id"]}), key=lambda c: c.get("created_at") or "")
    checkins = sorted(store.select("checkins", {"worker_id": w["id"]}), key=lambda c: c.get("created_at") or "")
    # The voice AI saves several times during one call: merge saves of the same kind
    # less than 15 minutes apart into one row per call.
    calls_said: list[dict] = []
    for ch in checkins:
        if ch.get("kind") == "briefing":
            continue
        at = parse_ts(ch["created_at"])
        last = calls_said[-1] if calls_said else None
        if last and last["kind"] == ch.get("kind") and at and last["last"] and at - last["last"] < timedelta(minutes=15):
            last["answers"].update({k: v for k, v in (ch.get("answers") or {}).items() if v not in (None, "")})
            last["reasons"].update({r["code"]: r for r in ch.get("risk_reasons") or []})
            last["last"] = at
        else:
            calls_said.append({"at": ch["created_at"], "last": at, "kind": ch.get("kind"),
                               "answers": {k: v for k, v in (ch.get("answers") or {}).items() if v not in (None, "")},
                               "reasons": {r["code"]: r for r in ch.get("risk_reasons") or []}})
    rows = []
    yn = lambda v: {True: "yes", False: "NO"}.get(v, "")
    for g in calls_said:
        a = g["answers"]
        pay = ("not paid" + (f" ({a['months_unpaid']} months)" if a.get("months_unpaid") else "")
               if a.get("salary_received") is False or a.get("months_unpaid") else
               "paid" if a.get("salary_received") else "")
        if a.get("salary_amount"):
            pay = (pay + f", {a['salary_amount']} {w.get('salary_currency') or ''}").strip(", ").strip()
        rows.append({"when": fmt_ist(g["at"]), "kind": g["kind"],
                     "where": ", ".join(x for x in [a.get("current_city"), a.get("landmark"), a.get("current_location")] if x),
                     "work": a.get("current_job") or "", "pay": pay, "passport": yn(a.get("passport_with_worker")),
                     "said": "; ".join(reason_text(r) for r in g["reasons"].values()) or "no problem reported"})
    first = lambda test: next((r["when"] for r, g in zip(rows, calls_said) if test(g["answers"])), None)
    unpaid_from = first(lambda a: a.get("salary_received") is False or bool(a.get("months_unpaid")))
    passport_from = first(lambda a: a.get("passport_with_worker") is False)
    answered = [c for c in calls if c.get("answered")]
    summary = [
        f"Worker: {w['worker_name']}   Phone: {w['worker_phone']}   Gulf Saathi case {w['case_id']}",
        f"Employer: {w.get('employer_name') or 'not recorded'}   Sponsor: {w.get('sponsor_name') or 'not recorded'} "
        f"(ID {w.get('sponsor_id') or 'not recorded'})",
        f"Promised before departure: {w.get('job_title') or 'job not recorded'}, "
        + (f"{int(float(w['contract_salary']))} {w.get('salary_currency') or ''}".strip()
           if w.get("contract_salary") else "salary not recorded")
        + f", in {', '.join(x for x in [w.get('dest_city'), w.get('dest_country')] if x) or 'place not recorded'}"
        + f" (recorded {fmt_ist(w.get('created_at'))})",
        f"Calls answered: {len(answered)}. First: {fmt_ist(answered[0]['created_at']) if answered else 'none'}. "
        f"Last contact: {fmt_ist(w.get('last_contact_at'))}.",
    ]
    if unpaid_from:
        summary.append(f"Salary first reported unpaid: {unpaid_from}.")
    if passport_from:
        summary.append(f"Passport first reported not with the worker: {passport_from}.")
    recordings = [f"{fmt_ist(c.get('created_at'))}: {c['recording_url']}" for c in calls if c.get("recording_url")]
    return {
        "title": f"Record of contact and work: {w['worker_name']} (Gulf Saathi case {w['case_id']})",
        "summary": summary, "rows": rows, "recordings": recordings,
        "note": f"Prepared by Gulf Saathi (Telangana) on {fmt_ist(now)} from dated phone calls with the worker. "
                "What the worker said is recorded as said and not independently verified; the call recordings are "
                "the evidence. Gulf Saathi is a helpline, not a government body.",
    }


def _death_alert(w: dict, now: datetime) -> dict:
    v = lambda x: x if x not in (None, "") else "not recorded"
    lines = [
        f"Reported death of an Indian worker. Gulf Saathi case {w['case_id']}, {fmt_ist(now)}.",
        "",
        f"Name: {w['worker_name']}   Phone: {w['worker_phone']}",
        f"What was reported: {v(w.get('death_note'))}",
        f"Went to: {', '.join(x for x in [w.get('dest_city'), w.get('dest_country')] if x) or 'not recorded'}"
        f"   Job: {v(w.get('job_title'))}",
        f"Employer: {v(w.get('employer_name'))}   Employer phone: {v(w.get('employer_phone'))}",
        f"Sponsor: {v(w.get('sponsor_name'))} (ID {v(w.get('sponsor_id'))})",
        f"Recruiting agent: {v(w.get('agent_name'))}",
        f"Next of kin in India: {v(w.get('family_name'))} ({v(w.get('family_relation'))}), {v(w.get('family_phone'))}",
        f"Last contact with Gulf Saathi: {fmt_ist(w.get('last_contact_at'))}",
        "",
        "The family asks for help to: confirm the death and its cause, get the death certificate, bring the body home "
        "or arrange burial there (as the next of kin decides), and recover unpaid wages and dues.",
        "Reported by phone to Gulf Saathi (Telangana) and not independently verified. Full case packet available on request.",
    ]
    return {"subject": f"Death of Indian worker reported, {w.get('dest_country') or 'Gulf'}, case {w['case_id']}",
            "body": "\n".join(lines)}


def death_packet(store, worker: dict, now: datetime) -> dict:
    """Papers for the family and the caseworker after a death: the facts the embassy
    needs, and the steps, in English and Telugu. Saathi does not make the NOC or
    consent form: the embassy has its own, which the next of kin signs."""
    w = worker
    v = lambda x, d="not recorded": x if x not in (None, "") else d
    name_te = w.get("worker_name_te") or w["worker_name"]
    country = v(w.get("dest_country"), "the country where it happened")
    eg = ex_gratia_country(w)
    facts = [
        f"Worker: {w['worker_name']}   Phone: {w['worker_phone']}   Gulf Saathi case: {w['case_id']}",
        "Passport number: ____________________ (copy it from the family's passport copy; Saathi never stores it)",
        f"What was reported: {v(w.get('death_note'))} (reported {fmt_ist(w.get('death_reported_at'))})",
        f"Went to: {', '.join(x for x in [w.get('dest_city'), w.get('dest_country')] if x) or 'not recorded'}   "
        f"Job: {v(w.get('job_title'))}   Departure: {v(w.get('departure_date'))} {w.get('flight_no') or ''}".rstrip(),
        f"Employer: {v(w.get('employer_name'))}   Phone: {v(w.get('employer_phone'))}",
        f"Sponsor (kafeel): {v(w.get('sponsor_name'))}   Sponsor ID: {v(w.get('sponsor_id'))}",
        f"Recruiting agent: {v(w.get('agent_name'))}   Village agent phone: {v(w.get('sub_agent_phone'))}",
        f"Next of kin: {v(w.get('family_name'), '____________')} ({v(w.get('family_relation'), '______')}), "
        f"phone {v(w.get('family_phone'), '____________')}",
        f"Last contact with Gulf Saathi: {fmt_ist(w.get('last_contact_at'))}",
    ]
    steps = [
        f"Tell the Indian Embassy / Consulate in {country} with the facts above, and register it on MADAD "
        "(madad.gov.in). The embassy works with the employer and the local authorities.",
        "The next of kin decides: bring the body home, or burial / cremation there. The embassy gives its own "
        "consent (NOC) form; the next of kin signs it. Read it to them in Telugu before they sign.",
        "Costs: ask the employer to pay, as the contract usually requires. If they do not, ask the embassy whether the "
        "Indian Community Welfare Fund (ICWF) can help.",
        "Keep copies of: the local death certificate and its translation, the embassy's papers, the cancelled "
        "passport, the airline cargo papers, and the job contract or visa.",
        "Unpaid salary and end-of-service money: ask the embassy to claim them from the employer for the family.",
        "If the death was an accident and the worker had Pravasi Bharatiya Bima Yojana insurance (compulsory for ECR "
        "emigrants), claim it through the insurer. Check the current amount and rules.",
    ]
    if eg is not False:
        steps.append("Telangana ex-gratia (G.O. 216, as reported in the news): Rs 5 lakh for families of workers who "
                     "die in Bahrain, Iraq, Kuwait, Oman, Qatar, Saudi Arabia or the UAE, for deaths from 7 Dec 2023. "
                     "Apply at the District Collector's office with the death certificate, cancelled passport, proof "
                     "of work abroad and the family's bank details. Check the current rules at the Collectorate.")
    te_steps = [
        f"సాథి బృందం {country} లోని భారత రాయబార కార్యాలయానికి వివరాలు పంపుతుంది.",
        "మృతదేహాన్ని ఇంటికి తీసుకురావాలా, అక్కడే అంత్యక్రియలు చేయాలా అనేది కుటుంబమే నిర్ణయిస్తుంది. "
        "రాయబార కార్యాలయం ఇచ్చే అనుమతి పత్రం (NOC) పై కుటుంబ సభ్యులు సంతకం చేయాలి. "
        "సంతకం చేసే ముందు సాథి కేస్‌వర్కర్ దాన్ని తెలుగులో చదివి వినిపిస్తారు.",
        "ఖర్చులు యజమాని భరించాలి. భరించకపోతే, రాయబార కార్యాలయాన్ని ICWF నిధి నుంచి సహాయం అడుగుతాం.",
        "ఈ పత్రాలు దాచుకోండి: మరణ ధ్రువీకరణ పత్రం, రద్దు చేసిన పాస్‌పోర్ట్, ఉద్యోగ పత్రాలు, బ్యాంక్ ఖాతా వివరాలు.",
        "రావాల్సిన జీతం, ఇతర డబ్బుల కోసం రాయబార కార్యాలయం ద్వారా యజమానిని అడుగుతాం.",
    ]
    if eg is not False:
        te_steps.append("గల్ఫ్ దేశాల్లో మరణించిన కార్మికుల కుటుంబాలకు తెలంగాణ ప్రభుత్వం ఎక్స్‌గ్రేషియా ఇస్తుంది. "
                        "జిల్లా కలెక్టర్ కార్యాలయంలో దరఖాస్తు చేయాలి. సాథి కేస్‌వర్కర్ సహాయం చేస్తారు.")
    english = {
        "title": f"Death of a worker abroad: facts and next steps (Gulf Saathi case {w['case_id']})",
        "facts": facts, "steps": steps,
        "status": f"Body: {v(w.get('remains_status'))}   Ex-gratia: {v(w.get('ex_gratia_status'))}",
        "note": f"Prepared by Gulf Saathi on {fmt_ist(now)}. Facts are as reported by phone and not independently "
                "verified. The rules above can change: check each one with the embassy or the Collectorate.",
    }
    telugu = {
        "title": f"{name_te} గారి మరణం: తర్వాత ఏం చేయాలి (గల్ఫ్ సాథి కేసు {w['case_id']})",
        "opening": "మీకు కలిగిన నష్టానికి చాలా బాధగా ఉంది. మీరు ఒంటరి కాదు. ఈ పనులన్నీ సాథి కేస్‌వర్కర్ మీతో కలిసి చేస్తారు.",
        "steps": te_steps,
    }
    return {"english": english, "telugu": telugu}


# --- case packet ------------------------------------------------------------------

def timeline(store, worker: dict) -> list[dict]:
    events = [{"at": worker["created_at"], "type": "registered", "text": "Case registered before departure"}]
    for c in store.select("calls", {"worker_id": worker["id"]}):
        events.append({"at": c.get("updated_at") or c["created_at"], "type": "call", "call": c})
    for ch in store.select("checkins", {"worker_id": worker["id"]}):
        events.append({"at": ch["created_at"], "type": "checkin", "checkin": ch})
    for e in store.select("escalations", {"worker_id": worker["id"]}):
        events.append({"at": e["created_at"], "type": "escalation", "escalation": e})
    return sorted(events, key=lambda e: parse_ts(e["at"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def prajavani_petition(store, worker: dict, now: datetime) -> dict:
    """A petition the family does not have to carry to Hyderabad: Saathi fills it from
    the case; a caseworker hands it in at Pravasi Prajavani (Praja Bhavan) for them.
    Telugu is machine-drafted from fixed sentences and needs a native speaker's check."""
    w = worker
    v = lambda x, d="not known": x if x not in (None, "") else d
    latest = next((ch for ch in store.select("checkins", {"worker_id": w["id"]}, limit=5)), None)
    a = (latest or {}).get("answers") or {}
    where = ", ".join(x for x in [a.get("current_city"), a.get("landmark"), a.get("current_location")] if x) \
        or ", ".join(x for x in [w.get("dest_city"), w.get("dest_country")] if x) or "not known"
    reasons = w.get("risk_reasons") or []
    petitioner = w.get("family_name") or ""
    relation = w.get("family_relation") or w.get("reported_by") or ""
    name_te = w.get("worker_name_te") or w["worker_name"]
    country = v(w.get("dest_country"), "Gulf")
    job_line = None
    if w.get("job_title") or a.get("current_job") or w.get("visa_job"):
        job_line = (f"Promised job: {v(w.get('job_title'))}. Job on the visa: {v(w.get('visa_job'))}. "
                    f"Work he/she says they are made to do: {v(a.get('current_job'))}.")
    events = []
    for e in timeline(store, w)[:10][::-1]:
        when = fmt_ist(e["at"]).split(",")[0]
        if e["type"] == "registered":
            events.append(f"{when}: case registered with Gulf Saathi")
        elif e["type"] == "checkin":
            ch = e["checkin"]
            what = "; ".join(reason_text(r) for r in ch.get("risk_reasons") or []) or "no problem reported"
            events.append(f"{when}: {ch.get('kind')} call, worker said: {what}")
        elif e["type"] == "escalation":
            events.append(f"{when}: Gulf Saathi raised a {e['escalation']['level'].upper()} alert")
    english = {
        "to": "To: The Officer in charge, Pravasi Prajavani, Praja Bhavan, Hyderabad, Telangana",
        "subject": f"Subject: Request for help for {w['worker_name']}, a worker from Telangana in distress in "
                   f"{country} (Gulf Saathi case {w['case_id']})",
        "facts": [
            f"Worker: {w['worker_name']}   Phone: {w['worker_phone']}",
            f"Where he/she is now (as told on the phone): {where}",
            f"Employer: {v(w.get('employer_name'))}   Sponsor (kafeel): {v(w.get('sponsor_name'))} "
            f"(ID {v(w.get('sponsor_id'))})",
            f"Recruiting agent: {v(w.get('agent_name'))}   Village agent phone: {v(w.get('sub_agent_phone'))}   "
            f"Check against the MEA licensed list: {v(w.get('agent_check'), 'not checked')}",
        ] + ([f"Paid to the agent: Rs {fmt_rupees(int(w['amount_paid_total']))} (legal limit Rs 35,400)"]
             if w.get("amount_paid_total") else []) + ([job_line] if job_line else []),
        "problems": [reason_text(r) for r in reasons] or ["See timeline below."],
        "timeline": events,
        "requests": [
            f"Forward this case to the Indian Embassy / Consulate in {country} so that they contact the worker.",
            "Help the worker get his/her passport and unpaid wages, and return home safely if he/she wishes.",
            "Look into the recruiting agent named above (eMigrate complaint / police), if the facts are confirmed.",
        ],
        "note": f"Prepared by Gulf Saathi on {fmt_ist(now)} from phone calls with the worker and family. Facts are as "
                "reported and not independently verified. Call recordings and the full case packet are available on "
                "request.",
        "petitioner": f"Petitioner: {v(petitioner, '____________')} ({v(relation, 'relation ______')}), "
                      f"phone {v(w.get('family_phone'), '____________')}",
    }
    telugu = {
        "to": "గౌరవనీయులైన అధికారి గారికి, ప్రవాసీ ప్రజావాణి, ప్రజా భవన్, హైదరాబాద్.",
        "subject": f"విషయం: గల్ఫ్‌లో ఇబ్బందుల్లో ఉన్న {name_te} గారికి సహాయం కోసం విన్నపం "
                   f"(గల్ఫ్ సాథి కేసు {w['case_id']})",
        "body": [f"{name_te} గారు {country} కి పనికి వెళ్లారు. ఫోన్‌లో వారు చెప్పినదాని ప్రకారం:"]
                + [f"• {reason_text(r, 'te')}" for r in reasons]
                + ["దయచేసి ఈ విషయాన్ని భారత రాయబార కార్యాలయానికి పంపి, వారిని సురక్షితంగా ఇంటికి తీసుకురావడానికి, "
                   "జీతం, పాస్‌పోర్ట్ ఇప్పించడానికి, ఏజెంట్‌పై చర్య తీసుకోవడానికి సహాయం చేయగలరు.",
                   "పూర్తి వివరాలు ఇంగ్లీష్‌లో క్రింద ఉన్నాయి."],
        "petitioner": f"విన్నపం చేసేవారు: {v(petitioner, '____________')}, ఫోన్ {v(w.get('family_phone'), '____________')}",
    }
    return {"english": english, "telugu": telugu}


def case_packet(store, worker: dict, now: datetime) -> str:
    """Plain English summary for MADAD, TOMCOM or the Indian Embassy. A person files it."""
    w = worker
    v = lambda x: x if x not in (None, "") else "not recorded"
    lines = [
        f"GULF SAATHI CASE PACKET - {w['case_id']}",
        f"Prepared {fmt_ist(now)} from the worker's own phone answers. Facts below are as reported and have not "
        "been independently verified.",
        "",
        f"CURRENT RISK LEVEL: {w['risk_level'].upper()}",
    ]
    for r in w.get("risk_reasons") or []:
        lines.append(f"  - {reason_text(r)}")
    if w.get("death_reported_at"):
        lines.append(f"DEATH REPORTED {fmt_ist(w['death_reported_at'])}: {w.get('death_note') or ''}. "
                     f"Body: {w.get('remains_status') or '-'}. Ex-gratia: {w.get('ex_gratia_status') or '-'}.")
    lines += [
        "",
        "1. WORKER",
        f"  Name: {w['worker_name']}",
        f"  Phone: {w['worker_phone']}",
        f"  Status: {w['status']}",
        f"  Last contact: {fmt_ist(w.get('last_contact_at'))}   Missed check-ins in a row: {w.get('missed_checkins', 0)}",
        "",
        "2. FAMILY CONTACT",
        f"  {v(w.get('family_name'))} ({v(w.get('family_relation'))}), {w.get('family_phone')}",
        "",
        "3. EMPLOYER / SPONSOR",
        f"  Employer: {v(w.get('employer_name'))}   Phone: {v(w.get('employer_phone'))}",
        f"  Sponsor (kafeel): {v(w.get('sponsor_name'))}   Sponsor ID: {v(w.get('sponsor_id'))}",
        f"  Destination: {v(w.get('dest_city'))}, {v(w.get('dest_country'))}   Job: {v(w.get('job_title'))}",
        f"  Contract salary: {v(w.get('contract_salary'))} {w.get('salary_currency') or ''}".rstrip(),
        "",
        "4. RECRUITING AGENT",
        f"  Agency: {v(w.get('agent_name'))}   Owner: {v(w.get('agent_owner'))}",
        f"  Licence no. given: {v(w.get('agent_licence'))}   District: {v(w.get('agent_district'))}",
        f"  Check against MEA licensed list: {v(w.get('agent_check'))}",
    ]
    if w.get("amount_paid_total"):
        lines.append(f"  Paid to agent: Rs {fmt_rupees(int(w['amount_paid_total']))} "
                     f"({'OVER' if w.get('fee_status') == 'over_cap' else 'within'} the Rs 35,400 limit)")
    lines += [
        "",
        "5. TRAVEL",
        f"  Departure: {v(w.get('departure_date'))}   Flight: {v(w.get('flight_no'))}",
        "",
        "6. TIMELINE (newest first)",
    ]
    for e in timeline(store, w):
        when = fmt_ist(e["at"])
        if e["type"] == "registered":
            lines.append(f"  {when}  Registered")
        elif e["type"] == "call":
            c = e["call"]
            state = "answered" if c.get("answered") else "MISSED" if c.get("missed") else (c.get("status") or "")
            lines.append(f"  {when}  {(c.get('kind') or 'call').title()} call, {state}"
                         + (f", {int(c['duration_seconds'])}s" if c.get("duration_seconds") else "")
                         + (f"  Recording: {c['recording_url']}" if c.get("recording_url") else ""))
        elif e["type"] == "checkin":
            ch = e["checkin"]
            said = ", ".join(f"{k}={val}" for k, val in (ch.get("answers") or {}).items() if val not in (None, ""))
            lines.append(f"  {when}  Worker's answers ({ch.get('kind')}): {said or 'none recorded'}")
        else:
            es = e["escalation"]
            lines.append(f"  {when}  ALERT {es['level'].upper()}: "
                         + "; ".join(reason_text(r) for r in es.get("reasons") or [])
                         + f". Family SMS: {es.get('sms_status')}")
    last = next((e["call"] for e in timeline(store, w) if e["type"] == "call" and e["call"].get("transcript")), None)
    if last:
        lines += ["", "7. LATEST CALL TRANSCRIPT (Telugu, as recognised by speech software; needs translation)",
                  last["transcript"].strip()]
    lines += [
        "",
        "WHERE TO FILE",
        "  - MADAD (madad.gov.in): grievance for Indians abroad",
        f"  - Indian Embassy / Consulate in {v(w.get('dest_country'))}",
        "  - eMigrate (emigrate.gov.in) > Register Grievance: complaint against the recruiting agent",
        "  - Telangana: TOMCOM / NRI cell",
    ]
    return "\n".join(lines) + "\n"
