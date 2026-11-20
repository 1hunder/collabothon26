import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { VOICE_KEY, VoiceProvider, VoiceToggle, useVoice } from '.';
import { AudioUrlProvider, WebSpeechProvider, type VoiceProvider as Impl } from './providers';

function fakeAudio() {
  const a = { src: '', currentTime: 0, onerror: null as null | (() => void), play: vi.fn(() => Promise.resolve()), pause: vi.fn() };
  return a as unknown as HTMLAudioElement & typeof a;
}

function fakeImpl(): Impl & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    unlock: () => void calls.push('unlock'),
    speak: (_id, text, voice) => void calls.push(`speak:${voice}:${text}`),
    stop: () => void calls.push('stop'),
  };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe('AudioUrlProvider', () => {
  it('unlock plays silence on one reused element; speak reuses it with the tts url', () => {
    const audio = fakeAudio();
    const make = vi.fn(() => audio);
    const p = new AudioUrlProvider(null, make);
    p.unlock();
    expect(audio.play).toHaveBeenCalledTimes(1);
    expect(audio.src).toMatch(/^data:audio\/wav/);
    p.speak('abc', 'hi', 'buddy');
    expect(make).toHaveBeenCalledTimes(1);
    expect(audio.src).toMatch(/\/tts\/abc\?voice=buddy$/);
    expect(audio.play).toHaveBeenCalledTimes(2);
  });

  it('stop pauses the element and the fallback', () => {
    const audio = fakeAudio();
    const fb = fakeImpl();
    const p = new AudioUrlProvider(fb, () => audio);
    p.speak('abc', 'hi', 'dm');
    p.stop();
    expect(audio.pause).toHaveBeenCalled();
    expect(fb.calls).toContain('stop');
  });

  it('falls back to Web Speech without an audio id or when playback fails', async () => {
    const audio = fakeAudio();
    audio.play.mockRejectedValueOnce(new Error('blocked'));
    const fb = fakeImpl();
    const p = new AudioUrlProvider(fb, () => audio);
    p.speak(null, 'no id', 'dm');
    expect(fb.calls).toContain('speak:dm:no id');
    p.speak('abc', 'blocked', 'buddy');
    await Promise.resolve();
    await Promise.resolve();
    expect(fb.calls).toContain('speak:buddy:blocked');
  });
});

describe('WebSpeechProvider', () => {
  it('uses different pitch/rate for the two voices', () => {
    class Utt {
      voice: unknown = null;
      pitch = 1;
      rate = 1;
      volume = 1;
      constructor(public text: string) {}
    }
    vi.stubGlobal('SpeechSynthesisUtterance', Utt);
    const spoken: Utt[] = [];
    const speech = { speak: (u: Utt) => void spoken.push(u), cancel: vi.fn(), getVoices: () => [] };
    const p = new WebSpeechProvider(speech as never);
    p.speak(null, 'dm line', 'dm');
    p.speak(null, 'buddy line', 'buddy');
    expect(speech.cancel).toHaveBeenCalledTimes(2);
    expect(spoken[0].pitch).not.toBe(spoken[1].pitch);
    expect(spoken[0].rate).not.toBe(spoken[1].rate);
    vi.unstubAllGlobals();
  });
});

describe('VoiceProvider and useVoice', () => {
  const wrap = (impl: Impl) =>
    function W({ children }: { children: ReactNode }) {
      return <VoiceProvider provider={impl}>{children}</VoiceProvider>;
    };

  it('is on by default and reads replies', () => {
    const impl = fakeImpl();
    const { result } = renderHook(() => useVoice(), { wrapper: wrap(impl) });
    expect(result.current.enabled).toBe(true);
    act(() => result.current.onPageShown('hello', 'dm'));
    expect(impl.calls).toContain('speak:dm:hello');
  });

  it('toggle off stops reading, persists, and reading stays silent', () => {
    const impl = fakeImpl();
    const { result } = renderHook(() => useVoice(), { wrapper: wrap(impl) });
    act(() => result.current.toggle());
    expect(impl.calls).toContain('stop');
    expect(result.current.enabled).toBe(false);
    expect(localStorage.getItem(VOICE_KEY)).toBe('off');
    act(() => result.current.onPageShown('silent', 'dm'));
    expect(impl.calls.some((c) => c.startsWith('speak'))).toBe(false);
  });

  it('a persisted off survives a new provider (new campaign, same phone)', () => {
    localStorage.setItem(VOICE_KEY, 'off');
    const { result } = renderHook(() => useVoice(), { wrapper: wrap(fakeImpl()) });
    expect(result.current.enabled).toBe(false);
  });

  it('turning voice on reads the next reply only, not the one already shown', () => {
    localStorage.setItem(VOICE_KEY, 'off');
    const impl = fakeImpl();
    const { result } = renderHook(() => useVoice(), { wrapper: wrap(impl) });
    act(() => result.current.onPageShown('already shown', 'dm'));
    act(() => result.current.toggle());
    expect(impl.calls.some((c) => c.startsWith('speak'))).toBe(false);
    expect(impl.calls).toContain('unlock');
    act(() => result.current.onPageShown('next reply', 'buddy'));
    expect(impl.calls.filter((c) => c.startsWith('speak'))).toEqual(['speak:buddy:next reply']);
  });

  it('stop() and unmount stop the provider', () => {
    const impl = fakeImpl();
    const { result, unmount } = renderHook(() => useVoice(), { wrapper: wrap(impl) });
    act(() => result.current.stop());
    const before = impl.calls.filter((c) => c === 'stop').length;
    unmount();
    expect(before).toBe(1);
    expect(impl.calls.filter((c) => c === 'stop').length).toBe(2);
  });

  it('the speaker button shows state and toggles', async () => {
    const impl = fakeImpl();
    render(
      <VoiceProvider provider={impl}>
        <VoiceToggle />
      </VoiceProvider>,
    );
    const btn = screen.getByRole('button', { name: 'Voice on' });
    await userEvent.click(btn);
    expect(screen.getByRole('button', { name: 'Voice off' })).toBeInTheDocument();
  });
});
