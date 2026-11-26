---
name: gulf-saathi
description: Project memory for Gulf Saathi, the Telugu voice line and case system for Telangana's Gulf migrant workers. Load at the start of any work in this repository, before changing code, wording, Bolna agents, Plivo, Vercel or Supabase.
---

# Gulf Saathi: what to remember

## The product, in one line
A Telugu phone line (Bolna voice agents, Plivo number) plus a case system: checks agents and fees before
a family pays, calls the worker on arrival day and every week, and turns trouble into a case file for
MADAD, the Indian Embassy, Pravasi Prajavani or the state ex-gratia scheme.

## Dates
- Production (Jagtial pilot) target: about 1 Dec 2026. Work starts 30 Nov. Keep changes small and safe.

## How the user works
- Explain like they are 5: short bullets, tables, no long paragraphs. Be decisive, ask few questions.
- Wait for "go" before big changes; when they say "don't do anything until I ask", stop.
- Honest about what is built and what is not. No invented numbers, sources or quotes.

## Rules that must never break
- Telugu only on the phone. Never call an agent safe, genuine, trusted or good.
- Never promise rescue, money back, or that someone will come.
- Never tell a worker to run away or to call the embassy; a caseworker acts.
- Alerts and messages never name a person or a phone number. Passport numbers are never stored.
- Demo data (`is_demo`) never counts in real totals or feeds live warnings.
- Real cases stay behind the team login. The demo story is open to everyone.
- No secrets in the repo (it is public). Keys live in Vercel env vars; never paste keys in chat.
- No model IDs in commits, PRs or code comments.
- On the public site, name no official and never say "approved" or "government pilot".

## Code and infrastructure (today)
| Piece | Where |
|---|---|
| Live API, webhooks, site, dashboard | Python FastAPI in `gulf_saathi/`, deployed by Vercel from branch `claude/practical-cray-rj4tyo` (Hobby plan, project `gulf-saathi`) |
| TypeScript rewrite | `ts/` (Express 5, Node 22). Complete: same URLs, pages and rules as Python, 194 tests. Not deployed yet; `.vercelignore` keeps it out of the Vercel deploy. See `ts/README.md` |
| Database | Supabase project `gulf-saathi` (Mumbai), Free plan. Schema in `supabase/schema.sql`; `/health/db` checks columns |
| Voice | Bolna agents "Gulf Saathi" (help line, inbound) and "Saathi Check-in agent" (outbound). Both default to Hindi with Telugu switching: fix to Telugu |
| Phone | Plivo number +91 80659 52403, routed to the help-line agent's Bolna application only |
| Hostinger | Business Web Hosting (Node.js, PHP, static; no Python, no VPS). Candidate for the TS server and the shadcn dashboard |
| Old hackathon app | `gulfsaathione` repo and Vercel project: paused. Parts worth porting: TS harness (Telugu numbers, phones, Gulf terms), `caller_said`, exit-path tool, helplines data, MSG91 SMS, CI workflow |

## Open items before real calls
- Webhook token: set `GS_WEBHOOK_TOKEN` in Vercel and add `?token=` to every Bolna tool and webhook URL in the same step.
- Bolna: Telugu as default language on both agents; after-call extraction on.
- Test calls: inbound, check-in, a Gulf number, a weekly alert. Then set `GS_HELPLINE_NUMBER`.
- Vercel function region to Mumbai (`bom1`). Rotate keys used at the hackathon.
- Supabase Pro before families depend on it (Free pauses after 7 quiet days; no backup download).

## How to change code safely
- Python: `python -m pytest -q` must pass before every push (`pytest -q > /dev/null && git push ...`).
- TypeScript: `cd ts && npm test && npx tsc --noEmit`. Pure logic and every dashboard page are checked against
  golden outputs from the Python code (`ts/scripts/make_golden.py`, `make_page_golden.py`); re-run those after a
  Python change. While both exist, change Python and TypeScript together.
- Page text and CSS live in Python; `PYTHONPATH=. python ts/scripts/export_page_text.py` copies them to
  `ts/src/tables/pages.json`.
- Known harmless differences: the 422 message for a body that is not JSON; Python's in-memory store prints a
  salary as "1500.0" where Supabase (and TypeScript) give "1500".
- Never stop the shell with `pkill -f`; use `fuser -k <port>/tcp`.
- Commit messages end with the attribution lines given in the session.
