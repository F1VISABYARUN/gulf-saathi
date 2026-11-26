// Storage for worker cases, calls, check-ins and escalations. Port of gulf_saathi/db.py.
//
// SupabaseStore talks to Supabase's REST API with the server-side secret key. MemoryStore keeps rows
// in arrays, for tests and for running locally without Supabase. Both offer the same five calls: get,
// select, insert, update, upsert. Unlike Python, every call is async (fetch is async in Node).
import { randomUUID } from 'node:crypto';
import { pySorted } from './py.js';

export type Row = Record<string, any>;

export const TABLES = ['workers', 'calls', 'checkins', 'escalations', 'contact_reports', 'scam_alerts'] as const;
// Tables whose primary key the database generates (calls use Bolna's execution id).
export const GENERATED_IDS = new Set(['workers', 'checkins', 'escalations', 'contact_reports', 'scam_alerts']);

export class StoreError extends Error {}

/** Python datetime.isoformat() for a UTC time: "2026-10-25T04:00:00.123000+00:00". */
export function isoUtc(d: Date): string {
  const s = d.toISOString(); // 2026-10-25T04:00:00.123Z
  const ms = d.getUTCMilliseconds();
  return (ms ? s.slice(0, 19) + '.' + String(ms).padStart(3, '0') + '000' : s.slice(0, 19)) + '+00:00';
}

export const nowIso = () => isoUtc(new Date());

export interface SelectOpts { order?: string; desc?: boolean; limit?: number | null }

export interface Store {
  readonly kind: 'memory' | 'supabase';
  select(table: string, match?: Row | null, opts?: SelectOpts): Promise<Row[]>;
  get(table: string, match: Row): Promise<Row | null>;
  insert(table: string, row: Row): Promise<Row>;
  update(table: string, match: Row, changes: Row): Promise<Row[]>;
  upsert(table: string, row: Row, key?: string): Promise<Row>;
}

const copy = (r: Row): Row => ({ ...r });
const eq = (a: unknown, b: unknown) => a === b || ((a === undefined || a === null) && (b === undefined || b === null));

export class MemoryStore implements Store {
  readonly kind = 'memory' as const;
  tables: Record<string, Row[]> = Object.fromEntries(TABLES.map((t) => [t, []]));

  private static matches(row: Row, match: Row): boolean {
    return Object.entries(match).every(([k, v]) => eq(row[k], v));
  }

  private rows(table: string): Row[] {
    const t = this.tables[table];
    if (!t) throw new Error(`KeyError: '${table}'`);
    return t;
  }

  async select(table: string, match: Row | null = null, { order = 'created_at', desc = true, limit = null }: SelectOpts = {}) {
    const rows = this.rows(table).filter((r) => MemoryStore.matches(r, match ?? {})).map(copy);
    const sorted = pySorted(rows, (r) => r[order] || '', desc);
    return limit ? sorted.slice(0, limit) : sorted;
  }

  async get(table: string, match: Row) {
    const rows = await this.select(table, match, { limit: 1 });
    return rows[0] ?? null;
  }

  async insert(table: string, row: Row) {
    const r = copy(row);
    if (GENERATED_IDS.has(table) && !Object.hasOwn(r, 'id')) r.id = randomUUID();
    if (!Object.hasOwn(r, 'created_at')) r.created_at = nowIso();
    this.rows(table).push(r);
    return copy(r);
  }

  async update(table: string, match: Row, changes: Row) {
    const out: Row[] = [];
    for (const r of this.rows(table)) {
      if (MemoryStore.matches(r, match)) {
        Object.assign(r, changes);
        out.push(copy(r));
      }
    }
    return out;
  }

  async upsert(table: string, row: Row, key = 'id') {
    const existing = this.rows(table).find((r) => eq(r[key], row[key]));
    if (existing) {
      Object.assign(existing, row);
      return copy(existing);
    }
    return this.insert(table, row);
  }
}

/** A PostgREST filter value, written the way Python's f"eq.{v}" writes it. */
const pyFilter = (v: unknown) => `eq.${v === null || v === undefined ? 'None' : typeof v === 'boolean' ? (v ? 'True' : 'False') : String(v)}`;

export class SupabaseStore implements Store {
  readonly kind = 'supabase' as const;
  private base: string;
  private headers: Record<string, string>;

  constructor(url: string, key: string, private timeoutMs = 5000) {
    this.base = url.replace(/\/+$/, '') + '/rest/v1/';
    this.headers = { apikey: key, 'Content-Type': 'application/json' };
    // Older keys are JWTs ("eyJ...") and also go in Authorization. The newer sb_secret_ keys are not
    // JWTs and go in the apikey header only.
    if (key.startsWith('eyJ')) this.headers.Authorization = `Bearer ${key}`;
  }

  static fromEnv(): SupabaseStore | null {
    const url = process.env.SUPABASE_URL ?? '';
    const names = ['SUPABASE_SERVICE_KEY', 'SUPABASE_SECRET_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_KEY'];
    const key = names.map((n) => process.env[n]).find((v) => v) ?? '';
    return url && key ? new SupabaseStore(url, key) : null;
  }

  private async send(method: string, table: string, params: Record<string, string>, body?: unknown, extra: Record<string, string> = {}) {
    const qs = new URLSearchParams(params).toString();
    let r: Response;
    try {
      r = await fetch(this.base + table + (qs ? `?${qs}` : ''), {
        method, headers: { ...this.headers, ...extra }, body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (e) {
      throw new StoreError(`Supabase unreachable: ${(e as Error).message}`);
    }
    const text = await r.text();
    if (r.status >= 300) throw new StoreError(`Supabase ${r.status}: ${text.slice(0, 300)}`);
    return text ? JSON.parse(text) : null;
  }

  private static filters(match: Row | null | undefined): Record<string, string> {
    return Object.fromEntries(Object.entries(match ?? {}).map(([k, v]) => [k, pyFilter(v)]));
  }

  async select(table: string, match: Row | null = null, { order = 'created_at', desc = true, limit = null }: SelectOpts = {}) {
    const params: Record<string, string> = { select: '*', ...SupabaseStore.filters(match), order: `${order}.${desc ? 'desc' : 'asc'}` };
    if (limit) params.limit = String(limit);
    return (await this.send('GET', table, params)) ?? [];
  }

  async get(table: string, match: Row) {
    const rows = await this.select(table, match, { limit: 1 });
    return rows[0] ?? null;
  }

  async insert(table: string, row: Row) {
    return (await this.send('POST', table, {}, row, { Prefer: 'return=representation' }))[0];
  }

  async update(table: string, match: Row, changes: Row) {
    return (await this.send('PATCH', table, SupabaseStore.filters(match), changes, { Prefer: 'return=representation' })) ?? [];
  }

  async upsert(table: string, row: Row, key = 'id') {
    return (await this.send('POST', table, { on_conflict: key }, row,
      { Prefer: 'resolution=merge-duplicates,return=representation' }))[0];
  }
}
