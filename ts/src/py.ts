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
  if (typeof v === 'object') return Object.keys(v as object).length > 0;
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
