// A small test client, like FastAPI's TestClient: starts the app once and sends real HTTP requests.
import { after, before } from 'node:test';
import { listenForTests } from '../src/api.js';

export interface Reply { status: number; text: string; headers: Headers; json: () => any }
interface Opts { json?: unknown; body?: string; auth?: [string, string]; headers?: Record<string, string>; params?: Record<string, string> }

let base = '';
let close: () => Promise<void> = async () => {};
before(async () => { ({ base, close } = await listenForTests()); });
after(async () => { await close(); });

async function send(method: string, path: string, o: Opts = {}): Promise<Reply> {
  const headers: Record<string, string> = { ...(o.headers ?? {}) };
  if (o.auth) headers.Authorization = 'Basic ' + Buffer.from(o.auth.join(':')).toString('base64');
  let body: string | undefined = o.body;
  if (o.json !== undefined) { body = JSON.stringify(o.json); headers['Content-Type'] = 'application/json'; }
  const url = new URL(base + path);
  for (const [k, v] of Object.entries(o.params ?? {})) url.searchParams.set(k, v);
  const r = await fetch(url, { method, headers, body, redirect: 'manual' });
  const text = await r.text();
  return { status: r.status, text, headers: r.headers, json: () => JSON.parse(text) };
}

export const client = {
  get: (path: string, o?: Opts) => send('GET', path, o),
  post: (path: string, o?: Opts) => send('POST', path, o),
  head: (path: string, o?: Opts) => send('HEAD', path, o),
};
