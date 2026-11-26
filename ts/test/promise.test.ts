// Port of tests/test_promise.py.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MemoryStore, type Row } from '../src/db.js';
import { compareJobs, comparePlaces, predepartureChecks, promiseRows } from '../src/promise.js';
import { checkContact, recordContact, repeatedSignals, reportedContacts, signalsForCase } from '../src/signals.js';

test('jobs compare by kind of work', () => {
  assert.equal(compareJobs('Cleaner', 'Agricultural worker'), 'conflict');
  assert.equal(compareJobs('Cleaner', 'cleaning in a hospital'), 'match');
  assert.equal(compareJobs('Cleaner', 'మేకలు కాస్తున్నాను'), 'conflict');
  assert.equal(compareJobs('House driver', 'డ్రైవర్'), 'match');
  assert.equal(compareJobs('Cleaner', ''), 'unknown');
  assert.equal(compareJobs('Cleaner', 'something else'), 'unknown');
});

test('places', () => {
  assert.equal(comparePlaces('Riyadh', 'near Riyadh'), 'match');
  assert.equal(comparePlaces('Riyadh', 'Al Kharj'), 'conflict');
  assert.equal(comparePlaces('Riyadh', null), 'unknown');
});

test('predeparture checks', () => {
  const w = { agent_check: 'not_found', fee_status: 'over_cap', amount_paid_total: 90000,
    visa_type: 'visit', job_title: 'Cleaner', visa_job: 'Shepherd' };
  assert.deepEqual(predepartureChecks(w).map((f) => f.code), ['agent_not_listed', 'fee_over_cap', 'visit_visa', 'visa_job_mismatch']);
  assert.deepEqual(predepartureChecks({ agent_check: 'confirmed_in_list', visa_type: 'employment', job_title: 'Cleaner', visa_job: 'Cleaner' }), []);
});

test('promise rows', () => {
  const rows = promiseRows({ job_title: 'Cleaner', visa_job: 'Cleaner', visa_type: 'employment', dest_city: 'Riyadh' },
    { current_job: 'herding goats', current_city: 'Al Kharj' });
  assert.deepEqual(rows.map((r) => r.verdict), ['conflict', 'match', 'conflict', 'unknown']);
});

test('repeated signals never match names', () => {
  const ws = [
    { case_id: 'GS-A', sub_agent_phone: '+919848012345', sub_agent_name: 'Raju', risk_level: 'critical' },
    { case_id: 'GS-B', sub_agent_phone: '98480 12345', sub_agent_name: 'Raju', risk_level: 'ok', visa_type: 'visit', is_demo: true },
    { case_id: 'GS-C', sub_agent_name: 'Raju', payment_to: 'x@upi' },
  ];
  const s = repeatedSignals(ws);
  assert.equal(s.length, 1); assert.deepEqual(s[0].cases, ['GS-A', 'GS-B']);
  assert.equal(s[0].at_risk, 1); assert.equal(s[0].flagged, 1); assert.equal(s[0].demo, false);
  assert.deepEqual(signalsForCase(ws[2], ws), []);
});

const w = (cid: string, kw: Row = {}): Row => ({ case_id: cid, risk_level: 'ok', ...kw });

test('live contact check warns without names or case numbers', () => {
  const ws = [w('GS-A', { sub_agent_phone: '+919848012345', risk_level: 'critical', agent_district: 'Jagtial' }),
    w('GS-B', { payment_to: 'raju@upi', agent_district: 'Nizamabad' }),
    w('GS-C', { sub_agent_phone: '+919848012345', is_demo: true, risk_level: 'critical' })];
  let r = checkContact(ws, '98480 12345');
  assert.ok(r.found); assert.equal(r.cases, 1); assert.equal(r.at_risk, 1);
  assert.ok(r.instruction.includes('do not pay any more money') && !JSON.stringify(r).includes('GS-A'));
  r = checkContact(ws, '', ' Raju@UPI ');
  assert.equal(r.cases, 1); assert.equal(r.at_risk, 0); assert.ok(r.instruction.includes('none reported a problem'));
  r = checkContact(ws, '9000011111');
  assert.ok(!r.found && r.instruction.includes('does not mean the agent is safe'));
  assert.ok(checkContact(ws).instruction.includes("Ask for the agent's phone number"));
});

test('employer names link only with country and are weak', () => {
  const ws = [w('GS-A', { employer_name: 'Al Noor Cleaning LLC', dest_country: 'UAE' }),
    w('GS-B', { employer_name: 'AL NOOR CLEANING', dest_country: 'UAE' }),
    w('GS-C', { employer_name: 'Al Noor Cleaning', dest_country: 'Oman' }),
    w('GS-D', { employer_name: 'Noor', dest_country: 'UAE' }), w('GS-E', { employer_name: 'Noor', dest_country: 'UAE' })];
  const s = repeatedSignals(ws);
  assert.equal(s.length, 1); assert.deepEqual(new Set(s[0].cases), new Set(['GS-A', 'GS-B'])); assert.equal(s[0].strong, false);
});

test('numbers heard on calls count even without a case', async () => {
  const store = new MemoryStore();
  for (const [caller, amt, district] of [['9000000001', '150000', 'Jagtial'], ['9000000002', '90000', 'Nizamabad'],
    ['9000000002', '90000', 'Nizamabad'], ['9000000003', '30000', 'Jagtial']]) {
    await recordContact(store, { phone: '98480 12345', amount: amt, district, caller_phone: caller,
      visa_type: caller.endsWith('1') ? 'visit' : '' }, '2026-10-22T10:00:00+00:00');
  }
  assert.equal(await recordContact(store, { phone: '' }, 'x'), null);
  const reports = await store.select('contact_reports');
  const r = checkContact([], '9848012345', '', reports, '9000000003');
  assert.equal(r.callers, 2); assert.equal(r.callers_over_limit, 2); assert.equal(r.callers_visit_visa, 1);
  assert.ok(r.instruction.includes('asked for more than the legal limit') && r.instruction.includes('not proof'));
  const g = reportedContacts(reports, [])[0];
  assert.equal(g.callers, 3); assert.equal(g.reports, 4); assert.equal(g.over_limit, 3);
  assert.deepEqual(g.districts, ['Jagtial', 'Nizamabad']);
});
