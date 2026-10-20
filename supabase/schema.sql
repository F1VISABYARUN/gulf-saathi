-- Gulf Saathi database. Paste this whole file into Supabase > SQL Editor > New query > Run.
-- Safe to run again: it only creates what is missing.

create extension if not exists pgcrypto;

-- One row per worker: the pre-departure trail.
create table if not exists workers (
  id uuid primary key default gen_random_uuid(),
  case_id text unique not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  worker_name text not null,
  worker_name_te text,            -- name in Telugu script, used in the family SMS
  worker_phone text not null,
  family_name text,
  family_phone text,
  family_relation text,

  employer_name text,
  employer_phone text,
  sponsor_name text,              -- kafeel
  sponsor_id text,
  dest_country text,
  dest_city text,
  job_title text,
  contract_salary numeric,
  salary_currency text,

  agent_name text,
  agent_owner text,
  agent_licence text,
  agent_district text,
  agent_check text,               -- confirmed_in_list / needs_confirmation / not_found / need_more_info
  agent_check_detail jsonb not null default '{}',
  payments jsonb not null default '[]',
  amount_paid_total numeric,
  fee_status text,                -- within_cap / over_cap / no_amount

  departure_date date,
  flight_no text,
  arrival_call_at timestamptz,
  code_phrase text,

  status text not null default 'registered',   -- registered / abroad / closed
  risk_level text not null default 'ok',       -- ok / medium / high / critical
  risk_reasons jsonb not null default '[]',
  missed_checkins int not null default 0,
  last_contact_at timestamptz,
  next_call_at timestamptz,
  notes text
);

-- Every Bolna call, keyed by Bolna's execution id. Updated by the webhook.
create table if not exists calls (
  id text primary key,
  worker_id uuid references workers(id) on delete set null,
  kind text,                      -- arrival / weekly / manual / other
  status text,
  answered boolean,
  missed boolean,
  duration_seconds numeric,
  transcript text,
  recording_url text,
  extracted jsonb not null default '{}',
  scheduled_at timestamptz,
  processed_at timestamptz,
  raw jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Answers the voice agent recorded during a check-in call (record_checkin tool).
create table if not exists checkins (
  id uuid primary key default gen_random_uuid(),
  worker_id uuid not null references workers(id) on delete cascade,
  kind text,
  answers jsonb not null default '{}',
  risk_level text,
  risk_reasons jsonb not null default '[]',
  created_at timestamptz not null default now()
);

-- HIGH / CRITICAL alerts, with the Telugu SMS sent to the family.
create table if not exists escalations (
  id uuid primary key default gen_random_uuid(),
  worker_id uuid not null references workers(id) on delete cascade,
  level text not null,
  reasons jsonb not null default '[]',
  family_sms text,
  sms_status text,
  status text not null default 'open',          -- open / resolved
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index if not exists calls_worker_idx on calls (worker_id, created_at desc);
create index if not exists checkins_worker_idx on checkins (worker_id, created_at desc);
create index if not exists escalations_worker_idx on escalations (worker_id, created_at desc);

-- Row level security on, with no policies: the public (publishable/anon) key can
-- read nothing. Only the server's secret key, kept in Vercel, can read and write.
alter table workers enable row level security;
alter table calls enable row level security;
alter table checkins enable row level security;
alter table escalations enable row level security;

-- Added October 2026: promise vs reality, repeated-risk signals, help calls,
-- family welcome SMS and demo cases. Safe to run again.
alter table workers add column if not exists visa_job text;            -- job written on the visa (typed by a helper)
alter table workers add column if not exists visa_type text;           -- employment / visit / tourist / unknown
alter table workers add column if not exists sub_agent_name text;      -- village sub-agent
alter table workers add column if not exists sub_agent_phone text;
alter table workers add column if not exists payment_to text;          -- UPI ID / account / number money went to
alter table workers add column if not exists welcome_sms text;
alter table workers add column if not exists welcome_sms_status text;
alter table workers add column if not exists source text;              -- dashboard / help_call / demo
alter table workers add column if not exists is_demo boolean not null default false;
