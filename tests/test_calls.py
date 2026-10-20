import os

import pytest
from fastapi.testclient import TestClient

from gulf_saathi.api import app
from gulf_saathi.calls import parse_call, was_answered

client = TestClient(app)

# Synthetic: shaped like Hark's notes describe Bolna's payload, not a captured one.
TALKED = {
    "id": "exec-1", "agent_id": "agent-1", "status": "completed", "conversation_duration": 42,
    "transcript": "assistant: నమస్కారం\nuser: బొల్లె గంగా నరసయ్య\nassistant: ఒక్క నిమిషం",
    "telephony_data": {"recording_url": "https://example.com/rec.mp3"},
    "context_details": {"recipient_data": {"worker_id": "w1", "employer_name": "X"}},
    "extracted_data": {"passport_with_worker": "no"},
}


def test_answered_call():
    r = parse_call(TALKED)
    assert r["terminal"] and r["answered"] and not r["missed"]
    assert r["recording_url"].endswith("rec.mp3")
    assert r["recipient_data"]["worker_id"] == "w1" and r["extracted"]["passport_with_worker"] == "no"


def test_completed_but_nobody_spoke_is_missed():
    p = {**TALKED, "transcript": "assistant: నమస్కారం\nassistant: మీరు లైన్లో ఉన్నారా?\nuser:"}
    assert not was_answered(p) and parse_call(p)["missed"]
    assert parse_call({**TALKED, "conversation_duration": 0})["missed"]


@pytest.mark.parametrize("status", ["no-answer", "busy", "failed", "canceled"])
def test_unanswered_statuses_are_missed(status):
    assert parse_call({"id": "x", "status": status, "conversation_duration": 0})["missed"]


@pytest.mark.parametrize("status", ["queued", "ringing", "in-progress", "call-disconnected", ""])
def test_in_progress_updates_are_not_final(status):
    r = parse_call({**TALKED, "status": status})
    assert not r["terminal"] and not r["missed"] and not r["answered"]


def test_missing_fields_do_not_crash():
    r = parse_call({})
    assert r["call_id"] is None and r["recipient_data"] == {} and r["extracted"] == {}


def test_webhook_accepts_payload_and_returns_summary(caplog):
    caplog.set_level("WARNING")
    r = client.post("/webhooks/bolna", json=TALKED).json()
    assert r["call_id"] == "exec-1" and r["answered"]
    assert any("BOLNA_WEBHOOK_RAW" in m for m in caplog.messages)


def test_webhook_rejects_bad_input_and_checks_token(monkeypatch):
    assert client.post("/webhooks/bolna", content=b"not json").status_code == 400
    assert client.post("/webhooks/bolna", json=[1, 2]).status_code == 400
    monkeypatch.setenv("GS_WEBHOOK_TOKEN", "s3cret")
    assert client.post("/webhooks/bolna", json=TALKED).status_code == 401
    assert client.post("/webhooks/bolna?token=s3cret", json=TALKED).status_code == 200
