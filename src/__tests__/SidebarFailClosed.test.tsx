/**
 * Phase 77 (ACC-06, C02, C04, C05): the sidebar fails closed. A missing context, a null user, a
 * missing permission function or an undelivered permission list grants nothing, and the menu is
 * filtered by the same evaluateViewAccess rule the render-time gate uses.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  authFetch: vi.fn(),
  fetchSupportUnreadCount: () => Promise.resolve(0),
}));
vi.mock('../../services/socketService', () => ({ socketService: { on: vi.fn(), off: vi.fn() } }));

import { Sidebar } from '../../components/Sidebar';
import { UserContext } from '../../contexts/UserContext';
import { NAV_GROUPS } from '../../utils/catalogueAccess';

const itemLabel = (view: string) =>
  NAV_GROUPS.flatMap(g => g.items).find(i => i.view === view)!.label;

const tenantUser = (permissions?: string[], role = 'Tenant Admin') =>
  ({ id: 'u', name: 'T', email: 't@x', role, tenantId: 'tenant-a', permissions }) as any;

function renderWith(value: any, props: { isOpen?: boolean; isViewingTenant?: boolean } = {}) {
  return render(
    <UserContext.Provider value={value}>
      <Sidebar
        isOpen={props.isOpen ?? true}
        currentView="dashboard"
        setCurrentView={() => {}}
        isViewingTenant={props.isViewingTenant ?? false}
        onBackToTenants={() => {}}
      />
    </UserContext.Provider>,
  );
}

const overList = (list: string[]) => (p: string) => list.includes(p);
const labels = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('button')).map(b => b.textContent?.trim() ?? '');
const hasLabel = (container: HTMLElement, label: string) => labels(container).some(l => l.startsWith(label));

describe('Sidebar fails closed (ACC-06)', () => {
  it('renders no item when the user is null', () => {
    const { container } = renderWith({ currentUser: null, hasPermission: (p: string) => !p.startsWith('screen-off:') });
    expect(labels(container).filter(l => l !== '')).toEqual([]);
  });

  it('renders no item when the context has no hasPermission function', () => {
    const { container } = renderWith({ currentUser: tenantUser(['view:dashboard']) });
    expect(labels(container).filter(l => l !== '')).toEqual([]);
  });

  it('renders no item and no group header for a tenant user holding nothing', () => {
    const { container } = renderWith({ currentUser: tenantUser([]), hasPermission: () => false });
    expect(labels(container).filter(l => l !== '')).toEqual([]);
  });

  it('shows only the catalogues an itam_viewer-like user holds', () => {
    const perms = ['view:assets', 'view:itam', 'view:licenses', 'view:profile'];
    const { container } = renderWith({ currentUser: tenantUser(perms), hasPermission: overList(perms) });
    expect(hasLabel(container, itemLabel('assetManagement'))).toBe(true);
    expect(hasLabel(container, itemLabel('itam'))).toBe(true);
    expect(hasLabel(container, itemLabel('dashboard'))).toBe(false);
  });

  it('hides a screen the tenant switched off', () => {
    const perms = ['view:security', 'screen-off:alertManagement'];
    const { container } = renderWith({ currentUser: tenantUser(perms), hasPermission: overList(perms) });
    expect(hasLabel(container, itemLabel('edr'))).toBe(true);
    expect(hasLabel(container, itemLabel('alertManagement'))).toBe(false);
  });

  it('recognises the platform-admin spelling as a super admin and offers Back to Tenants', () => {
    const user = tenantUser([], 'platform-admin');
    const { container } = renderWith({ currentUser: user, hasPermission: () => false }, { isViewingTenant: true });
    const shown = labels(container);
    const manifestItems = NAV_GROUPS.flatMap(g => g.items).filter(i => i.permission !== 'manage:tenants');
    for (const item of manifestItems) expect(shown.some(l => l.startsWith(item.label))).toBe(true);
    expect(shown.some(l => l.startsWith('Back to Tenants'))).toBe(true);
  });
});
