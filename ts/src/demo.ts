// The demo story for judges: made-up cases, marked is_demo, that walk through what Saathi catches. No
// real call or SMS is made for them. Port of gulf_saathi/demo.py.
//
// Yadaiah was promised a cleaner's job; the visa says agricultural worker; on arrival day he says he is
// herding goats far from the city. (Inspired by Aadujeevitham.) A second made-up worker paid the same
// village sub-agent, so a repeated-risk signal appears. A third, Saraswathi, is a woman sent for
// housework on a tourist visa.
import { randomInt } from 'node:crypto';
import { parseTs, recordCheckin, registerWorker } from './cases.js';
import type { Row, Store } from './db.js';
import type { LicensedList } from './matcher.js';
import { orStr, truthy } from './py.js';

export const DEMO_NOTE = 'DEMO CASE: made-up person for the demo story. No real call or SMS was made.';

// A fresh number each run, so each run's two cases form their own signal.
const subAgentPhone = () => '+9190000' + Array.from({ length: 5 }, () => String(randomInt(10))).join('');

export async function runDemo(store: Store, licensed: LicensedList, now: Date): Promise<Row> {
  const subPhone = subAgentPhone();
  const upi = `demo.subagent${subPhone.slice(-4)}@upi`;
  const yadaiah = (await registerWorker(store, licensed, {
    worker_name: 'Yadaiah (demo)', worker_name_te: 'యాదయ్య', worker_phone: '+919000000001',
    family_name: 'Lakshmi', family_relation: 'wife', family_phone: '+919000000002',
    employer_name: 'Demo Cleaning Co. (made up)',
    dest_country: 'Saudi Arabia', dest_city: 'Riyadh', job_title: 'Cleaner',
    contract_salary: '1500', salary_currency: 'SAR',
    visa_type: 'employment', visa_job: 'Agricultural worker',
    agent_name: 'Demo Agency (made up)', agent_district: 'Nizamabad',
    sub_agent_name: 'Village agent (demo)', sub_agent_phone: subPhone,
    payments: '50000; 40000', payment_to: upi, notes: DEMO_NOTE,
  }, now, true)).worker;

  const ramesh = (await registerWorker(store, licensed, {
    worker_name: 'Ramesh (demo)', worker_name_te: 'రమేష్', worker_phone: '+919000000003',
    family_phone: '+919000000004', dest_country: 'Saudi Arabia', dest_city: 'Dammam',
    job_title: 'Driver', visa_type: 'visit', agent_name: 'Demo Agency (made up)',
    agent_district: 'Nizamabad', sub_agent_phone: subPhone, payments: '60000; 30000',
    payment_to: upi, notes: DEMO_NOTE,
  }, now, true)).worker;

  // A woman sent for housework on a tourist visa: the route MEA has warned about.
  const saraswathi = (await registerWorker(store, licensed, {
    worker_name: 'Saraswathi (demo)', worker_name_te: 'సరస్వతి', worker_phone: '+919000000005',
    worker_gender: 'woman', worker_age: '27', family_name: 'Raju', family_relation: 'son',
    family_phone: '+919000000006', dest_country: 'Oman', dest_city: 'Muscat', job_title: 'Housemaid',
    visa_type: 'tourist', agent_name: 'Demo Agency (made up)', agent_district: 'Nizamabad',
    payments: '80000', notes: DEMO_NOTE,
  }, now, true)).worker;

  // What the arrival-day call would record. Simulated: no call is placed.
  const arrival = await recordCheckin(store, {
    case_id: yadaiah.case_id, call_kind: 'arrival',
    pickup_status: 'other_person', pickup_person: "a man who said he was the sponsor's driver",
    current_location: 'a goat farm in the desert', current_job: 'herding goats',
    current_city: 'Al Kharj', passport_with_worker: 'no',
    notes: 'Simulated arrival call for the demo.',
  }, now);
  return { yadaiah: yadaiah.case_id, ramesh: ramesh.case_id, saraswathi: saraswathi.case_id, arrival };
}

export const REUSE_FOR_MS = 3600_000;

/** The demo page is public: if a story was made in the last hour, show it again instead of filling the
 * database with new made-up cases on every click. */
export function recentStory(workers: Row[], now: Date): Row | null {
  const latest = new Map<string, Row>();
  for (const w of workers) {
    if (!truthy(w.is_demo)) continue;
    const made = parseTs(w.created_at);
    if (!made || now.getTime() - made.getTime() > REUSE_FOR_MS) continue;
    const key = orStr(w.worker_name).split(' (demo)')[0].toLowerCase();
    if (['yadaiah', 'ramesh', 'saraswathi'].includes(key)
      && (!latest.has(key) || made > parseTs(latest.get(key)!.created_at)!)) latest.set(key, w);
  }
  if (latest.size < 3) return null;
  return { yadaiah: latest.get('yadaiah')!.case_id, ramesh: latest.get('ramesh')!.case_id,
    saraswathi: latest.get('saraswathi')!.case_id, reused: true };
}
