/**
 * fetchAssets(tenantId) names the selected tenant in the X-Tenant-ID header (the one a Platform
 * Owner's tenant choice travels in; the list route ignored the old ?tenantId= query it sent) and
 * keeps each tenant's offline copy in its own sessionStorage slot, so one tenant's list is never
 * served for another. Without a tenant it behaves as before: no header, the shared slot.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const ITEMS = { 'tenant-a': [{ id: 'a-1', tenantId: 'tenant-a' }], 'tenant-b': [{ id: 'b-1', tenantId: 'tenant-b' }] };

/** fetch stub: answers the list from the X-Tenant-ID header it is sent (all tenants without one). */
function stubFetch() {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
    const tenant = (init?.headers as Record<string, string> | undefined)?.['X-Tenant-ID'] as keyof typeof ITEMS | undefined;
    return Promise.resolve(json({ items: tenant ? ITEMS[tenant] : [...ITEMS['tenant-a'], ...ITEMS['tenant-b']], total: 2 }));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function freshApi() {
  vi.resetModules();
  return import('../../services/apiService');
}

const headerOf = (fetchMock: ReturnType<typeof stubFetch>, call = 0) =>
  (fetchMock.mock.calls[call][1]?.headers as Record<string, string>)['X-Tenant-ID'];

describe('fetchAssets tenant scope', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it('sends the tenant as the X-Tenant-ID header', async () => {
    sessionStorage.setItem('token', 'tok');
    const fetchMock = stubFetch();
    const api = await freshApi();
    expect(await api.fetchAssets('tenant-a')).toEqual(ITEMS['tenant-a']);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/assets$/);
    expect(headerOf(fetchMock)).toBe('tenant-a');
  });

  it('sends no tenant header without a tenant', async () => {
    sessionStorage.setItem('token', 'tok');
    const fetchMock = stubFetch();
    const api = await freshApi();
    expect(await api.fetchAssets()).toHaveLength(2);
    expect(headerOf(fetchMock)).toBeUndefined();
  });

  it('keeps each tenant in its own cache slot, apart from the unscoped one', async () => {
    sessionStorage.setItem('token', 'tok');
    stubFetch();
    const api = await freshApi();
    await api.fetchAssets('tenant-a');
    await api.fetchAssets('tenant-b');
    await api.fetchAssets();
    expect(JSON.parse(sessionStorage.getItem('omni_cache_assets_tenant-a')!)).toEqual(ITEMS['tenant-a']);
    expect(JSON.parse(sessionStorage.getItem('omni_cache_assets_tenant-b')!)).toEqual(ITEMS['tenant-b']);
    expect(JSON.parse(sessionStorage.getItem('omni_cache_assets')!)).toHaveLength(2);
  });

  it('serves a tenant its own offline copy, never another tenant\'s', async () => {
    sessionStorage.setItem('token', 'tok');
    stubFetch();
    const api = await freshApi();
    await api.fetchAssets('tenant-a');
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    expect(await api.fetchAssets('tenant-a')).toEqual(ITEMS['tenant-a']);
    expect(await api.fetchAssets('tenant-b')).toEqual([]);
    expect(await api.fetchAssets()).toEqual([]);
  });

  it('empties only the slot of the tenant the server refused', async () => {
    sessionStorage.setItem('token', 'tok');
    stubFetch();
    const api = await freshApi();
    await api.fetchAssets('tenant-a');
    await api.fetchAssets('tenant-b');
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(null, { status: 403 }))));
    expect(await api.fetchAssets('tenant-a')).toEqual([]);
    expect(sessionStorage.getItem('omni_cache_assets_tenant-a')).toBeNull();
    expect(sessionStorage.getItem('omni_cache_assets_tenant-b')).not.toBeNull();
  });
});
