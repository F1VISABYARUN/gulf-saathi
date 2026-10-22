"""Gulf Saathi server: tools the Bolna voice agents call, Bolna's webhook, and
the caseworker dashboard.

Deployed on Vercel (see pyproject.toml). Run locally with:
  uvicorn gulf_saathi.api:app --port 8000
Without SUPABASE_URL / SUPABASE_SERVICE_KEY it keeps data in memory only.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, field_validator

from . import bolna, cases, dashboard, demo, signals, site, sms
from .db import TABLES, MemoryStore, StoreError, SupabaseStore
from .fees import check_fee as compute_fee
from .matcher import LicensedList

app = FastAPI(title="Gulf Saathi API")
licensed = LicensedList.load()
STORE = SupabaseStore.from_env() or MemoryStore()
log = logging.getLogger("gulf_saathi")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _blank(v: Any) -> bool:
    # Bolna fills a request template from what its LLM extracted. A field the caller
    # never mentioned can arrive as null, an unfilled placeholder such as
    # {"$var": "district"} or "%(district)s", or "none".
    if v is None or isinstance(v, dict):
        return True
    s = str(v).strip()
    return not s or s.startswith("%(") or s.lower() in ("none", "null", "unknown", "n/a", "na", "-")


def clean_tool_args(data: dict) -> dict:
    return {k: ("" if _blank(v) else (v.strip() if isinstance(v, str) else v)) for k, v in data.items()}


def require_bolna_token(token: str = "") -> None:
    """If GS_WEBHOOK_TOKEN is set, Bolna's URLs must end in ?token=<it>."""
    expected = os.getenv("GS_WEBHOOK_TOKEN", "")
    if expected and not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, "bad token")


def require_dashboard(request: Request) -> None:
    """Browser password prompt. The dashboard shows workers' and families' personal data."""
    # Spaces or a line break copied along with a value pasted into Vercel would
    # otherwise make the right password fail.
    expected = os.getenv("GS_DASHBOARD_PASSWORD", "").strip()
    if not expected:
        raise HTTPException(503, "Dashboard is off: set GS_DASHBOARD_PASSWORD in Vercel and redeploy.")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            given = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)[1].strip()
        except Exception:
            given = ""
        if secrets.compare_digest(given.encode(), expected.encode()):
            return
    raise HTTPException(401, "Password needed", headers={"WWW-Authenticate": 'Basic realm="Gulf Saathi"'})


def status() -> dict:
    return {"storage": STORE.kind, "bolna": bolna.configured(), "sms": sms.provider()}


async def json_object(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "body is not JSON")
    if not isinstance(data, dict):
        raise HTTPException(400, "expected a JSON object")
    return data


# --- public website ---------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home():
    """Public home page. Shows totals only, never a name or number."""
    try:
        workers = STORE.select("workers", order="updated_at")
        counts = {**cases.summary_counts(workers, {}), "demo": sum(1 for w in workers if w.get("is_demo")),
                  "signals": sum(1 for x in signals.repeated_signals(workers) if x["strong"])}
    except StoreError:
        counts = {}
    return site.render_home(counts, demo_calls_on=bool(os.getenv("GS_DEMO_CODE", "").strip() and demo_agent_id()))


def demo_agent_id() -> str:
    """The Gulf Saathi agent (the one workers call before paying an agent)."""
    return os.getenv("BOLNA_AGENT_ID", "").strip()


_last_demo_call: dict[str, datetime] = {}  # per server instance only: a speed bump, not a guarantee


@app.post("/api/demo-call")
async def api_demo_call(request: Request):
    """"Get a call from Saathi" on the home page. Needs the demo code, since every
    call costs Bolna credits."""
    data = await json_object(request)
    expected = os.getenv("GS_DEMO_CODE", "").strip()
    if not expected or not demo_agent_id():
        raise HTTPException(503, "Demo calls are off (GS_DEMO_CODE / BOLNA_AGENT_ID not set).")
    if not secrets.compare_digest(str(data.get("code") or "").strip().encode(), expected.encode()):
        raise HTTPException(403, "Wrong demo code.")
    try:
        phone = cases.normalize_phone(data.get("phone"))
    except cases.CaseError as e:
        raise HTTPException(400, str(e))
    if not phone.startswith("+91"):
        raise HTTPException(400, "Indian numbers only for now.")
    last = _last_demo_call.get(phone)
    if last and (now() - last).total_seconds() < 120:
        raise HTTPException(429, "Saathi called this number less than 2 minutes ago. Please wait.")
    res = bolna.place_call(phone, {"source": "website_demo"}, agent_id=demo_agent_id())
    if not res["ok"]:
        raise HTTPException(502, res["error"])
    _last_demo_call[phone] = now()
    return {"ok": True, "execution_id": res["execution_id"]}


@app.get("/demo", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def demo_page():
    return site.render_demo()


@app.post("/api/demo/run", dependencies=[Depends(require_dashboard)])
def api_demo_run():
    """Creates made-up demo cases (is_demo). No real call or SMS."""
    try:
        return demo.run_demo(STORE, licensed, now())
    except StoreError as e:
        raise HTTPException(503, f"Could not save the demo cases. Has supabase/schema.sql been run again? {e}")


# --- health -------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "service": "gulf-saathi",
        "licensed_agents_loaded": len(licensed.agents),
        "storage": STORE.kind,
        "bolna_checkin_calls": bolna.configured(),
        "sms": sms.provider(),
        "dashboard": bool(os.getenv("GS_DASHBOARD_PASSWORD")),
        "webhook_token": bool(os.getenv("GS_WEBHOOK_TOKEN")),
        # "Get a call from Saathi" needs both. Shows only whether each is set, never the value.
        "demo_calls": {"GS_DEMO_CODE": bool(os.getenv("GS_DEMO_CODE", "").strip()),
                       "BOLNA_AGENT_ID": bool(demo_agent_id())},
    }


NEW_WORKER_COLUMNS = ("visa_job", "visa_type", "sub_agent_name", "sub_agent_phone", "payment_to",
                      "welcome_sms", "welcome_sms_status", "source", "reported_by", "petition_status",
                      "petition_ref")


@app.get("/health/db")
def health_db():
    """Can we read each table? Shows Supabase's error message, never data."""
    tables = {}
    for t in TABLES:
        try:
            STORE.select(t, limit=1)
            tables[t] = "ok"
        except Exception as e:  # noqa: BLE001 - report whatever went wrong
            tables[t] = str(e)[:300]
    try:
        # Filtering on a column fails if it doesn't exist: catches a schema.sql not re-run.
        STORE.select("workers", {c: "x" for c in NEW_WORKER_COLUMNS}, limit=1)
        tables["workers (new columns)"] = "ok"
    except Exception as e:  # noqa: BLE001
        tables["workers (new columns)"] = "missing: run supabase/schema.sql again. " + str(e)[:200]
    return {"storage": STORE.kind, "ok": all(v == "ok" for v in tables.values()), "tables": tables}


# --- tools for the Bolna voice agents --------------------------------------------

class AgentQuery(BaseModel):
    agency: str = ""
    owner: str = ""
    district: str = ""
    licence_no: str = ""
    query: str = ""  # free text, when the caller's words weren't split into fields

    @field_validator("*", mode="before")
    @classmethod
    def blank_if_missing(cls, v: Any) -> str:
        return "" if _blank(v) else str(v).strip()


@app.get("/check-agent")
def check_agent_get(agency: str = "", owner: str = "", district: str = "", licence_no: str = "", query: str = ""):
    """Same check from a browser link, e.g. /check-agent?owner=Seedi Kavitha"""
    return check_agent(AgentQuery(agency=agency, owner=owner, district=district, licence_no=licence_no, query=query))


@app.post("/check-agent")
def check_agent(q: AgentQuery):
    """Is this agent in the MEA licensed list? `match` is confirmed_in_list /
    needs_confirmation / not_found / need_more_info. It never endorses an agent."""
    return licensed.check(q.agency, q.owner, q.district, q.licence_no, q.query)


class FeeQuery(BaseModel):
    # Digits only, one payment each, separated by semicolons: "10000; 25000".
    # A real list of numbers is accepted too.
    payments: Any = ""

    @field_validator("payments", mode="before")
    @classmethod
    def blank_if_unfilled(cls, v: Any) -> Any:
        return v if isinstance(v, list) else ("" if _blank(v) else v)


@app.get("/check-fee")
def check_fee_get(payments: str = ""):
    """Same check from a browser link, e.g. /check-fee?payments=10000;25000"""
    return compute_fee(payments)


@app.post("/check-fee")
def check_fee(q: FeeQuery):
    """Add up every payment to the agent and compare with the legal cap."""
    return compute_fee(q.payments)


class ContactQuery(BaseModel):
    phone: str = ""     # the agent's phone number, as the caller said it
    payment: str = ""   # UPI ID / account / number the money was paid to
    amount: str = ""    # what the agent asked for, if said
    visa_type: str = ""
    agent_name: str = ""
    district: str = ""  # caller's district
    reporter: str = ""  # worker / family
    caller_phone: str = ""  # Bolna's user_number: counts distinct callers, never shown to callers
    notes: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def blank_if_missing(cls, v: Any) -> str:
        return "" if _blank(v) else str(v).strip()


@app.get("/check-contact")
def check_contact_get(phone: str = "", payment: str = ""):
    """Same check from a browser link, e.g. /check-contact?phone=9848012345 (saves nothing)."""
    return _contact_result(ContactQuery(phone=phone, payment=payment))


@app.post("/check-contact")
def check_contact(q: ContactQuery):
    """Saathi Intelligence, live on the call: has this agent phone or payment account
    come up in other cases or been reported by other callers? Saves this report too.
    Counts only; never names, case numbers or accusations."""
    out = _contact_result(q)
    try:
        signals.record_contact(STORE, q.model_dump(), now().isoformat())
    except StoreError as e:  # the answer matters more than saving it
        log.error("contact report not saved: %s", e)
    return out


def _contact_result(q: ContactQuery) -> dict:
    try:
        workers = STORE.select("workers", order="updated_at")
        reports = STORE.select("contact_reports")
    except StoreError as e:
        log.error("check_contact failed: %s", e)
        return {"found": False, "instruction": "Say you could not check the number right now; do not pay more until "
                                               "the licence and a written contract are checked."}
    return signals.check_contact(workers, q.phone, q.payment, reports, q.caller_phone)


@app.post("/tools/record-checkin", dependencies=[Depends(require_bolna_token)])
async def tool_record_checkin(request: Request):
    """The check-in agent sends the worker's answers here during the call. The
    reply tells it what to say next; HIGH / CRITICAL answers alert the family."""
    data = await json_object(request)
    try:
        return cases.record_checkin(STORE, clean_tool_args(data), now())
    except StoreError as e:
        log.error("record_checkin failed: %s", e)
        return {"ok": False, "instruction": "The system is not available right now. Thank the caller, do not "
                                            "promise anything, and say Saathi will call back."}


@app.post("/tools/report-problem", dependencies=[Depends(require_bolna_token)])
async def tool_report_problem(request: Request):
    """The Gulf Saathi line: a worker abroad calls in with a problem. Opens or finds
    their case, applies the same risk rules, and alerts the family when HIGH or CRITICAL."""
    data = await json_object(request)
    try:
        return cases.report_problem(STORE, clean_tool_args(data), now())
    except StoreError as e:
        log.error("report_problem failed: %s", e)
        return {"ok": False, "instruction": "The system is not available right now. If they are in danger, tell them "
                                            "to call the Indian Embassy. Say Saathi will call back."}


# --- Bolna webhook ----------------------------------------------------------------

@app.post("/webhooks/bolna", dependencies=[Depends(require_bolna_token)])
async def bolna_webhook(request: Request):
    """Bolna posts here several times per call. Saves the call; once it has ended,
    counts a miss or a contact, raises alerts and books the next call."""
    payload = await json_object(request)
    if os.getenv("GS_LOG_WEBHOOK", "1") != "0":  # contains phone numbers and transcripts
        log.warning("BOLNA_WEBHOOK_RAW %s", json.dumps(payload, ensure_ascii=False)[:20000])
    try:
        return cases.process_call_record(STORE, payload, now())
    except StoreError as e:
        log.error("webhook not saved: %s", e)
        raise HTTPException(503, "storage unavailable")  # lets Bolna retry


# --- dashboard ----------------------------------------------------------------------

def _worker_or_404(case_id: str) -> dict:
    w = STORE.get("workers", case_id=case_id.strip().upper())
    if not w:
        raise HTTPException(404, "case not found")
    return w


@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def dashboard_list():
    workers = STORE.select("workers", order="updated_at")
    totals = cases.summary_counts(workers, cases.briefed_worker_ids(STORE))
    return dashboard.render_list(workers, status(), totals)


@app.get("/dashboard/agents", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def dashboard_agents():
    workers = STORE.select("workers", order="updated_at")
    reported = signals.reported_contacts(STORE.select("contact_reports"), workers)
    return dashboard.render_agents(cases.agent_stats(workers), signals.repeated_signals(workers), reported)


@app.get("/dashboard/new", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def dashboard_new():
    return dashboard.render_new()


@app.get("/dashboard/case/{case_id}", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def dashboard_case(case_id: str):
    w = _worker_or_404(case_id)
    sig = signals.signals_for_case(w, STORE.select("workers", order="updated_at"))
    return dashboard.render_case(w, cases.timeline(STORE, w), status(), sig, cases.embassy_alert(STORE, w, now()))


@app.get("/dashboard/case/{case_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def dashboard_edit(case_id: str):
    w = _worker_or_404(case_id)
    return dashboard.render_form(w, w["case_id"])


@app.get("/dashboard/case/{case_id}/packet.txt", dependencies=[Depends(require_dashboard)])
def dashboard_packet(case_id: str):
    w = _worker_or_404(case_id)
    return PlainTextResponse(cases.case_packet(STORE, w, now()),
                             headers={"Content-Disposition": f'attachment; filename="{w["case_id"]}-case-packet.txt"'})


@app.get("/dashboard/case/{case_id}/petition", response_class=HTMLResponse, dependencies=[Depends(require_dashboard)])
def dashboard_petition(case_id: str):
    w = _worker_or_404(case_id)
    return dashboard.render_petition(w, cases.prajavani_petition(STORE, w, now()))


@app.post("/api/cases/{case_id}/petition", dependencies=[Depends(require_dashboard)])
async def api_petition(case_id: str, request: Request):
    data = await json_object(request)
    try:
        w = cases.update_petition(STORE, _worker_or_404(case_id), str(data.get("status") or ""),
                                  str(data.get("ref") or ""), now())
    except cases.CaseError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "petition_status": w["petition_status"]}


@app.post("/api/workers", dependencies=[Depends(require_dashboard)])
async def api_register(request: Request):
    data = await json_object(request)
    try:
        out = cases.register_worker(STORE, licensed, data, now())
    except cases.CaseError as e:
        raise HTTPException(400, str(e))
    return {"case_id": out["worker"]["case_id"], "arrival_call": out["arrival_call"]}


@app.post("/api/cases/{case_id}", dependencies=[Depends(require_dashboard)])
async def api_update(case_id: str, request: Request):
    data = await json_object(request)
    try:
        w = cases.update_worker(STORE, licensed, _worker_or_404(case_id), data, now())
    except cases.CaseError as e:
        raise HTTPException(400, str(e))
    return {"case_id": w["case_id"]}


@app.post("/api/cases/{case_id}/book-arrival", dependencies=[Depends(require_dashboard)])
def api_book_arrival(case_id: str):
    try:
        res = cases.book_arrival_call(STORE, _worker_or_404(case_id), now())
    except cases.CaseError as e:
        raise HTTPException(400, str(e))
    if not res["ok"]:
        raise HTTPException(502, res["error"])
    return res


@app.post("/api/cases/{case_id}/call", dependencies=[Depends(require_dashboard)])
async def api_call_now(case_id: str, request: Request):
    body = await json_object(request) if await request.body() else {}
    kind = body.get("kind", "weekly")
    if kind not in cases.CALL_KINDS:
        raise HTTPException(400, f"kind must be one of {cases.CALL_KINDS}")
    res = cases.schedule_call(STORE, _worker_or_404(case_id), kind, None, now())
    if not res["ok"]:
        raise HTTPException(502, res["error"])
    return res


@app.post("/api/escalations/{escalation_id}/resolve", dependencies=[Depends(require_dashboard)])
def api_resolve(escalation_id: str):
    if not cases.resolve_escalation(STORE, escalation_id, now()):
        raise HTTPException(404, "alert not found")
    return {"ok": True}
