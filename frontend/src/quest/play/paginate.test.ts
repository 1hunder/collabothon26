import { splitPages } from './paginate';

const sentence = (n: number, tag: string): string => `${Array.from({ length: n }, (_, i) => `${tag}${i}`).join(' ')}.`;
const words = (s: string): number => s.split(' ').length;

describe('splitPages', () => {
  it('keeps a short reply on one page', () => {
    expect(splitPages('One. Two.')).toEqual(['One. Two.']);
  });

  it('never exceeds 50 words and breaks only at sentence boundaries', () => {
    const text = [sentence(30, 'a'), sentence(30, 'b'), sentence(30, 'c')].join(' ');
    const pages = splitPages(text);
    expect(pages).toHaveLength(3);
    for (const p of pages) {
      expect(words(p)).toBeLessThanOrEqual(50);
      expect(p.endsWith('.')).toBe(true);
    }
    expect(pages.join(' ')).toBe(text);
  });

  it('packs sentences up to the limit before starting a new page', () => {
    const pages = splitPages([sentence(25, 'a'), sentence(25, 'b'), sentence(25, 'c')].join(' '));
    expect(pages.map(words)).toEqual([50, 25]);
  });

  it('cuts a single over-long sentence at word boundaries as a last resort', () => {
    const pages = splitPages(sentence(120, 'w'));
    expect(pages.map(words)).toEqual([50, 50, 20]);
  });

  it('returns one empty page for empty text', () => {
    expect(splitPages('   ')).toEqual(['']);
  });
});

describe('splitPages with decimals and abbreviations', () => {
  const samples = [
    'The price rose to 3000.807 gold pieces. Then it fell 6.7 percent. Nobody knew why, e.g. the board.',
    'Revenue was 1.5 billion, i.e. 1500.25 million. Done.',
    `${'Growth of 3.14 percent was seen. '.repeat(30)}End at 99.9.`,
  ];
  it.each(samples)('join(pages) equals the original', (text) => {
    expect(splitPages(text).join(' ')).toBe(text.replace(/\s+/g, ' ').trim());
  });
  it('never splits inside a number', () => {
    for (const p of splitPages(samples[2] ?? '')) expect(p).not.toMatch(/\d\. \d/);
    expect(splitPages('Cost 3000.807 now. Next.')).toEqual(['Cost 3000.807 now. Next.']);
  });
});
