// Add up everything a worker has paid or been asked to pay an agent, and compare
// it with the legal cap. The voice agent never does this arithmetic itself: a model
// adding "10,000 then 25,000 then 5,000" in its head is where a wrong "that's fine" comes from.
import { FEE_CAP_INR } from './config.js';
import { findAmounts, UNITS } from './offer.js';
import { asciiDigits, pyFloat, pyRound, truthy } from './py.js';

export const MIN_PAYMENT = 100; // smaller bare numbers are more likely days, ages or months than rupees

/** Indian digit grouping: 150000 -> 1,50,000. */
export function fmtRupees(n: number): string {
  const s = String(n);
  if (s.length <= 3) return s;
  let head = s.slice(0, -3);
  const tail = s.slice(-3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  return [head, ...groups, tail].join(',');
}

/** Every rupee amount in the text: "10000; 25000", "80,000", "1.5 lakh", "60 వేలు". */
export function parseAmounts(text: string): number[] {
  // "10000,25000" is two payments, not one number: a thousands comma is followed by
  // exactly 2 or 3 digits ("1,50,000"), never 4 or more.
  const t = text.toLowerCase().replace(/,(?=\p{Nd}{4,})/gu, '; ');
  const out: number[] = [];
  for (const [num, unit] of findAmounts(t)) {
    const digits = asciiDigits(num).replace(/\D/g, '');
    if (digits.length >= 10) continue; // a phone number
    let value = pyFloat(num.replace(/,/g, ''));
    if (unit) value *= UNITS[unit];
    else if (value < MIN_PAYMENT) continue;
    out.push(pyRound(value));
  }
  return out;
}

export interface FeeResult {
  payments: number[]; total: number; cap: number; total_spoken: string; cap_spoken: string;
  status: string; over_by: number; over_by_spoken: string; instruction: string;
}

/** `payments` is a list of amounts, or text containing amounts. */
export function checkFee(payments: unknown): FeeResult {
  const amounts = Array.isArray(payments)
    ? payments.flatMap((item) => parseAmounts(pyStrLoose(item)))
    : parseAmounts(truthy(payments) ? pyStrLoose(payments) : '');
  const cap = FEE_CAP_INR;
  const total = amounts.reduce((a, b) => a + b, 0);
  const base = { payments: amounts, total, cap, total_spoken: fmtRupees(total), cap_spoken: fmtRupees(cap) };
  if (!amounts.length) {
    return { ...base, status: 'no_amount', over_by: 0, over_by_spoken: '0',
      instruction: 'No rupee amount was understood. Ask the caller for the total amount in rupees, as digits.' };
  }
  if (total > cap) {
    const over = total - cap;
    return { ...base, status: 'over_cap', over_by: over, over_by_spoken: fmtRupees(over),
      instruction: `The total of ${fmtRupees(total)} rupees is ${fmtRupees(over)} rupees more than the legal maximum of `
        + `${fmtRupees(cap)}. Tell the caller this is illegal overcharging. Payment must be digital or by bank `
        + 'draft, with a receipt for every payment.' };
  }
  return { ...base, status: 'within_cap', over_by: 0, over_by_spoken: '0',
    instruction: `The total of ${fmtRupees(total)} rupees is within the legal maximum of ${fmtRupees(cap)}. `
      + 'Do not say the agent is honest or safe. Payment must still be digital or by bank draft, with a receipt '
      + 'for every payment, and more payments later would count towards the same limit.' };
}

/** str(x) for values arriving in JSON (numbers keep Python's float spelling). */
function pyStrLoose(v: unknown): string {
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'boolean') return v ? 'True' : 'False';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
