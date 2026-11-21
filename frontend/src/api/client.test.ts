import { ApiError, api, clearSession } from './client';

function res(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  clearSession();
  vi.stubEnv('VITE_API_MODE', 'live');
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test');
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

it('bootstraps a session once, stores it and sends X-Session-Id', async () => {
  const f = vi.fn()
    .mockResolvedValueOnce(res(200, { session_id: 'abc' }))
    .mockImplementation(() => Promise.resolve(res(200, [])));
  vi.stubGlobal('fetch', f);
  await api.playable();
  await api.playable();
  expect(f.mock.calls[0]?.[0]).toBe('http://api.test/session');
  expect(f.mock.calls[0]?.[1]).toMatchObject({ method: 'POST' });
  expect(f.mock.calls[1]?.[1].headers['X-Session-Id']).toBe('abc');
  expect(f).toHaveBeenCalledTimes(3);
  expect(localStorage.getItem('fq.session.v1')).toBe('abc');
});

it('re-bootstraps once on 401 and retries', async () => {
  localStorage.setItem('fq.session.v1', 'old');
  const f = vi.fn()
    .mockResolvedValueOnce(res(401))
    .mockResolvedValueOnce(res(200, { session_id: 'new' }))
    .mockResolvedValueOnce(res(200, [{ id: 'x' }]));
  vi.stubGlobal('fetch', f);
  await expect(api.playable()).resolves.toEqual([{ id: 'x' }]);
  expect(f.mock.calls[2]?.[1].headers['X-Session-Id']).toBe('new');
});

it('maps 403 to RevealLocked', async () => {
  localStorage.setItem('fq.session.v1', 's');
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(res(403))));
  await expect(api.reveal('1')).rejects.toMatchObject({ kind: 'RevealLocked' });
  await expect(api.reveal('1')).rejects.toBeInstanceOf(ApiError);
});

it('serves fixtures in fixture mode without fetch', async () => {
  vi.stubEnv('VITE_API_MODE', 'fixture');
  const f = vi.fn();
  vi.stubGlobal('fetch', f);
  expect((await api.playable()).length).toBeGreaterThan(0);
  expect(f).not.toHaveBeenCalled();
});

it('coerces decimal-string prices of the spec 002 endpoints to numbers', async () => {
  const f = vi.fn()
    .mockResolvedValueOnce(res(200, { session_id: 'abc' }))
    .mockResolvedValueOnce(res(200, { id: 's', chart: [{ story_day: 1, price: '31.95' }] }))
    .mockResolvedValueOnce(
      res(200, {
        series: [{ date: '2001-01-01', price: '40.5' }],
        news_points: [{ story_day: 1, real_date: 'x', real_price: '41.25', headline: 'h' }],
      }),
    );
  vi.stubGlobal('fetch', f);
  expect((await api.view('s')).chart[0]?.price).toBe(31.95);
  const r = await api.reveal('s');
  expect(r.series[0]?.price).toBe(40.5);
  expect(r.news_points[0]?.real_price).toBe(41.25);
});

it('keeps code, fields and campaign_id of the error envelope', async () => {
  const f = vi.fn()
    .mockResolvedValueOnce(res(200, { session_id: 'abc' }))
    .mockResolvedValueOnce(res(422, { error: { code: 'invalid_commit', message: 'bad', fields: { evidence: 'too short' } } }));
  vi.stubGlobal('fetch', f);
  const e = await api.playable().catch((x: unknown) => x);
  expect(e).toBeInstanceOf(ApiError);
  expect((e as ApiError).code).toBe('invalid_commit');
  expect((e as ApiError).fields).toEqual({ evidence: 'too short' });
});

it('adopts a session from ?session= and removes it from the address bar', async () => {
  const { adoptSessionFromUrl } = await import('./client');
  const id = '0b7e5c3a-1d2f-4a6b-9c8d-123456789abc';
  window.history.replaceState(null, '', `/quest?session=${id}&x=1`);
  expect(adoptSessionFromUrl()).toBe(true);
  expect(localStorage.getItem('fq.session.v1')).toBe(id);
  expect(window.location.search).toBe('?x=1');
  window.history.replaceState(null, '', '/quest?session=not-a-uuid');
  expect(adoptSessionFromUrl()).toBe(false);
  expect(localStorage.getItem('fq.session.v1')).toBe(id);
  expect(window.location.search).toBe('');
});
