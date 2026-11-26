// The three rapidfuzz scorers the matcher uses, written out so results match the Python
// library exactly (checked against it in test/golden.test.ts). All work on code points,
// with no preprocessing, like rapidfuzz 3.

const cps = (s: string) => Array.from(s);

/** Indel distance = len(a) + len(b) - 2 * longest common subsequence. */
export function indelDistance(a: string, b: string): number {
  const x = cps(a), y = cps(b);
  if (!x.length || !y.length) return x.length + y.length;
  let prev = new Array<number>(y.length + 1).fill(0);
  let cur = new Array<number>(y.length + 1).fill(0);
  for (let i = 1; i <= x.length; i++) {
    for (let j = 1; j <= y.length; j++) {
      cur[j] = x[i - 1] === y[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    [prev, cur] = [cur, prev];
    cur.fill(0);
  }
  return x.length + y.length - 2 * prev[y.length];
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
