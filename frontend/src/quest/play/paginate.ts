export const MAX_PAGE_WORDS = 50;

const wordCount = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

/** Sentences keep their trailing punctuation and spacing is normalised to single spaces. */
function sentences(text: string): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  const out: string[] = [];
  let start = 0;
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i] ?? '';
    if (!'.!?…'.includes(ch)) continue;
    // A period between digits (3000.807) or inside an abbreviation (e.g., i.e.) is not a sentence end.
    if (ch === '.' && /\d/.test(clean[i - 1] ?? '') && /\d/.test(clean[i + 1] ?? '')) continue;
    if (ch === '.' && /(?:^|[\s(])(?:e\.g|i\.e|etc|vs|approx|Mr|Mrs|Dr|St|No)$/i.test(clean.slice(start, i))) continue;
    if (ch === '.' && /(?:^|[\s(])[a-z]$/i.test(clean.slice(start, i)) && /^[a-z]\./i.test(clean.slice(i + 1))) continue;
    let end = i + 1;
    while (end < clean.length && '.!?…'.includes(clean[end] ?? '')) end++;
    while (end < clean.length && `"'”’)`.includes(clean[end] ?? '')) end++;
    if (end < clean.length && clean[end] !== ' ') {
      i = end - 1;
      continue;
    }
    out.push(clean.slice(start, end).trim());
    start = end;
    i = end - 1;
  }
  if (start < clean.length) out.push(clean.slice(start).trim());
  return out.filter(Boolean);
}

/**
 * Split a reply into pages of at most `max` words, breaking at sentence boundaries. A single
 * sentence longer than `max` is cut at a word boundary as a last resort.
 */
export function splitPages(text: string, max: number = MAX_PAGE_WORDS): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean === '') return [''];
  const pages: string[] = [];
  let current: string[] = [];
  let count = 0;
  const flush = (): void => {
    if (current.length > 0) pages.push(current.join(' '));
    current = [];
    count = 0;
  };
  for (const sentence of sentences(clean)) {
    const n = wordCount(sentence);
    if (n > max) {
      flush();
      const words = sentence.split(' ');
      for (let i = 0; i < words.length; i += max) pages.push(words.slice(i, i + max).join(' '));
      continue;
    }
    if (count + n > max) flush();
    current.push(sentence);
    count += n;
  }
  flush();
  return pages;
}
