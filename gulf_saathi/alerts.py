"""Weekly scam alerts: one short Telugu warning, sent to every worker and family who
agreed to receive them. Asked for by officials at Pravasi Prajavani (Oct 2026).

Alerts warn about scam patterns, never about a person: a message that contains a
phone number is refused, so nobody is named or accused in a broadcast. Voice alerts
go out as a short Bolna call (the check-in agent's "alert" section reads the text);
SMS goes out once an SMS provider is configured.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import bolna, sms
from .cases import CaseError, iso, normalize_phone, parse_ts

CHANNELS = ("voice", "sms")
MAX_LEN = 300

# Ready warnings a caseworker can pick, each about a pattern Saathi sees.
TEMPLATES = [
    ("visit_visa", "Visit visa jobs",
     "గల్ఫ్ సాథి హెచ్చరిక: విజిట్ లేదా టూరిస్ట్ వీసా మీద పని ఇస్తామంటే నమ్మకండి. ఉద్యోగానికి ఎంప్లాయ్‌మెంట్ వీసా మాత్రమే."),
    ("fee", "Fee over the legal limit",
     "గల్ఫ్ సాథి హెచ్చరిక: ఏజెంట్‌కు 35,400 రూపాయల కంటే ఎక్కువ ఇవ్వకండి. ప్రతి చెల్లింపుకు రసీదు తీసుకోండి."),
    ("licence", "Unlicensed agents",
     "గల్ఫ్ సాథి హెచ్చరిక: డబ్బు ఇచ్చే ముందు ఏజెంట్ ప్రభుత్వ లైసెన్స్ జాబితాలో ఉన్నాడో సాథికి ఫోన్ చేసి చెక్ చేయండి."),
    ("id_misuse", "ID, SIM and bank card",
     "గల్ఫ్ సాథి హెచ్చరిక: మీ ID, సిమ్, ఫోన్ లేదా బ్యాంక్ కార్డు ఎవరికీ ఇవ్వకండి. మీ పేరుతో లోన్ తీసుకుంటే మీరు జైలుకు వెళ్లవచ్చు."),
    ("routes", "Russia and South-East Asia jobs",
     "గల్ఫ్ సాథి హెచ్చరిక: రష్యా, మయన్మార్, కంబోడియా, లావోస్ ఉద్యోగాల పేరుతో మోసాలు జరుగుతున్నాయి. వెళ్లే ముందు సాథికి చెప్పండి."),
    ("contract", "Contract before paying",
     "గల్ఫ్ సాథి హెచ్చరిక: పూర్తి ఒప్పందం కాగితం చూపించే వరకు ఏజెంట్‌కు డబ్బు ఇవ్వకండి."),
]


def clean_message(text: str) -> str:
    msg = " ".join(str(text or "").split())
    if not msg:
        raise CaseError("write the alert, or pick one")
    if len(msg) > MAX_LEN:
        raise CaseError(f"keep the alert under {MAX_LEN} characters ({len(msg)} now)")
    if re.search(r"\d[\d\s-]{7,}\d", msg):
        raise CaseError("an alert must not contain a phone number: warn about the pattern, never a person")
    return msg


def recipients(workers: list[dict]) -> list[dict]:
    """Every number that agreed to alerts: the worker and the family, once each.
    Never demo cases, never a case where a death was reported."""
    out, seen = [], set()
    for w in workers:
        if w.get("alerts_opt_in") != "yes" or w.get("is_demo") or w.get("death_reported_at"):
            continue
        for who, raw in (("worker", w.get("worker_phone")), ("family", w.get("family_phone"))):
            try:
                phone = normalize_phone(raw) if raw else ""
            except CaseError:
                phone = ""
            if phone and phone not in seen:
                seen.add(phone)
                out.append({"phone": phone, "case_id": w["case_id"], "who": who})
    return out


def suggestions(reports: list[dict], now: datetime) -> list[dict]:
    """What callers reported in the last 7 days, as hints for this week's topic."""
    week = [r for r in reports if not r.get("is_demo") and (parse_ts(r.get("created_at")) or now) >= now - timedelta(days=7)]
    from .config import FEE_CAP_INR
    over = sum(1 for r in week if r.get("amount_asked") and float(r["amount_asked"]) > FEE_CAP_INR)
    visit = sum(1 for r in week if r.get("visa_type") in ("visit", "tourist"))
    hints = []
    if visit:
        hints.append({"template": "visit_visa", "text": f"{visit} caller(s) this week were offered a visit or tourist visa for a job"})
    if over:
        hints.append({"template": "fee", "text": f"{over} caller(s) this week were asked for more than the legal fee"})
    return hints


def send_alert(store, workers: list[dict], message: str, channel: str, now: datetime) -> dict:
    """Send one alert to everyone who opted in, and keep a record of it."""
    if channel not in CHANNELS:
        raise CaseError(f"channel must be one of {', '.join(CHANNELS)}")
    msg = clean_message(message)
    people = recipients(workers)
    if not people:
        raise CaseError("nobody has agreed to receive alerts yet")
    sent = failed = prepared = 0
    for p in people:
        if channel == "sms":
            status = sms.send_sms(p["phone"], msg)
        else:
            res = bolna.place_call(p["phone"], {"call_kind": "alert", "alert_text": msg, "case_id": p["case_id"]})
            status = "sent" if res["ok"] else f"failed: {res['error']}"
        if status == "sent":
            sent += 1
        elif status.startswith("demo"):
            prepared += 1
        else:
            failed += 1
    return store.insert("scam_alerts", {
        "created_at": iso(now), "message": msg, "channel": channel, "recipients": len(people),
        "sent": sent, "prepared": prepared, "failed": failed,
    })
