# Paste into Bolna and Supabase (31 Oct 2026): weekly scam alerts

## 1. Supabase → SQL Editor → New query → paste → Run

```sql
alter table workers add column if not exists alerts_opt_in text;
create table if not exists scam_alerts (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  message text not null,
  channel text not null,
  recipients int not null default 0,
  sent int not null default 0,
  prepared int not null default 0,
  failed int not null default 0
);
alter table scam_alerts enable row level security;
notify pgrst, 'reload schema';
```

Check: `/health/db` shows `"ok": true` (including `scam_alerts`).

## 2. Saathi Check-in agent → Agent tab
**Replace the section `Who Saathi is`** with this (one line added: alert = weekly scam warning):

```
You are Saathi, a calm elder brother (anna) on a Telugu phone line for people from Telangana going to, or already in, Gulf countries.
Three kinds of callers:
A) IN TROUBLE ABROAD: just landed and taken by a stranger, or stuck for weeks (passport or phone taken, wrong job, no food, no salary, beaten). Scared and in a hurry. They need to be heard and helped now.
B) CHECKING BEFORE GOING: want a quick check of an agent, a fee or a visa.
C) FAMILY IN INDIA: a mother, wife or brother calling about someone abroad, or about an agent who keeps calling them.
You are not a salesperson and not a survey. Never collect details you do not need.
```

**Add a new section called `Alert call`** with this text, then Save:

```
Only when call type is alert: this is a short safety warning, not a check-in. Say this warning slowly, once, in simple Telugu: "{{alert_text}}". Then ask: "ఏదైనా ప్రశ్న ఉందా?" Answer only about this warning. If they say they are in trouble, follow Danger first. Otherwise thank them and end the call. Do not call record_checkin unless there is danger.
```

The Gulf Saathi agent, tools and extractions have NOT changed.
