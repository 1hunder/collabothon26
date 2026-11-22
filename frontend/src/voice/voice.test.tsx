import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { VOICE_KEY, VoiceProvider, VoiceToggle, useVoice } from '.';
import { AudioUrlProvider, englishVoices, WebSpeechProvider, type VoiceProvider as Impl } from './providers';

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

describe('AudioUrlProvider speed and superseded lines', () => {
  it('plays the narrator 15% faster with the pitch kept, Buddy at normal speed', () => {
    const audio = fakeAudio() as ReturnType<typeof fakeAudio> & { playbackRate?: number; preservesPitch?: boolean };
    const p = new AudioUrlProvider(null, () => audio as never);
    p.speak('1', 'narration', 'dm');
    expect(audio.playbackRate).toBe(1.15);
    expect(audio.preservesPitch).toBe(true);
    p.speak('2', 'buddy line', 'buddy');
    expect(audio.playbackRate).toBe(1);
  });

  it('a line replaced by a newer one never falls back to the browser voice', async () => {
    const audio = fakeAudio();
    audio.play.mockRejectedValueOnce(Object.assign(new Error('interrupted'), { name: 'AbortError' }));
    const fb = fakeImpl();
    const p = new AudioUrlProvider(fb, () => audio);
    p.speak('1', 'old line', 'dm');
    p.speak('2', 'new line', 'dm');
    await Promise.resolve();
    await Promise.resolve();
    expect(fb.calls.filter((c) => c.startsWith('speak'))).toEqual([]);
  });
});

describe('AudioUrlProvider timeout and errors', () => {
  it('falls back to Web Speech when /tts errors', () => {
    const audio = fakeAudio();
    const fb = fakeImpl();
    new AudioUrlProvider(fb, () => audio).speak('abc', 'whole reply', 'dm');
    audio.onerror?.();
    expect(fb.calls).toContain('speak:dm:whole reply');
  });

  it('falls back after the timeout when audio never starts, but not once it plays', () => {
    vi.useFakeTimers();
    const fb = fakeImpl();
    const slow = fakeAudio();
    new AudioUrlProvider(fb, () => slow, 15_000).speak('a', 'slow', 'dm');
    vi.advanceTimersByTime(14_000);
    expect(fb.calls).not.toContain('speak:dm:slow');
    vi.advanceTimersByTime(1_500);
    expect(fb.calls).toContain('speak:dm:slow');
    const ok = fakeAudio();
    const fb2 = fakeImpl();
    new AudioUrlProvider(fb2, () => ok, 15_000).speak('a', 'ok', 'dm');
    (ok as unknown as { onplaying: () => void }).onplaying();
    vi.advanceTimersByTime(20_000);
    expect(fb2.calls).not.toContain('speak:dm:ok');
    vi.useRealTimers();
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

  it('reads English with English voices only, natural ones first, never a Ukrainian system voice', () => {
    class Utt {
      voice: { name: string; lang: string } | null = null;
      lang = '';
      pitch = 1;
      rate = 1;
      volume = 1;
      constructor(public text: string) {}
    }
    vi.stubGlobal('SpeechSynthesisUtterance', Utt);
    const voices = [
      { name: 'Microsoft Ostap - Ukrainian (Ukraine)', lang: 'uk-UA' },
      { name: 'Microsoft David - English (United States)', lang: 'en-US' },
      { name: 'Microsoft Ryan Online (Natural) - English (United Kingdom)', lang: 'en-GB' },
      { name: 'Microsoft Polina Online (Natural) - Ukrainian (Ukraine)', lang: 'uk-UA' },
    ];
    expect(englishVoices(voices as never).map((v) => v.name)).toEqual([
      'Microsoft Ryan Online (Natural) - English (United Kingdom)',
      'Microsoft David - English (United States)',
    ]);
    const spoken: Utt[] = [];
    const p = new WebSpeechProvider({ speak: (u: Utt) => void spoken.push(u), cancel: vi.fn(), getVoices: () => voices } as never);
    p.speak(null, 'dm line', 'dm');
    p.speak(null, 'buddy line', 'buddy');
    expect(spoken.map((u) => u.voice?.lang)).toEqual(['en-GB', 'en-US']);
    expect(spoken.every((u) => u.lang.startsWith('en'))).toBe(true);
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

describe('AudioUrlProvider: one line at a time', () => {
  it('asked again for the line it is already playing, it carries on instead of restarting', () => {
    const audio = fakeAudio();
    const p = new AudioUrlProvider(null, () => audio);
    p.speak('42', 'whole reply', 'dm');
    p.speak('42', 'whole reply', 'dm');
    expect(audio.play).toHaveBeenCalledTimes(1);
    (audio as unknown as { onended: () => void }).onended();
    p.speak('42', 'whole reply', 'dm'); // finished: may be heard again
    expect(audio.play).toHaveBeenCalledTimes(2);
    p.stop();
    p.speak('42', 'whole reply', 'dm'); // stopped: starts again
    expect(audio.play).toHaveBeenCalledTimes(3);
  });

  it('a new server line silences a browser-voice line still speaking', () => {
    const fb = fakeImpl();
    const p = new AudioUrlProvider(fb, () => fakeAudio());
    p.speak(null, 'browser line', 'dm');
    p.speak('43', 'server line', 'dm');
    expect(fb.calls).toEqual(['speak:dm:browser line', 'stop']);
  });
});
});
