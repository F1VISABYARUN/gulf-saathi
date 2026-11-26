// Settings and policy numbers. Policy numbers change over time; each one says where it comes from.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pyRound } from './py.js';

const HERE = dirname(fileURLToPath(import.meta.url));

/** Folder holding licensed_agents.csv and public/: next to the built server, or the repo root. */
export function findDir(name: string): string {
  const candidates = [process.env.GS_DATA_ROOT ? join(process.env.GS_DATA_ROOT, name) : '',
    join(HERE, name), join(HERE, '..', name), join(HERE, '..', '..', name)].filter(Boolean);
  for (const c of candidates) if (existsSync(c)) return c;
  return candidates[candidates.length - 1];
}

// Maximum service charge a registered recruiting agent may collect from a worker:
// Emigration (Amendment) Rules 2017 (Rule 25) and MEA advisories, 30,000 + 18% GST
// = 35,400. Older MEA pages still show the 2009 rule (45 days' wages, max 20,000).
// All payments to the agent are added up and compared with this total.
export const MAX_SERVICE_FEE_INR = parseInt(process.env.GS_MAX_SERVICE_FEE ?? '30000', 10);
export const GST_PERCENT = parseInt(process.env.GS_GST_PERCENT ?? '18', 10);
export const FEE_CAP_INR = pyRound(MAX_SERVICE_FEE_INR * (100 + GST_PERCENT) / 100);
