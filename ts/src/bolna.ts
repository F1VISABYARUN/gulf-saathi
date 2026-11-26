// Place outbound calls through Bolna's API. Port of gulf_saathi/bolna.py.
//
// POST /call with agent_id, recipient_phone_number, optional scheduled_at and user_data. Used on live
// calls from the dashboard ("Call now": arrival and weekly check-ins, Oct 2026). Seen so far: Bolna
// placed booked calls at once, so scheduled_at may be ignored; automatic repeat calls are therefore off
// by default.
import { isoUtc } from './db.js';
import { pyStr } from './py.js';

export const apiUrl = () => process.env.BOLNA_API_URL || 'https://api.bolna.ai';
export const apiKey = () => process.env.BOLNA_API_KEY ?? '';
/** The Bolna agent that makes arrival and weekly check-in calls. */
export const checkinAgentId = () => process.env.BOLNA_CHECKIN_AGENT_ID ?? '';
export const configured = () => Boolean(apiKey() && checkinAgentId());

export interface CallResult { ok: boolean; execution_id: string | null; error: string | null }

// Tests swap this out so no real call is ever placed.
export const hooks: { fetch: typeof fetch } = { fetch: (...a) => fetch(...a) };

export async function placeCall(phone: string, userData: Record<string, unknown>, scheduledAt: Date | null = null,
  agentId = ''): Promise<CallResult> {
  agentId = agentId || checkinAgentId();
  if (!(apiKey() && agentId)) {
    return { ok: false, execution_id: null, error: 'Bolna not configured (BOLNA_API_KEY / BOLNA_CHECKIN_AGENT_ID)' };
  }
  const body: Record<string, unknown> = {
    agent_id: agentId,
    recipient_phone_number: phone,
    // Bolna gives these to the agent's prompt as variables and returns them in
    // context_details.recipient_data, which is how the webhook finds the case.
    user_data: Object.fromEntries(Object.entries(userData).map(([k, v]) => [k, v === null || v === undefined ? '' : pyStr(v)])),
  };
  if (scheduledAt) body.scheduled_at = isoUtc(scheduledAt);
  let r: Response;
  try {
    r = await hooks.fetch(`${apiUrl()}/call`, {
      method: 'POST', body: JSON.stringify(body), signal: AbortSignal.timeout(8000),
      headers: { Authorization: `Bearer ${apiKey()}`, 'Content-Type': 'application/json' },
    });
  } catch (e) {
    return { ok: false, execution_id: null, error: `Bolna unreachable: ${(e as Error).message}` };
  }
  const text = await r.text();
  if (r.status >= 300) return { ok: false, execution_id: null, error: `Bolna ${r.status}: ${text.slice(0, 300)}` };
  const data = text ? JSON.parse(text) : {};
  return { ok: true, execution_id: data.execution_id || data.id || null, error: null };
}
