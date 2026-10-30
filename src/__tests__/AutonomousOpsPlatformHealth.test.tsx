/**
 * Phase 82 / HEAL-01..05, D-20: the Platform health section on the Autonomous Ops screen.
 * authFetch is mocked; the health payload follows GET /api/platform/autonomous-ops/health (82-08).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsActivity } from '../../components/AutonomousOpsActivity';
import { mockAuthFetch, jsonRes, healthDoc, healthCalls } from './_platformHealthHarness';

const PLATFORM_CONTROL = 'control:platform_autonomous_ops';
const TENANT_ADMIN = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops'];
const SUPER = [...TENANT_ADMIN, PLATFORM_CONTROL];

function tenantStatus() {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
  };
}
const platformStatus = () => ({
  scope: 'platform', stop: { platform: null }, tenantStopsCount: 0, canStopPlatform: true, canResumePlatform: true,
});

/** Route authFetch by path; an unknown path fails loudly so a stray request shows up in the test. */
function route(health: () => Response | Promise<Response> = () => jsonRes(healthDoc())) {
  mockAuthFetch.mockImplementation(async (url: string) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return jsonRes(tenantStatus());
    if (path === '/api/platform/autonomous-ops/status') return jsonRes(platformStatus());
    if (path === '/api/autonomous-ops/actions' || path === '/api/platform/autonomous-ops/actions') {
      return jsonRes({ items: [], nextCursor: null });
    }
    if (path === '/api/platform/autonomous-ops/health') return health();
    throw new Error(`unexpected request ${url}`);
  });
}

function screenFor(role: string, permissions: string[], tenantId: string | null = null) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role, tenantId: 'tenant-a', permissions } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p),
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={tenantId} enabled>
        <AutonomousOpsActivity tenantId={tenantId} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

beforeEach(() => { mockAuthFetch.mockReset(); });
afterEach(() => { vi.useRealTimers(); });

describe('Platform health section (tracer)', () => {
  it('Super Admin in platform scope: one health request, the section between the status card and Activity, the watchdog Running and the four services in order', async () => {
    route();
    const { container } = render(screenFor('Super Admin', SUPER));

    const heading = await screen.findByRole('heading', { level: 2, name: 'Platform health' });
    expect(heading).toHaveAttribute('id', 'platform-health-title');
    expect(healthCalls().length).toBe(1);

    const section = container.querySelector('#platform-health') as HTMLElement;
    expect(section).not.toBeNull();
    expect(section).toHaveAttribute('aria-labelledby', 'platform-health-title');
    const status = container.querySelector('[data-slot="autonomous-ops-status"]') as HTMLElement;
    const activity = screen.getByRole('heading', { level: 2, name: 'Activity' });
    expect(status.compareDocumentPosition(section) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(section.compareDocumentPosition(activity) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await waitFor(() => expect(within(section).getByText('Running')).toBeInTheDocument());
    const cells = Array.from(section.querySelectorAll('dl.grid > div')).filter(c => c.querySelector('dt .font-mono'));
    expect(cells.map(c => c.querySelector('dt .font-mono')!.textContent)).toEqual(['mongod', 'omni-backend', 'nginx', 'ollama']);
    expect(cells.map(c => c.querySelector('dt')!.textContent)).toEqual(
      ['MongoDBmongod', 'Backendomni-backend', 'nginxnginx', 'Ollamaollama'],
    );
    expect(within(cells[0] as HTMLElement).getByText('Healthy')).toBeInTheDocument();
    expect(within(cells[3] as HTMLElement).getByText('Expected off')).toBeInTheDocument();
  });

  it('Super Admin viewing a tenant: no health request and no section', async () => {
    route();
    render(screenFor('Super Admin', SUPER, 'tenant-a'));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('heading', { name: 'Platform health' })).toBeNull();
    expect(healthCalls().length).toBe(0);
  });

  it('a tenant admin: no health request and no section', async () => {
    route();
    render(screenFor('Tenant Admin', TENANT_ADMIN));
    await screen.findByRole('heading', { level: 2, name: 'Activity' });
    expect(screen.queryByRole('heading', { name: 'Platform health' })).toBeNull();
    expect(healthCalls().length).toBe(0);
  });
});
