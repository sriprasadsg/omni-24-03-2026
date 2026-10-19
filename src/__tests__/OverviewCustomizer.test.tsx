/**
 * Customize Overview: a user hides widgets for themselves only. The role's gates still apply first,
 * so a widget the role cannot read is neither shown nor offered; hiding everything shows a way back.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ authFetch: vi.fn() }));
const { stub } = vi.hoisted(() => ({
  stub: (id: string) => async () => { const R = await import('react'); return { [id]: () => R.createElement('div', { 'data-testid': id }) }; },
}));
vi.mock('../../components/MetricCard', stub('MetricCard'));
vi.mock('../../components/AlertsPanel', stub('AlertsPanel'));
vi.mock('../../components/ComplianceStatus', stub('ComplianceStatus'));
vi.mock('../../components/ComplianceScorePanel', stub('ComplianceScorePanel'));
vi.mock('../../components/AiInsights', stub('AiInsights'));
vi.mock('../../components/AiSystemHealth', stub('AiSystemHealth'));
vi.mock('../../components/BusinessKpiChart', stub('BusinessKpiChart'));
vi.mock('../../components/SystemHealthChart', stub('SystemHealthChart'));

import { Dashboard } from '../../components/Dashboard';
import { UserContext } from '../../contexts/UserContext';
import { derivePermissionState } from '../../utils/permissions';

const user = { id: 'u', name: 'Vi Ewer', email: 'vi@x.test', role: 'viewer', tenantId: 't1', permissions: ['view:dashboard', 'view:compliance', 'view:profile'] } as any;
const metric = { id: 'cpu', title: 'CPU', value: '42%', change: '+1%', changeType: 'increase', type: 'cpu', data: [] } as any;

function renderOverview() {
  return render(
    <UserContext.Provider value={{ currentUser: user, hasPermission: derivePermissionState(user).hasPermission } as any}>
      <Dashboard metrics={[metric]} alerts={[]} complianceFrameworks={[]} aiSystems={[]} agents={[]} currentUser={user} setCurrentView={vi.fn()} />
    </UserContext.Provider>,
  );
}

const openCustomizer = () => fireEvent.click(screen.getByRole('button', { name: 'Customize' }));

beforeEach(() => localStorage.clear());

describe('Customize Overview', () => {
  it('offers only the widgets the role can read', () => {
    renderOverview();
    openCustomizer();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('switch', { name: 'Show Compliance' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('switch', { name: 'Show Recent signals' })).toBeNull();
    expect(within(dialog).queryByRole('switch', { name: 'Show Business KPIs' })).toBeNull();
  });

  it('hides a widget for this user and remembers it', () => {
    const first = renderOverview();
    expect(screen.getByTestId('ComplianceStatus')).toBeInTheDocument();
    openCustomizer();
    fireEvent.click(screen.getByRole('switch', { name: 'Show Compliance' }));
    expect(screen.queryByTestId('ComplianceStatus')).toBeNull();
    expect(JSON.parse(localStorage.getItem('omni.overview.hidden.vi@x.test|t1')!)).toEqual(['compliance']);
    first.unmount();
    renderOverview();
    expect(screen.queryByTestId('ComplianceStatus')).toBeNull();
    expect(screen.getByTestId('SystemHealthChart')).toBeInTheDocument();
  });

  it('shows a way back when every widget is hidden, and "Show all" restores them', () => {
    renderOverview();
    openCustomizer();
    for (const sw of within(screen.getByRole('dialog')).getAllByRole('switch')) fireEvent.click(sw);
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.getByText('Every widget is hidden')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Customize Overview' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(screen.queryByText('Every widget is hidden')).toBeNull();
    expect(screen.getByTestId('MetricCard')).toBeInTheDocument();
  });

  it('never shows a role-gated widget even if storage lists it as visible', () => {
    localStorage.setItem('omni.overview.hidden.vi@x.test|t1', JSON.stringify(['bogus']));
    renderOverview();
    expect(screen.queryByTestId('AlertsPanel')).toBeNull();
    expect(screen.queryByTestId('BusinessKpiChart')).toBeNull();
  });
});
