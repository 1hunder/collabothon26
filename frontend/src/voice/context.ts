import { createContext, useContext } from 'react';
import type { VoiceName } from './providers';

export const VOICE_KEY = 'fq.voice.v1';

export interface VoiceApi {
  enabled: boolean;
  unlock: () => void;
  speak: (textId: string | null, text: string, voice: VoiceName) => void;
  stop: () => void;
  toggle: () => void;
  /** Hook point for the play screen: call when a new dialogue page is shown. */
  onPageShown: (text: string, voice: VoiceName, textId?: string | null) => void;
}

const noop = (): void => undefined;
export const inertVoice: VoiceApi = { enabled: false, unlock: noop, speak: noop, stop: noop, toggle: noop, onPageShown: noop };

export const VoiceContext = createContext<VoiceApi>(inertVoice);

export function useVoice(): VoiceApi {
  return useContext(VoiceContext);
}
