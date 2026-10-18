"""Outbound SMS and calls. Without Twilio credentials, messages are only logged."""
from __future__ import annotations

import logging

from . import config

log = logging.getLogger("gulf_saathi.notify")
sent: list[dict] = []  # what would have gone out; inspected by tests and the simulator


def _client():
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM_NUMBER):
        return None
    from twilio.rest import Client

    return Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


def send_sms(to: str, body: str) -> None:
    sent.append({"kind": "sms", "to": to, "body": body})
    client = _client()
    if client is None:
        log.warning("SMS not sent (no Twilio credentials) to=%s body=%s", to, body)
        return
    client.messages.create(to=to, from_=config.TWILIO_FROM_NUMBER, body=body)


def place_call(to: str, url: str, status_callback: str) -> None:
    sent.append({"kind": "call", "to": to, "url": url})
    client = _client()
    if client is None:
        log.warning("Call not placed (no Twilio credentials) to=%s url=%s", to, url)
        return
    client.calls.create(
        to=to,
        from_=config.TWILIO_FROM_NUMBER,
        url=url,
        status_callback=status_callback,
        status_callback_event=["completed"],
    )
