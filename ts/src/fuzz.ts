// The three rapidfuzz scorers the matcher uses, written out so results match the Python
// library exactly (checked against it in test/golden.test.ts). All work on code points,
// with no preprocessing, like rapidfuzz 3.

const cps = (s: string) => Array.from(s);

/** Indel distance = len(a) + len(b) - 2 * longest common subsequence. The LCS uses the bit-parallel
 * method (Hyyrö 2004), 32 characters of `a` per machine word, like rapidfuzz itself: the agent check runs
 * this thousands of times per call, so a plain table was too slow under load. */
export function indelDistance(a: string, b: string): number {
  const x = cps(a), y = cps(b);
  if (!x.length || !y.length) return x.length + y.length;
  return x.length + y.length - 2 * lcsLength(x, y);
}

function lcsLength(x: string[], y: string[]): number {
  const m = x.length, words = (m + 31) >>> 5;
  // For each character, a bit mask of where it appears in x.
  const pm = new Map<string, Uint32Array>();
  for (let i = 0; i < m; i++) {
    let v = pm.get(x[i]);
    if (!v) { v = new Uint32Array(words); pm.set(x[i], v); }
    v[i >>> 5] |= 1 << (i & 31);
  }
  const V = new Uint32Array(words).fill(0xffffffff);
  for (const ch of y) {
    const M = pm.get(ch);
    if (!M) continue; // V & M is 0: V stays the same
    let carry = 0;
    for (let w = 0; w < words; w++) {
      const v = V[w], u = (v & M[w]) >>> 0;
      const sum = v + u + carry; // up to 2^33, exact in a double
      carry = sum > 0xffffffff ? 1 : 0;
      V[w] = ((sum >>> 0) | (v & ~u)) >>> 0;
    }
  }
  let lcs = 0;
  for (let w = 0; w < words; w++) {
    const bits = w === words - 1 && (m & 31) ? (m & 31) : 32;
    let z = ~V[w] >>> 0;
    if (bits < 32) z &= (1 << bits) - 1;
    while (z) { z &= z - 1; lcs++; }
  }
  return lcs;
}

function normSim(dist: number, lensum: number): number {
  if (lensum === 0) return 100;
  return (1 - dist / lensum) * 100;
}

/** fuzz.ratio */
export function ratio(a: string, b: string): number {
  return normSim(indelDistance(a, b), cps(a).length + cps(b).length);
}

const splitWs = (s: string) => s.split(/\s+/u).filter(Boolean);
const pySort = (arr: string[]) => [...arr].sort((p, q) => (p < q ? -1 : p > q ? 1 : 0));

/** fuzz.token_sort_ratio */
export function tokenSortRatio(a: string, b: string): number {
  return ratio(pySort(splitWs(a)).join(' '), pySort(splitWs(b)).join(' '));
}

/** fuzz.token_set_ratio */
export function tokenSetRatio(a: string, b: string): number {
  const ta = new Set(splitWs(a)), tb = new Set(splitWs(b));
  if (!ta.size || !tb.size) return 0;
  const inter = [...ta].filter((t) => tb.has(t));
  const diffAB = pySort([...ta].filter((t) => !tb.has(t)));
  const diffBA = pySort([...tb].filter((t) => !ta.has(t)));
  if (inter.length && (!diffAB.length || !diffBA.length)) return 100;
  const abJoined = diffAB.join(' '), baJoined = diffBA.join(' ');
  const abLen = cps(abJoined).length, baLen = cps(baJoined).length;
  const sectLen = cps(pySort(inter).join(' ')).length;
  const sep = sectLen !== 0 ? 1 : 0;
  const sectAbLen = sectLen + sep + abLen;
  const sectBaLen = sectLen + sep + baLen;
  const dist = indelDistance(abJoined, baJoined);
  let result = normSim(dist, sectAbLen + sectBaLen);
  if (sectLen === 0) return result;
  const sectAbDist = sep + abLen;
  const sectAbRatio = normSim(sectAbDist, sectLen + sectAbLen);
  const sectBaDist = sep + baLen;
  const sectBaRatio = normSim(sectBaDist, sectLen + sectBaLen);
  result = Math.max(result, sectAbRatio, sectBaRatio);
  return result;
}
