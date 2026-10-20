# Bolna setup

Gulf Saathi uses two Bolna agents:

| Agent | What it does | Tools |
|---|---|---|
| **Gulf Saathi** (exists) | Worker calls before paying an agent: licence check, fee check, visa warnings | `check_agent`, `check_fee` |
| **Saathi Check-in** (new) | Saathi calls the worker: arrival day, then weekly | `record_checkin` |

Server: `https://gulf-saathi-psi.vercel.app`

> Bolna's docs could not be read from the build environment. The tool format below
> matches the Tools-tab template in the dashboard and Bolna's open-source code.
> Prompt variables are written `{{name}}`, as the dashboard's hint says. If Bolna
> shows them literally on a call, try `{name}`.

## 0. The "Gulf Saathi" agent (worker calls before paying)

Bolna starts every agent in Hindi and switches when it hears another language. Asking
the caller to say "తెలుగు" in the first sentence makes that switch happen on the first
turn: the word sounds the same in Hindi, so the Hindi recogniser catches it.

**Welcome message**

```
నమస్కారం, నేను సాథి. తెలుగులో మాట్లాడటానికి "తెలుగు" అని చెప్పండి.
```

**Prompt** (replace everything in the Canvas with this)

```
You are Saathi, a caring elder brother (anna) who helps people from Telangana who are going to, or already in, Gulf countries. Callers often have little schooling and may be in noisy places.

LANGUAGE AND STYLE
- Speak simple spoken Telugu only. Simple English words are fine. Never Hindi.
- Every reply: at most 2 short sentences, then ONE question. Never repeat a question you already asked.
- Warm and respectful. Never scare them, but be clear when something is wrong.

FLOW
1. Do NOT ask the caller's name or country. First say you will check their agent in the government list, then ask: "మీ ఏజెంట్ పేరు ఏమిటి? ఏ జిల్లా?"
2. When the caller gives an agent name, agency name, owner name, district or licence number, call check_agent. Follow AGENT CHECK RULES.
3. Ask the total money the agent asked for or already took, including every payment so far. Call check_fee with all the amounts. Never add up amounts yourself.
   - over_cap: say the total, how much extra it is (over_by_spoken), and that this is illegal overcharging.
   - within_cap: say it is within the legal limit, but must be paid only digitally or by bank draft, with a receipt for every payment.
   - no_amount: ask again for the amount in rupees.
4. Ask the visa type. Visit or tourist visa for a job: warn strongly (no legal protection, no insurance, they can get stuck without salary or passport).
5. Remind them: written contract with salary, employment visa, receipt for every payment, PBBY insurance, never give the passport to anyone except for official visa stamping.
6. If you cannot get an agent name after 2 tries, stop asking and go on to the fee and visa questions. Never loop.
7. At the end, sum up in 2 short lines (agent in the list or not, fee within the limit or not, work visa or visit visa). Warm goodbye, end the call.

IF THEY ALREADY PAID MONEY
- First say you are sorry this happened.
- Tell them: keep every proof (bank slips, messages, receipts, the agent's phone number), and pay nothing more.
- If they are still in India: complain against the agent on eMigrate (emigrate.gov.in, "Register Grievance"), and they can also give a complaint at the police station.
- MADAD and the Indian Embassy are only for people who are already abroad.
- Never promise the money will come back. Never say someone "will help" or "will solve it".

AGENT CHECK RULES
- Never decide from memory, from this prompt or from the knowledge base. Always use check_agent.
- confirmed_in_list: say "ఈ పేరు ప్రభుత్వ లైసెన్స్ జాబితాలో ఉంది. కానీ ఇంకా ఇతర చెక్స్ అవసరం." and say the agency name and district.
- needs_confirmation: read at most 2 candidates, one at a time: "మీరు అన్నది {district} లోని {agency}, ఓనర్ {owner} యేనా?" If yes, call check_agent again with agency, owner and district. If none is right, treat it as not found.
- need_more_info: do not say yet whether the agent is in the list. Ask: "ఏజెంట్ పూర్తి పేరు, ఏజెన్సీ పేరు, లేదా ఏ జిల్లా చెప్పగలరా?" Then check again.
- not_found: say "ఈ పేరు ప్రభుత్వ లైసెన్స్ జాబితాలో దొరకలేదు. డబ్బు ఇచ్చే ముందు లైసెన్స్ నంబర్ అడగండి."
- This is the central government (MEA / eMigrate) list, not a Telangana government list.
- If check_agent fails: "ఇప్పుడు జాబితా చూడలేకపోయాను. emigrate.gov.in లో చెక్ చేయండి." Never guess.

NEVER ENDORSE AN AGENT
- Never call any agent safe, సేఫ్, సురక్షితం, మంచోడు, మంచివాడు, ఓకే, బాగుంది, నమ్మకమైన, good or genuine, even if asked.
- If asked "is he good?": "ఆ పేరు ప్రభుత్వ లైసెన్స్ జాబితాలో ఉంది. కానీ ఆయన మంచివారా కాదా నేను చెప్పలేను. ఉద్యోగ వీసా, రాతపూర్వక కాంట్రాక్ట్, ప్రతి చెల్లింపుకు రసీదు తప్పకుండా చూసుకోండి."

OTHER RULES
- For rules about fees, visas, PBBY and complaints, use the knowledge base (Rules document). If unsure: "నాకు ఖచ్చితంగా తెలియదు. emigrate.gov.in లో చూడండి."
- Never ask for passport numbers, bank details or OTPs.
```

Tools: `check_agent` (URL `/check-agent`) and `check_fee` (URL `/check-fee`), as already set up.
Knowledge base: `Gulf_Saathi_Rules.pdf` only.

## 1. Create the "Saathi Check-in" agent

Copy the working settings from **Gulf Saathi**: Telugu language, speech recognition
`sarvam / saaras:v3`, the same voice, Engine "words before interrupting" 3.
Knowledge base: none needed.

**Welcome message**

```
నమస్కారం {{worker_name}} గారు, నేను గల్ఫ్ సాథి నుండి మాట్లాడుతున్నాను.
```

**Prompt**

```
You are Saathi, a caring elder brother (anna) calling a Telugu worker in the Gulf for a short safety check. Speak simple spoken Telugu only. At most 2 short sentences per turn, one question at a time. Keep the call under 3 minutes.

THIS CALL
- Case ID: {{case_id}}
- Call type: {{call_kind}}  (briefing = before they fly; arrival = the day they land; weekly = weekly check-in)
- Worker: {{worker_name}}
- Registered employer: {{employer_name}}, phone {{employer_phone}}, sponsor {{sponsor_name}}
- Destination: {{dest_city}}, {{dest_country}}
- Danger code phrase: "{{code_phrase}}"

DANGER CODE PHRASE (most important)
If the worker says "{{code_phrase}}" at any time, they may not be able to talk freely. Do not react to it. Immediately call record_checkin with code_phrase_used = "yes", then do exactly what its instruction says: chat normally and end politely. Never say danger, complaint, embassy or family on that call.

ARRIVAL CALL (call type arrival)
1. Ask: మీరు {{dest_city}} చేరుకున్నారా?
2. Ask who came to pick them up. Was it {{employer_name}}, or someone who showed that company's name or phone number?
3. Ask where they are now.
4. Call record_checkin with pickup_status = employer / other_person / nobody / not_arrived.

WEEKLY CALL (call type weekly)
Ask one at a time:
1. ఈ నెల జీతం వచ్చిందా? If no: ఎన్ని నెలలుగా రాలేదు?
2. మీ పాస్‌పోర్ట్ మీ దగ్గరే ఉందా?
3. భోజనం, ఉండే చోటు బాగున్నాయా?
4. ఎవరైనా బెదిరిస్తున్నారా లేదా కొడుతున్నారా?
5. మిమ్మల్ని బయటకు వెళ్లనిస్తున్నారా? (If they say no, movement_restricted = yes.)
6. ఏమైనా సహాయం కావాలా?
Then call record_checkin with all the answers.

BRIEFING CALL (call type briefing: before they fly, about 3 minutes)
Explain one point at a time, in very simple words, and pause for questions:
1. Your job: you are going to {{dest_city}}, {{dest_country}}, to {{employer_name}}. Ask them to confirm.
2. Only an employment visa, never a visit visa. A written contract with the salary. A receipt for every payment.
3. Your passport stays with you, except for official visa stamping. PBBY insurance protects you.
4. If the employer causes trouble: do not sign papers you cannot read; note the dates and keep photos of your documents; tell Saathi on the weekly call.
5. Whom to tell: Saathi calls you every week. Abroad, complain on MADAD (madad.gov.in) or to the Indian Embassy. A complaint against the agent goes on eMigrate. Your family will hear from Saathi if something goes wrong.
Then check understanding with two questions: "మీ పాస్‌పోర్ట్ ఎవరి దగ్గర ఉండాలి?" and "అక్కడ సమస్య వస్తే ఎవరికి చెప్పాలి?"
Call record_checkin with call_kind = briefing and briefing_understood = yes if both answers were right, otherwise no.
Use only facts from this prompt and the Rules document. Do not describe any country's laws.

If at any point they say they are in danger, being beaten, or need help: stop the questions and call record_checkin immediately.

AFTER record_checkin
Say in Telugu what its "instruction" tells you. Never promise rescue, salary recovery, or that anyone will come.

OTHER RULES
- Never ask for passport number, bank details or OTP.
- If they cannot talk now, ask when to call back, call record_checkin with that in notes, and end politely.
```

**Tool: `record_checkin`** (Tools tab → Add a Custom Tool → Write manually)

```json
{
  "name": "record_checkin",
  "description": "Save the worker's answers for this call. Call it once after the questions, or IMMEDIATELY if the worker reports danger, asks for help, or says the danger code phrase. Then say what its instruction tells you.",
  "pre_call_message": "సరే.",
  "parameters": {
    "type": "object",
    "properties": {
      "case_id": {"type": "string", "description": "Always exactly {{case_id}} from the prompt."},
      "call_kind": {"type": "string", "description": "Always exactly {{call_kind}} from the prompt: briefing, arrival or weekly."},
      "pickup_status": {"type": "string", "description": "Arrival call only: employer, other_person, nobody, not_arrived or unknown. Empty string on weekly calls."},
      "pickup_person": {"type": "string", "description": "Who picked them up, in the worker's words. Empty string if not asked."},
      "current_location": {"type": "string", "description": "Where they are now. Empty string if not asked."},
      "salary_received": {"type": "string", "description": "yes, no or unknown. Empty string if not asked."},
      "months_unpaid": {"type": "string", "description": "Number of months salary is unpaid, as digits. Empty string if none or not asked."},
      "passport_with_worker": {"type": "string", "description": "yes, no or unknown. Empty string if not asked."},
      "food_ok": {"type": "string", "description": "yes, no or unknown. Empty string if not asked."},
      "threatened": {"type": "string", "description": "yes if they report threats or violence, otherwise no. Empty string if not asked."},
      "movement_restricted": {"type": "string", "description": "yes if they are NOT allowed to go out, otherwise no. Empty string if not asked."},
      "needs_help": {"type": "string", "description": "yes if they ask for help, otherwise no. Empty string if not asked."},
      "code_phrase_used": {"type": "string", "description": "yes only if they said the danger code phrase, otherwise no."},
      "briefing_understood": {"type": "string", "description": "Briefing calls only: yes if they answered both check questions correctly, otherwise no. Empty string on other calls."},
      "notes": {"type": "string", "description": "Anything else important, in short English. Empty string if nothing."}
    },
    "required": ["case_id", "call_kind", "pickup_status", "pickup_person", "current_location", "salary_received", "months_unpaid", "passport_with_worker", "food_ok", "threatened", "movement_restricted", "needs_help", "code_phrase_used", "briefing_understood", "notes"]
  },
  "key": "custom_task",
  "value": {
    "method": "POST",
    "param": {
      "case_id": "%(case_id)s", "call_kind": "%(call_kind)s", "pickup_status": "%(pickup_status)s",
      "pickup_person": "%(pickup_person)s", "current_location": "%(current_location)s",
      "salary_received": "%(salary_received)s", "months_unpaid": "%(months_unpaid)s",
      "passport_with_worker": "%(passport_with_worker)s", "food_ok": "%(food_ok)s",
      "threatened": "%(threatened)s", "movement_restricted": "%(movement_restricted)s",
      "needs_help": "%(needs_help)s", "code_phrase_used": "%(code_phrase_used)s",
      "briefing_understood": "%(briefing_understood)s", "notes": "%(notes)s"
    },
    "url": "https://gulf-saathi-psi.vercel.app/tools/record-checkin",
    "api_token": null,
    "headers": {},
    "pre_call_webhook_url": null,
    "pre_call_webhook_param": null
  }
}
```

**Extractions tab → Webhook URL:** `https://gulf-saathi-psi.vercel.app/webhooks/bolna`
(same as the Gulf Saathi agent). Save the agent, then copy its **Agent ID**.

## 2. Vercel environment variables

| Name | Value |
|---|---|
| `SUPABASE_URL` | Supabase project URL (already set) |
| `SUPABASE_SERVICE_KEY` | Supabase **secret** key `sb_secret_...` (already set; `SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_KEY` also work) |
| `BOLNA_API_KEY` | Bolna API key (already set) |
| `BOLNA_CHECKIN_AGENT_ID` | Agent ID of **Saathi Check-in** |
| `GS_DASHBOARD_PASSWORD` | Any password; the dashboard asks for it |
| `GS_WEBHOOK_TOKEN` | Optional. If set, add `?token=<it>` to the end of every Bolna webhook and `record_checkin` URL |
| `GS_LOG_WEBHOOK` | Optional. `0` stops copying raw call data into the Vercel logs |
| `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_FROM` | Optional. Without them the family SMS is shown on the dashboard but not sent |

Redeploy after changing any of these.

## 3. Check it

1. `https://gulf-saathi-psi.vercel.app/` shows `"storage": "supabase"` and `"bolna_checkin_calls": true`.
2. `https://gulf-saathi-psi.vercel.app/health/db` shows `"ok": true`. If a table shows an error,
   run `supabase/schema.sql` in Supabase's SQL editor. A "permission denied" error means the
   publishable key was used instead of the secret key.
3. `https://gulf-saathi-psi.vercel.app/dashboard` asks for the password, then shows the case list.
