import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ToastContext, defaultToastMessage, type ToastApi } from './useToast';

const dismissAfterMs = 3000;

interface ToastState {
  id: number;
  message: string;
}

export function ToastProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idRef = useRef(0);

  const clearTimer = useCallback((): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const dismiss = useCallback((): void => {
    clearTimer();
    setToast(null);
  }, [clearTimer]);

  const show = useCallback(
    (message: string = defaultToastMessage): void => {
      clearTimer();
      idRef.current += 1;
      setToast({ id: idRef.current, message });
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        setToast(null);
      }, dismissAfterMs);
    },
    [clearTimer],
  );

  useEffect(() => clearTimer, [clearTimer]);

  const api = useMemo<ToastApi>(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-[calc(80px+env(safe-area-inset-bottom))] left-1/2 z-[60] flex w-full max-w-[430px] -translate-x-1/2 justify-center px-4"
      >
        {toast !== null && (
          <button
            key={toast.id}
            type="button"
            onClick={dismiss}
            className="pointer-events-auto animate-[toast-in_150ms_ease-out] rounded-lg bg-petrol px-4 py-3 text-sm font-medium text-white shadow-lg"
          >
            {toast.message}
          </button>
        )}
      </div>
    </ToastContext.Provider>
  );
}
