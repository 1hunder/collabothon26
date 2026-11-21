import { createSseParser } from './sse';
import type { DmEvent } from './types';

const stream =
  'event: status\ndata: {"state":"writing"}\n\n' +
  'event: token\ndata: {"text":"Hel"}\n\n' +
  'event: token\r\ndata: {"text":"lo"}\r\n\r\n' +
  ': keep-alive\n\n' +
  'event: done\ndata: {"text":"Hello"}\n\n';

function parseWith(chunks: string[]): DmEvent[] {
  const out: DmEvent[] = [];
  const push = createSseParser((e) => out.push(e));
  chunks.forEach(push);
  return out;
}

describe('createSseParser', () => {
  const expected = parseWith([stream]);

  it('parses event and data lines', () => {
    expect(expected.map((e) => e.event)).toEqual(['status', 'token', 'token', 'done']);
    expect(expected[3]).toEqual({ event: 'done', data: { text: 'Hello' } });
  });

  it('gives the same events when split at every single character', () => {
    expect(parseWith(stream.split(''))).toEqual(expected);
  });

  it('gives the same events when split mid-line and mid-CRLF', () => {
    const cut = stream.indexOf('\r\n') + 1;
    expect(parseWith([stream.slice(0, 20), stream.slice(20, cut), stream.slice(cut)])).toEqual(expected);
  });

  it('ignores unknown events and malformed JSON', () => {
    const events = parseWith(['event: bogus\ndata: {}\n\nevent: token\ndata: {nope\n\nevent: token\ndata: {"text":"ok"}\n\n']);
    expect(events).toEqual([{ event: 'token', data: { text: 'ok' } }]);
  });
});

describe('postSse in fixture mode', () => {
  it('streams the scripted reply across chunk boundaries', async () => {
    vi.stubEnv('VITE_API_MODE', 'fixture');
    const { postSse } = await import('./sse');
    const events: DmEvent[] = [];
    await postSse('/campaigns/c1/opening', {}, (e) => events.push(e));
    vi.unstubAllEnvs();
    expect(events.map((e) => e.event)).toEqual(['status', 'token', 'token', 'state', 'done']);
  });
});
