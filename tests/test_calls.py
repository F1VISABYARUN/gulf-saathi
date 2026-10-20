import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gulf_saathi.api import app
from gulf_saathi.calls import parse_call, was_answered

client = TestClient(app)

REAL = json.loads((Path(__file__).parent / "fixtures" / "bolna_execution_2026-10-20.json").read_text(encoding="utf-8"))


def test_real_bolna_record_parses():
    r = parse_call(REAL)
    assert r["call_id"] == "d2d1c8ee-4056-4983-88db-89469b197c0e"
    assert r["terminal"] and r["answered"] and not r["missed"]  # "user:  sorry" has two spaces
    assert r["duration_seconds"] == 231
    assert r["recording_url"] == "https://api.bolna.ai/recordings/call/d2d1c8ee-4056-4983-88db-89469b197c0e"
    assert r["recipient_data"] == {"timezone": "Asia/Kolkata"}
    assert r["extracted"] == {}
    assert r["hangup_by"] == "Callee" and r["user_number"] == "+91XXXXXXXXXX"


# Synthetic: real field names, made-up values.
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


@pytest.mark.parametrize("status", ["queued", "initiated", "ringing", "in-progress", ""])
def test_in_progress_updates_are_not_final(status):
    r = parse_call({**TALKED, "status": status})
    assert not r["terminal"] and not r["missed"] and not r["answered"]


def test_missing_fields_do_not_crash():
    r = parse_call({})
    assert r["call_id"] is None and r["recipient_data"] == {} and r["extracted"] == {}


def test_webhook_accepts_payload(caplog, monkeypatch):
    from gulf_saathi import api
    from gulf_saathi.db import MemoryStore

    monkeypatch.setattr(api, "STORE", MemoryStore())
    caplog.set_level("WARNING")
    r = client.post("/webhooks/bolna", json=TALKED).json()
    assert r["stored"] is True and api.STORE.get("calls", id="exec-1")["answered"] is True
    assert any("BOLNA_WEBHOOK_RAW" in m for m in caplog.messages)


def test_webhook_rejects_bad_input_and_checks_token(monkeypatch):
    from gulf_saathi import api
    from gulf_saathi.db import MemoryStore

    monkeypatch.setattr(api, "STORE", MemoryStore())
    assert client.post("/webhooks/bolna", content=b"not json").status_code == 400
    assert client.post("/webhooks/bolna", json=[1, 2]).status_code == 400
    monkeypatch.setenv("GS_WEBHOOK_TOKEN", "s3cret")
    assert client.post("/webhooks/bolna", json=TALKED).status_code == 401
    assert client.post("/webhooks/bolna?token=s3cret", json=TALKED).status_code == 200


def test_call_disconnected_with_transcript_ends_the_call():
    r = parse_call({**TALKED, "status": "call-disconnected"})
    assert r["terminal"] and r["answered"]


def test_call_disconnected_without_transcript_waits_for_completed():
    r = parse_call({**TALKED, "status": "call-disconnected", "transcript": ""})
    assert not r["terminal"] and not r["missed"]
    assert parse_call({**TALKED, "status": "completed"})["terminal"]
