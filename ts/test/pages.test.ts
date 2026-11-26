// Every dashboard page rendered by the Python code (scripts/make_page_golden.py) must come out the same
// from the TypeScript port, byte for byte.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import * as d from '../src/pages/dashboard.js';

const pages: Array<{ name: string; args: any[]; html: string }> =
  JSON.parse(readFileSync(new URL('./golden/pages.json', import.meta.url), 'utf8'));

const render: Record<string, (...a: any[]) => string> = {
  list: d.renderList, list_q: d.renderList, list_empty: d.renderList, agents: d.renderAgents, agents_empty: d.renderAgents,
  form: d.renderForm, form_edit: d.renderForm, case: d.renderCase, proof: d.renderProofOfWork, petition: d.renderPetition,
  death: d.renderDeathPacket, intake: d.renderIntake, alerts: d.renderAlerts, alerts_none: d.renderAlerts,
};

function firstDiff(a: string, b: string): string {
  let i = 0;
  while (i < a.length && a[i] === b[i]) i++;
  return `at ${i}\n  python: ${JSON.stringify(a.slice(Math.max(0, i - 80), i + 80))}\n  ts:     ${JSON.stringify(b.slice(Math.max(0, i - 80), i + 80))}`;
}

for (const [i, p] of pages.entries()) {
  test(`dashboard page ${i} ${p.name}`, () => {
    const mine = render[p.name](...p.args);
    if (mine !== p.html) assert.fail(firstDiff(p.html, mine));
  });
}
