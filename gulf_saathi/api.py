"""HTTP API that the Bolna voice agent calls during a conversation.

Deployed on Vercel (see pyproject.toml). Run locally with:
  uvicorn gulf_saathi.api:app --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator

from .calls import parse_call
from .fees import check_fee as compute_fee
from .matcher import LicensedList

app = FastAPI(title="Gulf Saathi API")
licensed = LicensedList.load()


class AgentQuery(BaseModel):
    agency: str = ""
    owner: str = ""
    district: str = ""
    licence_no: str = ""
    query: str = ""  # free text, when the caller's words weren't split into fields

    @field_validator("*", mode="before")
    @classmethod
    def blank_if_missing(cls, v: Any) -> str:
        # Bolna fills a request template from what its LLM extracted. A field the
        # caller never mentioned can arrive as null, an unfilled placeholder such as
        # {"$var": "district"} or "%(district)s", or "none". Treat all of these as blank.
        if not isinstance(v, str):
            return ""
        v = v.strip()
        if v.startswith("%(") or v.lower() in ("none", "null", "unknown", "n/a", "na", "-"):
            return ""
        return v


@app.get("/")
def health():
    return {"service": "gulf-saathi", "licensed_agents_loaded": len(licensed.agents)}


@app.get("/check-agent")
def check_agent_get(agency: str = "", owner: str = "", district: str = "", licence_no: str = "", query: str = ""):
    """Same check from a browser link, e.g. /check-agent?owner=Seedi Kavitha"""
    return check_agent(AgentQuery(agency=agency, owner=owner, district=district, licence_no=licence_no, query=query))


@app.post("/check-agent")
def check_agent(q: AgentQuery):
    """Bolna custom tool: is this agent in the MEA licensed list?

    `match` is one of confirmed_in_list / needs_confirmation / not_found, and
    `instruction` tells the voice agent what to say. It never endorses an agent.
    """
    return licensed.check(q.agency, q.owner, q.district, q.licence_no, q.query)


class FeeQuery(BaseModel):
    # Digits only, one payment each, separated by semicolons: "10000; 25000".
    # A real list of numbers is accepted too.
    payments: Any = ""

    @field_validator("payments", mode="before")
    @classmethod
    def blank_if_unfilled(cls, v: Any) -> Any:
        if v is None or isinstance(v, dict):
            return ""
        if isinstance(v, str) and (v.strip().startswith("%(") or v.strip().lower() in ("none", "null", "unknown", "n/a", "na", "-")):
            return ""
        return v


@app.get("/check-fee")
def check_fee_get(payments: str = ""):
    """Same check from a browser link, e.g. /check-fee?payments=10000;25000"""
    return compute_fee(payments)


@app.post("/check-fee")
def check_fee(q: FeeQuery):
    """Bolna custom tool: add up every payment to the agent and compare with the legal cap."""
    return compute_fee(q.payments)


log = logging.getLogger("gulf_saathi.webhook")


@app.post("/webhooks/bolna")
async def bolna_webhook(request: Request, token: str = ""):
    """Bolna posts here several times per call. Right now this only records what
    arrived (raw JSON goes to the Vercel logs) and returns what we understood.
    Saving cases and raising alerts comes next, once a real payload has been seen.
    """
    expected = os.getenv("GS_WEBHOOK_TOKEN", "")
    if expected and not secrets.compare_digest(token, expected):
        raise HTTPException(401, "bad token")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "body is not JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "expected a JSON object")
    if os.getenv("GS_LOG_WEBHOOK", "1") != "0":  # contains phone numbers and transcripts
        log.warning("BOLNA_WEBHOOK_RAW %s", json.dumps(payload, ensure_ascii=False)[:20000])
    return parse_call(payload)
