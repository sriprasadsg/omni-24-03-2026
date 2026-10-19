/**
 * Phase 77 (D-08, D-17 app-shell scope): a role never requests, nor renders, what it cannot read.
 * canReadView mirrors the backend read rule; the startup fetches, the dashboard refresh, the
 * notification centre and the dashboard widgets all ask it.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { canReadView } from '../../utils/viewAccess';
import { derivePermissionState } from '../../utils/permissions';
import type { User } from '../../types';

const mk = (role: string, permissions?: string[]): User =>
  ({ id: 'u1', name: 'U', email: 'u@x.test', role, tenantId: 't1', permissions }) as unknown as User;

const can = (view: string, user: User | null) =>
  canReadView(view as never, user, derivePermissionState(user).hasPermission);

const ITAM_VIEWER = ['view:itam', 'view:assets', 'view:profile'];
const VIEWER = ['view:dashboard', 'view:compliance', 'view:profile'];

describe('canReadView (D-08)', () => {
  it('lets an ITAM viewer read its own catalogues and nothing outside them', () => {
    const user = mk('itam_viewer', ITAM_VIEWER);
    expect(can('assetManagement', user)).toBe(true);
    expect(can('itam', user)).toBe(true);
    expect(can('notifications', user)).toBe(false);
    expect(can('integrations', user)).toBe(false);
  });

  it('lets a viewer read compliance but not settings', () => {
    const user = mk('viewer', VIEWER);
    expect(can('compliance', user)).toBe(true);
    expect(can('notifications', user)).toBe(true);
    expect(can('settings', user)).toBe(false);
  });

  it('reads user and role lists through the read list, not only the write permission', () => {
    const admin = mk('itam_admin', ['view:itam', 'manage:users']);
    expect(can('userManagement', admin)).toBe(true);
    expect(can('roleManagement', admin)).toBe(true);
    expect(can('settings', admin)).toBe(false);
    expect(can('settings', mk('Platform Support', ['view:dashboard']))).toBe(false);
  });

  it('lets a super admin read every manifest view and nothing unmapped', () => {
    const sa = mk('Super Admin', []);
    expect(can('settings', sa)).toBe(true);
    expect(can('userManagement', sa)).toBe(true);
    expect(can('noSuchView', sa)).toBe(false);
    expect(can('settings', mk('Tenant Admin', ['*']))).toBe(true);
  });

  it('never reads for a missing user', () => {
    expect(can('dashboard', null)).toBe(false);
  });

  it('keeps hide-only screens readable when switched off, and closes other switched-off screens', () => {
    expect(can('agents', mk('analyst', ['view:agents', 'screen-off:agents']))).toBe(true);
    expect(can('alertManagement', mk('analyst', ['view:security', 'screen-off:alertManagement']))).toBe(false);
  });
});

describe('startup fetch plan (App.tsx source guard)', () => {
  const app = readFileSync(resolve(__dirname, '../../App.tsx'), 'utf8');

  it('gates ifOn on canReadView and fails closed without a user', () => {
    expect(app).toMatch(/const ifOn[\s\S]{0,400}canReadView\(/);
    expect(app).not.toMatch(/const ifOn[^\n]*!user \|\|/);
  });

  it('gates the user and role lists by their catalogues and recognises Super Admin by name', () => {
    expect(app).toContain("ifOn('userManagement', api.fetchUsers)");
    expect(app).toContain("ifOn('roleManagement', api.fetchRoles)");
    expect(app).toContain('isSuperAdminRoleName(_jwtPayload.role)');
  });

  it('skips the dashboard alerts refresh when alerts are unreadable', () => {
    expect(app).toMatch(/canReadView\('alertManagement', currentUser/);
  });
});

describe('fetchIntegrations (Pitfall 10)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('returns [] on a refused response instead of keeping the error body', async () => {
    localStorage.setItem('token', 'x');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'no' }), { status: 403 })));
    const { fetchIntegrations } = await import('../../services/apiService');
    expect(await fetchIntegrations()).toEqual([]);
  });
});
