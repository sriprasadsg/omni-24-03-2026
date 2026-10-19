/**
 * Phase 77 / ACC-07, D-10, D-17, D-18: the Roles table, its chips, accessible actions and
 * tab access for anyone who can list roles.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/roleApi', async () => {
  const actual = await vi.importActual<any>('../../services/roleApi');
  return { ...actual, fetchRoles: vi.fn(), fetchRoleVisibility: vi.fn(() => new Promise(() => {})) };
});

import { fetchRoles } from '../../services/roleApi';
import { SettingsRolesTab } from '../../components/SettingsRolesTab';
import { SettingsDashboard } from '../../components/SettingsDashboard';
import { UserContext } from '../../contexts/UserContext';

const mockRoles = fetchRoles as unknown as ReturnType<typeof vi.fn>;

const builtin = { id: 'role-viewer', name: 'Viewer', description: 'Read only', permissions: ['view:dashboard'], isEditable: false, builtIn: true } as any;
const unflagged = { id: 'role-x', name: 'Legacy', description: 'no flag', permissions: [], isEditable: true } as any;
const custom = { id: 'role-c1', name: 'Auditors', description: 'Custom one', permissions: [], isEditable: true, builtIn: false, tenantId: 'tenant-a' } as any;

const noop = () => {};
function tab(props: any = {}) {
  return render(<SettingsRolesTab roles={[builtin]} tenantId="tenant-a" canManageRBAC onEdit={noop} onDelete={noop} onNew={noop} {...props} />);
}

beforeEach(() => { mockRoles.mockReset(); mockRoles.mockRejectedValue(new Error('offline')); });

describe('SettingsRolesTab rows', () => {
  it('shows Built-in for builtIn true or a missing flag and Custom for builtIn false', () => {
    tab({ roles: [builtin, unflagged, custom] });
    const row = (name: string) => screen.getByText(name).closest('tr')!;
    expect(within(row('Viewer')).getByText('Built-in')).toBeTruthy();
    expect(within(row('Legacy')).getByText('Built-in')).toBeTruthy(); // fail safe: never from isEditable
    expect(within(row('Auditors')).getByText('Custom')).toBeTruthy();
  });

  it('labels Edit and Delete, disables built-in Edit with aria-disabled and omits its Delete', () => {
    tab({ roles: [builtin, custom] });
    const edit = screen.getByRole('button', { name: 'Edit role Viewer' });
    expect(edit.getAttribute('aria-disabled')).toBe('true');
    expect(edit.getAttribute('title')).toBe('Built-in roles cannot be edited.');
    expect(screen.queryByRole('button', { name: 'Delete role Viewer' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Edit role Auditors' }).getAttribute('aria-disabled')).not.toBe('true');
    expect(screen.getByRole('button', { name: 'Delete role Auditors' })).toBeTruthy();
  });

  it('keeps the table in an overflow-x-auto wrapper and truncates names with a title', () => {
    const { container } = tab({ roles: [builtin] });
    expect(container.querySelector('.overflow-x-auto table')).not.toBeNull();
    expect(screen.getByText('Viewer').getAttribute('title')).toBe('Viewer');
  });

  it('offers only What it can see when canManageRBAC is false', () => {
    tab({ roles: [builtin, custom], canManageRBAC: false });
    expect(screen.queryByRole('button', { name: /New Custom Role/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Edit role/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Delete role/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'What Viewer can see' })).toBeTruthy();
  });

  it('shows the no-custom-roles helper only when the list has no custom role', () => {
    const helper = 'No custom roles yet. Built-in roles cannot be edited; create a custom role to tailor access.';
    const { unmount } = tab({ roles: [builtin] });
    expect(screen.getByText(helper)).toBeTruthy();
    unmount();
    tab({ roles: [builtin, custom] });
    expect(screen.queryByText(helper)).toBeNull();
  });
});

describe('SettingsRolesTab list loading', () => {
  it('loads with fetchRoles(tenantId) and shows the fetched list', async () => {
    mockRoles.mockResolvedValue([builtin, custom]);
    tab({ roles: [builtin], tenantId: 'tenant-a' });
    await waitFor(() => expect(mockRoles).toHaveBeenCalledWith('tenant-a'));
    expect(await screen.findByText('Auditors')).toBeTruthy();
  });

  it('refetches when the tenant changes and keeps the seeded list on a rejected fetch', async () => {
    const { rerender } = tab({ roles: [builtin], tenantId: 'tenant-a' });
    await waitFor(() => expect(mockRoles).toHaveBeenCalledTimes(1));
    expect(screen.getByText('Viewer')).toBeTruthy();
    rerender(<SettingsRolesTab roles={[builtin]} tenantId="tenant-b" canManageRBAC onEdit={noop} onDelete={noop} onNew={noop} />);
    await waitFor(() => expect(mockRoles).toHaveBeenLastCalledWith('tenant-b'));
    expect(screen.getByText('Viewer')).toBeTruthy();
  });

  it('calls fetchRoles with no tenant when none is selected', async () => {
    tab({ tenantId: null, isSuperAdmin: true });
    await waitFor(() => expect(mockRoles).toHaveBeenCalledWith(undefined));
  });
});

describe('SettingsRolesTab New Custom Role (D-17)', () => {
  it('is disabled for a Super Admin without a tenant and enabled with one', () => {
    const { unmount } = tab({ tenantId: null, isSuperAdmin: true });
    const btn = screen.getByRole('button', { name: /New Custom Role/ }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute('title')).toBe('Select a tenant first: custom roles belong to one tenant.');
    unmount();
    tab({ tenantId: 'tenant-a', isSuperAdmin: true });
    expect((screen.getByRole('button', { name: /New Custom Role/ }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('SettingsDashboard Roles tab access (D-10)', () => {
  it('shows the Roles tab to a user with manage:settings and manage:users but not manage:rbac', () => {
    const granted = new Set(['manage:settings', 'manage:users']);
    const user = { id: 'u', name: 'T', email: 't@x', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: Array.from(granted) } as any;
    const props: any = {
      integrations: [], alertRules: [], roles: [builtin], users: [], apiKeys: [], dataSources: [], newlyGeneratedKey: null,
      databaseSettings: null, llmSettings: null, tenants: [], viewingTenantId: null,
    };
    const { container } = render(
      <UserContext.Provider value={{ currentUser: user, hasPermission: (p: string) => granted.has(p) } as any}>
        <SettingsDashboard {...props} />
      </UserContext.Provider>,
    );
    const labels = Array.from(container.querySelectorAll('nav button')).map(b => b.textContent?.trim());
    expect(labels).toContain('Roles & Permissions');
    expect(labels).not.toContain('User Management');
  });
});
