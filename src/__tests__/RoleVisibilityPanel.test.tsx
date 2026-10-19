/**
 * Phase 77 / ACC-07: the "What it can see" panel renders the server's
 * GET /api/roles/{id}/visibility payload as delivered.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../services/roleApi', async () => {
  const actual = await vi.importActual<any>('../../services/roleApi');
  return { ...actual, fetchRoleVisibility: vi.fn(), fetchRoles: vi.fn() };
});

import { fetchRoleVisibility, fetchRoles } from '../../services/roleApi';
import { RoleVisibilityPanel } from '../../components/RoleVisibilityPanel';
import { SettingsRolesTab } from '../../components/SettingsRolesTab';

const mockFetch = fetchRoleVisibility as unknown as ReturnType<typeof vi.fn>;
const mockRoles = fetchRoles as unknown as ReturnType<typeof vi.fn>;

const TITLES = [
  'Dashboards & Insights', 'Observability', 'Infrastructure & Assets', 'Security (SecOps)',
  'DevSecOps & Engineering', 'Governance & Compliance', 'Automation & Intelligence', 'Management & Settings',
];

function payload(over: any = {}) {
  return {
    roleId: 'role-viewer', roleName: 'Viewer', builtIn: true,
    basis: { kind: 'tenant', tenantId: 'tenant-a', tenantName: 'Tenant A' },
    visibleCount: 44, totalCount: 188,
    groups: TITLES.map((title, i) => ({
      id: `g${i}`, title, total: 10, visibleCount: i === 0 ? 2 : 0,
      screens: i === 0 ? [
        { view: 'dashboard', label: 'Overview', access: 'view' },
        { view: 'cmdb', label: 'CMDB Records', access: 'manage' },
      ] : [],
      switchedOff: i === 0 ? [{ view: 'mlops', label: 'MLOps Studio' }] : [],
    })),
    ...over,
  };
}

const viewer = { id: 'role-viewer', name: 'Viewer', description: 'd', permissions: [], isEditable: false, builtIn: true } as any;
const custom = { id: 'role-c1', name: 'Auditors', description: 'c', permissions: [], isEditable: true, builtIn: false, tenantId: 'tenant-a' } as any;

beforeEach(() => { mockFetch.mockReset(); mockRoles.mockReset(); mockRoles.mockRejectedValue(new Error('no list')); });

describe('RoleVisibilityPanel', () => {
  it('shows aria-busy and 3 group skeleton bars while loading', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" panelId="p1" />);
    const region = screen.getByRole('region', { name: 'What Viewer can see' });
    expect(region.getAttribute('aria-busy')).toBe('true');
    expect(region.querySelectorAll('[data-skeleton="group"]').length).toBe(3);
    expect(region.querySelector('[data-skeleton="header"]')).not.toBeNull();
  });

  it('renders summary, basis, legend and 8 collapsed groups from the payload', async () => {
    mockFetch.mockResolvedValue(payload());
    render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" panelId="p1" />);
    expect(await screen.findByText('Viewer can see 44 of 188 screens')).toBeTruthy();
    expect(screen.getByText("Based on this role's permissions, narrowed by the screens switched on for Tenant A.")).toBeTruthy();
    expect(screen.getByText('View: can open the screen')).toBeTruthy();
    expect(screen.getByText('Manage: can also change data')).toBeTruthy();
    expect(screen.getByText('Switched off: granted, but off for this tenant')).toBeTruthy();
    const headers = screen.getAllByRole('button').filter(b => b.hasAttribute('aria-expanded'));
    expect(headers.length).toBe(8);
    expect(headers.every(h => h.getAttribute('aria-expanded') === 'false')).toBe(true);
    expect(headers.map(h => h.textContent)).toEqual(expect.arrayContaining([expect.stringContaining('2 of 10')]));
    expect(screen.getByText('+1 switched off')).toBeTruthy();
    expect(screen.getAllByText(/0 of 10/).length).toBe(7);
    // payload order, no client sorting
    expect(headers.map(h => TITLES.findIndex(t => h.textContent!.includes(t)))).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
  });

  it('expands a group into View and Manage screens and a separate switched-off sub-list', async () => {
    mockFetch.mockResolvedValue(payload());
    render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" panelId="p1" />);
    await screen.findByText('Viewer can see 44 of 188 screens');
    const first = screen.getAllByRole('button').find(b => b.textContent!.includes('Dashboards & Insights'))!;
    fireEvent.click(first);
    expect(first.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Overview')).toBeTruthy();
    expect(screen.getByText('CMDB Records')).toBeTruthy();
    expect(screen.getByText('Switched off for this tenant')).toBeTruthy();
    expect(screen.getByText('MLOps Studio')).toBeTruthy();
    // each screen appears once only (never in both lists)
    expect(screen.getAllByText('MLOps Studio').length).toBe(1);
    expect(screen.getAllByText('Overview').length).toBe(1);
    const cells = Array.from(document.querySelectorAll('[data-marker]')).map(m => m.getAttribute('data-marker'));
    expect(cells).toEqual(expect.arrayContaining(['view', 'manage', 'switched-off']));
  });

  it('Expand all opens every group and Collapse all closes them', async () => {
    mockFetch.mockResolvedValue(payload());
    render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" panelId="p1" />);
    await screen.findByText('Viewer can see 44 of 188 screens');
    const headers = () => screen.getAllByRole('button').filter(b => b.hasAttribute('aria-expanded'));
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    expect(headers().every(h => h.getAttribute('aria-expanded') === 'true')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }));
    expect(headers().every(h => h.getAttribute('aria-expanded') === 'false')).toBe(true);
  });

  it('platform_role basis reads as a platform role and has no switched-off sub-list', async () => {
    mockFetch.mockResolvedValue(payload({ basis: { kind: 'platform_role', tenantId: null, tenantName: null } }));
    render(<RoleVisibilityPanel role={viewer} panelId="p1" />);
    expect(await screen.findByText('Platform role. Tenant screen switches do not narrow it.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    expect(screen.queryByText('Switched off for this tenant')).toBeNull();
  });

  it('no_tenant basis reads as no tenant selected', async () => {
    mockFetch.mockResolvedValue(payload({ basis: { kind: 'no_tenant', tenantId: null, tenantName: null } }));
    render(<RoleVisibilityPanel role={viewer} tenantId={null} panelId="p1" />);
    expect(await screen.findByText('No tenant selected. Tenant screen switches do not narrow it.')).toBeTruthy();
  });

  it('shows the empty message for a role that sees nothing, with the edit hint for custom roles only', async () => {
    mockFetch.mockResolvedValue(payload({ roleId: 'role-c1', roleName: 'Auditors', builtIn: false, visibleCount: 0, groups: payload().groups.map((g: any) => ({ ...g, screens: [], switchedOff: [], visibleCount: 0 })) }));
    const { unmount } = render(<RoleVisibilityPanel role={custom} tenantId="tenant-a" panelId="p1" />);
    expect(await screen.findByText("This role can't see any screens yet.")).toBeTruthy();
    expect(screen.getByText('Edit the role to grant permissions.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Expand all' })).toBeNull();
    unmount();
    mockFetch.mockResolvedValue(payload({ visibleCount: 0, groups: payload().groups.map((g: any) => ({ ...g, screens: [], switchedOff: [], visibleCount: 0 })) }));
    render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" panelId="p1" />);
    expect(await screen.findByText("This role can't see any screens yet.")).toBeTruthy();
    expect(screen.queryByText('Edit the role to grant permissions.')).toBeNull();
  });

  it('shows a role=alert error and Try again refetches once', async () => {
    mockFetch.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(payload());
    render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" panelId="p1" />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't load what this role can see.");
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Viewer can see 44 of 188 screens')).toBeTruthy();
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('refetches when refreshKey changes but not on a plain re-render', async () => {
    mockFetch.mockResolvedValue(payload());
    const { rerender } = render(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" refreshKey={0} panelId="p1" />);
    await screen.findByText('Viewer can see 44 of 188 screens');
    rerender(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" refreshKey={0} panelId="p1" />);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    rerender(<RoleVisibilityPanel role={viewer} tenantId="tenant-a" refreshKey={1} panelId="p1" />);
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
  });
});

describe('SettingsRolesTab What it can see toggle', () => {
  it('opens one panel at a time with aria-expanded and aria-controls', async () => {
    mockFetch.mockResolvedValue(payload());
    render(<SettingsRolesTab roles={[viewer, custom]} tenantId="tenant-a" canManageRBAC onEdit={() => {}} onDelete={() => {}} onNew={() => {}} />);
    const b1 = screen.getByRole('button', { name: 'What Viewer can see' });
    const b2 = screen.getByRole('button', { name: 'What Auditors can see' });
    expect(b1.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(b1);
    expect(b1.getAttribute('aria-expanded')).toBe('true');
    const id = b1.getAttribute('aria-controls')!;
    expect(document.getElementById(id)).not.toBeNull();
    fireEvent.click(b2);
    expect(b1.getAttribute('aria-expanded')).toBe('false');
    expect(b2.getAttribute('aria-expanded')).toBe('true');
    expect(document.getElementById(id)).toBeNull();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
  });
});
