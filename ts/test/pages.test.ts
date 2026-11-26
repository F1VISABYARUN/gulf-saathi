// Snapshot test: every page must come out exactly as saved in golden/pages.json (first made from the old
// Python version). After a deliberate page change, run `npm run snapshot` and check the diff.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { test } from 'node:test';
import * as d from '../src/pages/dashboard.js';
import * as site from '../src/pages/site.js';

process.env.GS_HELPLINE_NUMBER = '918065952403';
process.env.GS_PILOT_WHATSAPP = '919999999999';

const pages: Array<{ name: string; args: any[]; html: string }> =
  JSON.parse(readFileSync(new URL('./golden/pages.json', import.meta.url), 'utf8'));

const render: Record<string, (...a: any[]) => string> = {
  list: d.renderList, list_q: d.renderList, list_empty: d.renderList, agents: d.renderAgents, agents_empty: d.renderAgents,
  form: d.renderForm, form_edit: d.renderForm, case: d.renderCase, proof: d.renderProofOfWork, petition: d.renderPetition,
  site_home: site.renderHome, site_demo: site.renderDemo, site_login: site.renderLogin,
  death: d.renderDeathPacket, intake: d.renderIntake, alerts: d.renderAlerts, alerts_none: d.renderAlerts,
};

function firstDiff(a: string, b: string): string {
  let i = 0;
  while (i < a.length && a[i] === b[i]) i++;
  return `at ${i}\n  python: ${JSON.stringify(a.slice(Math.max(0, i - 80), i + 80))}\n  ts:     ${JSON.stringify(b.slice(Math.max(0, i - 80), i + 80))}`;
}

const UPDATE = process.env.UPDATE_SNAPSHOT === '1';
for (const [i, p] of pages.entries()) {
  test(`page ${i} ${p.name}`, () => {
    const mine = render[p.name](...p.args);
    if (UPDATE) p.html = mine;
    else if (mine !== p.html) assert.fail(firstDiff(p.html, mine));
  });
}
if (UPDATE) test('save snapshot', () => writeFileSync(new URL('./golden/pages.json', import.meta.url), JSON.stringify(pages)));
