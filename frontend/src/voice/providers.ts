import { baseUrl } from '../api/client';

export type VoiceName = 'dm' | 'buddy';

export interface VoiceProvider {
  /** Call from a tap handler: lets later, non-gesture playback make sound. */
  unlock(): void;
  /** `textId` is the server's audio_text_id; null when the reply has no stored audio. */
  speak(textId: string | null, text: string, voice: VoiceName): void;
  stop(): void;
}

/** Server audio that has not started playing by then is replaced by browser speech. */
export const TTS_TIMEOUT_MS = 30_000; // a new reply takes 7-15 s to synthesize
/** The narrator's server voice plays 15% faster (pitch kept); Buddy at normal speed. */
export const PLAYBACK_RATE: Partial<Record<VoiceName, number>> = { dm: 1.15 };

// 0.1 s of silence; played once on unlock so the reused Audio element is allowed to play later.
const SILENT_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

interface SpeechLike {
  speak(u: SpeechSynthesisUtterance): void;
  cancel(): void;
  getVoices(): SpeechSynthesisVoice[];
}

function defaultSpeech(): SpeechLike | null {
  return typeof window !== 'undefined' && 'speechSynthesis' in window ? window.speechSynthesis : null;
}

/** Natural-sounding voices first (Edge "Online (Natural)", Chrome "Google"), then other English. */
function voiceRank(v: SpeechSynthesisVoice): number {
  const name = v.name.toLowerCase();
  if (name.includes('natural') || name.includes('online')) return 0;
  if (name.includes('google')) return 1;
  return 2;
}

/**
 * The English voices of this device, best first. Only English: on a device with, say, Ukrainian
 * voices installed, the system's first voice would otherwise read English with a foreign accent.
 */
export function englishVoices(voices: readonly SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  return voices
    .filter((v) => v.lang.toLowerCase().replace('_', '-').startsWith('en'))
    .sort((a, b) => voiceRank(a) - voiceRank(b));
}

/** Browser voices: two distinct English voices when available, otherwise pitch and rate variation. */
export class WebSpeechProvider implements VoiceProvider {
  private readonly speech: SpeechLike | null;

  constructor(speech: SpeechLike | null = defaultSpeech()) {
    this.speech = speech;
  }

  unlock(): void {
    // Speech synthesis needs no unlock beyond being called from a gesture; prime it silently.
    if (!this.speech) return;
    const u = new SpeechSynthesisUtterance('');
    u.volume = 0;
    this.speech.speak(u);
  }

  speak(_textId: string | null, text: string, voice: VoiceName): void {
    if (!this.speech) return;
    this.speech.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voices = englishVoices(this.speech.getVoices());
    const pick = voice === 'dm' ? voices[0] : (voices[1] ?? voices[0]);
    if (pick) u.voice = pick;
    u.lang = pick?.lang ?? 'en-US';
    u.pitch = voice === 'dm' ? 0.92 : 1.12;
    u.rate = voice === 'dm' ? 1.1 : 1.05;
    this.speech.speak(u);
  }

  stop(): void {
    this.speech?.cancel();
  }
}

/** Server audio via GET /tts/{audio_text_id}?voice=..., on one reused, unlocked Audio element. */
export class AudioUrlProvider implements VoiceProvider {
  private audio: HTMLAudioElement | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private request = 0;

  constructor(
    private readonly fallback: VoiceProvider | null = null,
    private readonly makeAudio: () => HTMLAudioElement = () => new Audio(),
    private readonly timeoutMs: number = TTS_TIMEOUT_MS,
  ) {}

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private element(): HTMLAudioElement {
    this.audio ??= this.makeAudio();
    return this.audio;
  }

  unlock(): void {
    const a = this.element();
    a.src = SILENT_WAV;
    void Promise.resolve(a.play()).catch(() => undefined);
    this.fallback?.unlock();
  }

  speak(textId: string | null, text: string, voice: VoiceName): void {
    if (textId === null) {
      this.fallback?.speak(null, text, voice);
      return;
    }
    const a = this.element();
    this.clearTimer();
    const request = ++this.request;
    let settled = false;
    const fail = (): void => {
      // a newer line replaced this one (its play() rejects with AbortError): stay silent
      if (settled || request !== this.request) return;
      settled = true;
      this.clearTimer();
      a.onerror = null;
      a.onplaying = null;
      a.pause();
      this.fallback?.speak(null, text, voice);
    };
    a.onerror = fail;
    a.onplaying = () => {
      settled = true;
      this.clearTimer();
    };
    this.timer = setTimeout(fail, this.timeoutMs);
    a.src = `${baseUrl()}/tts/${encodeURIComponent(textId)}?voice=${voice}`;
    // after src: loading a new source resets the rate to the default
    a.preservesPitch = true;
    a.defaultPlaybackRate = PLAYBACK_RATE[voice] ?? 1;
    a.playbackRate = PLAYBACK_RATE[voice] ?? 1;
    void Promise.resolve(a.play()).catch(fail);
  }

  stop(): void {
    this.clearTimer();
    this.request += 1; // a line still loading must not fall back to the browser voice later
    if (this.audio) {
      this.audio.onerror = null;
      this.audio.onplaying = null;
      this.audio.pause();
      this.audio.currentTime = 0;
    }
    this.fallback?.stop();
  }
}

export function createProvider(mode: string | undefined = import.meta.env.VITE_TTS as string | undefined): VoiceProvider {
  const web = new WebSpeechProvider();
  return mode === 'webspeech' ? web : new AudioUrlProvider(web);
}

let shared: VoiceProvider | null = null;

export function sharedProvider(): VoiceProvider {
  shared ??= createProvider();
  return shared;
}

/** Test helper. */
export function setSharedProvider(p: VoiceProvider | null): void {
  shared = p;
}

/** Unlock audio from a tap handler ("Find my quest", "Continue"). Never throws. */
export function unlockVoice(): void {
  try {
    sharedProvider().unlock();
  } catch {
    // voice is optional
  }
}
