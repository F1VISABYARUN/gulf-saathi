"""Weekly check-in calls and escalation when a worker misses them or reports trouble.

Escalation records a case for a caseworker and SMSes the family. Filing on MADAD
(madad.gov.in) is done by the caseworker: as far as I know MADAD has no public
API for third parties, so nothing here files on it automatically.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, notify
from .prompts import say
from .store import Store

REASONS = {
    "unpaid": "wages not paid",
    "passport": "passport not with worker",
    "unsafe": "worker asked for help",
    "missed": "missed check-in calls",
}


def escalate(store: Store, worker_id: int, reasons: list[str]) -> int:
    w = store.worker(worker_id)
    reason = ", ".join(REASONS[r] for r in reasons)
    case_id = store.add_escalation(worker_id, reason)
    if w.get("family_phone"):
        notify.send_sms(w["family_phone"], say("sms_escalation", w["lang"], phone=w["phone"], reason=reason))
    return case_id


def run_due(store: Store, base_url: str = config.PUBLIC_BASE_URL, now: datetime | None = None) -> int:
    """Place a call to every active worker not called in the last interval."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=config.CHECKIN_INTERVAL_DAYS)).isoformat(timespec="seconds")
    workers = store.due_workers(cutoff)
    for w in workers:
        notify.place_call(
            w["phone"],
            url=f"{base_url}/voice/checkin?worker_id={w['id']}",
            status_callback=f"{base_url}/voice/status?worker_id={w['id']}",
        )
        store.mark_called(w["id"])
    return len(workers)


def handle_call_status(store: Store, worker_id: int, call_status: str) -> None:
    """Twilio status callback. Unanswered calls, and answered calls hung up before
    the questions were answered, count towards escalation."""
    w = store.worker(worker_id)
    if w is None or call_status not in ("completed", "no-answer", "busy", "failed", "canceled"):
        return
    answered_questions = w["last_checkin_at"] and w["last_checkin_at"] >= (w["last_call_at"] or "")
    if call_status == "completed" and answered_questions:
        return
    missed = store.record_missed(worker_id)
    if missed == config.MISSED_CALLS_BEFORE_ESCALATION:
        escalate(store, worker_id, ["missed"])
