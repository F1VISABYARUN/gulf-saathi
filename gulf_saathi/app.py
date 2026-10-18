"""FastAPI app: Twilio voice webhooks, offer-text API and a caseworker view.

Run:  uvicorn gulf_saathi.app:app --port 8000
Point your Twilio number's "A call comes in" webhook at POST {base}/voice.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel
from twilio.twiml.voice_response import Gather, VoiceResponse

from . import checkin, config
from .agents import AgentRegistry
from .engine import Engine, Reply, Session, fmt_rupees
from .offer import analyze_text
from .prompts import LANGS, say
from .store import Store

app = FastAPI(title="Gulf Saathi")
store = Store(config.DB_PATH)
engine = Engine(AgentRegistry.from_csv(config.AGENTS_CSV), store)
sessions: dict[str, Session] = {}  # CallSid -> Session; in-memory is fine for one server


def twiml(reply: Reply) -> Response:
    vr = VoiceResponse()
    lang = reply.say[-1][1] if reply.say else "te"

    def speak(target, text, l):
        target.say(text, voice=config.VOICES[l], language=config.LOCALES[l])

    if reply.expect is None:
        for text, l in reply.say:
            speak(vr, text, l)
        vr.hangup()
    else:
        kw = dict(
            action="/voice/step",
            method="POST",
            language=config.LOCALES[lang],
            action_on_empty_result=True,
            timeout=6,
        )
        if reply.expect == "speech":
            kw.update(input="speech", speech_timeout="auto")
            if reply.hints:
                kw["hints"] = ", ".join(reply.hints)
        elif reply.expect == "digits":
            kw.update(input="dtmf speech", finish_on_key="#", speech_timeout="auto", timeout=10)
        else:
            kw.update(input="dtmf speech", num_digits=1, speech_timeout="auto")
        g = Gather(**kw)
        for text, l in reply.say:
            speak(g, text, l)
        vr.append(g)
    return Response(str(vr), media_type="application/xml")


async def twilio_form(request: Request) -> dict:
    form = dict(await request.form())
    if config.VALIDATE_TWILIO_SIGNATURE:
        from twilio.request_validator import RequestValidator

        url = config.PUBLIC_BASE_URL.rstrip("/") + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        sig = request.headers.get("X-Twilio-Signature", "")
        if not RequestValidator(config.TWILIO_AUTH_TOKEN).validate(url, form, sig):
            raise HTTPException(403, "bad Twilio signature")
    return form


@app.post("/voice")
async def voice_incoming(request: Request):
    form = await twilio_form(request)
    s = Session(caller=form.get("From", ""))
    sessions[form.get("CallSid", "")] = s
    return twiml(engine.start_inbound(s))


@app.post("/voice/checkin")
async def voice_checkin(request: Request, worker_id: int):
    form = await twilio_form(request)
    if store.worker(worker_id) is None:
        raise HTTPException(404, "unknown worker")
    s = Session(caller=form.get("To", ""))
    sessions[form.get("CallSid", "")] = s
    return twiml(engine.start_checkin(s, worker_id))


@app.post("/voice/step")
async def voice_step(request: Request):
    form = await twilio_form(request)
    sid = form.get("CallSid", "")
    s = sessions.get(sid)
    if s is None:  # server restarted mid-call
        s = sessions[sid] = Session(caller=form.get("From", ""))
        return twiml(engine.start_inbound(s))
    reply = engine.handle(s, digits=form.get("Digits"), speech=form.get("SpeechResult"))
    if reply.expect is None:
        sessions.pop(sid, None)
    return twiml(reply)


@app.post("/voice/status")
async def voice_status(request: Request, worker_id: int):
    form = await twilio_form(request)
    sessions.pop(form.get("CallSid", ""), None)
    checkin.handle_call_status(store, worker_id, form.get("CallStatus", ""))
    return Response(status_code=204)


class OfferText(BaseModel):
    text: str
    lang: str = "te"


@app.post("/offer/analyze")
def offer_analyze(body: OfferText):
    """For offers forwarded as text (e.g. from a WhatsApp bot). Returns the flags
    and the warning text to read or send back in the caller's language."""
    if body.lang not in LANGS:
        raise HTTPException(400, f"lang must be one of {LANGS}")
    answers, flags = analyze_text(body.text)
    kw = {"n": len(flags), "max_fee": fmt_rupees(config.MAX_SERVICE_FEE_INR)}
    if answers.fee_inr is not None:
        kw["fee"] = fmt_rupees(answers.fee_inr)
    keys = ["offer_bad", *flags] if flags else ["offer_ok"]
    return {"flags": flags, "fee_inr": answers.fee_inr, "message": " ".join(say(k, body.lang, **kw) for k in keys)}


@app.get("/agents/lookup")
def agent_lookup(q: str):
    m = engine.registry.lookup(q)
    return {
        "match": m.kind,
        "score": round(m.score, 1),
        "agent": m.agent and {"name": m.agent.name, "licence_no": m.agent.licence_no, "status": m.agent.status, "city": m.agent.city},
    }


def require_admin(x_admin_token: str = Header(default="")):
    if not config.ADMIN_TOKEN:
        raise HTTPException(503, "set GS_ADMIN_TOKEN to enable admin endpoints")
    if not secrets.compare_digest(x_admin_token, config.ADMIN_TOKEN):
        raise HTTPException(401, "bad admin token")


# Caseworker endpoints: they expose workers' phone numbers.
admin = Depends(require_admin)


@app.get("/admin/escalations", dependencies=[admin])
def admin_escalations():
    return store.open_escalations()


@app.get("/admin/callbacks", dependencies=[admin])
def admin_callbacks():
    return store.open_callbacks()


@app.get("/admin/lookups", dependencies=[admin])
def admin_lookups():
    return store.recent_lookups()


@app.post("/admin/run-checkins", dependencies=[admin])
def admin_run_checkins():
    return {"calls_placed": checkin.run_due(store)}
