/**
 * 77 WR-11: after a 401, only a failed token refresh ends the session. An abort (a screen that
 * cancels its request on unmount) or a network error on the retried request reaches the caller,
 * and the refreshed session stays signed in.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/** fetch stub: /auth/refresh answers `refresh`; the first other call answers 401, later ones run `retry`. */
function stubFetch(refresh: () => Promise<Response>, retry: (init?: RequestInit) => Promise<Response>) {
  let calls = 0;
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/auth/refresh')) return refresh();
    calls += 1;
    return calls === 1 ? Promise.resolve(new Response(null, { status: 401 })) : retry(init);
  }));
  return () => calls;
}

async function freshApi() {
  vi.resetModules();
  return import('../../services/apiService');
}

describe('authFetch 401 retry (77 WR-11)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    sessionStorage.clear();
  });

  it('lets an abort of the retried request reach the caller without signing out', async () => {
    sessionStorage.setItem('token', 'tok');
    const controller = new AbortController();
    const calls = stubFetch(
      () => Promise.resolve(json({ success: true, access_token: 'tok2' })),
      init => new Promise((_res, rej) => {
        init?.signal?.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError')));
        controller.abort();
      }));
    const api = await freshApi();
    const err = await api.authFetch('/api/remote-access/sessions', { signal: controller.signal }).catch(e => e);
    expect(err).toBeInstanceOf(DOMException);
    expect((err as DOMException).name).toBe('AbortError');
    expect(calls()).toBe(2);
    expect(sessionStorage.getItem('token')).toBe('tok2');
    expect(sessionStorage.getItem(api.SESSION_ENDED_KEY)).toBeNull();
    // The session did not end: the next request is still sent.
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ ok: true }))));
    await expect(api.authFetch('/api/assets')).resolves.toBeInstanceOf(Response);
  });

  it('lets a network error on the retried request reach the caller without signing out', async () => {
    sessionStorage.setItem('token', 'tok');
    stubFetch(
      () => Promise.resolve(json({ success: true, access_token: 'tok2' })),
      () => Promise.reject(new TypeError('Failed to fetch')));
    const api = await freshApi();
    await expect(api.authFetch('/api/assets')).rejects.toThrow('Failed to fetch');
    expect(sessionStorage.getItem('token')).toBe('tok2');
    expect(sessionStorage.getItem(api.SESSION_ENDED_KEY)).toBeNull();
  });

  it('still ends the session when the token refresh itself fails', async () => {
    vi.useFakeTimers();
    sessionStorage.setItem('token', 'tok');
    const calls = stubFetch(() => Promise.resolve(new Response(null, { status: 500 })),
      () => Promise.resolve(json({ ok: true })));
    const api = await freshApi();
    await expect(api.authFetch('/api/assets')).rejects.toThrow('Session expired');
    expect(calls()).toBe(1);
    expect(sessionStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem(api.SESSION_ENDED_KEY)).toBe('1');
  });
});
