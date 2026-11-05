/** Partner UI QA 2026-11-04: the user list showed stored role keys such as "partner_admin". */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SettingsUsersTab } from '../../components/SettingsUsersTab';
import { UserContext } from '../../contexts/UserContext';

const people = [
  { id: 'u1', name: 'Pat', email: 'pat@x.test', role: 'partner_admin', tenantId: 'p1', status: 'Active' },
  { id: 'u2', name: 'Sam', email: 'sam@x.test', role: 'security_analyst', tenantId: 't1', status: 'Active' },
  { id: 'u3', name: 'Hal', email: 'hal@x.test', role: 'QA Helpdesk', tenantId: 't1', status: 'Active' },
] as any[];

describe('Settings > User Management role column', () => {
  it('shows each role by its readable name', () => {
    render(
      <UserContext.Provider value={{ currentUser: { id: 'me', role: 'Tenant Admin', tenantId: 't1' }, hasPermission: () => true } as any}>
        <SettingsUsersTab users={people} roles={[]} tenants={[]} filteredUsers={people} searchQuery="" canManageRBAC
          onSearchChange={vi.fn()} onEditUser={vi.fn()} onDeleteUser={vi.fn()} onResetPassword={vi.fn()} onAddUser={vi.fn()} />
      </UserContext.Provider>,
    );
    expect(screen.getByText('Partner Admin')).toBeTruthy();
    expect(screen.getByText('Security Analyst')).toBeTruthy();
    expect(screen.getByText('QA Helpdesk')).toBeTruthy();
    expect(screen.queryByText('partner_admin')).toBeNull();
  });
});

describe('no screen prints a stored role key', () => {
  it('every component shows a role as text through roleLabel', async () => {
    const { readdirSync, readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    const dir = resolve(__dirname, '../../components');
    const raw = readdirSync(dir).filter(f => f.endsWith('.tsx'))
      .filter(f => />\s*\{(currentUser|user|u|member)\??\.role\}\s*</.test(readFileSync(resolve(dir, f), 'utf8')));
    expect(raw).toEqual([]);
  });
});
