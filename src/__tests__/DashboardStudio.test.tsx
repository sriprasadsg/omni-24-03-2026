/**
 * Dashboard Studio (tenant-designed dashboards): the catalogue stays in step with the manifest
 * and the loaders, designers only get widgets of screens their organization has, and viewers can
 * hide widgets for themselves.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import widgetCatalogue from '../../shared/dashboard-widgets.json';
import manifest from '../../shared/catalogue-access.json';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
const api = vi.hoisted(() => ({
  listDashboards: vi.fn(), getDashboard: vi.fn(), getWidgetCatalogue: vi.fn(), createDashboard: vi.fn(),
  saveDashboard: vi.fn(), publishDashboard: vi.fn(), unpublishDashboard: vi.fn(), deleteDashboard: vi.fn(),
  setHiddenWidgets: vi.fn(),
}));
vi.mock('../../services/dashboardsApi', () => ({
  ...api,
  DashboardApiError: class extends Error {},
}));
vi.mock('../../services/roleApi', () => ({
  fetchRoles: () => Promise.resolve([{ name: 'analyst' }, { name: 'viewer' }, { name: 'Super Admin' }]),
}));

import { WIDGET_LOADERS, groupCounts, severityOf } from '../../components/dashboards/widgetData';
import { DashboardStudio, nudge, placeNew } from '../../components/dashboards/DashboardStudio';
import { DashboardsHub } from '../../components/dashboards/DashboardsHub';
import type { CatalogueWidget } from '../../services/dashboardsApi';

const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
const CATALOGUE = widgetCatalogue.widgets.map(w => ({ ...w, available: w.view !== 'patchManagement' })) as CatalogueWidget[];
const spec = (id: string) => CATALOGUE.find(w => w.id === id)!;

beforeEach(() => {
  Object.values(api).forEach(fn => fn.mockReset());
  authFetch.mockReset();
  authFetch.mockImplementation(() => ok([{ status: 'Online', platform: 'Linux' }, { status: 'Offline', platform: 'Windows' }]));
  api.getWidgetCatalogue.mockResolvedValue({ grid: widgetCatalogue.grid, widgets: CATALOGUE });
});

describe('widget catalogue', () => {
  it('has a loader for every widget and a widget for every loader', () => {
    expect(Object.keys(WIDGET_LOADERS).sort()).toEqual(widgetCatalogue.widgets.map(w => w.id).sort());
  });

  it('names only manifest screens', () => {
    const views = new Set(manifest.catalogues.map(c => c.view));
    expect(widgetCatalogue.widgets.filter(w => !views.has(w.view))).toEqual([]);
  });

  it('reads severities and folds the long tail into Other', () => {
    expect(['CRITICAL', 'serious', 'moderate', 'informational', 'x'].map(severityOf))
      .toEqual(['Critical', 'High', 'Medium', 'Low', null]);
    const counts = groupCounts(['a', 'a', 'b', 'c', 'd'], 2);
    expect(counts).toEqual([{ label: 'a', value: 2 }, { label: 'b', value: 1 }, { label: 'Other', value: 2 }]);
  });

  it('counts online agents from the agents API', async () => {
    await expect(WIDGET_LOADERS['agents-status']()).resolves.toEqual({ kind: 'kpi', value: 1, sub: 'of 2 agents' });
    expect(authFetch).toHaveBeenCalledWith('/api/agents');
  });
});

describe('layout helpers', () => {
  it('places a new widget below everything already on the grid', () => {
    const placed = placeNew([{ i: 'a', widget: 'agents-status', x: 0, y: 0, w: 3, h: 2 },
                             { i: 'b', widget: 'alerts-by-severity', x: 3, y: 1, w: 6, h: 4 }], spec('compliance-score'));
    expect(placed).toMatchObject({ widget: 'compliance-score', x: 0, y: 5, w: 3, h: 2 });
  });

  it('moves and resizes within the grid and the widget limits', () => {
    const w = { i: 'a', widget: 'agents-status', x: 9, y: 0, w: 3, h: 2 };
    expect(nudge(w, spec('agents-status'), 'ArrowRight', false)).toBeNull(); // already at the right edge
    expect(nudge(w, spec('agents-status'), 'ArrowLeft', false)).toMatchObject({ x: 8 });
    expect(nudge(w, spec('agents-status'), 'ArrowUp', true)).toBeNull();    // minH is 2
    expect(nudge(w, spec('agents-status'), 'ArrowDown', true)).toMatchObject({ h: 3 });
  });
});

describe('DashboardStudio', () => {
  it('offers only widgets of screens the organization has, and saves what was added', async () => {
    api.createDashboard.mockResolvedValue({ id: 'dash-1', version: 1, status: 'draft' });
    render(<DashboardStudio dashboardId={null} onClose={vi.fn()} />);
    await screen.findByText('Agents online');
    expect(screen.queryByText('Pending OS updates')).toBeNull();
    expect(screen.getByText(/2 more widgets come with screens/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ops wall' } });
    fireEvent.click(screen.getByText('Agents online'));
    expect(await screen.findByRole('group', { name: 'Agents online' })).toBeTruthy();

    // No audience yet: Publish stays off.
    expect(screen.getByRole('button', { name: /Publish/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(api.createDashboard).toHaveBeenCalled());
    const draft = api.createDashboard.mock.calls[0][0];
    expect(draft.name).toBe('Ops wall');
    expect(draft.widgets).toHaveLength(1);
    expect(draft.widgets[0]).toMatchObject({ widget: 'agents-status', x: 0, y: 0, w: 3, h: 2 });
  });

  it('lists tenant roles, not platform roles, as the audience', async () => {
    render(<DashboardStudio dashboardId={null} onClose={vi.fn()} />);
    await screen.findByText('Agents online');
    expect(screen.getByLabelText('analyst')).toBeTruthy();
    expect(screen.queryByLabelText('Super Admin')).toBeNull();
  });

  it('moves the focused widget with the arrow keys', async () => {
    api.getDashboard.mockResolvedValue({
      id: 'dash-1', name: 'Ops', description: '', status: 'draft', version: 3, widgetCount: 1, withheld: 0, hidden: [],
      mode: 'draft', sharing: { everyone: true, roles: [] },
      widgets: [{ i: 'a', widget: 'agents-status', x: 0, y: 0, w: 3, h: 2 }],
    });
    api.saveDashboard.mockResolvedValue({ id: 'dash-1', version: 4, status: 'draft' });
    render(<DashboardStudio dashboardId="dash-1" onClose={vi.fn()} />);
    const card = await screen.findByRole('group', { name: 'Agents online' });
    fireEvent.keyDown(card, { key: 'ArrowRight' });
    // Screen-reader users hear where the widget went.
    await waitFor(() => expect(document.querySelector('[aria-live]')?.textContent)
      .toBe('Agents online moved to column 2, row 1'));
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(api.saveDashboard).toHaveBeenCalled());
    const [, draft, version] = api.saveDashboard.mock.calls[0];
    expect(version).toBe(3);
    expect(draft.widgets[0]).toMatchObject({ x: 1 });
  });
});

describe('DashboardsHub', () => {
  it('tells a user when nothing has been shared with them', async () => {
    api.listDashboards.mockResolvedValue({ dashboards: [], canDesign: false });
    render(<DashboardsHub />);
    expect(await screen.findByText(/hasn't shared a dashboard with you/)).toBeTruthy();
    expect(screen.queryByText('New dashboard')).toBeNull();
  });

  it('opens a shared dashboard, says what the role cannot see, and hides a widget for this user', async () => {
    api.listDashboards.mockResolvedValue({ canDesign: false, dashboards: [
      { id: 'dash-1', name: 'SecOps', description: '', widgetCount: 2, status: 'published' }] });
    api.getDashboard.mockResolvedValue({
      id: 'dash-1', name: 'SecOps', description: 'Daily view', status: 'published', widgetCount: 2, withheld: 1,
      hidden: [], mode: 'published', widgets: [{ i: 'a', widget: 'agents-status', x: 0, y: 0, w: 3, h: 2 }],
    });
    api.setHiddenWidgets.mockResolvedValue({ hidden: ['a'] });
    render(<DashboardsHub />);
    fireEvent.click(await screen.findByRole('button', { name: /Open/ }));
    expect(await screen.findByText(/1 widget isn't shown because your role can't open its screen/)).toBeTruthy();
    fireEvent.click(await screen.findByRole('button', { name: 'Hide Agents online for me' }));
    expect(await screen.findByText('Every widget is hidden.')).toBeTruthy();
    expect(api.setHiddenWidgets).toHaveBeenCalledWith('dash-1', ['a']);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});
