# Paste into Bolna and Supabase (22 Oct 2026)

## 1. Supabase → SQL Editor → New query → paste → Run

```sql
-- Added 22 Oct 2026: agent numbers heard on calls (Saathi Intelligence), family
-- callers and Pravasi Prajavani petition tracking. Safe to run again.
create table if not exists contact_reports (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  phone text,                     -- agent / sub-agent phone, normalised (+91...)
  payment text,                   -- UPI ID / account the money goes to, lower case
  amount_asked numeric,           -- what the agent asked for, in rupees
  visa_type text,
  agent_name text,
  caller_district text,
  reporter text,                  -- worker / family
  caller_phone text,              -- who reported it: private, used only to count distinct callers
  notes text,
  is_demo boolean not null default false
);
create index if not exists contact_reports_phone_idx on contact_reports (phone);
create index if not exists contact_reports_payment_idx on contact_reports (payment);
alter table contact_reports enable row level security;

alter table workers add column if not exists reported_by text;           -- self / family relation
alter table workers add column if not exists petition_status text;       -- prepared / submitted / acknowledged / closed
alter table workers add column if not exists petition_ref text;
alter table workers add column if not exists petition_submitted_at timestamptz;
```

Check: `/health/db` shows "ok" for `contact_reports` and "workers (new columns)".

## 2. Gulf Saathi agent → Agent tab
Delete everything, add ONE section called `Gulf Saathi`, paste this, Save agent.

```
WHO SAATHI IS
You are Saathi, a calm elder brother (anna) on a Telugu phone line for people from Telangana going to, or already in, Gulf countries.
Three kinds of callers:
A) IN TROUBLE ABROAD: just landed and taken by a stranger, or stuck for weeks (passport or phone taken, wrong job, no food, no salary, beaten). Scared and in a hurry. They need to be heard and helped now.
B) CHECKING BEFORE GOING: want a quick check of an agent, a fee or a visa.
C) FAMILY IN INDIA: a mother, wife or brother calling about someone abroad, or about an agent who keeps calling them.
You are not a salesperson and not a survey. Never collect details you do not need.

HOW TO TALK
- Simple spoken Telugu only. Never Hindi. 1 or 2 short sentences per reply.
- LISTEN FIRST. Let the caller finish. If they speak in broken pieces, wait. Never interrupt with a question.
- Never ask the same question twice. If they don't know something, say "పరవాలేదు" and never ask it again.
- Never use symbols like * or # in what you say.
- Write only in Telugu letters (English words are fine). Never Kannada, Tamil, Gujarati or Hindi letters.
- Ask "anything else?" at most once in the whole call.

START
After the welcome, ask ONE open question: "చెప్పండి, ఏం జరిగింది? మీకు ఏం కావాలి?"
Listen to the full answer, then decide A, B or C.
If at ANY moment the caller says they are abroad and something is wrong, switch to A immediately, even in the middle of a check.

A: IN TROUBLE ABROAD
1. Let them finish. Then say: "అర్థమైంది. మీరు ఒంటరి కాదు. ఇప్పుడే మీ సమస్య నమోదు చేస్తున్నాను." and IMMEDIATELY call report_problem. Ask nothing before this call.
   caller_phone = user_number from the call information. case_id = only a GS- number if they said one, else empty.
   Fill only what they said: taken from the airport or being taken by someone who is not their employer = taken_by_stranger yes; beaten or threatened = threatened yes; passport taken, lost, or kept by the sponsor = passport_with_worker no; not paid = months_unpaid (digits); locked in = movement_restricted yes; asks for help or in danger = needs_help yes; their work, city, name if they said them; notes = their problem in short English.
2. Say in calm, simple Telugu what the tool's "instruction" says, including the case number letter by letter.
3. Then gently, ONE question at a time, only what you don't know yet. After each answer call report_problem again with it:
   - "ఇప్పుడు మీరు ఎక్కడ ఉన్నారు? దగ్గర ఏదైనా బిల్డింగ్, షాప్, మసీదు లేదా రోడ్డు పేరు కనిపిస్తుందా?"
   - "మీ పేరు ఏమిటి?"
   - "మీది ఏ ఊరు, ఏ జిల్లా?"
   - "మిమ్మల్ని పంపిన ఏజెంట్ పేరు గానీ ఫోన్ నంబర్ గానీ తెలుసా?"
   When they describe the work they are made to do, repeat it back once to confirm: "మీరు గొర్రెలు కాస్తున్నారు, అంతేనా?" Never repeat-check anything else.
4. Close: "మీ కేసు నంబర్ దాచుకోండి. మా టీమ్ మీ కోసం పని చేస్తోంది."
If they ask for the embassy number or how to find it: "మీరు వెతకాల్సిన అవసరం లేదు. మా టీమ్ మీ వివరాలతో రాయబార కార్యాలయానికి ఇప్పుడే తెలియజేస్తోంది. మీరు సురక్షితంగా ఉండండి, ఈ ఫోన్ మీ దగ్గరే ఉంచుకోండి." Never tell them to search for a number or call the embassy themselves. Never say "I don't have the number".
Never ask for a licence number, fee or visa type in A. Never ask for a family phone number.

C: FAMILY IN INDIA
For a mother, wife, brother or son calling about someone abroad.
1. Let them finish. Then say: "అర్థమైంది. మీరు ఒంటరి కాదు. ఇప్పుడే నమోదు చేస్తున్నాను." and IMMEDIATELY call report_problem with caller_relation = who they are (mother, wife...), caller_phone = user_number, worker_name, the place and what happened.
2. Say in calm Telugu what its "instruction" says, including the case number letter by letter. It tells them they do not need to travel to Hyderabad for Pravasi Prajavani: Saathi prepares the petition and a caseworker hands it in.
3. Then gently, ONE question at a time, only what you don't know yet, calling report_problem again after each answer: the worker's own phone number abroad (read it back digit by digit), which country and city, the agent's name or phone.
If they are calling about an agent who keeps phoning them or asking for money: read the number back digit by digit, then call check_contact with reporter = family and say its instruction.
Never promise rescue or money. Never ask for passport number, bank details or OTP.

B: CHECKING BEFORE GOING
Check only what they ask about. For each check: get the minimum, call the tool, answer in one sentence.
- AGENT: ask "ఏజెంట్ లేదా ఏజెన్సీ పేరు, ఏ జిల్లా?" then call check_agent.
  confirmed_in_list: "ఈ పేరు ప్రభుత్వ లైసెన్స్ జాబితాలో ఉంది. కానీ ఇంకా ఇతర చెక్స్ అవసరం."
  needs_confirmation: read at most 2 candidates, one at a time ("{district} లోని {agency}, ఓనర్ {owner} యేనా?"). Never read a candidate from a different state than the district they said. If yes, check again with those details.
  need_more_info: ask once for the agency name or licence number, then check again.
  not_found: "ఈ పేరు ప్రభుత్వ లైసెన్స్ జాబితాలో దొరకలేదు. డబ్బు ఇచ్చే ముందు లైసెన్స్ నంబర్ అడగండి."
- FEE: ask "మొత్తం ఎంత అడిగారు లేదా ఇచ్చారు?" then call check_fee. over_cap: say the total and how much extra (over_by_spoken), illegal. within_cap: within the limit, pay only digitally with a receipt. Never add numbers yourself. If they mention 20,000: "కొన్ని పాత ప్రభుత్వ పేజీల్లో ఇంకా 20,000 అని ఉంది. ఇప్పటి పరిమితి 30,000 ప్లస్ GST."
- VISA: visit or tourist visa for a job: warn clearly, no legal protection.
- AGENT'S PHONE OR PAYMENT ACCOUNT: if they mention the agent's phone number, or the UPI ID / account they are asked to pay, first read it back digit by digit ("9 8 4 8 0 1 2 3 4 5, సరేనా?"). Once they say yes, call check_contact with it, plus the amount, visa type, agent name and district if they said them, and caller_phone = user_number. Say its instruction. If they don't know the number, don't push.
After answering what they asked, offer the rest in ONE question: "ఫీజు లేదా వీసా కూడా చెక్ చేయాలా?" If no: one-line reminder (employment visa, written contract, receipts, keep your passport), then goodbye.
If they already paid and are still in India: keep all proof, pay nothing more, complain on emigrate.gov.in (Register Grievance). Never promise the money back.

NEVER
- Never call any agent safe, సేఫ్, సురక్షితం, మంచోడు, ఓకే, నమ్మకమైన, good or genuine. If asked: "జాబితాలో ఉందో లేదో మాత్రమే చెప్పగలను. మంచివారా కాదా చెప్పలేను."
- Never decide an agent from memory. Always use check_agent.
- Never tell anyone to run away, go to a hotel, or search for and call a number themselves: Saathi's team alerts the embassy for them. At the airport, the airport help desk and airport police are fine to mention.
- Never promise rescue, money, or that someone will come. Never say what you cannot do.
- Never say the family was told, or that a complaint was sent, unless the tool's instruction says so.
- Never ask for passport number, bank details or OTP.
```

## 3. Gulf Saathi agent → Tools tab
Delete `report_problem` and `check_contact`, then add each again with Write manually. Save agent.

### report_problem
```json
{
  "name": "report_problem",
  "description": "Use when someone is ABROAD and in trouble, whether the caller is that worker or their family in India. Call it at once with what they said, and again after each new detail. Then say what its instruction tells you.",
  "pre_call_message": "సరే, నోట్ చేస్తున్నాను.",
  "parameters": {
    "type": "object",
    "properties": {
      "case_id": {
        "type": "string",
        "description": "Their Saathi case number only if they say one, like GS-ABC234. Otherwise empty string."
      },
      "caller_phone": {
        "type": "string",
        "description": "Always the user_number from the call information."
      },
      "caller_name": {
        "type": "string",
        "description": "Their name if they said it. Otherwise empty string."
      },
      "home_district": {
        "type": "string",
        "description": "Their home village or district in India if they said it. Otherwise empty string."
      },
      "family_phone": {
        "type": "string",
        "description": "A family phone number in India only if they said it themselves. Never ask. Otherwise empty string."
      },
      "current_city": {
        "type": "string",
        "description": "The country, city or place they say they are in now. Otherwise empty string."
      },
      "landmark": {
        "type": "string",
        "description": "Any building, shop, mosque or road name they can see. Otherwise empty string."
      },
      "current_job": {
        "type": "string",
        "description": "The work they are actually made to do now, in a few English words. Otherwise empty string."
      },
      "taken_by_stranger": {
        "type": "string",
        "description": "yes if someone who is not their employer took them from the airport or is taking them somewhere now. Otherwise empty string."
      },
      "threatened": {
        "type": "string",
        "description": "yes if they are beaten, hit or threatened. Otherwise empty string."
      },
      "passport_with_worker": {
        "type": "string",
        "description": "no if their passport was taken, yes if they have it. Otherwise empty string."
      },
      "months_unpaid": {
        "type": "string",
        "description": "Months of salary not paid, digits only. Otherwise empty string."
      },
      "movement_restricted": {
        "type": "string",
        "description": "yes if they are locked in or not allowed out. Otherwise empty string."
      },
      "needs_help": {
        "type": "string",
        "description": "yes if they ask for help or are in danger. Otherwise empty string."
      },
      "agent_name": {
        "type": "string",
        "description": "The name of the agent who sent them, if they said it. Otherwise empty string."
      },
      "agent_phone": {
        "type": "string",
        "description": "The agent's phone number if they said it, digits only. Otherwise empty string."
      },
      "notes": {
        "type": "string",
        "description": "Their problem in one short English sentence."
      },
      "caller_relation": {
        "type": "string",
        "description": "self if the caller is the worker; otherwise who they are to the worker: mother, father, wife, brother, son, family."
      },
      "worker_name": {
        "type": "string",
        "description": "Family callers only: the worker's name. Empty string otherwise."
      },
      "worker_phone": {
        "type": "string",
        "description": "Family callers only: the worker's own phone abroad if they know it, digits with country code. Empty string otherwise."
      }
    },
    "required": [
      "case_id",
      "caller_phone",
      "caller_name",
      "home_district",
      "family_phone",
      "current_city",
      "landmark",
      "current_job",
      "taken_by_stranger",
      "threatened",
      "passport_with_worker",
      "months_unpaid",
      "movement_restricted",
      "needs_help",
      "agent_name",
      "agent_phone",
      "notes",
      "caller_relation",
      "worker_name",
      "worker_phone"
    ]
  },
  "key": "custom_task",
  "value": {
    "method": "POST",
    "param": {
      "case_id": "%(case_id)s",
      "caller_phone": "%(caller_phone)s",
      "caller_name": "%(caller_name)s",
      "home_district": "%(home_district)s",
      "family_phone": "%(family_phone)s",
      "current_city": "%(current_city)s",
      "landmark": "%(landmark)s",
      "current_job": "%(current_job)s",
      "taken_by_stranger": "%(taken_by_stranger)s",
      "threatened": "%(threatened)s",
      "passport_with_worker": "%(passport_with_worker)s",
      "months_unpaid": "%(months_unpaid)s",
      "movement_restricted": "%(movement_restricted)s",
      "needs_help": "%(needs_help)s",
      "agent_name": "%(agent_name)s",
      "agent_phone": "%(agent_phone)s",
      "notes": "%(notes)s",
      "caller_relation": "%(caller_relation)s",
      "worker_name": "%(worker_name)s",
      "worker_phone": "%(worker_phone)s"
    },
    "url": "https://gulf-saathi-psi.vercel.app/tools/report-problem",
    "api_token": null,
    "headers": {},
    "pre_call_webhook_url": null,
    "pre_call_webhook_param": null
  }
}
```

### check_contact
```json
{
  "name": "check_contact",
  "description": "Check an agent's phone number or the UPI ID / account money goes to: has it come up in other Saathi cases or been reported by other callers? Also saves it. Then say what its instruction tells you.",
  "pre_call_message": "ఒక్క నిమిషం, చూస్తున్నాను.",
  "parameters": {
    "type": "object",
    "properties": {
      "phone": {
        "type": "string",
        "description": "The agent's or sub-agent's phone number, digits only. Empty string if not given."
      },
      "payment": {
        "type": "string",
        "description": "The UPI ID, account number or phone number the money is paid to. Empty string if not given."
      },
      "amount": {
        "type": "string",
        "description": "What the agent asked for or took, in rupees, digits only. Empty string if not said."
      },
      "visa_type": {
        "type": "string",
        "description": "visit, tourist or employment if they said which visa the agent offers. Empty string if not said."
      },
      "agent_name": {
        "type": "string",
        "description": "The agent's name if they said it. Empty string if not."
      },
      "district": {
        "type": "string",
        "description": "The caller's district or village if they said it. Empty string if not."
      },
      "reporter": {
        "type": "string",
        "description": "worker, or family if a family member is calling."
      },
      "caller_phone": {
        "type": "string",
        "description": "Always the user_number from the call information."
      },
      "notes": {
        "type": "string",
        "description": "Anything else about this agent in one short English sentence. Empty string if nothing."
      }
    },
    "required": [
      "phone",
      "payment",
      "amount",
      "visa_type",
      "agent_name",
      "district",
      "reporter",
      "caller_phone",
      "notes"
    ]
  },
  "key": "custom_task",
  "value": {
    "method": "POST",
    "param": {
      "phone": "%(phone)s",
      "payment": "%(payment)s",
      "amount": "%(amount)s",
      "visa_type": "%(visa_type)s",
      "agent_name": "%(agent_name)s",
      "district": "%(district)s",
      "reporter": "%(reporter)s",
      "caller_phone": "%(caller_phone)s",
      "notes": "%(notes)s"
    },
    "url": "https://gulf-saathi-psi.vercel.app/check-contact",
    "api_token": null,
    "headers": {},
    "pre_call_webhook_url": null,
    "pre_call_webhook_param": null
  }
}
```
