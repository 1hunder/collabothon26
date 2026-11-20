import { FixtureHttpError, fixtureResponse } from './fixtures';
import type { RevealData, ScenarioSummary, ScenarioView, SessionResponse } from './types';

const SESSION_KEY = 'fq.session.v1';

export type ApiErrorKind =
  | 'Unauthorized'
  | 'RevealLocked'
  | 'NotFound'
  | 'Conflict'
  | 'Validation'
  | 'Server'
  | 'Network';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;

  constructor(kind: ApiErrorKind, status: number, message?: string) {
    super(message ?? `${kind} (${status})`);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
  }
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return 'Unauthorized';
  if (status === 403) return 'RevealLocked';
  if (status === 404) return 'NotFound';
  if (status === 409) return 'Conflict';
  if (status === 422) return 'Validation';
  return 'Server';
}

let memorySession: string | null = null;

function readSession(): string | null {
  try {
    return window.localStorage.getItem(SESSION_KEY) ?? memorySession;
  } catch {
    return memorySession;
  }
}

function writeSession(id: string | null): void {
  memorySession = id;
  try {
    if (id === null) window.localStorage.removeItem(SESSION_KEY);
    else window.localStorage.setItem(SESSION_KEY, id);
  } catch {
    // in-memory fallback already set
  }
}

/** Test helper: forget the stored session. */
export function clearSession(): void {
  writeSession(null);
}

export function baseUrl(): string {
  return ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '').replace(/\/$/, '');
}

export function isFixtureMode(): boolean {
  return import.meta.env.VITE_API_MODE === 'fixture';
}

async function bootstrapSession(): Promise<string> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl()}/session`, { method: 'POST' });
  } catch {
    throw new ApiError('Network', 0, 'Could not reach the server');
  }
  if (!res.ok) throw new ApiError(kindForStatus(res.status), res.status);
  const body = (await res.json()) as SessionResponse;
  writeSession(body.session_id);
  return body.session_id;
}

async function send(
  method: string,
  path: string,
  body: unknown,
  sessionId: string,
  signal?: AbortSignal,
): Promise<Response> {
  const headers: Record<string, string> = { 'X-Session-Id': sessionId };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  try {
    return await fetch(`${baseUrl()}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch {
    throw new ApiError('Network', 0, 'Could not reach the server');
  }
}

/** Session-aware fetch with one re-bootstrap on 401. Returns the raw Response (used for SSE too). */
export async function authedFetch(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  let sessionId = readSession() ?? (await bootstrapSession());
  let res = await send(method, path, body, sessionId, signal);
  if (res.status === 401) {
    // Stale session: bootstrap a new one and retry once.
    writeSession(null);
    sessionId = await bootstrapSession();
    res = await send(method, path, body, sessionId, signal);
  }
  return res;
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (isFixtureMode()) {
    try {
      const data = fixtureResponse(method, path, body);
      if (data === undefined) throw new ApiError('NotFound', 404);
      return data as T;
    } catch (e: unknown) {
      if (e instanceof FixtureHttpError) throw new ApiError(kindForStatus(e.status), e.status);
      throw e;
    }
  }
  const res = await authedFetch(method, path, body);
  if (!res.ok) throw new ApiError(kindForStatus(res.status), res.status);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  playable: (): Promise<ScenarioSummary[]> => request('GET', '/scenarios/playable'),
  view: (id: string): Promise<ScenarioView> => request('GET', `/scenario/${id}/view`),
  reveal: (id: string): Promise<RevealData> => request('GET', `/scenario/${id}/reveal`),
  postEvent: (id: string, type: string): Promise<unknown> =>
    request('POST', `/scenario/${id}/events`, { type }),
};
