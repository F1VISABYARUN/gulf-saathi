# Gulf Saathi

A Telugu, Hindi and Urdu phone line for Telangana's Gulf migrant workers: check an
agent before paying, check a job offer for red flags, get a weekly safety call
once abroad, and get help with the death ex gratia and PBBY insurance claims.
No app and no reading.

## What the line does

| Key | Flow | What happens |
|-----|------|--------------|
| 1 | **Is this agent real?** | Caller says the agency name or licence number. It's fuzzy-matched (Telugu, Devanagari, Urdu or English) against the licensed and flagged lists. Reply: licensed (with the fee cap), **flagged (warning)**, or not found (unlicensed recruitment is illegal). Then an ECR and visit-visa warning. Unclear matches are confirmed ("Did you say…?"). Every lookup is logged. |
| 2 | **Offer check** | Five yes/no questions (contract, visa type, fee, country, passport). Answers are read back as red flags. |
| 3 | **Weekly check-in** | Registers the caller's country and a family number. A weekly outbound call asks "Got paid? Have your passport? Safe?" A "no", or 2 missed or abandoned calls, opens a case and SMSes the family. |
| 4 | **Family help** | Explains the ex gratia and PBBY, and queues a callback from a caseworker. |

Every menu also accepts spoken answers ("ఒకటి", "అవును", "हाँ", "نہیں"…), and the
language can be picked by speaking in it.

`POST /offer/analyze` runs the same red-flag checks on forwarded text (e.g. a
WhatsApp offer). It catches visit visas, Russia and Europe jobs, fees over the
cap, passport deposits, GPay or cash payments and "today only" pressure.

## Run it

```bash
pip install -r requirements.txt
python -m pytest                      # 25 tests
python -m gulf_saathi.simulate        # talk to the line in a terminal
python -m gulf_saathi.simulate --checkin --lang te
```

In the simulator, type digits to press keys and any other text to "speak".

### Live phone demo (Twilio)

```bash
export TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... TWILIO_FROM_NUMBER=+1...
export GS_PUBLIC_BASE_URL=https://<your-ngrok>.ngrok.app GS_ADMIN_TOKEN=<random>
uvicorn gulf_saathi.app:app --port 8000
ngrok http 8000
```

Set the Twilio number's "A call comes in" webhook to `POST {GS_PUBLIC_BASE_URL}/voice`.
Set `GS_VALIDATE_TWILIO=1` to reject requests not signed by Twilio.

**Demo script:** call → press 1 (Telugu) → press 1 → say "Golconda Overseas" →
you hear "జాగ్రత్త! గోల్కొండ ఓవర్సీస్ ప్రభుత్వ జాబితాలో అక్రమ ఏజెంట్‌గా…"

Caseworker endpoints (send header `X-Admin-Token`): `GET /admin/escalations`,
`/admin/callbacks`, `/admin/lookups`, and `POST /admin/run-checkins`. Run that
last one from cron, daily, to place the weekly calls that are due.

## Agent data

`data/agents_sample.csv` is **fictional demo data**. Every name contains "Demo" so
no real business is labelled illegal. To use the real lists:

1. Save eMigrate's licensed-agent list page and illegal-agent list page as HTML.
2. `python scripts/import_agents.py --licensed lic.html --flagged flagged.html -o data/agents.csv`
3. Review the output by hand, add Telugu, Hindi and Urdu spellings to `aliases`
   (pipe-separated), and set `GS_AGENTS_CSV=data/agents.csv`.

Adding aliases matters most for Urdu: that script isn't transliterated, so Urdu
names only match through aliases.

## Before this goes in front of real workers

**Facts to verify.** These are configurable in `gulf_saathi/config.py`; I
couldn't confirm them against primary sources:
- Max recruitment service charge (default ₹30,000), from the Emigration Rules on emigrate.gov.in.
- ₹5 lakh ex gratia and its document list (TOMCOM / Telangana NRI dept). The document list in the prompts is generic.
- PBBY cover (default ₹10 lakh) and who it is mandatory for.

**Language.** The prompts in `gulf_saathi/prompts.py` are machine-drafted. Get
native speakers to review them. Better still, record them in a familiar local
voice and swap `<Say>` for `<Play>`; that also helps with trust.

**Telephony.**
- Twilio is used here for the demo. For Indian numbers, look at Indian providers such as Exotel or Plivo.
- I'm not sure which voices and speech locales Twilio currently supports for Telugu and Urdu. Override them with `GS_VOICE_*` if a call errors.
- Commercial SMS in India requires DLT registration.

**Cost to the worker.** Consider a missed-call model: the worker gives a missed call and the line calls back. Callers from labour camps shouldn't pay for international minutes.

**MADAD.** As far as I know it has no public API, so escalations go to a caseworker queue. A person files the MADAD grievance.

**Privacy.** The database holds workers' and families' phone numbers. Run it under India's DPDP Act obligations, get consent at registration, and keep the admin token secret.

**Scaling.** Sessions are in memory, so this runs on one server process. Move them to Redis to run more than one.

## Layout

```
gulf_saathi/
  engine.py    call flow state machine (no telephony code, fully testable)
  app.py       FastAPI: Twilio webhooks, /offer/analyze, /agents/lookup, admin
  agents.py    fuzzy, multi-script agent matching
  offer.py     red-flag rules for IVR answers and free text
  checkin.py   weekly calls, missed-call tracking, escalation
  prompts.py   all spoken text in te / hi / ur
  store.py     SQLite
  simulate.py  terminal simulator
scripts/import_agents.py   eMigrate HTML -> agents.csv
```
