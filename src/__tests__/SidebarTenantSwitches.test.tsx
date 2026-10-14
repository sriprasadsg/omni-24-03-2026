/**
 * Spec C6: a tenant user's sidebar shows exactly the features the Super Admin switched on,
 * with no "Requires <plan> — click to upgrade" items.
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
import { isTenantSwitchable, switchedOnFor } from '../../utils/permissions';

// The server already removed switched-off features from this list (backend/tenant_features.py).
const granted = new Set(['view:dashboard', 'view:profile', 'view:mlops', 'view:agents']);
// Plan-tier locks as /api/platform/features reports them for a Free tenant.
const locks = { mlops: 'Enterprise', digital_twin: 'Enterprise', cxo_dashboard: 'Enterprise' };

function renderSidebar(role: string) {
  const user = { id: 'u', name: 'T', email: 't@x', role, tenantId: role === 'Super Admin' ? 'platform-admin' : 'tenant-a' } as any;
  return render(
    <UserContext.Provider value={{ currentUser: user, hasPermission: (p: string) => granted.has(p), serverLockedFeatures: locks } as any}>
      <Sidebar isOpen currentView="dashboard" setCurrentView={() => {}} isViewingTenant={false} onBackToTenants={() => {}} />
    </UserContext.Provider>,
  );
}

const labels = (container: HTMLElement) => Array.from(container.querySelectorAll('button')).map(b => b.textContent?.trim() ?? '');

describe('Sidebar for a tenant user (spec C6)', () => {
  it('shows a switched-on feature unlocked, hides a switched-off one, and never offers an upgrade', () => {
    const { container } = renderSidebar('Tenant Admin');
    const shown = labels(container);
    expect(shown.some(l => l.startsWith('MLOps'))).toBe(true);           // Enterprise-gated, but switched on
    expect(shown.some(l => l.startsWith('Digital Twin'))).toBe(true);    // Enterprise-gated, its screen switched on
    expect(shown.some(l => l.startsWith('CXO Insights'))).toBe(false);   // switched off (not granted)
    expect(container.querySelector('[title*="click to upgrade"]')).toBeNull();
  });

  it('hides a sidebar item whose own screen switch is off, even one every role reaches', () => {
    granted.add('screen-off:digitalTwin');
    granted.add('screen-off:internalTickets');
    try {
      const shown = labels(renderSidebar('Tenant Admin').container);
      expect(shown.some(l => l.startsWith('Digital Twin'))).toBe(false);
      expect(shown.some(l => l.startsWith('Tickets'))).toBe(false);
      expect(shown.some(l => l.startsWith('AI Assistant'))).toBe(true);  // same permission, still on
    } finally {
      granted.delete('screen-off:digitalTwin');
      granted.delete('screen-off:internalTickets');
    }
  });

  it('the Super Admin still sees everything, unlocked', () => {
    const { container } = renderSidebar('Super Admin');
    expect(labels(container).some(l => l.startsWith('Digital Twin'))).toBe(true);
    expect(container.querySelector('[title*="click to upgrade"]')).toBeNull();
  });

  it('knows which permissions a tenant switch governs, as the server does', () => {
    expect(isTenantSwitchable('view:mlops')).toBe(true);
    expect(isTenantSwitchable('manage:mlops')).toBe(true);     // the view twin goes with the switch
    expect(isTenantSwitchable('view:itam')).toBe(true);
    expect(isTenantSwitchable('view:dashboard')).toBe(false);
    expect(isTenantSwitchable('view:profile')).toBe(false);
    expect(isTenantSwitchable('view:dashboard', 'digitalTwin')).toBe(true);  // its own screen switch
  });
});

describe('Per-screen switches (spec C6)', () => {
  it('shows only the Security screens switched on for the tenant', async () => {
    const manifest = (await import('../../shared/catalogue-access.json')).default as { catalogues: { view: string; label: string }[] };
    const label = (view: string) => manifest.catalogues.find(c => c.view === view)!.label;
    granted.add('view:security');
    granted.add('screen-off:alertManagement');   // the server marks the switched-off screen
    try {
      const { container } = renderSidebar('Tenant Admin');
      const shown = labels(container);
      expect(shown.some(l => l.startsWith(label('edr')))).toBe(true);
      expect(shown.some(l => l.startsWith(label('alertManagement')))).toBe(false);
    } finally {
      granted.delete('view:security');
      granted.delete('screen-off:alertManagement');
    }
  });
});

describe('Startup fetches skip what the tenant switches took away (spec C6)', () => {
  const holding = (...perms: string[]) => (p: string) => perms.includes(p);
  it('skips a switched-off feature and a switched-off screen, never a role-only or hide-only one', () => {
    expect(switchedOnFor('chaosEngineering', 'view:chaos', holding())).toBe(false);                 // switch off
    expect(switchedOnFor('chaosEngineering', 'view:chaos', holding('manage:chaos'))).toBe(true);    // the guard accepts the twin
    expect(switchedOnFor('distributedTracing', 'view:tracing',
      holding('view:tracing', 'screen-off:distributedTracing'))).toBe(false);                        // screen off
    expect(switchedOnFor('distributedTracing', 'view:tracing', holding('view:tracing'))).toBe(true);
    expect(switchedOnFor('agents', 'view:agents', holding('view:agents', 'screen-off:agents'))).toBe(true); // hide-only
    expect(switchedOnFor('dashboard', 'view:dashboard', holding())).toBe(true);                      // no switch: unchanged
  });
});
