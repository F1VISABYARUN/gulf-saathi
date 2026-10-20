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

from . import bolna, sms
from .calls import parse_call
from .fees import check_fee, fmt_rupees
from .matcher import LicensedList

IST = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving
CHECKIN_DAYS = int(os.getenv("GS_CHECKIN_DAYS", "7"))
RETRY_HOURS = {"arrival": 3, "weekly": 24}  # after a missed call
DEFAULT_CODE_PHRASE = "అమ్మ బాగుందా"  # "Is Amma well?": says "I can't talk freely" without saying it
CHECKIN_KINDS = ("arrival", "weekly")  # calls that count towards misses and alerts
CALL_KINDS = (*CHECKIN_KINDS, "briefing")  # briefing: pre-departure, before the worker flies

LEVELS = ("ok", "medium", "high", "critical")

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
    "passport_taken": ("high", "Passport is not with the worker", "పాస్‌పోర్ట్ వారి దగ్గర లేదు"),
    "unpaid_2plus": ("high", "Salary unpaid for {n} months", "{n} నెలలుగా జీతం రాలేదు"),
    "missed_2plus": ("high", "{n} check-in calls missed in a row", "వరుసగా {n} కాల్స్‌కు జవాబు రాలేదు"),
    "unpaid_1": ("medium", "Salary unpaid this month", "ఈ నెల జీతం రాలేదు"),
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
    return (te if lang == "te" else en).format(n=reason.get("n", ""))


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
    text = lambda k: str(raw.get(k) or "").strip()[:500]
    return {
        "pickup_status": pickup,
        "pickup_person": text("pickup_person"),
        "current_location": text("current_location"),
        "salary_received": yes_no(raw.get("salary_received")),
        "months_unpaid": as_int(raw.get("months_unpaid")),
        "passport_with_worker": yes_no(raw.get("passport_with_worker")),
        "food_ok": yes_no(raw.get("food_ok")),
        "threatened": yes_no(raw.get("threatened")),
        "movement_restricted": yes_no(raw.get("movement_restricted")),
        "needs_help": yes_no(raw.get("needs_help")),
        "code_phrase_used": yes_no(raw.get("code_phrase_used")),
        "briefing_understood": yes_no(raw.get("briefing_understood")),
        "notes": text("notes"),
    }


def assess(answers: dict, missed_in_row: int = 0) -> tuple[str, list[dict]]:
    reasons = []
    if answers.get("pickup_status") == "other_person":
        reasons.append({"code": "wrong_pickup"})
    elif answers.get("pickup_status") == "nobody":
        reasons.append({"code": "no_pickup"})
    for key, code in (("threatened", "threatened"), ("movement_restricted", "movement_restricted"),
                      ("needs_help", "needs_help"), ("code_phrase_used", "code_phrase")):
        if answers.get(key) is True:
            reasons.append({"code": code})
    if answers.get("passport_with_worker") is False:
        reasons.append({"code": "passport_taken"})
    months = answers.get("months_unpaid")
    if answers.get("salary_received") is False and not months:
        months = 1
    if months and months >= 2:
        reasons.append({"code": "unpaid_2plus", "n": months})
    elif months == 1:
        reasons.append({"code": "unpaid_1"})
    if answers.get("food_ok") is False:
        reasons.append({"code": "food_not_ok"})
    if missed_in_row >= 2:
        reasons.append({"code": "missed_2plus", "n": missed_in_row})
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


def escalate(store, worker: dict, level: str, reasons: list[dict], now: datetime) -> dict | None:
    """Open an alert and text the family, unless an unresolved alert already covers
    the same problems. Repeating the same SMS every day would teach families to
    ignore it; a new kind of problem still gets through."""
    codes = {r["code"] for r in reasons}
    for e in store.select("escalations", {"worker_id": worker["id"], "status": "open"}):
        if rank(e["level"]) >= rank(level) and codes <= {r["code"] for r in e.get("reasons") or []}:
            return None
    text = family_sms(worker, level, reasons)
    status = sms.send_sms(worker.get("family_phone") or "", text)
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
    code_phrase = _text(data, "code_phrase") or DEFAULT_CODE_PHRASE
    if not code_phrase_ok(code_phrase):
        raise CaseError(f'danger code phrase "{code_phrase}" is too easy to say by accident. {CODE_PHRASE_HELP}')

    return {
        "worker_name": name, "worker_name_te": _text(data, "worker_name_te"), "worker_phone": worker_phone,
        "family_name": _text(data, "family_name"), "family_phone": family_phone,
        "family_relation": _text(data, "family_relation"),
        "employer_name": _text(data, "employer_name"),
        "employer_phone": normalize_phone(data.get("employer_phone")) if data.get("employer_phone") else None,
        "sponsor_name": _text(data, "sponsor_name"), "sponsor_id": _text(data, "sponsor_id"),
        "dest_country": _text(data, "dest_country"), "dest_city": _text(data, "dest_city"),
        "job_title": _text(data, "job_title"),
        "contract_salary": salary, "salary_currency": _text(data, "salary_currency", 10),
        **agent, "agent_check": agent_check, "agent_check_detail": agent_detail,
        "payments": fee["payments"], "amount_paid_total": fee["total"], "fee_status": fee["status"],
        "departure_date": departure, "flight_no": _text(data, "flight_no", 20),
        "arrival_call_at": iso(arrival_call_at) if arrival_call_at else None,
        "code_phrase": code_phrase,
        "notes": _text(data, "notes", 2000),
    }


def register_worker(store, licensed: LicensedList, data: dict, now: datetime) -> dict:
    """Create the pre-departure case. Returns {"worker": ..., "arrival_call": ...}."""
    fields = clean_case_fields(data, licensed)
    worker = store.insert("workers", {
        "case_id": new_case_id(store), "created_at": iso(now), "updated_at": iso(now), **fields,
        "status": "registered", "risk_level": "ok", "risk_reasons": [], "missed_checkins": 0,
    })
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
        "employer_phone": worker.get("employer_phone") or "",
        "sponsor_name": worker.get("sponsor_name") or "",
        "dest_city": worker.get("dest_city") or "", "dest_country": worker.get("dest_country") or "",
        "code_phrase": worker.get("code_phrase") or DEFAULT_CODE_PHRASE,
    }


def schedule_call(store, worker: dict, kind: str, when: datetime | None, now: datetime) -> dict:
    """Ask Bolna to call the worker at `when` (or now). Records the call so the
    webhook can match it and the dashboard can show it."""
    later = when is not None and when > now + timedelta(minutes=1)
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

    if not c["terminal"] or not worker or kind not in CHECKIN_KINDS or (existing or {}).get("processed_at"):
        return {"stored": True, "processed": False, "worker": worker["case_id"] if worker else None}
    store.update("calls", {"id": c["call_id"]}, {"processed_at": iso(now)})

    if c["missed"]:
        missed = int(worker.get("missed_checkins") or 0) + 1
        level, reasons = assess({}, missed_in_row=missed)
        changes = {"missed_checkins": missed}
        next_when = now + timedelta(hours=RETRY_HOURS[kind])
        next_kind = kind
    else:
        # Answers normally arrive during the call through record_checkin. Only use
        # Bolna's extracted_data if it actually has some, so an empty one doesn't
        # wipe what the tool recorded.
        answers = normalize_answers(c["extracted"])
        has_answers = any(val not in (None, "") for val in answers.values())
        level, reasons = assess(answers) if has_answers else (None, [])
        changes = {"missed_checkins": 0, "last_contact_at": iso(now)}
        if kind == "arrival":
            changes["status"] = "abroad"
        next_when = now + timedelta(days=CHECKIN_DAYS)
        next_kind = "weekly"

    escalation = escalate(store, worker, level, reasons, now) if level and rank(level) >= rank("high") else None
    changes["updated_at"] = iso(now)
    if level:
        changes.update({"risk_level": overall_level(store, worker["id"], level), "risk_reasons": reasons})
    store.update("workers", {"id": worker["id"]}, changes)
    worker = store.get("workers", id=worker["id"])

    # Book the next call unless another one is already booked for later.
    next_call = None
    if not _other_booked_call(store, worker["id"], c["call_id"], now):
        next_call = schedule_call(store, worker, next_kind, next_when, now)
    return {"stored": True, "processed": True, "worker": worker["case_id"], "missed": c["missed"],
            "risk_level": worker["risk_level"], "escalated": bool(escalation), "next_call": next_call}


def record_checkin(store, data: dict, now: datetime) -> dict:
    """Bolna tool, called by the check-in agent with the worker's answers during the
    call. Returns what the voice agent should say next."""
    case_id = str(data.get("case_id") or "").strip().upper()
    worker = store.get("workers", case_id=case_id) if case_id else None
    if not worker:
        return {"ok": False, "instruction": "The case was not found. Thank the caller, do not promise anything, "
                                            "and say Saathi will call back."}
    kind = str(data.get("call_kind") or "weekly").strip().lower()
    kind = kind if kind in CALL_KINDS else "weekly"
    answers = normalize_answers(data)
    # Danger answers count on any call, a briefing included.
    level, reasons = assess(answers)
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
    if "code_phrase" in codes:
        say = ("IMPORTANT: the worker said the danger phrase and may not be able to talk freely. Do NOT mention "
               "danger, help, complaints, family or embassy. Chat normally for a few seconds and end the call politely.")
    elif level == "critical":
        say = ("Speak calmly. Say: we have told your family and prepared your complaint for the Indian Embassy. "
               "If you are in danger right now, call the Indian Embassy. Do not promise rescue.")
        if codes & {"wrong_pickup", "no_pickup"}:
            employer = worker.get("employer_name") or "your registered employer"
            say += (f" If they are still at the airport: do not go with anyone except {employer}; stay inside "
                    "the airport and call the Indian Embassy.")
    elif level == "high":
        say = ("Say: we have told your family and prepared your complaint. Do not promise that the salary or the "
               "passport will be recovered. Say Saathi will call again soon.")
    elif kind == "briefing":
        say = ("Thank them warmly. Say Saathi will call on the day they land, and every week after that. "
               "Remind them to keep this number.")
    else:
        say = "Thank them warmly. Say Saathi will call again next week."
    return {"ok": True, "risk_level": level, "escalated": bool(escalation), "instruction": say}


def briefed_worker_ids(store) -> dict:
    """worker id -> the latest briefing check-in, for workers who had one."""
    out = {}
    for ch in store.select("checkins", order="created_at", desc=False):
        if ch.get("kind") == "briefing":
            out[ch["worker_id"]] = ch
    return out


def has_predeparture_flags(w: dict) -> bool:
    return w.get("agent_check") in ("not_found", "need_more_info") or w.get("fee_status") == "over_cap"


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
