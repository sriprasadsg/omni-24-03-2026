/**
 * 77 WR-07: for a Super Admin the App role list holds the built-in roles only, so Add User and Edit User
 * read the chosen tenant's custom roles themselves (GET /api/roles?tenantId=). Other callers already get
 * their own tenant's custom roles in the list and make no extra request.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

const fetchRoles = vi.fn();
vi.mock('../../services/roleApi', () => ({ fetchRoles: (...args: unknown[]) => fetchRoles(...args) }));

import { AddUserModal } from '../../components/AddUserModal';
import { EditUserModal } from '../../components/EditUserModal';
import { UserContext } from '../../contexts/UserContext';

const BUILTINS = [{ id: 'r-ta', name: 'Tenant Admin', builtIn: true }, { id: 'r-v', name: 'viewer', builtIn: true }] as any[];
const CUSTOM: Record<string, any[]> = {
  't-acme': [{ id: 'c-hd', name: 'Help Desk', builtIn: false }, { id: 'c-d2', name: 'Desk Two', builtIn: false }],
  't-beta': [{ id: 'c-ns', name: 'Night Shift', builtIn: false }],
};
const TENANTS = [{ id: 't-acme', name: 'Acme' }, { id: 't-beta', name: 'Beta' }] as any[];

const as = (role: string, ui: React.ReactElement) => render(
  <UserContext.Provider value={{ currentUser: { id: 'u0', role, tenantId: role === 'Super Admin' ? 'platform-admin' : 't-acme' }, hasPermission: () => true } as any}>
    {ui}
  </UserContext.Provider>);
const options = (label: string) => within(screen.getByLabelText(label)).getAllByRole('option').map(o => o.textContent);

beforeEach(() => {
  fetchRoles.mockReset();
  fetchRoles.mockImplementation((tenantId: string) => Promise.resolve([...BUILTINS, ...(CUSTOM[tenantId] ?? [])]));
});

describe('User forms offer the tenant custom roles to a Super Admin', () => {
  it('Add User lists the selected tenant custom roles and saves one', async () => {
    const onSave = vi.fn();
    as('Super Admin', <AddUserModal isOpen onClose={vi.fn()} onSave={onSave} tenants={TENANTS} roles={BUILTINS} />);
    await waitFor(() => expect(options('Role')).toContain('Help Desk'));
    expect(fetchRoles).toHaveBeenCalledWith('t-acme');
    fireEvent.change(screen.getByLabelText('Tenant'), { target: { value: 't-beta' } });
    await waitFor(() => expect(options('Role')).toContain('Night Shift'));
    expect(options('Role')).not.toContain('Help Desk');
    fireEvent.change(screen.getByLabelText('Full Name'), { target: { value: 'Nia' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'nia@beta.test' } });
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'Night Shift' } });
    fireEvent.submit(screen.getByLabelText('Role').closest('form')!);
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ role: 'Night Shift', tenantId: 't-beta' }));
  });

  it('Edit User shows the user custom role once and the other custom roles of that tenant', async () => {
    as('Super Admin', <EditUserModal user={{ id: 'u1', name: 'Ann', role: 'Help Desk', tenantId: 't-acme', status: 'Active' } as any}
      roles={BUILTINS} onClose={vi.fn()} onSave={vi.fn()} />);
    await waitFor(() => expect(options('Role')).toContain('Desk Two'));
    expect(fetchRoles).toHaveBeenCalledWith('t-acme');
    expect(options('Role').filter(t => t === 'Help Desk')).toHaveLength(1);
    expect((screen.getByLabelText('Role') as HTMLSelectElement).value).toBe('Help Desk');
  });

  it('keeps the built-in roles when the tenant roles cannot be read', async () => {
    fetchRoles.mockImplementation(() => Promise.reject(new Error('down')));
    as('Super Admin', <AddUserModal isOpen onClose={vi.fn()} onSave={vi.fn()} tenants={TENANTS} roles={BUILTINS} />);
    await waitFor(() => expect(fetchRoles).toHaveBeenCalled());
    expect(options('Role')).toEqual(['Tenant Admin', 'Viewer']);
  });

  it('a tenant admin gets the roles from the App list, with no extra request', () => {
    const roles = [...BUILTINS, ...CUSTOM['t-acme']];
    as('Tenant Admin', <AddUserModal isOpen onClose={vi.fn()} onSave={vi.fn()} tenants={TENANTS.slice(0, 1)} roles={roles} />);
    expect(options('Role')).toContain('Help Desk');
    as('Tenant Admin', <EditUserModal user={{ id: 'u1', name: 'Ann', role: 'viewer', tenantId: 't-acme', status: 'Active' } as any}
      roles={roles} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(fetchRoles).not.toHaveBeenCalled();
  });
});
