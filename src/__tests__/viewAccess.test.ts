/**
 * Phase 77 (D-05, D-06, D-12): one pure function decides whether a signed-in user may see a view,
 * and which view they land on. Pure derivation over the manifest; no DOM.
 */
import { describe, it, expect } from 'vitest';
import {
  evaluateViewAccess,
  hasAnyScreen,
  landingView,
  permissionsKnown,
} from '../../utils/viewAccess';
import { CATALOGUES } from '../../utils/catalogueAccess';
import { derivePermissionState } from '../../utils/permissions';
import type { User } from '../../types';

const mk = (role: string, permissions?: string[]): User =>
  ({ id: 'u1', name: 'U', email: 'u@x.test', role, tenantId: 't1', permissions }) as unknown as User;

const evaluate = (view: string, user: User) =>
  evaluateViewAccess(view as never, user, derivePermissionState(user).hasPermission);

const landing = (user: User) => landingView(user, derivePermissionState(user).hasPermission);

const SUPER_ADMIN_SPELLINGS = ['Super Admin', 'super_admin', 'superadmin', 'platform-admin', 'Platform Owner'];

describe('evaluateViewAccess (D-05)', () => {
  it('denies a view with no manifest entry for everyone, super admin included (76 IN-04)', () => {
    expect(evaluate('noSuchView', mk('Tenant Admin', ['*']))).toMatchObject({ allowed: false, reason: 'unmapped' });
    expect(evaluate('noSuchView', mk('Super Admin', []))).toEqual({
      allowed: false,
      reason: 'unmapped',
      label: 'noSuchView',
    });
  });

  it('allows a held permission and denies a missing one with the required permission named', () => {
    const user = mk('itam_user', ['view:itam', 'view:profile']);
    expect(evaluate('itam', user)).toEqual({ allowed: true });
    expect(evaluate('dashboard', user)).toEqual({
      allowed: false,
      reason: 'role',
      permission: 'view:dashboard',
      label: 'Overview',
    });
  });

  it('denies a held permission whose screen carries a screen-off marker with reason switched_off', () => {
    const user = mk('Tenant Admin', ['view:security', 'screen-off:alertManagement']);
    expect(evaluate('alertManagement', user)).toMatchObject({ allowed: false, reason: 'switched_off' });
  });

  it('reports switched_off, not role, when the permission is gone and the screen is marked off', () => {
    const user = mk('Tenant Admin', ['view:dashboard', 'screen-off:compliance']);
    const result = evaluate('compliance', user);
    expect(result).toMatchObject({ allowed: false, reason: 'switched_off', label: 'Compliance' });
  });

  it.each(SUPER_ADMIN_SPELLINGS)('allows every manifest view for the super-admin spelling %s', role => {
    const user = mk(role, []);
    for (const entry of CATALOGUES) {
      expect(evaluate(entry.view, user)).toEqual({ allowed: true });
    }
  });

  it('allows a delivered wildcard grant on any role', () => {
    expect(evaluate('compliance', mk('Tenant Admin', ['*']))).toEqual({ allowed: true });
  });

  it('lets a platform role that holds the permission through even when a screen-off marker is present', () => {
    const user = mk('Platform Support', ['view:compliance', 'screen-off:compliance']);
    expect(evaluate('compliance', user)).toEqual({ allowed: true });
  });

  it('treats a user with no permission array as holding nothing', () => {
    expect(evaluate('dashboard', mk('Tenant Admin'))).toMatchObject({ allowed: false, reason: 'role' });
  });
});

describe('landingView (D-06, D-12)', () => {
  it('lands on dashboard when the role holds view:dashboard', () => {
    expect(landing(mk('Tenant Admin', ['view:dashboard', 'view:itam']))).toBe('dashboard');
  });

  it('lands on itam for the ITAM permission set although assetManagement precedes it in the menu', () => {
    expect(landing(mk('itam_viewer', ['view:assets', 'view:itam', 'view:licenses', 'view:profile']))).toBe('itam');
  });

  it('lands on the first allowed sidebar item in manifest order for Platform Billing', () => {
    expect(landing(mk('platform_billing', ['view:audit_log', 'view:profile', 'view:tenants']))).toBe('auditLog');
  });

  it('skips a preferred view whose screen is switched off', () => {
    const user = mk('Tenant Admin', ['view:dashboard', 'view:itam', 'screen-off:dashboard']);
    expect(landing(user)).toBe('itam');
  });

  it('is null for no user and for an empty permission list; hasAnyScreen mirrors it', () => {
    expect(landingView(null, () => false)).toBeNull();
    const empty = mk('Custom Role', []);
    expect(landing(empty)).toBeNull();
    expect(hasAnyScreen(empty, derivePermissionState(empty).hasPermission)).toBe(false);
    const some = mk('Tenant Admin', ['view:dashboard']);
    expect(hasAnyScreen(some, derivePermissionState(some).hasPermission)).toBe(true);
  });

  it('gives two roles with the same allowed set the same landing view', () => {
    const set = ['view:security', 'view:profile'];
    expect(landing(mk('Role A', set))).toBe(landing(mk('Role B', [...set].reverse())));
  });
});

describe('permissionsKnown (C09)', () => {
  it('is false for no user and for a user without a permissions array', () => {
    expect(permissionsKnown(null)).toBe(false);
    expect(permissionsKnown(mk('Tenant Admin'))).toBe(false);
  });

  it('is true for a super admin without a list and for a user with an empty list', () => {
    expect(permissionsKnown(mk('Super Admin'))).toBe(true);
    expect(permissionsKnown(mk('Tenant Admin', []))).toBe(true);
  });
});
