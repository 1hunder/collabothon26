import { VOICE_KEY } from '../voice/context';
import { createSseParser, voiceHeader } from './sse';
import { dmReducer, initialDmState } from './useDmStream';
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

describe('the speaker event and the voice header', () => {
  it('keeps the speaker event: who speaks and the audio id, before the first word', () => {
    const events = parseWith([
      'event: speaker\ndata: {"speaker":"Mira Fen","speaker_kind":"npc","audio_text_id":42,"audio_text":"Whole reply."}\n\n' +
        'event: token\ndata: {"text":"Whole "}\n\n',
    ]);
    expect(events[0]).toEqual({
      event: 'speaker',
      data: { speaker: 'Mira Fen', speaker_kind: 'npc', audio_text_id: 42, audio_text: 'Whole reply.' },
    });
  });

  it('the reducer keeps the audio id from the speaker event while the text streams', () => {
    let s = dmReducer(initialDmState, { type: 'send', clientMsgId: 'm1' });
    s = dmReducer(s, { type: 'event', event: { event: 'speaker', data: { speaker: 'Campaign Master', audio_text_id: 42, audio_text: 'Whole reply.' } } });
    s = dmReducer(s, { type: 'event', event: { event: 'token', data: { text: 'Whole ' } } });
    expect(s).toMatchObject({ phase: 'streaming', text: 'Whole ', audioTextId: 42, audioText: 'Whole reply.' });
  });

  it('tells the server whether voice is on (on unless switched off)', () => {
    localStorage.removeItem(VOICE_KEY);
    expect(voiceHeader()).toEqual({ 'X-Voice': 'on' });
    localStorage.setItem(VOICE_KEY, 'off');
    expect(voiceHeader()).toEqual({ 'X-Voice': 'off' });
    localStorage.removeItem(VOICE_KEY);
  });
});
