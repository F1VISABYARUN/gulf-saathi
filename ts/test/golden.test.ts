// Every case here was produced by the Python code (ts/scripts/make_golden.py and the
// recorded pytest run). The TypeScript port must give the same answers.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { parseCall } from '../src/calls.js';
import { checkFee, parseAmounts } from '../src/fees.js';
import { ratio, tokenSetRatio, tokenSortRatio } from '../src/fuzz.js';
import { canonicalGeneric, districtKey, findDistrict, LicensedList, phonetic, romanize, skeleton, splitAgency, tokens } from '../src/matcher.js';
import { analyzeText, parseAmount } from '../src/offer.js';
import { teluguToItrans } from '../src/translit.js';

const load = (name: string) => JSON.parse(readFileSync(new URL(`./golden/${name}.json`, import.meta.url), 'utf8'));
const close = (a: number, b: number) => Math.abs(a - b) < 1e-9;
const agents = LicensedList.load();

function call<T>(fn: () => T): T | { error: string } {
  try { return fn(); } catch { return { error: 'ValueError' }; }
}

test('fuzz scorers match rapidfuzz', () => {
  let n = 0;
  for (const r of load('fuzz')) {
    assert.ok(close(ratio(r.a, r.b), r.ratio), `ratio ${JSON.stringify([r.a, r.b])}: ${ratio(r.a, r.b)} vs ${r.ratio}`);
    assert.ok(close(tokenSortRatio(r.a, r.b), r.sort), `sort ${JSON.stringify([r.a, r.b])}`);
    assert.ok(close(tokenSetRatio(r.a, r.b), r.set), `set ${JSON.stringify([r.a, r.b])}: ${tokenSetRatio(r.a, r.b)} vs ${r.set}`);
    n++;
  }
  assert.ok(n > 1000);
});

test('Telugu transliteration and name helpers match', () => {
  for (const r of load('translit')) {
    if (r.itrans !== null) assert.equal(teluguToItrans(r.text), r.itrans, `itrans ${r.text}`);
    assert.equal(romanize(r.text), r.romanize, `romanize ${r.text}`);
    assert.deepEqual(tokens(r.text), r.tokens, `tokens ${r.text}`);
    assert.deepEqual(splitAgency(r.text), r.split_agency, `split ${r.text}`);
    assert.deepEqual(findDistrict(r.text), r.find_district, `district ${r.text}`);
    assert.equal(districtKey(r.text), r.district_key, `district key ${r.text}`);
  }
  for (const r of load('phonetic')) {
    assert.equal(phonetic(r.w), r.phonetic, `phonetic ${r.w}`);
    assert.equal(skeleton(r.w), r.skeleton, `skeleton ${r.w}`);
    assert.equal(canonicalGeneric(r.w), r.generic, `generic ${r.w}`);
  }
});

function check(args: Record<string, string>) {
  return agents.check(args.agency ?? '', args.owner ?? '', args.district ?? '', args.licence_no ?? '', args.query ?? '');
}

test('agent matcher matches on random and recorded queries', () => {
  const rows = [...load('matcher'), ...load('recorded')['matcher.check']];
  for (const r of rows) assert.deepEqual(check(r.args), r.result, `check ${JSON.stringify(r.args)}`);
  assert.ok(rows.length > 2000);
});

test('money parsing and fee check match', () => {
  for (const r of load('money')) {
    assert.deepEqual(call(() => parseAmounts(r.text)), r.parse_amounts, `parse_amounts ${r.text}`);
    assert.deepEqual(call(() => checkFee(r.text)), r.check_fee, `check_fee ${r.text}`);
    assert.deepEqual(call(() => parseAmount(r.text)), r.parse_amount, `parse_amount ${r.text}`);
    const [answers, flags] = analyzeText(r.text + ' visit visa contract urgent upi fee');
    assert.deepEqual({ answers, flags }, r.analyze, `analyze ${r.text}`);
  }
  const rec = load('recorded');
  for (const r of rec['fees.parse_amounts']) assert.deepEqual(parseAmounts(r.args.text), r.result);
  for (const r of rec['fees.check_fee']) assert.deepEqual(checkFee(r.args.payments), r.result, JSON.stringify(r.args));
  for (const r of rec['offer.parse_amount']) assert.deepEqual(parseAmount(r.args.text), r.result);
});

test('Bolna call records parse the same', () => {
  for (const r of load('recorded')['calls.parse_call']) assert.deepEqual(parseCall(r.args.payload), r.result, JSON.stringify(r.args).slice(0, 200));
});
