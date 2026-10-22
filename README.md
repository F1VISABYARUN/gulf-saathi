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
                                    ──▶ /tools/report-problem            (Gulf Saathi agent, help line)
                                    ──▶ /tools/record-checkin            (Saathi Check-in agent)
               Bolna, after each call ──▶ /webhooks/bolna
Anyone ──────────────── browser ──────▶ /  (home page, "Get a call from Saathi")
Caseworker ─────────── browser ──────▶ /dashboard, /demo
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
| Promise vs reality (`promise.py`) | Before flying: agent not in list, fee over the limit, visit or tourist visa, visa job different from the promised job. After arrival: the work and city the worker describes vs what was promised. Fixed word lists decide "same kind of work"; the AI only writes down what was said. |
| Saathi Intelligence (`signals.py`) | The same sub-agent phone, payment account, sponsor ID or employer phone in 2+ cases (strong), or the same employer name in the same country (weak): "seen in N cases, needs human review", with the agent districts involved. Person names are never matched. **Live on the call** (`/check-contact`): before paying, a worker can check an agent's phone or UPI ID and hears only a count ("came up in 3 cases, 2 reported serious problems"), never names; demo cases never feed it. A link is a lead for investigators, not a finding of fraud. |
| Help line (`cases.report_problem`) | A worker abroad calls the Gulf Saathi number with a problem: finds or opens their case, keeps trace details (name, home district, agent, nearby place) and applies the same rules and alerts. Safety net: after the call, Bolna's `help_check` extraction opens or updates the case even if the live voice AI never called the tool. |
| Agent numbers heard on calls (`signals.record_contact`) | Every agent phone or payment account a worker or family tells Saathi is saved with what the agent asked for, so patterns grow from every call, not only registered cases. Counted once per caller. Saathi reads the number back digit by digit before checking. Who owns a number can only be found by the telecom company or police. |
| Family callers and Pravasi Prajavani (`cases.report_problem`, `prajavani_petition`) | A mother or wife can call about someone abroad: the case is opened with them as the family contact. Each case has a printable Telugu + English Pravasi Prajavani petition and a status (prepared / submitted / acknowledged / closed) that callers hear when they call again, so families don't have to travel to Hyderabad. A person hands it in; Saathi does not submit it. |
| Women going for housework (`promise.py`) | A woman going as a housemaid on a visit or tourist visa is stopped before she flies (the route MEA has warned agents use to get past emigration checks). Also flags: under 30 (with an ECR passport India gives no emigration clearance for Gulf jobs) and "only a state government agency may send her". Abroad, one missed call is HIGH for her, not MEDIUM, and "moved or sold to another house or employer" is HIGH for anyone. Rules from MEA guidelines; check them before relying on them. |
| When a worker dies abroad (`cases.report_death`, `death_packet`) | A family caller says the worker died, or a caseworker records it: Saathi stops calling the number, opens a CRITICAL alert with a ready message for the embassy (next of kin, employer, sponsor), and never tells the family by SMS. Printable Telugu + English papers: the facts the embassy needs, the steps (NOC is the embassy's own form; ICWF if the employer won't pay; Telangana's Rs 5 lakh ex-gratia under G.O. 216, from news reports), and status tracking. The case list search answers "whose family is this?" for an embassy or volunteer. |
| Family welcome SMS | One Telugu SMS to the family at registration, with the case number. |
| Case packet (`cases.py`) | English summary with the whole timeline, recordings and the latest transcript, for a person to file. |
| Dashboard (`dashboard.py`) | Password-protected case list with risk badges, case page with timeline, promise-vs-reality table, "Call now", packet download, "Mark resolved". |
| Website (`site.py`, `demo.py`) | Public home page with totals only; "Get a call from Saathi" (needs `GS_DEMO_CODE`); a password-protected demo story that creates made-up cases marked DEMO, with no real call or SMS. |

## Setup

1. **Supabase:** SQL Editor → paste [`supabase/schema.sql`](supabase/schema.sql) → Run.
2. **Bolna and Vercel:** follow [`docs/BOLNA_SETUP.md`](docs/BOLNA_SETUP.md).
3. **Check:** `/health` and `/health/db` show `"ok": true`, and `/dashboard` opens after the password.

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

- **Policy figures:** the Rs 35,400 fee cap is Rs 30,000 + 18% GST (Emigration (Amendment) Rules 2017, MEA advisories); older pages still show the 2009 Rs 20,000 rule. The PBBY and ex gratia figures in the Rules PDF still need checking against official sources.
- **Bolna call API:** placing calls (`POST /call`) is written from Hark's notes on Bolna's docs and hasn't been tried against the live API yet.
- **Family SMS:** demo mode until Plivo and DLT registration are set up.
- **Filing:** MADAD has no public API that we know of. The case packet is filed by a person.
- **Privacy:** the database holds workers' and families' phone numbers and call recordings. Get consent at registration and keep the dashboard password and Supabase secret key private.
- **Demo calls:** a Bolna trial account may only call numbers verified in that account. Calls to Gulf numbers are untested.
- **Job matching:** the word lists in `promise.py` cover common jobs only. Unrecognised work never raises a flag, so some mismatches will be missed.
- **Language:** the Telugu wording (prompts, SMS) is machine-drafted and needs a native speaker's review.
