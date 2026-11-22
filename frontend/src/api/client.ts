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

interface ApiErrorExtra {
  code?: string;
  fields?: Record<string, string>;
  campaignId?: string;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  /** Server error code from the `{error: {code}}` envelope. */
  readonly code?: string;
  /** 422 field messages. */
  readonly fields?: Record<string, string>;
  /** 409 campaign_in_progress: the campaign to resume. */
  readonly campaignId?: string;

  constructor(kind: ApiErrorKind, status: number, message?: string, extra?: ApiErrorExtra) {
    super(message ?? `${kind} (${status})`);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.code = extra?.code;
    this.fields = extra?.fields;
    this.campaignId = extra?.campaignId;
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

/** Parse the `{error: {code, message, fields?, campaign_id?}}` envelope into an ApiError. */
export async function errorFromResponse(res: Response): Promise<ApiError> {
  let extra: ApiErrorExtra = {};
  let message: string | undefined;
  try {
    const body = (await res.json()) as { error?: Record<string, unknown> };
    const e = body.error;
    if (e) {
      extra = {
        code: typeof e.code === 'string' ? e.code : undefined,
        fields: e.fields && typeof e.fields === 'object' ? (e.fields as Record<string, string>) : undefined,
        campaignId: typeof e.campaign_id === 'string' ? e.campaign_id : undefined,
      };
      if (typeof e.message === 'string') message = e.message;
    }
  } catch {
    // not JSON
  }
  return new ApiError(kindForStatus(res.status), res.status, message, extra);
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

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Open the app as an existing session (`?session=<id>`, e.g. the prepared demo hero from
 * `financequest veteran demo-hero`). The parameter is removed from the address bar at once.
 */
export function adoptSessionFromUrl(loc: Location = window.location, history: History = window.history): boolean {
  const params = new URLSearchParams(loc.search);
  const id = params.get('session');
  if (id === null) return false;
  params.delete('session');
  const rest = params.toString();
  history.replaceState(history.state, '', `${loc.pathname}${rest ? `?${rest}` : ''}${loc.hash}`);
  if (!UUID.test(id)) return false;
  writeSession(id);
  return true;
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
  extra?: Record<string, string>,
): Promise<Response> {
  const headers: Record<string, string> = { ...extra, 'X-Session-Id': sessionId };
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
  extra?: Record<string, string>,
): Promise<Response> {
  let sessionId = readSession() ?? (await bootstrapSession());
  let res = await send(method, path, body, sessionId, signal, extra);
  if (res.status === 401) {
    // Stale session: bootstrap a new one and retry once.
    writeSession(null);
    sessionId = await bootstrapSession();
    res = await send(method, path, body, sessionId, signal, extra);
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
      if (e instanceof FixtureHttpError) throw new ApiError(kindForStatus(e.status), e.status, undefined, { code: e.code });
      throw e;
    }
  }
  const res = await authedFetch(method, path, body);
  if (!res.ok) throw await errorFromResponse(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const num = (v: unknown): number => Number(v);

/** Spec 002 sends prices as decimal strings; the UI works with numbers. */
export function coerceView(v: ScenarioView): ScenarioView {
  return { ...v, chart: v.chart.map((p) => ({ ...p, price: num(p.price) })) };
}

export function coerceReveal(r: RevealData): RevealData {
  return {
    ...r,
    series: r.series.map((p) => ({ ...p, price: num(p.price) })),
    news_points: r.news_points.map((p) => ({ ...p, real_price: num(p.real_price) })),
  };
}

export const api = {
  playable: (): Promise<ScenarioSummary[]> => request('GET', '/scenarios/playable'),
  view: async (id: string): Promise<ScenarioView> =>
    coerceView(await request<ScenarioView>('GET', `/scenario/${id}/view`)),
  reveal: async (id: string): Promise<RevealData> =>
    coerceReveal(await request<RevealData>('GET', `/scenario/${id}/reveal`)),
  postEvent: (id: string, type: string): Promise<unknown> =>
    request('POST', `/scenario/${id}/events`, { type }),
};
