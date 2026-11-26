// Telugu script to ITRANS, the same algorithm as indic_transliteration's _brahmic mapper,
// with its tables exported to data/telugu_itrans.json.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

interface Tables {
  vowel_marks: Record<string, string>; virama: Record<string, string>; consonants: string[];
  non_marks_viraama: Record<string, string>; max_key_length: number;
}

const HERE = dirname(fileURLToPath(import.meta.url));
const T: Tables = JSON.parse(readFileSync(join(HERE, 'tables', 'telugu_itrans.json'), 'utf8'));
const consonants = new Set(T.consonants);
const viramaOut = Object.values(T.virama)[0] ?? '';

export function teluguToItrans(input: string): string {
  const data = Array.from(input.replace(/ౝ/g, 'న్'));
  const buf: string[] = [];
  let i = 0;
  let hadConsonant = false;
  let found = false;
  while (i <= data.length) {
    let token = data.slice(i, i + T.max_key_length).join('');
    while (token) {
      const len = Array.from(token).length;
      if (len === 1) {
        if (Object.hasOwn(T.vowel_marks, token)) { buf.push(T.vowel_marks[token]); found = true; }
        else if (Object.hasOwn(T.virama, token)) { buf.push(T.virama[token]); found = true; }
        else {
          if (hadConsonant) buf.push('a');
          buf.push(Object.hasOwn(T.non_marks_viraama, token) ? T.non_marks_viraama[token] : token);
          found = true;
        }
      } else if (Object.hasOwn(T.non_marks_viraama, token)) {
        if (hadConsonant) buf.push('a');
        buf.push(T.non_marks_viraama[token]);
        found = true;
      }
      if (found) {
        hadConsonant = consonants.has(token);
        i += len;
        break;
      }
      token = Array.from(token).slice(0, -1).join('');
    }
    if (!found) {
      if (hadConsonant) buf.push(viramaOut);
      if (i < data.length) {
        buf.push(data[i]);
        hadConsonant = false;
      }
      i += 1;
    }
    found = false;
  }
  if (hadConsonant) buf.push('a');
  return buf.join('');
}

// Code points whose Unicode canonical combining class is not 0 (Python's unicodedata.combining).
const COMBINING: Array<[number, number]> = JSON.parse(readFileSync(join(HERE, 'tables', 'combining.json'), 'utf8'));

export function isCombining(ch: string): boolean {
  const cp = ch.codePointAt(0)!;
  let lo = 0, hi = COMBINING.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const [a, b] = COMBINING[mid];
    if (cp < a) hi = mid - 1;
    else if (cp > b) lo = mid + 1;
    else return true;
  }
  return false;
}
