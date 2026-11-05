/**
 * Partner UI QA 2026-11-04: the Sidebar polled /api/support/unread-count for a tenant whose Chat screen
 * was switched off, and every poll was refused (403). The count only feeds the Chat item's badge, so it
 * is asked for only while Chat is readable.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

const unread = vi.fn(() => Promise.resolve(0));
vi.mock('../../services/apiService', () => ({ authFetch: vi.fn(), fetchSupportUnreadCount: () => unread() }));
vi.mock('../../services/socketService', () => ({ socketService: { on: vi.fn(), off: vi.fn() } }));

import { Sidebar } from '../../components/Sidebar';
import { UserContext } from '../../contexts/UserContext';

function renderFor(role: string, permissions: string[]) {
  const granted = new Set(permissions);
  const user = { id: 'u', name: 'T', email: 't@x', role, tenantId: 'tenant-a', permissions } as any;
  return render(
    <UserContext.Provider value={{ currentUser: user, hasPermission: (p: string) => granted.has(p) } as any}>
      <Sidebar isOpen currentView="dashboard" setCurrentView={() => {}} isViewingTenant={false} onBackToTenants={() => {}} />
    </UserContext.Provider>,
  );
}

describe('Sidebar support unread poll', () => {
  beforeEach(() => unread.mockClear());

  it('asks while the Chat screen is readable', () => {
    renderFor('Tenant Admin', ['view:dashboard', 'manage:agents']);
    expect(unread).toHaveBeenCalledTimes(1);
  });

  it('never asks when the tenant switched Chat off', () => {
    renderFor('Tenant Admin', ['view:dashboard', 'manage:agents', 'screen-off:chat']);
    expect(unread).not.toHaveBeenCalled();
  });

  it('never asks for a role without the Chat permission', () => {
    renderFor('Viewer', ['view:dashboard']);
    expect(unread).not.toHaveBeenCalled();
  });
});
