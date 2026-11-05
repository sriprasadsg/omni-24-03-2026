/**
 * Partner UI QA 2026-11-04: #userManagement and its sibling links open Settings (they have no screen
 * of their own); Settings then opens the tab the link names, when the user may see that tab.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('../../services/roleApi', async () => {
  const actual = await vi.importActual<any>('../../services/roleApi');
  return { ...actual, fetchRoles: vi.fn(() => Promise.resolve([])), fetchRoleVisibility: vi.fn(() => new Promise(() => {})) };
});

import { SettingsDashboard } from '../../components/SettingsDashboard';
import { UserContext } from '../../contexts/UserContext';

const props: any = {
  integrations: [], alertRules: [], roles: [], users: [], apiKeys: [], dataSources: [], newlyGeneratedKey: null,
  databaseSettings: null, llmSettings: null, tenants: [], viewingTenantId: null,
};

function openAt(hash: string, role: string, permissions: string[]) {
  window.history.replaceState(null, '', hash);
  const granted = new Set(permissions);
  const user = { id: 'u', name: 'T', email: 't@x', role, tenantId: 'tenant-a', permissions } as any;
  const { container } = render(
    <UserContext.Provider value={{ currentUser: user, hasPermission: (p: string) => granted.has(p) } as any}>
      <SettingsDashboard {...props} />
    </UserContext.Provider>,
  );
  return Array.from(container.querySelectorAll('nav button'))
    .find(b => b.className.includes('border-primary-500'))?.textContent?.trim();
}

describe('Settings opens the tab a deep link names', () => {
  afterEach(() => window.history.replaceState(null, '', '#'));

  it('opens User Management for #userManagement', () => {
    expect(openAt('#userManagement', 'Super Admin', ['*'])).toBe('User Management');
  });

  it('opens Roles & Permissions for #roleManagement', () => {
    expect(openAt('#roleManagement', 'Super Admin', ['*'])).toBe('Roles & Permissions');
  });

  it('keeps the usual first tab when the link names a tab the user cannot see', () => {
    expect(openAt('#userManagement', 'Tenant Admin', ['manage:settings', 'manage:users'])).toBe('Appearance');
  });

  it('keeps the usual first tab for a plain #settings', () => {
    expect(openAt('#settings', 'Super Admin', ['*'])).toBe('Appearance');
  });
});
