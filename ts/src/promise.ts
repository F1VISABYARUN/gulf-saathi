// Promise vs reality: what the worker was promised (the case's job_title), what the papers say, and what
// the worker says is happening now. Port of gulf_saathi/promise.py.
//
// The voice AI only turns speech into words ("herding goats"). These fixed rules decide whether two jobs
// are the same kind of work, so every flag can be explained.
import { fmtRupees } from './fees.js';
import { pyInt, pyNum, pyStr, truthy } from './py.js';

export type Row = Record<string, any>;

// Kinds of work, with English and Telugu words that point to them. A job matching no category is
// "unknown" and never raises a flag on its own.
export const JOB_CATEGORIES: Record<string, string[]> = {
  'cleaning': ['cleaner', 'cleaning', 'housekeeping', 'janitor', 'sweeper', 'క్లీనర్', 'క్లీనింగ్', 'శుభ్రం'],
  'farm and livestock': ['agricultur', 'farm', 'shepherd', 'herder', 'herding', 'camel', 'goat', 'sheep', 'cattle',
    'livestock', 'date palm', 'వ్యవసాయ', 'పొలం', 'గొర్రె', 'మేక', 'ఒంటె', 'పశువు', 'గేదె', 'ఆవు'],
  'driving': ['driver', 'driving', 'chauffeur', 'డ్రైవర్', 'డ్రైవింగ్'],
  'domestic work': ['domestic', 'housemaid', 'maid', 'house worker', 'household', 'nanny', 'babysit',
    'ఇంటి పని', 'పనిమనిషి'],
  'construction': ['mason', 'construction', 'labour', 'labor', 'scaffold', 'steel fix', 'shuttering',
    'మేస్త్రి', 'కూలి', 'నిర్మాణ'],
  'electrical': ['electrician', 'electrical', 'ఎలక్ట్రీషియన్'],
  'plumbing': ['plumber', 'plumbing', 'ప్లంబర్'],
  'welding': ['welder', 'welding', 'వెల్డర్'],
  'carpentry': ['carpenter', 'carpentry', 'కార్పెంటర్', 'వడ్రంగి'],
  'painting': ['painter', 'painting', 'పెయింటర్'],
  'cooking': ['cook', 'chef', 'kitchen', 'వంట'],
  'security': ['security', 'guard', 'watchman', 'సెక్యూరిటీ', 'వాచ్‌మెన్'],
  'hotel and restaurant': ['waiter', 'hotel', 'restaurant', 'room boy', 'steward'],
  'sales': ['salesman', 'sales', 'cashier', 'store keeper', 'storekeeper'],
  'nursing and care': ['nurse', 'nursing', 'caregiver', 'నర్సు'],
  'tailoring': ['tailor', 'stitching', 'దర్జీ'],
  'gardening': ['gardener', 'garden', 'landscap'],
};

export const VISA_TYPES = ['employment', 'visit', 'tourist', 'unknown'] as const;
export const PASSPORT_TYPES = ['ecr', 'ecnr', 'unknown'] as const;

// The 18 Emigration Check Required countries (MEA). ECR passport holders going to work in them need
// emigration clearance on eMigrate and PBBY insurance.
export const ECR_COUNTRIES = ['afghanistan', 'bahrain', 'indonesia', 'iraq', 'jordan', 'kuwait', 'lebanon', 'libya',
  'malaysia', 'oman', 'qatar', 'saudi', 'ksa', 'sudan', 'syria', 'thailand', 'uae', 'emirates', 'dubai', 'abu dhabi',
  'sharjah', 'yemen', 'riyadh', 'jeddah', 'dammam', 'muscat', 'doha', 'manama'];
// Routes MEA or Indian embassies have warned about: Russian army "helper" jobs (Sept 2026), scam
// call-centre jobs in Myanmar, Cambodia and Laos (2022-24).
export const HIGH_RISK_ROUTES = ['russia', 'ukraine', 'myanmar', 'cambodia', 'laos'];

const orEmpty = (v: unknown) => (truthy(v) ? String(v) : '');
const lower = (s: string) => s.toLowerCase();

function where(w: Row): string {
  return lower(`${orEmpty(w.dest_country)} ${orEmpty(w.dest_city)}`);
}

/** Going to an ECR country? null if the destination is not recorded. */
export function ecrRoute(w: Row): boolean | null {
  const at = where(w).trim();
  return at ? ECR_COUNTRIES.some((c) => at.includes(c)) : null;
}

export function jobCategories(text: unknown): Set<string> {
  const t = lower(orEmpty(text));
  return new Set(Object.entries(JOB_CATEGORIES).filter(([, words]) => words.some((x) => t.includes(x))).map(([c]) => c));
}

/** "match", "conflict", or "unknown" when either job is missing or unrecognised. */
export function compareJobs(promised: unknown, other: unknown): 'match' | 'conflict' | 'unknown' {
  const a = jobCategories(promised), b = jobCategories(other);
  if (!a.size || !b.size) return 'unknown';
  return [...a].some((c) => b.has(c)) ? 'match' : 'conflict';
}

const normPlace = (text: unknown) => lower(orEmpty(text)).replace(/[^a-zఀ-౿]/gu, '');

export function comparePlaces(promised: unknown, now: unknown): 'match' | 'conflict' | 'unknown' {
  const a = normPlace(promised), b = normPlace(now);
  if (!a || !b) return 'unknown';
  return a.includes(b) || b.includes(a) ? 'match' : 'conflict';
}

/** A woman going for housework: the job most often hidden inside a private house abroad. */
export function isWomanDomestic(w: Row): boolean {
  const jobs = new Set([...jobCategories(w.job_title), ...jobCategories(w.visa_job)]);
  return w.worker_gender === 'woman' && jobs.has('domestic work');
}

const isVisit = (v: unknown) => v === 'visit' || v === 'tourist';

export interface Flag { code: string; text: string }

/** Red flags found before the worker flies. Each has a code and plain English text. */
export function predepartureChecks(w: Row): Flag[] {
  const flags: Flag[] = [];
  if (isWomanDomestic(w) && isVisit(w.visa_type)) {
    // MEA has said agents send women on tourist visas so emigration checks don't stop them.
    flags.push({ code: 'domestic_visit_visa',
      text: `Woman going for housework on a ${pyStr(w.visa_type)} visa: the route used to get past ` +
        'emigration checks. High risk of being sold between houses abroad' });
  } else if (isWomanDomestic(w)) {
    flags.push({ code: 'domestic_woman',
      text: 'Woman going for housework: with an ECR passport, only a state government recruiting ' +
        'agency may send her, and the employer must be approved on eMigrate' });
  }
  if (w.worker_gender === 'woman' && truthy(w.worker_age) && pyInt(w.worker_age) < 30) {
    flags.push({ code: 'woman_under_30',
      text: `Woman aged ${pyInt(w.worker_age)}: with an ECR passport, India does not give emigration ` +
        'clearance to women under 30 for jobs in ECR countries (all Gulf countries)' });
  }
  if (w.agent_check === 'not_found' || w.agent_check === 'need_more_info') {
    flags.push({ code: 'agent_not_listed', text: 'Agent not found in the licensed list' });
  }
  if (w.fee_status === 'over_cap' && truthy(w.amount_paid_total)) {
    flags.push({ code: 'fee_over_cap',
      text: `Paid agent Rs ${fmtRupees(pyInt(w.amount_paid_total))}, over the Rs 35,400 limit` });
  }
  if (isVisit(w.visa_type)) {
    flags.push({ code: 'visit_visa',
      text: `The visa on the papers is a ${pyStr(w.visa_type)} visa, not an employment visa` });
  }
  if (HIGH_RISK_ROUTES.some((r) => where(w).includes(r))) {
    flags.push({ code: 'high_risk_route',
      text: "A route the Indian government has warned about: Russian army 'helper' jobs, or scam " +
        'call-centre jobs in Myanmar, Cambodia or Laos' });
  }
  // Workers who passed 10th have an ECNR passport and need neither clearance nor PBBY.
  if (w.passport_type !== 'ecnr' && ecrRoute(w) !== false) {
    const maybe = w.passport_type === 'ecr' ? '' : 'If the passport is ECR: ';
    if (w.emigration_clearance === 'no') {
      flags.push({ code: 'no_emigration_clearance',
        text: maybe + 'no emigration clearance on eMigrate for a job in an ECR country: likely an illegal route' });
    }
    if (w.pbby === 'no') {
      flags.push({ code: 'no_pbby',
        text: maybe + 'no PBBY insurance (compulsory for ECR workers: Rs 10 lakh cover for accidental ' +
          'death or disability, premium Rs 275 for 2 years)' });
    }
  }
  if (truthy(w.exit_penalty)) {
    flags.push({ code: 'exit_penalty',
      text: `The contract makes the worker pay to leave or cancel the visa: ${pyStr(w.exit_penalty)}` });
  }
  if (w.contract_before_payment === 'no') {
    flags.push({ code: 'no_contract_before_paying', text: 'Payment taken before contract shown' });
  }
  if (compareJobs(w.job_title, w.visa_job) === 'conflict') {
    flags.push({ code: 'visa_job_mismatch',
      text: `Promised job "${pyStr(w.job_title)}" but the visa says "${pyStr(w.visa_job)}"` });
  }
  return flags;
}

// Flags serious enough that the worker should not pay more or fly until they are resolved.
export const STOP_FLAGS = new Set(['visit_visa', 'visa_job_mismatch', 'domestic_visit_visa', 'high_risk_route',
  'no_emigration_clearance']);

const get = (o: Row, k: string) => (Object.hasOwn(o, k) ? o[k] : null);

/** Rows for the promise-vs-reality table: promised, on papers, now, and the verdict. */
export function promiseRows(w: Row, latestAnswers: Row): Row[] {
  const nowJob = get(latestAnswers, 'current_job') ?? null;
  const nowCity = get(latestAnswers, 'current_city') ?? null;
  const papersVsPromise = compareJobs(w.job_title, w.visa_job);
  const nowVsPromise = compareJobs(w.job_title, nowJob);
  const both = [papersVsPromise, nowVsPromise];
  const verdict = both.includes('conflict') ? 'conflict' : both.includes('match') ? 'match' : 'unknown';
  return [
    { what: 'Job', promised: w.job_title ?? null, papers: w.visa_job ?? null, now: nowJob, verdict },
    { what: 'Visa type', promised: 'employment', papers: w.visa_type ?? null, now: null,
      verdict: isVisit(w.visa_type) ? 'conflict' : w.visa_type === 'employment' ? 'match' : 'unknown' },
    { what: 'City', promised: w.dest_city ?? null, papers: null, now: nowCity,
      verdict: comparePlaces(w.dest_city, nowCity) },
    { what: 'Salary', promised: money(w.contract_salary, w), papers: null,
      now: money(get(latestAnswers, 'salary_amount'), w), verdict: compareSalary(w, latestAnswers) },
  ];
}

function money(v: unknown, w: Row): string | null {
  if (v === null || v === undefined || v === '') return null;
  return `${Math.trunc(pyNum(v))} ${orEmpty(w.salary_currency)}`.trim();
}

/** Less than 90% of the contract is a conflict: the same rule the risk engine uses. */
export function compareSalary(w: Row, answers: Row): 'match' | 'conflict' | 'unknown' {
  const paid = get(answers, 'salary_amount'), promised = w.contract_salary;
  if (!truthy(paid) || !truthy(promised)) return 'unknown';
  return pyNum(paid) < pyNum(promised) * 0.9 ? 'conflict' : 'match';
}
