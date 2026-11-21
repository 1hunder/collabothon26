import { useCallback, useEffect, useReducer, useRef } from 'react';
import { postSse } from './sse';
import type { DmEvent } from './types';

/** First event must arrive within this window or the thread counts as lost. */
export const FIRST_EVENT_TIMEOUT_MS = 15_000;

export interface DmCard {
  kind: 'dice' | 'news';
  [field: string]: unknown;
}

export type DmStreamState =
  | { phase: 'idle' }
  | { phase: 'sending'; clientMsgId: string }
  | { phase: 'streaming'; clientMsgId: string; status: string | null; text: string; cards: DmCard[]; canDecide: boolean | null }
  | { phase: 'lost'; clientMsgId: string; reason: string }
  | {
      phase: 'done';
      clientMsgId: string;
      text: string;
      cards: DmCard[];
      audioTextId: number | string | null;
      canDecide: boolean | null;
      /** Every field of the `done` event (speaker, suggestions, ...). */
      extras: Record<string, unknown>;
    };

type Action =
  | { type: 'send'; clientMsgId: string }
  | { type: 'event'; event: DmEvent }
  | { type: 'lost'; reason: string }
  | { type: 'reset' };

export const initialDmState: DmStreamState = { phase: 'idle' };

export function dmReducer(state: DmStreamState, action: Action): DmStreamState {
  switch (action.type) {
    case 'send':
      return { phase: 'sending', clientMsgId: action.clientMsgId };
    case 'reset':
      return initialDmState;
    case 'lost':
      return state.phase === 'sending' || state.phase === 'streaming'
        ? { phase: 'lost', clientMsgId: state.clientMsgId, reason: action.reason }
        : state;
    case 'event': {
      if (state.phase !== 'sending' && state.phase !== 'streaming') return state;
      const current =
        state.phase === 'streaming'
          ? state
          : { phase: 'streaming' as const, clientMsgId: state.clientMsgId, status: null, text: '', cards: [], canDecide: null };
      const ev = action.event;
      switch (ev.event) {
        case 'status':
          return { ...current, status: ev.data.state };
        case 'token':
          return { ...current, text: current.text + ev.data.text };
        case 'card':
          return { ...current, cards: [...current.cards, ev.data as DmCard] };
        case 'state':
          return typeof ev.data.can_decide === 'boolean' ? { ...current, canDecide: ev.data.can_decide } : current;
        case 'done':
          return {
            phase: 'done',
            clientMsgId: current.clientMsgId,
            text: ev.data.text,
            cards: current.cards,
            audioTextId: ev.data.audio_text_id ?? null,
            canDecide: current.canDecide,
            extras: ev.data,
          };
        case 'error':
          return { phase: 'lost', clientMsgId: current.clientMsgId, reason: ev.data.message };
      }
    }
  }
}

function newMsgId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface DmDone {
  clientMsgId: string;
  text: string;
  cards: DmCard[];
  /** Every field of the `done` event (speaker, suggestions, ...). */
  extras: Record<string, unknown>;
}

export interface DmStream {
  state: DmStreamState;
  /** `to` overrides the default path for this request (retry reuses it). */
  send: (payload?: Record<string, unknown>, to?: string) => void;
  /** Resend the last request with the same client_msg_id (the server replays a stored reply). */
  retry: () => void;
  reset: () => void;
}

export function useDmStream(path: string, onDone?: (done: DmDone) => void): DmStream {
  const [state, dispatch] = useReducer(dmReducer, initialDmState);
  const last = useRef<{ payload: Record<string, unknown>; clientMsgId: string; path: string } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  });

  const clearTimer = useCallback((): void => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const run = useCallback(
    (payload: Record<string, unknown>, clientMsgId: string, target: string): void => {
      abort.current?.abort();
      clearTimer();
      const controller = new AbortController();
      abort.current = controller;
      last.current = { payload, clientMsgId, path: target };
      dispatch({ type: 'send', clientMsgId });
      const cards: DmCard[] = [];
      timer.current = setTimeout(() => {
        controller.abort();
        dispatch({ type: 'lost', reason: 'timeout' });
      }, FIRST_EVENT_TIMEOUT_MS);
      postSse(
        target,
        { ...payload, client_msg_id: clientMsgId },
        (event) => {
          if (controller.signal.aborted) return;
          clearTimer();
          dispatch({ type: 'event', event });
          if (event.event === 'card') cards.push(event.data as DmCard);
          if (event.event === 'done') onDoneRef.current?.({ clientMsgId, text: event.data.text, cards, extras: event.data });
        },
        controller.signal,
      )
        .then(() => {
          // A stream that closes without `done` is a lost thread (no-op once done).
          if (controller.signal.aborted) return;
          clearTimer();
          dispatch({ type: 'lost', reason: 'ended' });
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          clearTimer();
          dispatch({ type: 'lost', reason: 'network' });
        });
    },
    [clearTimer],
  );

  const send = useCallback(
    (payload: Record<string, unknown> = {}, to?: string): void => run(payload, newMsgId(), to ?? path),
    [run, path],
  );
  const retry = useCallback((): void => {
    if (last.current) run(last.current.payload, last.current.clientMsgId, last.current.path);
  }, [run]);
  const reset = useCallback((): void => {
    abort.current?.abort();
    clearTimer();
    dispatch({ type: 'reset' });
  }, [clearTimer]);

  useEffect(
    () => () => {
      abort.current?.abort();
      clearTimer();
    },
    [clearTimer],
  );

  return { state, send, retry, reset };
}
