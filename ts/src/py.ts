// Small helpers that copy Python's behaviour where JavaScript differs, so the
// TypeScript server gives the same answers as the Python one it replaces.

/** Python round(): exact ties go to the even number (banker's rounding). */
export function pyRound(x: number, ndigits = 0): number {
  if (ndigits === 0) {
    const f = Math.floor(x);
    const diff = x - f;
    if (diff > 0.5) return f + 1;
    if (diff < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }
  // Python rounds the exact binary value to nearest, and an exact tie (92.25 to 1 digit)
  // to even. toFixed rounds the exact value too but sends ties up, so handle ties here.
  const p = 10 ** ndigits;
  const scaled = x * p;
  const f = Math.floor(scaled);
  if (scaled - f === 0.5 && (f + 0.5) / p === x) return (f % 2 === 0 ? f : f + 1) / p;
  return Number(x.toFixed(ndigits));
}

const DIGIT_RE = /\p{Nd}/gu;

/** Any Unicode decimal digit to its ASCII digit, as Python's int()/float() accept. */
export function asciiDigits(s: string): string {
  return s.replace(DIGIT_RE, (d) => {
    const cp = d.codePointAt(0)!;
    // Unicode decimal digits come in runs of ten (0-9). Walk back to the start of the
    // run of digits; the value is the distance from there, modulo 10.
    let start = cp;
    while (start > 0 && /\p{Nd}/u.test(String.fromCodePoint(start - 1))) start--;
    return String((cp - start) % 10);
  });
}

/** Python float(str): rejects text that is not a number. */
export function pyFloat(s: string): number {
  const t = asciiDigits(s.trim()).replace(/_/g, '');
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) throw new Error(`could not convert string to float: '${s}'`);
  return Number(t);
}

/** Python str.isdigit() for one string (Unicode digits count). */
export function isDigits(s: string): boolean {
  return s.length > 0 && /^\p{Nd}+$/u.test(s);
}

/** Python's html.escape(s, quote=True). */
export function esc(v: unknown): string {
  if (v === null || v === undefined) return '';
  let s: string;
  if (typeof v === 'boolean') s = v ? 'True' : 'False';
  else s = String(v);
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

/** Python str() of a value, for text built into messages. */
export function pyStr(v: unknown): string {
  if (v === null || v === undefined) return 'None';
  if (typeof v === 'boolean') return v ? 'True' : 'False';
  return String(v);
}

/** Python's split() with no argument: split on runs of whitespace, drop empties. */
export function pySplit(s: string): string[] {
  return s.split(/\s+/u).filter(Boolean);
}

/** " ".join(s.split()): collapse whitespace. */
export function squash(s: string): string {
  return pySplit(s).join(' ');
}

/** Python truthiness for values that come from JSON or the database. */
export function truthy(v: unknown): boolean {
  if (v === null || v === undefined || v === false || v === 0 || v === '') return false;
  if (Array.isArray(v)) return v.length > 0;
  if (v instanceof Set || v instanceof Map) return v.size > 0;
  // Only plain objects (JSON dicts) are empty-or-not; a Date or other object is always "true", as in Python.
  if (typeof v === 'object' && Object.getPrototypeOf(v) === Object.prototype) return Object.keys(v as object).length > 0;
  return true;
}

/** Python str.title(). */
export function pyTitle(s: string): string {
  return s.replace(/[\p{L}\p{N}']+/gu, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .replace(/'(\p{Ll})/gu, (_m, c: string) => "'" + c.toUpperCase())
    .replace(/(\p{L})'(\p{Lu})/gu, (_m, a: string, b: string) => `${a}'${b}`);
}

/** Python str.capitalize(): first letter upper, the rest lower. */
export function pyCapitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s;
}

/** Python int(v) for a number or a string: numbers truncate, strings must be whole numbers. */
export function pyInt(v: unknown): number {
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) throw new Error(`cannot convert float ${v} to integer`);
    return Math.trunc(v);
  }
  const t = asciiDigits(String(v).trim()).replace(/(\d)_(?=\d)/g, '$1');
  if (!/^[+-]?\d+$/.test(t)) throw new Error(`invalid literal for int() with base 10: '${String(v)}'`);
  return Number(t);
}

/** Python float(v) for a number or a string. */
export function pyNum(v: unknown): number {
  if (typeof v === 'number') return v;
  if (typeof v === 'boolean') return v ? 1 : 0;
  return pyFloat(String(v));
}

/** Python's < for the values a sort key can hold (numbers, strings, booleans, None as ""). */
export function pyCompare(a: unknown, b: unknown): number {
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const c = pyCompare(a[i], b[i]);
      if (c) return c;
    }
    return a.length - b.length;
  }
  if (typeof a === 'boolean') a = a ? 1 : 0;
  if (typeof b === 'boolean') b = b ? 1 : 0;
  if (typeof a === 'number' && typeof b === 'number') return a < b ? -1 : a > b ? 1 : 0;
  if (typeof a === 'string' && typeof b === 'string') {
    // Python compares strings by code point, not by UTF-16 unit.
    const x = Array.from(a), y = Array.from(b);
    for (let i = 0; i < Math.min(x.length, y.length); i++) {
      if (x[i] !== y[i]) return x[i].codePointAt(0)! - y[i].codePointAt(0)!;
    }
    return x.length - y.length;
  }
  throw new TypeError(`'<' not supported between ${typeof a} and ${typeof b}`);
}

/** Python sorted(items, key=..., reverse=...): stable, and reverse keeps equal items in order. */
export function pySorted<T>(items: Iterable<T>, key: (x: T) => unknown = (x) => x, reverse = false): T[] {
  const arr = [...items].map((x, i) => ({ x, k: key(x), i }));
  arr.sort((p, q) => (reverse ? pyCompare(q.k, p.k) : pyCompare(p.k, q.k)) || p.i - q.i);
  return arr.map((e) => e.x);
}

/** s[:n] by code point, as Python slices strings. */
export function cut(s: string, n: number): string {
  if (s.length <= n) return s;
  return Array.from(s).slice(0, n).join('');
}

/** Python max(items, key=...): the first item with the largest key. */
export function maxBy<T>(items: T[], key: (x: T) => number, dflt?: T): T {
  if (!items.length) {
    if (dflt === undefined) throw new Error('max() arg is an empty sequence');
    return dflt;
  }
  let best = items[0];
  for (const x of items.slice(1)) if (key(x) > key(best)) best = x;
  return best;
}

/** Python `str(v or "")`. */
export const orStr = (v: unknown): string => (truthy(v) ? pyStr(v) : '');
