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
