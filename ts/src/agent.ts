// Machine-readable Gulf Saathi: structured data (JSON-LD), Markdown versions of the public pages,
// the About / Contact / Terms pages, a small read-only MCP server and its server card, and WebMCP tools.
// Everything here describes facts already on the public site; nothing here touches case data.
import { pyStr } from './py.js';
import { PAGES } from './pages/text.js';

const S = PAGES.site;
export const REPO_URL = 'https://github.com/F1VISABYARUN/gulf-saathi';
export const VERSION = '1.0.0';

/** The public address. Set GS_PUBLIC_URL in hPanel once your own domain is connected. */
export const publicUrl = () =>
  (process.env.GS_PUBLIC_URL || 'https://nimble-saddlebrown-kudu-33.hostingersite.com').trim().replace(/\/+$/, '');

/** A team contact email for the public pages, from GS_CONTACT_EMAIL. Empty until it is set. */
export function contactEmail(): string {
  const e = (process.env.GS_CONTACT_EMAIL ?? '').trim();
  return /^[^\s@<>"']+@[^\s@<>"']+\.[a-z]{2,}$/i.test(e) ? e : '';
}

/** Public profiles of the project (GS_SAME_AS, https links separated by commas), plus the source repository. */
export function sameAs(): string[] {
  const extra = (process.env.GS_SAME_AS ?? '').split(',').map((x) => x.trim()).filter((x) => /^https:\/\/[^\s"<>]+$/.test(x));
  return [...new Set([...extra, REPO_URL])];
}

/** The help-line number as [tel: link, shown], only once GS_HELPLINE_NUMBER is set (after a good test call). */
export function helplineTel(): [string, string] {
  const digits = (process.env.GS_HELPLINE_NUMBER ?? '').replace(/[\s+()-]/gu, '');
  if (!/^\d{10,15}$/.test(digits)) return ['', ''];
  const shown = digits.startsWith('91') && digits.length === 12 ? `+91 ${digits.slice(2, 7)} ${digits.slice(7)}` : '+' + digits;
  return [`tel:+${digits}`, shown];
}

const DESCRIPTION = 'A Telugu phone line and case system for people from Telangana who go to work in Gulf countries, ' +
  'and for their families. It checks recruiting agents, fees and visas before a worker pays, calls workers on arrival ' +
  'day and every week, and turns trouble into a ready case file for a caseworker.';

/** JSON-LD for a public page: the organisation, the website, the page and the service. */
export function jsonLd(path: string, title: string, description: string): string {
  const base = publicUrl();
  const [tel] = helplineTel();
  const email = contactEmail();
  const contactPoint = tel || email ? [{
    '@type': 'ContactPoint', contactType: 'customer support', areaServed: ['IN', 'AE', 'SA', 'OM', 'QA', 'KW', 'BH'],
    availableLanguage: ['te', 'en'], ...(tel ? { telephone: tel.slice(4) } : {}), ...(email ? { email } : {}),
  }] : undefined;
  const org = {
    '@type': 'Organization', '@id': `${base}/#organization`, name: 'Gulf Saathi', alternateName: 'గల్ఫ్ సాథి',
    url: `${base}/`, logo: `${base}/gulf-saathi-poster-960.jpg`, description: DESCRIPTION,
    areaServed: { '@type': 'State', name: 'Telangana, India' }, knowsLanguage: ['te', 'en'],
    sameAs: sameAs(), ...(email ? { email } : {}), ...(tel ? { telephone: tel.slice(4) } : {}),
    ...(contactPoint ? { contactPoint } : {}),
  };
  const graph = [
    org,
    { '@type': 'WebSite', '@id': `${base}/#website`, url: `${base}/`, name: 'Gulf Saathi', inLanguage: ['en', 'te'],
      publisher: { '@id': `${base}/#organization` } },
    { '@type': 'WebPage', '@id': `${base}${path}#webpage`, url: `${base}${path}`, name: title, description,
      isPartOf: { '@id': `${base}/#website` }, about: { '@id': `${base}/#organization` }, inLanguage: 'en' },
    { '@type': 'Service', '@id': `${base}/#service`, name: 'Gulf Saathi Telugu phone line', serviceType: 'Migrant worker support helpline',
      provider: { '@id': `${base}/#organization` }, areaServed: { '@type': 'State', name: 'Telangana, India' },
      availableLanguage: 'te', description: 'Checks a recruiting agent against the MEA eMigrate list of licensed agents, adds up ' +
        'payments against the legal limit of ₹35,400, flags a visit visa offered for a job, and calls the worker on arrival day ' +
        'and every week. Fixed rules, not the AI, set the risk level.' },
  ];
  // Escape "<" so the JSON can never close the script tag.
  return `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@graph': graph }).replace(/</g, '\\u003c')}</script>`;
}

/** Extra <head> tags for a public page: canonical address, Markdown alternate, llms.txt, structured data. */
export function headTags(path: string, title: string, description: string): string {
  const base = publicUrl();
  const md = path === '/' ? '/index.md' : `${path}.md`;
  return `<link rel="canonical" href="${base}${path}"><link rel="alternate" type="text/markdown" href="${md}">` +
    `<link rel="describedby" type="text/plain" href="/llms.txt">${jsonLd(path, title, description)}`;
}

const contactMd = () => {
  const [tel, shown] = helplineTel();
  const email = contactEmail();
  const lines = [
    ...(tel ? [`- Help line (Telugu): [${shown}](${tel})`] : []),
    ...(email ? [`- Email: [${email}](mailto:${email})`] : []),
  ];
  return lines.length ? lines.join('\n') : '- Contact details are being set up. Until then, see the demo story or the source repository.';
};

/** Markdown versions of the public pages, for agents that ask for text/markdown. */
export function markdown(path: string): string | null {
  const base = publicUrl();
  const nav = `[Home](${base}/) · [Demo story](${base}/demo) · [About](${base}/about) · [Contact](${base}/contact) · [Terms and privacy](${base}/terms)`;
  if (path === '/' || path === '/index') {
    const steps = (S.STEPS as string[][]).map(([en, , text]) => `- **${en}:** ${text}`).join('\n');
    const stats = (S.STATS as string[][]).map(([n, text, src, url]) => `- **${n}** ${text} Source: [${src}](${url})`).join('\n');
    return `# Gulf Saathi (గల్ఫ్ సాథి)

> ${DESCRIPTION}

${nav}

## How it works
One phone number, in Telugu, at every step of the journey. No app, no reading needed.

${steps}

The AI only writes down what was said. Fixed rules decide the risk level.

## The problem, in numbers
${stats}

## Status
Built and tested with test calls. A pilot with Gulf worker families in Jagtial district, Telangana, is starting.
Voice by Bolna, Telugu speech by Sarvam. Gulf Saathi is a help line, not a government body.

## Contact
${contactMd()}

## For agents
- [llms.txt](${base}/llms.txt) · [MCP server card](${base}/.well-known/mcp/server-card.json)
- Public read-only checks: \`GET ${base}/check-agent?agency=&owner=&district=\` and \`GET ${base}/check-fee?payments=10000;25000\`
`;
  }
  if (path === '/demo') {
    return `# The demo story

${nav}

Three made-up workers, from the first call to the case file. No password needed; no real call or SMS is made.

${(S.DEMO_PEOPLE as Array<Record<string, any>>).map((p) => `## ${p.name} (${p.te})
${p.who}

${(p.facts as string[][]).map(([k, v]) => `- ${k}: ${v}`).join('\n')}

What Saathi catches:
${(p.caught as string[]).map((c) => `- ${c}`).join('\n')}`).join('\n\n')}

Run it at ${base}/demo.
`;
  }
  const page = PUBLIC_PAGES[path];
  return page ? `# ${page.title}\n\n${nav}\n\n${page.md()}\n` : null;
}

interface InfoPage { title: string; description: string; md: () => string }

/** About, Contact and Terms: short, plain, and only what is true today. */
export const PUBLIC_PAGES: Record<string, InfoPage> = {
  '/about': {
    title: 'About Gulf Saathi',
    description: 'What Gulf Saathi is, who it is for, and how it started.',
    md: () => `Gulf Saathi is a Telugu phone line and case system for people from Telangana who go to work in Gulf countries, and for their families.

- **Before paying an agent:** it checks the agent's name against the MEA eMigrate list of licensed recruiting agents, adds up every payment against the legal limit of ₹35,400, and flags a visit visa offered for a job.
- **After the worker flies:** it calls on arrival day and every week (salary, passport, food, threats, the promised job and city).
- **When something is wrong:** a caseworker gets a ready English case file for MADAD, the Indian Embassy or Pravasi Prajavani, and a Telugu message for the family is prepared.

**How it started.** We sat in on Pravasi Prajavani, the Gulf workers' grievance desk at Praja Bhavan, Hyderabad, and heard real cases from families: wrong jobs, unpaid wages, and months of waiting for papers. Gulf Saathi was built for the Bolna Buildathon 2026.

**Status (November 2026).** Built and tested with test calls. A pilot with Gulf worker families in Jagtial district, Telangana, is starting.

**What it is not.** Gulf Saathi is a help line, not a government body. It never vouches for an agent, and it never promises rescue or money back. A trained caseworker decides and acts.

Voice by Bolna, Telugu speech by Sarvam. Source code: ${REPO_URL}`,
  },
  '/contact': {
    title: 'Contact Gulf Saathi',
    description: 'How to reach the Gulf Saathi team.',
    md: () => `${contactMd()}

If a worker abroad is in danger right now, the family can also contact the Indian Embassy or Consulate in that country, or register a grievance on MADAD (madad.gov.in).`,
  },
  '/terms': {
    title: 'Terms of use and privacy',
    description: 'How Gulf Saathi uses the information callers give, and the limits of the service.',
    md: () => `These are the plain terms of the Gulf Saathi service. They are not legal advice.

## The service
- Gulf Saathi is a help line, not a government body, a recruiting agency or a lawyer.
- The agent and fee checks compare what you tell us with public lists and rules. A match is not a verdict on an agent, and no match does not prove wrongdoing.
- Saathi never promises rescue, money back, or that anyone will come. A trained caseworker decides what to do.

## Calls and information
- Calls are recorded, and every call says so at the start.
- We keep what callers tell us (names, phone numbers, employer, agent, payments, what happened) in a case, so a caseworker can help and an official can act.
- Real cases are seen only by the Gulf Saathi team, behind a password, and are shared with officials (for example the Indian Embassy or Pravasi Prajavani) only to help the worker.
- We never store passport numbers, bank details or OTPs, and we never sell worker data.
- Weekly scam alerts go only to people who agreed to receive them. Alerts warn about patterns and never name a person or a phone number.
- The demo story uses made-up people only.

## Questions
${contactMd()}`,
  },
};

// --- a small, read-only MCP server (JSON-RPC over HTTP) ------------------------------------

export const MCP_TOOLS = [
  { name: 'check_recruiting_agent',
    description: 'Check whether an Indian recruiting agent appears in the MEA eMigrate list of licensed agents. ' +
      'Give the agency name, the owner name, or both, and the district if known. The result is not a verdict on any agent.',
    inputSchema: { type: 'object', properties: {
      agency: { type: 'string', description: 'Agency name, e.g. Gagan Manpower' },
      owner: { type: 'string', description: 'Owner name' },
      district: { type: 'string', description: 'District of the agency, e.g. Jagtial' },
      licence_no: { type: 'string', description: 'Licence / RA number, if known' } } } },
  { name: 'check_recruitment_fee',
    description: 'Add up every payment made to a recruiting agent and compare it with the legal limit for Indian ' +
      'emigrant workers (₹30,000 + 18% GST = ₹35,400).',
    inputSchema: { type: 'object', required: ['payments'], properties: {
      payments: { type: 'string', description: 'Each payment in rupees, separated by semicolons, e.g. "50000; 30000"' } } } },
];

export function serverCard() {
  const base = publicUrl();
  return {
    name: 'gulf-saathi', title: 'Gulf Saathi', version: VERSION,
    description: 'Read-only checks from Gulf Saathi, the Telugu phone line for Gulf migrant workers from Telangana: ' +
      'is a recruiting agent in the licensed list, and is a fee over the legal limit.',
    websiteUrl: `${base}/`,
    endpoint: `${base}/mcp`,
    remotes: [{ type: 'streamable-http', url: `${base}/mcp` }],
    protocolVersion: '2025-06-18',
    capabilities: { tools: { listChanged: false } },
    tools: MCP_TOOLS.map(({ name, description }) => ({ name, description })),
    authentication: { required: false },
    contact: contactEmail() || undefined,
    repository: REPO_URL,
  };
}

type Checks = { agent: (f: Record<string, string>) => unknown; fee: (payments: string) => unknown };

/** One JSON-RPC request to the MCP server. Returns null for notifications (no reply). */
export function mcpReply(msg: any, checks: Checks): object | null {
  const id = msg && Object.hasOwn(msg, 'id') ? msg.id : null;
  const ok = (result: object) => ({ jsonrpc: '2.0', id, result });
  const fail = (code: number, message: string) => ({ jsonrpc: '2.0', id, error: { code, message } });
  if (!msg || msg.jsonrpc !== '2.0' || typeof msg.method !== 'string') return fail(-32600, 'Invalid Request');
  if (id === null && msg.method.startsWith('notifications/')) return null;
  switch (msg.method) {
    case 'initialize':
      return ok({ protocolVersion: '2025-06-18', capabilities: { tools: { listChanged: false } },
        serverInfo: { name: 'gulf-saathi', title: 'Gulf Saathi', version: VERSION },
        instructions: 'Read-only checks. Results are not a verdict on any agent; a caseworker decides.' });
    case 'ping':
      return ok({});
    case 'tools/list':
      return ok({ tools: MCP_TOOLS });
    case 'tools/call': {
      const name = msg.params?.name;
      const args = (msg.params?.arguments ?? {}) as Record<string, unknown>;
      const str = (k: string) => (args[k] === undefined || args[k] === null ? '' : pyStr(args[k]).slice(0, 300));
      let out: unknown;
      if (name === 'check_recruiting_agent') {
        out = checks.agent({ agency: str('agency'), owner: str('owner'), district: str('district'), licence_no: str('licence_no'), query: '' });
      } else if (name === 'check_recruitment_fee') {
        out = checks.fee(str('payments'));
      } else {
        return fail(-32602, `Unknown tool: ${pyStr(name)}`);
      }
      return ok({ content: [{ type: 'text', text: JSON.stringify(out) }], structuredContent: out, isError: false });
    }
    default:
      return fail(-32601, 'Method not found');
  }
}

/** WebMCP: the same two checks, offered to agents running inside the visitor's browser. */
export const WEBMCP_SCRIPT = `<script>
(() => {
  const mc = navigator.modelContext;
  if (!mc || typeof mc.registerTool !== 'function') return;
  const call = async (path, input) => {
    const r = await fetch(path + '?' + new URLSearchParams(Object.entries(input || {}).filter(([, v]) => v != null && v !== '')));
    return { content: [{ type: 'text', text: await r.text() }] };
  };
  const tools = ${JSON.stringify(MCP_TOOLS)};
  try {
    mc.registerTool({ ...tools[0], execute: (input) => call('/check-agent', input) });
    mc.registerTool({ ...tools[1], execute: (input) => call('/check-fee', input) });
  } catch (e) { /* the page works the same without it */ }
})();
</script>`;

/** Just enough Markdown for the info pages: headings, bullet lists, paragraphs, **bold**, links and bare URLs. */
export function markdownToHtml(md: string): string {
  const escape = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const inline = (t: string) => escape(t)
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/\[([^\]]+)\]\(((?:https?:|mailto:|tel:|\/)[^)\s]*)\)/g, '<a href="$2">$1</a>')
    .replace(/(^|[\s(])(https:\/\/[^\s<)]+)/g, '$1<a href="$2">$2</a>');
  const out: string[] = [];
  let list: string[] = [];
  const flush = () => { if (list.length) { out.push(`<ul>${list.map((x) => `<li>${x}</li>`).join('')}</ul>`); list = []; } };
  for (const block of md.split(/\n{2,}/)) {
    for (const line of block.split('\n')) {
      if (/^- /.test(line)) { list.push(inline(line.slice(2))); continue; }
      flush();
      if (/^## /.test(line)) out.push(`<h2>${inline(line.slice(3))}</h2>`);
      else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
    flush();
  }
  return out.join('\n');
}
