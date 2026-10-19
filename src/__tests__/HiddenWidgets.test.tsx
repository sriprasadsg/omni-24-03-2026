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

// ---- Task 2: NotificationCenter, Dashboard and AllPartsHiddenNotice ---------------------------

const { getNotifications, socketOn } = vi.hoisted(() => ({ getNotifications: vi.fn(async () => []), socketOn: vi.fn() }));
vi.mock('../../services/apiService', async importOriginal => {
  const actual = await importOriginal<typeof import('../../services/apiService')>();
  return { ...actual, getNotifications: (...a: unknown[]) => getNotifications(...(a as [])) };
});
vi.mock('../../services/socketService', () => ({ socketService: { on: (...a: unknown[]) => socketOn(...a), off: vi.fn() } }));
vi.mock('../../components/MetricCard', async () => { const R = await import('react'); return { MetricCard: () => R.createElement('div', { 'data-testid': 'MetricCard' }) }; });
vi.mock('../../components/AlertsPanel', async () => { const R = await import('react'); return { AlertsPanel: () => R.createElement('div', { 'data-testid': 'AlertsPanel' }) }; });
vi.mock('../../components/ComplianceStatus', async () => { const R = await import('react'); return { ComplianceStatus: () => R.createElement('div', { 'data-testid': 'ComplianceStatus' }) }; });
vi.mock('../../components/ComplianceScorePanel', async () => { const R = await import('react'); return { ComplianceScorePanel: () => R.createElement('div', { 'data-testid': 'ComplianceScorePanel' }) }; });
vi.mock('../../components/AiInsights', async () => { const R = await import('react'); return { AiInsights: () => R.createElement('div', { 'data-testid': 'AiInsights' }) }; });
vi.mock('../../components/AiSystemHealth', async () => { const R = await import('react'); return { AiSystemHealth: () => R.createElement('div', { 'data-testid': 'AiSystemHealth' }) }; });
vi.mock('../../components/DashboardHeader', async () => { const R = await import('react'); return { DashboardHeader: () => R.createElement('div', { 'data-testid': 'DashboardHeader' }) }; });
vi.mock('../../components/BusinessKpiChart', async () => { const R = await import('react'); return { BusinessKpiChart: () => R.createElement('div', { 'data-testid': 'BusinessKpiChart' }) }; });
vi.mock('../../components/SystemHealthChart', async () => { const R = await import('react'); return { SystemHealthChart: () => R.createElement('div', { 'data-testid': 'SystemHealthChart' }) }; });

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { UserContext } from '../../contexts/UserContext';
import NotificationCenter from '../../components/NotificationCenter';
import { Dashboard } from '../../components/Dashboard';
import { AllPartsHiddenNotice } from '../../components/NoAccessPanel';

function withUser(user: User, ui: React.ReactElement) {
  const { hasPermission } = derivePermissionState(user);
  const value = { currentUser: user, hasPermission, enabledFeatures: [], serverLockedFeatures: {} } as never;
  return render(<UserContext.Provider value={value}>{ui}</UserContext.Provider>);
}

describe('NotificationCenter gating (D-08)', () => {
  afterEach(() => { getNotifications.mockClear(); socketOn.mockClear(); sessionStorage.clear(); });

  it('renders nothing and requests nothing for an ITAM role', () => {
    sessionStorage.setItem('token', 'x');
    const { container } = withUser(mk('itam_viewer', ITAM_VIEWER), <NotificationCenter />);
    expect(container.firstChild).toBeNull();
    expect(getNotifications).not.toHaveBeenCalled();
    expect(socketOn).not.toHaveBeenCalled();
  });

  it('renders the bell and polls once on mount for a viewer', () => {
    sessionStorage.setItem('token', 'x');
    const { container } = withUser(mk('viewer', VIEWER), <NotificationCenter />);
    expect(container.firstChild).not.toBeNull();
    expect(getNotifications).toHaveBeenCalledTimes(1);
    expect(socketOn).toHaveBeenCalledWith('notification', expect.any(Function));
  });
});

describe('Dashboard widget gating (D-08, C17, C20)', () => {
  const props = (user: User, metrics: unknown[] = []) => ({
    metrics: metrics as never[], alerts: [], complianceFrameworks: [], aiSystems: [], agents: [], currentUser: user, setCurrentView: vi.fn(),
  });
  const metric = [{ id: 'm1' }];

  it('shows compliance widgets for a viewer and hides the rest', () => {
    withUser(mk('viewer', VIEWER), <Dashboard {...props(mk('viewer', VIEWER), metric)} />);
    expect(screen.getByTestId('ComplianceScorePanel')).toBeTruthy();
    expect(screen.getByTestId('ComplianceStatus')).toBeTruthy();
    expect(screen.queryByTestId('BusinessKpiChart')).toBeNull();
    expect(screen.queryByTestId('AlertsPanel')).toBeNull();
    expect(screen.queryByTestId('AiSystemHealth')).toBeNull();
  });

  it('lets the one remaining KPI/health widget span the whole row', () => {
    const user = mk('analyst', ['view:dashboard', 'view:agents']);
    const { container } = withUser(user, <Dashboard {...props(user, metric)} />);
    expect(screen.getByTestId('AiSystemHealth')).toBeTruthy();
    expect(screen.queryByTestId('BusinessKpiChart')).toBeNull();
    expect(container.querySelector('.lg\\:col-span-3')).not.toBeNull();
    expect(container.querySelector('.lg\\:col-span-2')).toBeNull();
  });

  it('falls back to the all-hidden line with no Go to button when nothing is readable', () => {
    const user = mk('nobody', []);
    withUser(user, <Dashboard {...props(user)} />);
    expect(screen.getByText('Nothing on this screen is available to your role yet.')).toBeTruthy();
    expect(screen.queryByText(/^Go to /)).toBeNull();
  });
});

describe('AllPartsHiddenNotice (C17)', () => {
  it('offers the landing screen and calls the handler', () => {
    const go = vi.fn();
    render(<AllPartsHiddenNotice landingLabel="ITAM" onGoToLanding={go} />);
    fireEvent.click(screen.getByText('Go to ITAM'));
    expect(go).toHaveBeenCalledTimes(1);
  });
});
