import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as sse from './sse';
import { dmReducer, FIRST_EVENT_TIMEOUT_MS, initialDmState, useDmStream } from './useDmStream';

describe('dmReducer', () => {
  it('goes idle -> sending -> streaming -> done', () => {
    let s = dmReducer(initialDmState, { type: 'send', clientMsgId: 'm1' });
    expect(s.phase).toBe('sending');
    s = dmReducer(s, { type: 'event', event: { event: 'status', data: { state: 'writing' } } });
    s = dmReducer(s, { type: 'event', event: { event: 'token', data: { text: 'Hi ' } } });
    s = dmReducer(s, { type: 'event', event: { event: 'token', data: { text: 'there' } } });
    expect(s).toMatchObject({ phase: 'streaming', text: 'Hi there', status: 'writing' });
    s = dmReducer(s, { type: 'event', event: { event: 'done', data: { text: 'Hi there' } } });
    expect(s).toMatchObject({ phase: 'done', text: 'Hi there' });
  });

  it('an error event loses the thread', () => {
    const s = dmReducer(
      { phase: 'sending', clientMsgId: 'm1' },
      { type: 'event', event: { event: 'error', data: { code: 'lost_thread', message: 'x' } } },
    );
    expect(s).toMatchObject({ phase: 'lost', clientMsgId: 'm1' });
  });
});

describe('useDmStream', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('is lost after 15 s without an event and retries with the same client_msg_id', async () => {
    const bodies: unknown[] = [];
    vi.spyOn(sse, 'postSse').mockImplementation((_path, body) => {
      bodies.push(body);
      return new Promise<void>(() => {});
    });
    const { result } = renderHook(() => useDmStream('/campaigns/c1/actions'));
    act(() => result.current.send({ text: 'look around' }));
    expect(result.current.state.phase).toBe('sending');
    act(() => {
      vi.advanceTimersByTime(FIRST_EVENT_TIMEOUT_MS - 1);
    });
    expect(result.current.state.phase).toBe('sending');
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.state.phase).toBe('lost');
    act(() => result.current.retry());
    expect(result.current.state.phase).toBe('sending');
    const [first, second] = bodies as { client_msg_id: string; text: string }[];
    expect(second?.client_msg_id).toBe(first?.client_msg_id);
    expect(second?.text).toBe('look around');
  });

  it('a first event clears the timeout', async () => {
    vi.spyOn(sse, 'postSse').mockImplementation((_path, _body, onEvent) => {
      onEvent({ event: 'status', data: { state: 'writing' } });
      return new Promise<void>(() => {});
    });
    const { result } = renderHook(() => useDmStream('/campaigns/c1/actions'));
    act(() => result.current.send({ text: 'hi' }));
    act(() => {
      vi.advanceTimersByTime(FIRST_EVENT_TIMEOUT_MS * 2);
    });
    expect(result.current.state.phase).toBe('streaming');
  });
});
