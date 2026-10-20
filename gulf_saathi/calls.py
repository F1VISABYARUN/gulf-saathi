"""Read what Bolna sends after a call.

The field names below come from Hark's notes on Bolna's docs and from the
transcripts pasted in this project (lines start "assistant:" / "user:"). They are
NOT yet checked against a real payload from our own agent: the webhook endpoint
logs the raw JSON so the first real call settles that.
"""
from __future__ import annotations

from typing import Any

# Bolna sends several webhooks per call; only these statuses end it.
TERMINAL_STATUSES = {"completed", "no-answer", "busy", "failed", "canceled", "stopped", "error", "balance-low"}


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
        "recipient_data": _get(payload, "context_details", "recipient_data") or {},
        "extracted": extracted if isinstance(extracted, dict) else {},
    }
