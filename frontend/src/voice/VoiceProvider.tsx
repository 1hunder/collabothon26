import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { VOICE_KEY, VoiceContext } from './context';
import { sharedProvider, type VoiceName, type VoiceProvider as Provider } from './providers';

function readEnabled(): boolean {
  try {
    return localStorage.getItem(VOICE_KEY) !== 'off';
  } catch {
    return true;
  }
}

function writeEnabled(on: boolean): void {
  try {
    localStorage.setItem(VOICE_KEY, on ? 'on' : 'off');
  } catch {
    // not persisted
  }
}

interface VoiceProviderProps {
  provider?: Provider;
  children: React.ReactNode;
}

export function VoiceProvider({ provider, children }: VoiceProviderProps): React.JSX.Element {
  const impl = provider ?? sharedProvider();
  const [enabled, setEnabled] = useState(readEnabled);
  const enabledRef = useRef(enabled);

  const unlock = useCallback(() => impl.unlock(), [impl]);
  const stop = useCallback(() => impl.stop(), [impl]);
  // Replies shown while voice is off are never queued, so turning voice on reads the next reply only.
  const speak = useCallback(
    (textId: string | null, text: string, voice: VoiceName) => {
      if (enabledRef.current) impl.speak(textId, text, voice);
    },
    [impl],
  );
  const onPageShown = useCallback(
    (text: string, voice: VoiceName, textId: string | null = null) => speak(textId, text, voice),
    [speak],
  );
  const toggle = useCallback(() => {
    const next = !enabledRef.current;
    enabledRef.current = next;
    setEnabled(next);
    writeEnabled(next);
    impl.stop();
    if (next) impl.unlock();
  }, [impl]);

  useEffect(() => () => impl.stop(), [impl]);

  const api = useMemo(
    () => ({ enabled, unlock, speak, stop, toggle, onPageShown }),
    [enabled, unlock, speak, stop, toggle, onPageShown],
  );
  return <VoiceContext.Provider value={api}>{children}</VoiceContext.Provider>;
}
