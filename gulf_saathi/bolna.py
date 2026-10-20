"""Place outbound calls through Bolna's API.

Request shape from Hark's notes on Bolna's docs (POST /call with agent_id,
recipient_phone_number, optional scheduled_at and user_data). Not yet tried
against the live API from this code: the result says what happened.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

API_URL = os.getenv("BOLNA_API_URL", "https://api.bolna.ai")


def api_key() -> str:
    return os.getenv("BOLNA_API_KEY", "")


def checkin_agent_id() -> str:
    """The Bolna agent that makes arrival and weekly check-in calls."""
    return os.getenv("BOLNA_CHECKIN_AGENT_ID", "")


def configured() -> bool:
    return bool(api_key() and checkin_agent_id())


def place_call(phone: str, user_data: dict, scheduled_at: datetime | None = None, agent_id: str = "") -> dict:
    """Returns {"ok": bool, "execution_id": str | None, "error": str | None}."""
    agent_id = agent_id or checkin_agent_id()
    if not (api_key() and agent_id):
        return {"ok": False, "execution_id": None, "error": "Bolna not configured (BOLNA_API_KEY / BOLNA_CHECKIN_AGENT_ID)"}
    body = {
        "agent_id": agent_id,
        "recipient_phone_number": phone,
        # Bolna gives these to the agent's prompt as variables and returns them in
        # context_details.recipient_data, which is how the webhook finds the case.
        "user_data": {k: ("" if v is None else str(v)) for k, v in user_data.items()},
    }
    if scheduled_at:
        body["scheduled_at"] = scheduled_at.astimezone(timezone.utc).isoformat()
    try:
        r = httpx.post(f"{API_URL}/call", json=body, headers={"Authorization": f"Bearer {api_key()}"}, timeout=8)
    except httpx.HTTPError as e:
        return {"ok": False, "execution_id": None, "error": f"Bolna unreachable: {e}"}
    if r.status_code >= 300:
        return {"ok": False, "execution_id": None, "error": f"Bolna {r.status_code}: {r.text[:300]}"}
    data = r.json() if r.content else {}
    return {"ok": True, "execution_id": data.get("execution_id") or data.get("id"), "error": None}
