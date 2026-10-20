"""Family SMS. Sends through Plivo when it is configured; otherwise demo mode:
nothing is sent and the dashboard shows the text that would have gone out.

Commercial SMS to Indian numbers needs DLT registration, so expect demo mode
until that is done. The Plivo request below is untested from this code.
"""
from __future__ import annotations

import os

import httpx


def provider() -> str:
    return "plivo" if os.getenv("PLIVO_AUTH_ID") and os.getenv("PLIVO_AUTH_TOKEN") and os.getenv("PLIVO_FROM") else "demo"


def send_sms(to: str, text: str) -> str:
    """Returns a short status for the dashboard: "sent", "demo: not sent" or "failed: ..."."""
    if not to:
        return "failed: no family number"
    if provider() == "demo":
        return "demo: not sent (no SMS provider configured)"
    auth_id = os.environ["PLIVO_AUTH_ID"]
    try:
        r = httpx.post(
            f"https://api.plivo.com/v1/Account/{auth_id}/Message/",
            auth=(auth_id, os.environ["PLIVO_AUTH_TOKEN"]),
            json={"src": os.environ["PLIVO_FROM"], "dst": to, "text": text},
            timeout=5,
        )
    except httpx.HTTPError as e:
        return f"failed: {e}"
    return "sent" if r.status_code < 300 else f"failed: Plivo {r.status_code}"
