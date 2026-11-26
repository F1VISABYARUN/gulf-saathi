# Gulf Saathi, TypeScript server

The same server as the Python one in `gulf_saathi/`, rewritten in TypeScript (Node 22, Express 5): the same
URLs, the same answers to the Bolna tools and webhook, and the same HTML pages. It is not deployed yet; the
live site still runs the Python code on Vercel.

## Run it
```
cd ts
npm install
npm test            # 194 tests: ported Python tests plus golden checks against the Python output
npm run dev         # http://localhost:8000, data in memory
npm run build && npm start   # what a host runs (dist/server.js, PORT from the environment)
```
Without `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` it keeps data in memory only. Every other setting is the same
environment variable as on Vercel (`GS_DASHBOARD_PASSWORD`, `BOLNA_API_KEY`, `BOLNA_CHECKIN_AGENT_ID`,
`BOLNA_AGENT_ID`, `GS_WEBHOOK_TOKEN`, `GS_TEAM_PHONES`, ...). Images and the demo video are served from `public/`.

## How it is kept equal to the Python version
| Check | File |
|---|---|
| Agent matcher, fuzzy scores, Telugu transliteration, money parsing, call records | `test/golden.test.ts` (outputs from `scripts/make_golden.py` and a recorded pytest run) |
| Case rules, alerts, death papers, signals | `test/cases.test.ts`, `test/promise.test.ts` (ported from `tests/`) |
| Every dashboard page, byte for byte | `test/pages.test.ts` (outputs from `scripts/make_page_golden.py`) |
| HTTP API | `test/api.test.ts` (ported from `tests/test_api.py`) |

Page text and CSS are exported from the Python modules into `src/tables/pages.json`
(`PYTHONPATH=. python ts/scripts/export_page_text.py`). While both versions exist, change both together and
re-run the golden scripts.
