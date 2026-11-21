import { baseUrl } from '../api/client';

export type VoiceName = 'dm' | 'buddy';

export interface VoiceProvider {
  /** Call from a tap handler: lets later, non-gesture playback make sound. */
  unlock(): void;
  /** `textId` is the server's audio_text_id; null when the reply has no stored audio. */
  speak(textId: string | null, text: string, voice: VoiceName): void;
  stop(): void;
}

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

/** Browser voices: two distinct voices when available, otherwise pitch and rate variation. */
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
    const voices = this.speech.getVoices();
    const pick = voices.length >= 2 ? voices[voice === 'dm' ? 0 : 1] : undefined;
    if (pick) u.voice = pick;
    u.pitch = voice === 'dm' ? 0.8 : 1.3;
    u.rate = voice === 'dm' ? 0.95 : 1.08;
    this.speech.speak(u);
  }

  stop(): void {
    this.speech?.cancel();
  }
}

/** Server audio via GET /tts/{audio_text_id}?voice=..., on one reused, unlocked Audio element. */
export class AudioUrlProvider implements VoiceProvider {
  private audio: HTMLAudioElement | null = null;

  constructor(
    private readonly fallback: VoiceProvider | null = null,
    private readonly makeAudio: () => HTMLAudioElement = () => new Audio(),
  ) {}

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
    a.onerror = () => this.fallback?.speak(null, text, voice);
    a.src = `${baseUrl()}/tts/${encodeURIComponent(textId)}?voice=${voice}`;
    void Promise.resolve(a.play()).catch(() => this.fallback?.speak(null, text, voice));
  }

  stop(): void {
    if (this.audio) {
      this.audio.onerror = null;
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
