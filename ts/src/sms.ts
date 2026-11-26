// Family SMS. Port of gulf_saathi/sms.py. Sends through Plivo when it is configured; otherwise demo
// mode: nothing is sent and the dashboard shows the text that would have gone out.
//
// Commercial SMS to Indian numbers needs DLT registration, so expect demo mode until that is done. The
// Plivo request below is untested from this code.
export const provider = () =>
  process.env.PLIVO_AUTH_ID && process.env.PLIVO_AUTH_TOKEN && process.env.PLIVO_FROM ? 'plivo' : 'demo';

export const hooks: { fetch: typeof fetch } = { fetch: (...a) => fetch(...a) };

/** Returns a short status for the dashboard: "sent", "demo: not sent" or "failed: ...". */
export async function sendSms(to: string, text: string): Promise<string> {
  if (!to) return 'failed: no family number';
  if (provider() === 'demo') return 'demo: not sent (no SMS provider configured)';
  const id = process.env.PLIVO_AUTH_ID!, token = process.env.PLIVO_AUTH_TOKEN!;
  let r: Response;
  try {
    r = await hooks.fetch(`https://api.plivo.com/v1/Account/${id}/Message/`, {
      method: 'POST', signal: AbortSignal.timeout(5000),
      headers: { Authorization: 'Basic ' + Buffer.from(`${id}:${token}`).toString('base64'), 'Content-Type': 'application/json' },
      body: JSON.stringify({ src: process.env.PLIVO_FROM, dst: to, text }),
    });
  } catch (e) {
    return `failed: ${(e as Error).message}`;
  }
  return r.status < 300 ? 'sent' : `failed: Plivo ${r.status}`;
}
