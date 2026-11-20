export const MAX_PAGE_WORDS = 50;

const wordCount = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

/** Sentences keep their trailing punctuation and spacing is normalised to single spaces. */
function sentences(text: string): string[] {
  const parts = text.replace(/\s+/g, ' ').trim().match(/[^.!?…]+(?:[.!?…]+["'”’)]*|$)\s*/g);
  return (parts ?? [text]).map((s) => s.trim()).filter(Boolean);
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
