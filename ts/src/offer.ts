// Red-flag checks for a job offer, from IVR answers or a forwarded message.
import { FEE_CAP_INR } from './config.js';
import { asciiDigits, pyFloat } from './py.js';

export interface OfferAnswers {
  has_contract: boolean | null;
  visa: string | null; // "employment", "visit" or "unknown"
  fee_inr: number | null;
  region: string | null; // "gulf" or "other"
  passport_kept: boolean | null;
  personal_payment: boolean;
  pressure: boolean;
}

export function newAnswers(over: Partial<OfferAnswers> = {}): OfferAnswers {
  return { has_contract: null, visa: null, fee_inr: null, region: null, passport_kept: null,
    personal_payment: false, pressure: false, ...over };
}

/** Prompt keys for each red flag, most serious first. */
export function assessOffer(a: OfferAnswers): string[] {
  const flags: string[] = [];
  if (a.visa === 'visit') flags.push('flag_visit_visa');
  if (a.passport_kept) flags.push('flag_passport_kept');
  if (a.has_contract === false) flags.push('flag_no_contract');
  if (a.fee_inr !== null && a.fee_inr > FEE_CAP_INR) flags.push('flag_fee_high');
  if (a.region === 'other') flags.push('flag_non_gulf');
  if (a.visa === 'unknown') flags.push('flag_visa_unknown');
  if (a.personal_payment) flags.push('flag_personal_payment');
  if (a.pressure) flags.push('flag_pressure');
  return flags;
}

// --- Free-text analysis (forwarded WhatsApp offer, or transcribed speech) ---

const VISIT = ['visit visa', 'tourist visa', 'visit', 'tourist', 'విజిట్', 'టూరిస్ట్', 'विज़िट', 'विजिट', 'टूरिस्ट', 'وزٹ', 'ٹورسٹ'];
const EMPLOYMENT = ['employment visa', 'work visa', 'work permit', 'job visa', 'residence visa', 'ఉద్యోగ వీసా', 'वर्क वीज़ा', 'वर्क परमिट', 'ورک ویزا'];
const CONTRACT = ['contract', 'offer letter', 'agreement', 'appointment letter', 'కాంట్రాక్ట్', 'ఒప్పందం', 'कॉन्ट्रैक्ट', 'अनुबंध', 'करार', 'کانٹریکٹ', 'معاہدہ'];
const NON_GULF = [
  'russia', 'europe', 'poland', 'serbia', 'romania', 'croatia', 'armenia', 'georgia', 'belarus',
  'ukraine', 'lithuania', 'latvia', 'hungary', 'malta', 'cyprus', 'myanmar', 'laos', 'cambodia',
  'రష్యా', 'యూరప్', 'రష్యాలో', 'रूस', 'यूरोप', 'روس', 'یورپ',
];
const PASSPORT_KEPT = ['submit passport', 'passport submit', 'deposit passport', 'passport deposit', 'keep your passport',
  'hand over passport', 'original passport', 'పాస్‌పోర్ట్ ఇవ్వాలి', 'पासपोर्ट जमा', 'پاسپورٹ جمع'];
const PERSONAL_PAY = ['google pay', 'gpay', 'phonepe', 'phone pe', 'paytm', 'cash only', 'only cash', 'personal account', 'upi'];
const PRESSURE = ['urgent', 'today only', 'limited seats', 'last date today', 'hurry', 'అర్జెంట్', 'ఈరోజే', 'तुरंत', 'आज ही', 'فوری', 'آج ہی'];

export const UNITS: Record<string, number> = {
  lakh: 100000, lakhs: 100000, lac: 100000, lacs: 100000, l: 100000,
  'లక్ష': 100000, 'లక్షలు': 100000, 'लाख': 100000, 'لاکھ': 100000,
  k: 1000, thousand: 1000, 'వేలు': 1000, 'వేల': 1000, 'हज़ार': 1000, 'हजार': 1000, 'ہزار': 1000,
};

const reEscape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
// Python sorts by length, longest first, keeping insertion order for equal lengths.
const UNIT_ALT = Object.keys(UNITS).map(reEscape).sort((a, b) => b.length - a.length).join('|');
const AMOUNT_SRC = String.raw`(\p{Nd}+(?:[.,]\p{Nd}+)*)\s*(` + UNIT_ALT + String.raw`)?(?![a-zA-Z])`;

/** Every (number, unit) pair, like Python's _AMOUNT.findall. */
export function findAmounts(text: string): Array<[string, string]> {
  const re = new RegExp(AMOUNT_SRC, 'giu');
  const out: Array<[string, string]> = [];
  for (const m of text.matchAll(re)) out.push([m[1], m[2] ?? '']);
  return out;
}

const has = (text: string, words: string[]) => words.some((w) => text.includes(w));
const nonDigits = (s: string) => asciiDigits(s).replace(/\D/g, '');

/** Largest rupee amount mentioned, e.g. "1.5 lakh", "80,000", "60 వేలు". */
export function parseAmount(text: string): number | null {
  let best: number | null = null;
  for (const [num, rawUnit] of findAmounts(text)) {
    const unit = rawUnit.toLowerCase();
    let value: number;
    if (unit) {
      value = pyFloat(num.replace(/,/g, '')) * UNITS[unit];
    } else {
      value = pyFloat(num.replace(/,/g, ''));
      // Bare small numbers are ages, days, hours; 10+ digits are phone numbers.
      if (value < 1000 || nonDigits(num).length >= 10) continue;
    }
    best = Math.max(best ?? 0, Math.trunc(value));
  }
  return best;
}

export function analyzeText(text: string): [OfferAnswers, string[]] {
  const t = text.toLowerCase();
  const a = newAnswers();
  if (has(t, EMPLOYMENT)) a.visa = 'employment';
  else if (has(t, VISIT)) a.visa = 'visit';
  a.has_contract = has(t, CONTRACT);
  a.fee_inr = has(t, ['fee', 'charge', 'pay', '₹', 'rs', 'inr', 'రూపాయ', 'रुपये', 'रुपए', 'روپے', 'ఫీజు', 'फीस', 'فیس', 'lakh', 'లక్ష', 'लाख'])
    ? parseAmount(t) : null;
  a.region = has(t, NON_GULF) ? 'other' : null;
  a.passport_kept = has(t, PASSPORT_KEPT);
  a.personal_payment = has(t, PERSONAL_PAY);
  a.pressure = has(t, PRESSURE);
  return [a, assessOffer(a)];
}
