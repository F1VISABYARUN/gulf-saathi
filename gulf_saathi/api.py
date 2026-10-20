"""HTTP API that the Bolna voice agent calls during a conversation.

Deployed on Vercel (see pyproject.toml). Run locally with:
  uvicorn gulf_saathi.api:app --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .matcher import LicensedList

app = FastAPI(title="Gulf Saathi API")
licensed = LicensedList.load()


class AgentQuery(BaseModel):
    agency: str = ""
    owner: str = ""
    district: str = ""
    licence_no: str = ""
    query: str = ""  # free text, when the caller's words weren't split into fields


@app.get("/")
def health():
    return {"service": "gulf-saathi", "licensed_agents_loaded": len(licensed.agents)}


@app.post("/check-agent")
def check_agent(q: AgentQuery):
    """Bolna custom tool: is this agent in the MEA licensed list?

    `match` is one of confirmed_in_list / needs_confirmation / not_found, and
    `instruction` tells the voice agent what to say. It never endorses an agent.
    """
    return licensed.check(q.agency, q.owner, q.district, q.licence_no, q.query)
