export interface ShellRouteHandle {
  /** Screen title shown in the top bar. Omit on the Overview, which shows the logo. */
  title?: string;
  /** Show the back arrow in the top bar. */
  back?: boolean;
}

export function isShellRouteHandle(value: unknown): value is ShellRouteHandle {
  return typeof value === 'object' && value !== null;
}
