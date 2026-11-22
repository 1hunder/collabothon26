import { ApiError, authedFetch, errorFromResponse, isFixtureMode } from './client';
import { fixtureSseChunks } from './fixtures';
import type { DmEvent } from './types';
import { VOICE_KEY } from '../voice/context';

// "speaker" comes before the first token: who speaks, and the reply's audio id for the voice.
const eventNames = new Set(['status', 'speaker', 'token', 'card', 'state', 'done', 'error']);

/**
 * Incremental SSE parser. Feed it text chunks as they arrive; chunk boundaries may fall anywhere,
 * including inside a line or between "\r" and "\n".
 */
export function createSseParser(onEvent: (event: DmEvent) => void): (chunk: string) => void {
  let buffer = '';
  let eventName = 'message';
  let dataLines: string[] = [];

  const dispatch = (): void => {
    if (dataLines.length > 0 && eventNames.has(eventName)) {
      try {
        const data: unknown = JSON.parse(dataLines.join('\n'));
        onEvent({ event: eventName, data } as DmEvent);
      } catch {
        // malformed payload: skip the event
      }
    }
    eventName = 'message';
    dataLines = [];
  };

  const handleLine = (line: string): void => {
    if (line === '') {
      dispatch();
      return;
    }
    if (line.startsWith(':')) return;
    const sep = line.indexOf(':');
    const field = sep === -1 ? line : line.slice(0, sep);
    let value = sep === -1 ? '' : line.slice(sep + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') eventName = value;
    else if (field === 'data') dataLines.push(value);
  };

  return (chunk: string): void => {
    buffer += chunk;
    let idx: number;
    // A trailing "\r" may be half of a "\r\n" pair; wait for the next chunk to decide.
    while ((idx = buffer.search(/\r\n|\n|\r(?=.)/s)) !== -1) {
      const line = buffer.slice(0, idx);
      buffer = buffer.slice(buffer[idx] === '\r' && buffer[idx + 1] === '\n' ? idx + 2 : idx + 1);
      handleLine(line);
    }
  };
}

function fixtureStream(path: string, payload: unknown): Response {
  const chunks = fixtureSseChunks(path, payload);
  if (!chunks) return new Response(null, { status: 404 });
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

/** Voice on (the default) unless the player switched it off; read where the toggle stores it. */
export function voiceHeader(): Record<string, string> {
  let on = true;
  try {
    on = localStorage.getItem(VOICE_KEY) !== 'off';
  } catch {
    // storage blocked: voice stays on, like the toggle
  }
  return { 'X-Voice': on ? 'on' : 'off' };
}

/**
 * POST and consume an SSE response, calling onEvent for each parsed event. ``X-Voice`` tells the
 * server whether to start the reply's speech as soon as the text is final (before it streams).
 */
export async function postSse(
  path: string,
  body: unknown,
  onEvent: (event: DmEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = isFixtureMode() ? fixtureStream(path, body) : await authedFetch('POST', path, body, signal, voiceHeader());
  if (!res.ok) throw await errorFromResponse(res);
  if (!res.body) throw new ApiError('Server', res.status);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const push = createSseParser(onEvent);
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    push(value);
  }
}
