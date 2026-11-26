# Gulf Saathi server (TypeScript)

**This is the live server.** It runs on Hostinger (Node 22, Express 5) and rebuilds itself on every push to
the `claude/practical-cray-rj4tyo` branch. The Python code in `gulf_saathi/` is the old version: frozen,
not deployed, kept only for reference. Make every change here.

## Run it
```
cd ts
npm install
npm test            # all tests
npm run dev         # http://localhost:8000, data in memory
npm run build && npm start   # what Hostinger runs (dist/server.js, PORT from the environment)
```
Settings are environment variables, set in hPanel → Websites → the site → Node.js → Environment variables:
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `BOLNA_API_KEY`, `BOLNA_AGENT_ID`, `BOLNA_CHECKIN_AGENT_ID`,
`GS_WEBHOOK_TOKEN`, `GS_DASHBOARD_PASSWORD`, `GS_TEAM_PHONES` (and later `GS_HELPLINE_NUMBER`,
`GS_PILOT_WHATSAPP`, `GS_DEMO_CODE`). Never put a value in the repo: it is public.

## Tests
| Check | File |
|---|---|
| Agent matcher, fuzzy scores, Telugu transliteration, money parsing, call records | `test/golden.test.ts` |
| Case rules, alerts, death papers, signals | `test/cases.test.ts`, `test/promise.test.ts` |
| Every page, byte for byte against a saved snapshot | `test/pages.test.ts` (after a deliberate page change: `npm run snapshot`) |
| HTTP API, login, robots/sitemap/llms.txt | `test/api.test.ts` |

Page text and CSS live in `src/tables/pages.json` and the templates in `src/pages/`.
