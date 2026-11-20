import { createContext, useContext } from 'react';

export interface ToastApi {
  show: (message?: string) => void;
}

export const defaultToastMessage = 'Not available in this demo.';

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (api === null) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return api;
}
