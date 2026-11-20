import { createContext, createElement, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

// In-memory only: never persisted, so a reload always returns to Welcome.
let unlocked = false;

export function isUnlocked(): boolean {
  return unlocked;
}

export function unlockSession(): void {
  unlocked = true;
}

export function resetSession(): void {
  unlocked = false;
}

interface SessionValue {
  unlocked: boolean;
  unlock: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }): React.JSX.Element {
  const [isOpen, setIsOpen] = useState<boolean>(unlocked);
  const value = useMemo<SessionValue>(
    () => ({
      unlocked: isOpen,
      unlock: () => {
        unlockSession();
        setIsOpen(true);
      },
    }),
    [isOpen],
  );
  return createElement(SessionContext.Provider, { value }, children);
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used inside SessionProvider');
  return value;
}
