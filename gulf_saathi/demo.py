"""The demo story for judges: made-up cases, marked is_demo, that walk through
what Saathi catches. No real call or SMS is made for them.

Yadaiah was promised a cleaner's job; the visa says agricultural worker; on
arrival day he says he is herding goats far from the city. (Inspired by
Aadujeevitham.) A second made-up worker paid the same village sub-agent, so a
repeated-risk signal appears.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from .cases import record_checkin, register_worker
from .matcher import LicensedList

DEMO_NOTE = "DEMO CASE: made-up person for the demo story. No real call or SMS was made."


def _sub_agent_phone() -> str:
    # A fresh number each run, so each run's two cases form their own signal.
    return "+9190000" + "".join(secrets.choice("0123456789") for _ in range(5))


def run_demo(store, licensed: LicensedList, now: datetime) -> dict:
    sub_phone = _sub_agent_phone()
    upi = f"demo.subagent{sub_phone[-4:]}@upi"
    yadaiah = register_worker(store, licensed, {
        "worker_name": "Yadaiah (demo)", "worker_name_te": "యాదయ్య", "worker_phone": "+919000000001",
        "family_name": "Lakshmi", "family_relation": "wife", "family_phone": "+919000000002",
        "employer_name": "Demo Cleaning Co. (made up)",
        "dest_country": "Saudi Arabia", "dest_city": "Riyadh", "job_title": "Cleaner",
        "contract_salary": "1500", "salary_currency": "SAR",
        "visa_type": "employment", "visa_job": "Agricultural worker",
        "agent_name": "Demo Agency (made up)", "agent_district": "Nizamabad",
        "sub_agent_name": "Village agent (demo)", "sub_agent_phone": sub_phone,
        "payments": "50000; 40000", "payment_to": upi, "notes": DEMO_NOTE,
    }, now, is_demo=True)["worker"]

    ramesh = register_worker(store, licensed, {
        "worker_name": "Ramesh (demo)", "worker_name_te": "రమేష్", "worker_phone": "+919000000003",
        "family_phone": "+919000000004", "dest_country": "Saudi Arabia", "dest_city": "Dammam",
        "job_title": "Driver", "visa_type": "visit", "agent_name": "Demo Agency (made up)",
        "agent_district": "Nizamabad", "sub_agent_phone": sub_phone, "payments": "60000; 30000",
        "payment_to": upi, "notes": DEMO_NOTE,
    }, now, is_demo=True)["worker"]

    # What the arrival-day call would record. Simulated: no call is placed.
    arrival = record_checkin(store, {
        "case_id": yadaiah["case_id"], "call_kind": "arrival",
        "pickup_status": "other_person", "pickup_person": "a man who said he was the sponsor's driver",
        "current_location": "a goat farm in the desert", "current_job": "herding goats",
        "current_city": "Al Kharj", "passport_with_worker": "no",
        "notes": "Simulated arrival call for the demo.",
    }, now)
    return {"yadaiah": yadaiah["case_id"], "ramesh": ramesh["case_id"], "arrival": arrival}
