# Gulf Saathi · గల్ఫ్ సాథి

A Telugu phone line that walks with Telangana's Gulf workers at every step: it checks the agent and the fee
before they pay, records what they were promised, calls them on arrival day and every week, and turns trouble
into a ready case file for the people who can act.

Nearly 15 lakh people from Telangana work in Gulf countries ([The Hindu, Mar 2026](https://www.thehindu.com/news/national/telangana/telangana-families-worry-about-gulf-migrant-workers-amid-west-asia-tensions/article70692242.ece)).
Between 2021 and 2025 the state logged 476 complaints against illegal agents and 0 prosecution sanctions
(Lok Sabha USQ 2190, 31 Jul 2026). Today help usually starts after a crisis, from a selfie video.

Live at **[gulf-saathi-psi.vercel.app](https://gulf-saathi-psi.vercel.app)**. Built for the Bolna Buildathon 2026.

## How it works

1. **Before paying:** the worker or family calls in Telugu. Saathi checks the agent against the MEA eMigrate
   licensed list (2,447 agents, 8 Apr 2026) and the fee against the ₹35,400 legal limit.
2. **Before flying:** the promised job, visa, payments, papers and family contact are recorded, and red flags
   show at once.
3. **Arrival day:** Saathi calls: did the registered employer pick you up?
4. **Every week:** salary, passport, food, safety, and is this the job and city you were promised?
5. **When something is wrong:** the case is flagged, a Telugu message for the family is ready, and a caseworker
   gets an English case file for MADAD, the Indian Embassy or Pravasi Prajavani.

## What makes it different

- **Repeat-agent warning:** the same agent number or payment account across cases warns the next family before
  they pay.
- **Case file from the first call:** officials don't spend weeks collecting the employer, visa, agent and route.
- **Proof of work:** a dated record of every call, against a false absconding report.
- **When a worker dies abroad:** the facts the embassy needs and the family's papers for the state ex-gratia,
  in Telugu and English.
- **Weekly scam alerts** to workers and families who sign up.
- **Family callers:** a mother or wife can raise a case without travelling to Hyderabad.

## Built with

Bolna voice agents (Telugu speech by Sarvam) · Python FastAPI on Vercel · Supabase.

## Status

- Working on real Bolna calls: agent and fee checks, the help line, arrival and weekly check-in calls, the
  repeat-agent warning.
- Next: SMS provider, a native Telugu review of all wording, and a family pilot in Jagtial district.

## Run it locally

```
pip install -r requirements-dev.txt
python -m pytest
GS_DASHBOARD_PASSWORD=test uvicorn gulf_saathi.api:app --port 8000
```

Database setup: run `supabase/schema.sql` in the Supabase SQL editor. Without Supabase settings the server keeps
data in memory.

`data/licensed_agents.csv` comes from the MEA eMigrate active recruiting-agent list (8 Apr 2026).
