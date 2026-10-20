# Gulf Saathi

A Telugu voice safety line and case system for Telangana's Gulf migrant workers.
Workers check an agent before paying. Once they fly, Saathi calls them on arrival
day and every week. When something goes wrong, the family hears about it in Telugu
and a caseworker gets an English case packet for MADAD, TOMCOM or the embassy.

Voice and phone calls run on [Bolna](https://www.bolna.ai). This repo is the server
behind them, deployed on Vercel with a Supabase database.

## How it fits together

```
Worker's phone ── Bolna voice agent ──▶ /check-agent, /check-fee        (Gulf Saathi agent)
                                    ──▶ /tools/record-checkin            (Saathi Check-in agent)
               Bolna, after each call ──▶ /webhooks/bolna
Caseworker ─────────── browser ──────▶ /dashboard
Server ─────── Bolna API (POST /call) ──▶ arrival and weekly calls
All data ─────────────────────────────▶ Supabase
```

| Piece | What it does |
|---|---|
| Agent check (`matcher.py`) | Matches a spoken agency, owner, district or licence number, in Telugu or English, against the 2,447 MEA-licensed agents. Answers `confirmed_in_list`, `needs_confirmation`, `not_found` or `need_more_info`. Never endorses an agent. |
| Fee check (`fees.py`) | Adds every payment to the agent and compares with Rs 30,000 + 18% GST = Rs 35,400. |
| Worker case (`cases.py`) | Pre-departure trail: employer, sponsor, destination, salary, agent, payments, family. Case ID like `GS-7K3P9Q`. |
| Calls (`cases.py`, `bolna.py`) | Books the arrival-day call, then a weekly call. A missed call is retried (3 hours for arrival, 24 hours for weekly). "Completed" counts as missed unless the worker actually spoke. |
| Risk and alerts (`cases.py`, `sms.py`) | CRITICAL: wrong person or nobody at the airport, threats, not allowed out, asked for help, danger code phrase. HIGH: passport taken, 2+ months unpaid, 2 missed calls in a row. MEDIUM: 1 month unpaid, food or room problems, 1 missed call. HIGH and CRITICAL text the family in Telugu, once per open alert. |
| Case packet (`cases.py`) | English summary with the whole timeline, recordings and the latest transcript, for a person to file. |
| Dashboard (`dashboard.py`) | Password-protected case list with risk badges, case page with timeline, "Call now", packet download, "Mark resolved". |

## Setup

1. **Supabase:** SQL Editor → paste [`supabase/schema.sql`](supabase/schema.sql) → Run.
2. **Bolna and Vercel:** follow [`docs/BOLNA_SETUP.md`](docs/BOLNA_SETUP.md).
3. **Check:** `/health/db` shows `"ok": true`, and `/dashboard` opens after the password.

## Run locally

```bash
pip install -r requirements-dev.txt
python -m pytest                                   # all tests
GS_DASHBOARD_PASSWORD=test uvicorn gulf_saathi.api:app --port 8000
```

Without Supabase settings the server keeps data in memory. Without Bolna settings
"Call now" says Bolna isn't configured. Without Plivo the family SMS is shown on the
dashboard but not sent.

Try the agent and fee checks from the command line:

```bash
python -m gulf_saathi.matcher --owner "Seedi Kavitha"
python -m gulf_saathi.matcher "చెల్లా మల్లేశం జగిత్యాల్"
```

## Data

`data/licensed_agents.csv` comes from the MEA / eMigrate active recruiting-agent list
(as on 08-04-2026). Regenerate it from the PDF with `scripts/agents_pdf_to_csv.py`.

## Not done, or not verified

- **Policy figures:** the Rs 35,400 fee cap and the PBBY and ex gratia figures must be checked against official sources before any public claim (marked VERIFY in `config.py`).
- **Bolna call API:** placing calls (`POST /call`) is written from Hark's notes on Bolna's docs and hasn't been tried against the live API yet.
- **Family SMS:** demo mode until Plivo and DLT registration are set up.
- **Filing:** MADAD has no public API that we know of. The case packet is filed by a person.
- **Privacy:** the database holds workers' and families' phone numbers and call recordings. Get consent at registration and keep the dashboard password and Supabase secret key private.
- **Language:** the Telugu wording (prompts, SMS) is machine-drafted and needs a native speaker's review.
