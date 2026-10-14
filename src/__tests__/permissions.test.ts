/**
 * Phase 75 (D-17, D-26): the UI grants only what the server delivered, and the
 * cached role list never outlives a sign-in. Pure derivation plus the
 * apiService cache rules; no DOM rendering.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { derivePermissionState, isPlatformRoleName, isSuperAdminRoleName, platformTier, roleLabel } from '../../utils/permissions';
import { fetchRoles, fetchUsers, logoutSession } from '../../services/apiService';
import type { Permission, Tenant, User } from '../../types';

const user = (over: Partial<User>): User =>
  ({ id: 'u1', name: 'U', email: 'u@x.test', role: 'Tenant Admin', tenantId: 't1', ...over }) as User;

const tenant = (over: Partial<Tenant>): Tenant =>
  ({ id: 't1', name: 'T', enabledFeatures: [], ...over }) as Tenant;

const perm = (p: string) => p as Permission;

describe('derivePermissionState (D-17)', () => {
  it('grants nothing without a user', () => {
    const state = derivePermissionState(null, []);
    expect(state.enabledFeatures).toEqual([]);
    expect(state.hasPermission(perm('view:dashboard'))).toBe(false);
  });

  it('empty server permissions mean no access, even for a Tenant Admin', () => {
    const state = derivePermissionState(user({ permissions: [] }), [tenant({ enabledFeatures: [perm('view:dashboard')] })]);
    expect(state.enabledFeatures).toEqual([]);
    expect(state.hasPermission(perm('view:dashboard'))).toBe(false);
    expect(state.hasPermission(perm('view:profile'))).toBe(false);
  });

  it('a missing permissions field is treated as empty', () => {
    const state = derivePermissionState(user({ permissions: undefined }), []);
    expect(state.hasPermission(perm('view:dashboard'))).toBe(false);
  });

  it('intersects the server list with the tenant enabled features', () => {
    const itamViewer = user({
      role: 'itam_viewer',
      permissions: ['view:assets', 'view:itam', 'view:licenses', 'view:profile'].map(perm),
    });
    const state = derivePermissionState(itamViewer, [tenant({ enabledFeatures: ['view:itam', 'view:profile'].map(perm) })]);
    expect(state.hasPermission(perm('view:itam'))).toBe(true);
    expect(state.hasPermission(perm('view:profile'))).toBe(true);
    expect(state.hasPermission(perm('view:assets'))).toBe(false);
    expect(state.hasPermission(perm('view:dashboard'))).toBe(false);
  });

  it('uses the server list as-is when no tenant matches', () => {
    const state = derivePermissionState(user({ tenantId: 'other', permissions: [perm('view:itam')] }), [tenant({})]);
    expect(state.enabledFeatures).toEqual(['view:itam']);
    expect(state.hasPermission(perm('view:itam'))).toBe(true);
    expect(state.hasPermission(perm('view:assets'))).toBe(false);
  });

  it.each(['Super Admin', 'superadmin', 'super_admin', 'platform-admin', '  SUPER ADMIN  '])(
    'super-admin role name %j gets every permission with an empty list',
    (role) => {
      expect(isSuperAdminRoleName(role)).toBe(true);
      const state = derivePermissionState(user({ role, permissions: [] }), []);
      expect(state.hasPermission(perm('manage:tenants'))).toBe(true);
    },
  );

  it.each(['super-admin', 'Super-Admin', 'platform_admin', 'platform admin', 'Platform Admin'])(
    'accepts the backend spelling %j of the super-admin role (WR-07)',
    (role) => {
      expect(isSuperAdminRoleName(role)).toBe(true);
      expect(derivePermissionState(user({ role, permissions: [] }), []).hasPermission(perm('manage:tenants'))).toBe(true);
    },
  );

  it('a delivered "*" is a super grant that skips the tenant intersection (WR-07)', () => {
    const state = derivePermissionState(
      user({ role: 'Some Custom Name', permissions: [perm('*')] }),
      [tenant({ enabledFeatures: [perm('view:dashboard')] })],
    );
    expect(state.hasPermission(perm('manage:tenants'))).toBe(true);
    expect(state.hasPermission(perm('view:assets'))).toBe(true);
  });

  it('does not treat ordinary roles as super admin', () => {
    expect(isSuperAdminRoleName('Tenant Admin')).toBe(false);
    expect(isSuperAdminRoleName(undefined)).toBe(false);
    expect(isSuperAdminRoleName(null)).toBe(false);
  });
});

describe('platform roles (spec C1)', () => {
  it('names the three platform tiers and no tenant role', () => {
    expect(platformTier('Platform Owner')).toBe('owner');
    expect(platformTier('Super Admin')).toBe('owner');
    expect(platformTier('Platform Support')).toBe('support');
    expect(platformTier('platform_billing')).toBe('billing');
    for (const role of ['admin', 'Tenant Admin', 'viewer', '', null]) {
      expect(isPlatformRoleName(role)).toBe(false);
    }
    expect(roleLabel('Super Admin')).toBe('Platform Owner');
    expect(roleLabel('Platform Support')).toBe('Platform Support');
  });

  it("support is not narrowed by the Platform tenant's empty feature list", () => {
    const support = user({ role: 'Platform Support', tenantId: 'platform-admin', permissions: [perm('view:agents')] });
    const state = derivePermissionState(support, [tenant({ id: 'platform-admin', enabledFeatures: [] })]);
    expect(state.hasPermission(perm('view:agents'))).toBe(true);
    expect(state.hasPermission(perm('manage:agents'))).toBe(false);
  });
});

describe('role-list cache hygiene (D-26)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it('logout removes the cached role list', async () => {
    sessionStorage.setItem('omni_cache_roles', JSON.stringify([{ name: 'admin' }]));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
    await logoutSession();
    expect(sessionStorage.getItem('omni_cache_roles')).toBeNull();
  });

  it('logout removes the cached role list even when offline', async () => {
    sessionStorage.setItem('omni_cache_roles', JSON.stringify([{ name: 'admin' }]));
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    await logoutSession();
    expect(sessionStorage.getItem('omni_cache_roles')).toBeNull();
  });

  it('logout removes every omni_cache_* entry and leaves other keys alone (WR-08)', async () => {
    for (const k of ['roles', 'users', 'tenants', 'assets', 'agents']) {
      sessionStorage.setItem(`omni_cache_${k}`, JSON.stringify([{ id: `previous-${k}` }]));
    }
    sessionStorage.setItem('unrelated', 'keep');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
    await logoutSession();
    for (const k of ['roles', 'users', 'tenants', 'assets', 'agents']) {
      expect(sessionStorage.getItem(`omni_cache_${k}`)).toBeNull();
    }
    expect(sessionStorage.getItem('unrelated')).toBe('keep');
  });

  it('the previous users list is not served after logout when the backend is offline (WR-08)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 'a1', email: 'a@tenant-a.test' }]), { status: 200 })));
    expect(await fetchUsers()).toHaveLength(1);
    await logoutSession();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    expect(await fetchUsers()).toEqual([]);
  });

  it('a 403 returns an empty list and drops the previous cached copy', async () => {
    sessionStorage.setItem('omni_cache_roles', JSON.stringify([{ name: 'previous-admin-role' }]));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"no"}', { status: 403 })));
    const roles = await fetchRoles();
    expect(roles).toEqual([]);
    expect(sessionStorage.getItem('omni_cache_roles')).toBeNull();
  });

  it('offline still serves the cached list', async () => {
    sessionStorage.setItem('omni_cache_roles', JSON.stringify([{ name: 'cached-role' }]));
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    const roles = await fetchRoles();
    expect(roles).toEqual([{ name: 'cached-role' }]);
  });
});
