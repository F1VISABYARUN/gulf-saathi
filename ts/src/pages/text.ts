// The fixed text and CSS of the web pages, exported from the Python modules by
// scripts/export_page_text.py, so both versions show exactly the same words.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
export const PAGES: { site: Record<string, any>; dashboard: Record<string, any> } =
  JSON.parse(readFileSync(join(HERE, '..', 'tables', 'pages.json'), 'utf8'));
