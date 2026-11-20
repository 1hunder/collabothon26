import { useCallback, useState } from 'react';

function read(key: string): string {
  try {
    return window.sessionStorage.getItem(key) ?? '';
  } catch {
    return '';
  }
}

function write(key: string, value: string): void {
  try {
    if (value === '') window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    // a lost draft is acceptable
  }
}

/** A text draft that survives closing and reopening its panel (sessionStorage only). */
export function useSessionDraft(key: string): [string, (value: string) => void] {
  const [value, setValue] = useState(() => read(key));
  const set = useCallback(
    (next: string): void => {
      setValue(next);
      write(key, next);
    },
    [key],
  );
  return [value, set];
}

export const ACTION_DRAFT_KEY = 'fq.draft.action';
export const BUDDY_DRAFT_KEY = 'fq.draft.buddy';
