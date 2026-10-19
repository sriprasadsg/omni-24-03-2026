/**
 * Assets inventory bulk actions: check rows, scan exactly those, export them as CSV (formula-safe),
 * and a filter that hides a checked row drops it from the selection.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  fetchAssetById: () => Promise.resolve(null),
  fetchAgents: () => Promise.resolve([]),
  linkAssetToAgent: vi.fn(),
  authFetch: vi.fn(),
}));
vi.mock('../../components/MetricsChartsTab', () => ({ MetricsChartsTab: () => null }));
vi.mock('../../components/RemoteTerminal', () => ({ RemoteTerminal: () => null }));
vi.mock('../../components/RemoteDesktop', () => ({ RemoteDesktop: () => null }));
vi.mock('../../components/FimAlertsPanel', () => ({ FimAlertsPanel: () => null }));

import { AssetManagementDashboard } from '../../components/AssetManagementDashboard';
import { csvCell, toCsv } from '../../utils/csvExport';

const asset = (id: string, hostname: string, osName: string) =>
  ({ id, hostname, osName, osVersion: '1', ipAddress: '10.0.0.1', lastScanned: new Date().toISOString(), vulnerabilities: [], tenantId: 't' }) as any;
const ASSETS = [asset('a1', 'WKS-1', 'Windows 11'), asset('a2', 'SRV-2', 'Ubuntu'), asset('a3', 'WKS-3', 'Windows 10')];

function renderAssets(onSchedule = vi.fn().mockResolvedValue(undefined)) {
  render(
    <AssetManagementDashboard
      assets={ASSETS} patches={[]} onRunVulnerabilityScan={vi.fn()} filters={[]} onClearFilters={vi.fn()}
      vulnerabilityScanJobs={[]} onScheduleVulnerabilityScan={onSchedule} onDeleteAsset={vi.fn()}
    />,
  );
  return onSchedule;
}

describe('csvExport', () => {
  it('quotes commas, quotes and newlines, and defuses formulas', () => {
    expect(csvCell('a,b')).toBe('"a,b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell('=HYPERLINK("http://x")')).toBe(`"'=HYPERLINK(""http://x"")"`);
    expect(csvCell('@SUM(A1)')).toBe("'@SUM(A1)");
    expect(csvCell(null)).toBe('');
    expect(toCsv(['h1', 'h2'], [[1, 'x']])).toBe('h1,h2\r\n1,x');
  });
});

describe('Assets bulk actions', () => {
  it('scans exactly the checked assets', () => {
    renderAssets();
    expect(screen.queryByRole('region', { name: 'Bulk actions' })).toBeNull();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select WKS-1' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select WKS-3' }));
    const bar = screen.getByRole('region', { name: 'Bulk actions' });
    expect(bar).toHaveTextContent('2 selected');
    fireEvent.click(within(bar).getByRole('button', { name: /Scan/ }));
    expect(screen.getByText(/initiate a vulnerability scan/).textContent).toContain('for 2 asset(s)');
  });

  it('selects all and clears all from the header checkbox', () => {
    renderAssets();
    const all = screen.getByRole('checkbox', { name: 'Select all assets in the list' });
    fireEvent.click(all);
    expect(screen.getByRole('region', { name: 'Bulk actions' })).toHaveTextContent('3 selected');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Clear selection' }));
    expect(screen.queryByRole('region', { name: 'Bulk actions' })).toBeNull();
  });

  it('drops a checked asset from the selection when a filter hides it', () => {
    renderAssets();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select WKS-1' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select SRV-2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Linux' }));
    expect(screen.getByRole('region', { name: 'Bulk actions' })).toHaveTextContent('1 selected');
  });
});
