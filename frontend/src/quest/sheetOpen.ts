import { createContext, useContext, useEffect } from 'react';

/** The quest layout hides its own close button while a full-screen sheet carries one. */
export const SheetOpenContext = createContext<(open: boolean) => void>(() => undefined);

export function useReportSheetOpen(open: boolean): void {
  const report = useContext(SheetOpenContext);
  useEffect(() => {
    report(open);
    return () => report(false);
  }, [open, report]);
}
