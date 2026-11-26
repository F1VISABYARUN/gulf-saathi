import { truthy } from './py.js';

// Read what Bolna sends after a call. Field names follow a real execution record from our
// own agent (tests/fixtures/bolna_execution_2026-10-20.json).

// Bolna sends several webhooks per call (initiated, ringing, in-progress, call-disconnected).
// Only these statuses end it.
export const TERMINAL_STATUSES = new Set(['completed', 'call-disconnected', 'no-answer', 'busy', 'failed', 'canceled',
  'stopped', 'error', 'balance-low']);
// "call-disconnected" may arrive before the transcript: then wait for "completed".
export const NEEDS_TRANSCRIPT = new Set(['call-disconnected']);

type Obj = Record<string, any>;

function get(d: unknown, ...path: string[]): any {
  let cur: any = d;
  for (const key of path) {
    if (!cur || typeof cur !== 'object' || Array.isArray(cur)) return null;
    cur = cur[key] ?? null;
  }
  return cur;
}

const pyText = (v: unknown) => (v === null || v === undefined || v === '' || v === false || v === 0 ? '' : String(v));

/** "completed" does not mean someone spoke: answered = longer than 0 s AND a caller line. */
export function wasAnswered(payload: Obj): boolean {
  let duration = 0;
  const raw = payload.conversation_duration;
  if (raw !== null && raw !== undefined && raw !== '' && raw !== false && raw !== 0) {
    const n = Number(raw);
    duration = Number.isFinite(n) ? n : 0;
  }
  const transcript = pyText(payload.transcript);
  const spoke = transcript.split(/\r\n|\r|\n/).some((line) => {
    const l = line.trim();
    return l.toLowerCase().startsWith('user:') && l.slice(5).trim().length > 0;
  });
  return duration > 0 && spoke;
}

export interface ParsedCall {
  call_id: any; agent_id: any; status: string; terminal: boolean; answered: boolean; missed: boolean;
  duration_seconds: any; transcript: string; recording_url: any; user_number: any; hangup_by: any;
  hangup_reason: any; recipient_data: Obj; extracted: Obj;
}

export function parseCall(payload: Obj): ParsedCall {
  const status = pyText(payload.status).toLowerCase();
  let terminal = TERMINAL_STATUSES.has(status);
  if (NEEDS_TRANSCRIPT.has(status) && !pyText(payload.transcript).trim()) terminal = false;
  const answered = terminal ? wasAnswered(payload) : false;
  const extracted = payload.extracted_data;
  const rd = get(payload, 'context_details', 'recipient_data');
  return {
    call_id: payload.id ?? null,
    agent_id: payload.agent_id ?? null,
    status,
    terminal,
    answered,
    missed: terminal && !answered,
    duration_seconds: payload.conversation_duration ?? null,
    transcript: pyText(payload.transcript),
    recording_url: get(payload, 'telephony_data', 'recording_url'),
    user_number: payload.user_number || get(payload, 'telephony_data', 'to_number'),
    hangup_by: get(payload, 'telephony_data', 'hangup_by'),
    hangup_reason: get(payload, 'telephony_data', 'hangup_reason'),
    recipient_data: truthy(rd) ? rd : {},
    extracted: extracted && typeof extracted === 'object' && !Array.isArray(extracted) ? extracted : {},
  };
}
