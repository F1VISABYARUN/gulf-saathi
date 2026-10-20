"""Read what Bolna sends after a call.

Field names are checked against a real execution record from our own agent
(tests/fixtures/bolna_execution_2026-10-20.json, from Bolna's Debug page). That
is the record Bolna stores for a call; that the webhook body has the same shape
is still an assumption until the webhook is switched on.
"""
from __future__ import annotations

from typing import Any

# Bolna sends several webhooks per call (seen on a real call: initiated, ringing,
# in-progress, call-disconnected). Only these statuses end it.
TERMINAL_STATUSES = {"completed", "call-disconnected", "no-answer", "busy", "failed", "canceled", "stopped",
                     "error", "balance-low"}
# Not yet seen: whether "call-disconnected" already carries the transcript. If it
# doesn't, wait for the "completed" message rather than wrongly count a miss.
NEEDS_TRANSCRIPT = {"call-disconnected"}


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def was_answered(payload: dict) -> bool:
    """"completed" does not mean someone spoke. Count a call as answered only if it
    lasted more than 0 seconds AND the transcript has a line from the caller."""
    try:
        duration = float(payload.get("conversation_duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    transcript = payload.get("transcript") or ""
    spoke = any(line.strip().lower().startswith("user:") and line.strip()[5:].strip() for line in str(transcript).splitlines())
    return duration > 0 and spoke


def parse_call(payload: dict) -> dict:
    status = str(payload.get("status") or "").lower()
    terminal = status in TERMINAL_STATUSES
    if status in NEEDS_TRANSCRIPT and not str(payload.get("transcript") or "").strip():
        terminal = False
    answered = was_answered(payload) if terminal else False
    extracted = payload.get("extracted_data")
    return {
        "call_id": payload.get("id"),
        "agent_id": payload.get("agent_id"),
        "status": status,
        "terminal": terminal,
        # A finished call nobody talked on counts as missed, whatever its status says.
        "answered": answered,
        "missed": terminal and not answered,
        "duration_seconds": payload.get("conversation_duration"),
        "transcript": payload.get("transcript") or "",
        "recording_url": _get(payload, "telephony_data", "recording_url"),
        "user_number": payload.get("user_number") or _get(payload, "telephony_data", "to_number"),
        "hangup_by": _get(payload, "telephony_data", "hangup_by"),
        "hangup_reason": _get(payload, "telephony_data", "hangup_reason"),
        "recipient_data": _get(payload, "context_details", "recipient_data") or {},
        "extracted": extracted if isinstance(extracted, dict) else {},
    }
