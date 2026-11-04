/**
 * Partner roles in User Management: a partner organization's users hold only partner roles and nobody
 * else holds one. The server refuses the rest ("Role 'Partner Admin' is a partner role and can only be
 * held in a partner organization"), so the forms must not offer them where they cannot be saved.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { AddUserModal } from '../../components/AddUserModal';
import { EditUserModal } from '../../components/EditUserModal';
import { UserContext } from '../../contexts/UserContext';

const ROLES = [
  { id: 'r-ta', name: 'Tenant Admin' }, { id: 'r-v', name: 'viewer' },
  { id: 'r-pa', name: 'Partner Admin' }, { id: 'r-pv', name: 'Partner Viewer' },
] as any[];
const TENANTS = [{ id: 't-acme', name: 'Acme' }, { id: 'p-retail', name: 'Retail Partner', type: 'partner' }] as any[];
const asOwner = (ui: React.ReactElement) => render(
  <UserContext.Provider value={{ currentUser: { id: 'u0', role: 'Super Admin', tenantId: 'platform-admin' }, hasPermission: () => true } as any}>
    {ui}
  </UserContext.Provider>);
const options = (label: string) => within(screen.getByLabelText(label)).getAllByRole('option').map(o => o.textContent);

describe('User Management role lists and partner organizations', () => {
  it('Add User offers partner roles only for a partner organization', () => {
    asOwner(<AddUserModal isOpen onClose={vi.fn()} onSave={vi.fn()} tenants={TENANTS} roles={ROLES} />);
    expect(options('Role').some(t => /partner/i.test(t || ''))).toBe(false);
    fireEvent.change(screen.getByLabelText('Tenant'), { target: { value: 'p-retail' } });
    expect(options('Role').every(t => /partner/i.test(t || ''))).toBe(true);
  });

  it('Edit User keeps a tenant user on tenant roles and a partner user on partner roles', () => {
    const { unmount } = asOwner(<EditUserModal user={{ id: 'u1', name: 'Ann', role: 'Tenant Admin', tenantId: 't-acme', status: 'Active' } as any} roles={ROLES} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(options('Role').some(t => /partner/i.test(t || ''))).toBe(false);
    unmount();
    asOwner(<EditUserModal user={{ id: 'u2', name: 'Bo', role: 'Partner Admin', tenantId: 'p-retail', status: 'Active' } as any} roles={ROLES} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(options('Role').every(t => /partner/i.test(t || ''))).toBe(true);
  });
});
