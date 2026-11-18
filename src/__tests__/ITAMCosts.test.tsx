/**
 * Phases 79-80 (COST-04, COST-08): the ITAM Costs tab and license cost entry.
 *  1. The tab shows the organization totals, "Not tracked" (never $0) for what cannot be computed, a coverage
 *     banner saying how disposed assets and cost-less licenses are treated, and per-asset rows.
 *  2. Export goes through the report registry's endpoint_costs report for the tenant it started in.
 *  3. A Platform Owner without a tenant gets the select-a-tenant state and no request; a switch drops the old answer.
 *  4. The license form records a cost in whole cents with its basis, refuses a bad amount, and removes a cost.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

const authFetch = vi.fn();
const generateItamReport = vi.fn();
const downloadItamReport = vi.fn();
const fetchLicenses = vi.fn();
const createLicense = vi.fn();
const updateLicense = vi.fn();
vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...a: unknown[]) => authFetch(...a),
  generateItamReport: (...a: unknown[]) => generateItamReport(...a),
  downloadItamReport: (...a: unknown[]) => downloadItamReport(...a),
  fetchItamKpis: vi.fn(),
  fetchLicenses: (...a: unknown[]) => fetchLicenses(...a),
  createLicense: (...a: unknown[]) => createLicense(...a),
  updateLicense: (...a: unknown[]) => updateLicense(...a),
  assignLicenseSeat: vi.fn(), reclaimLicenseSeat: vi.fn(), fetchLicenseAssignments: vi.fn(),
  fetchConsumables: vi.fn(async () => []), createConsumable: vi.fn(), checkoutConsumable: vi.fn(), checkinConsumable: vi.fn(),
  fetchComponents: vi.fn(async () => []), createComponent: vi.fn(), attachComponent: vi.fn(), detachComponent: vi.fn(),
}));
const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...a: unknown[]) => showToast(...a) }));

import { CostsPanel } from '../../components/itam/CostsPanel';
import { LicensesPanel } from '../../components/itam/LicensesPanel';
import { centsToAmount, formatMaybeCents, parseAmountToCents } from '../../components/itam/money';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const bucket = (over: Record<string, unknown> = {}) => ({ spendCents: null, allocatedCents: null, unattributedCents: null, idleCents: null,
  allocatedToExcludedCents: null, licenses: 0, hasData: false, ...over });
const summary = (tenant: string, purchase: number) => ({
  tenantId: tenant, computedAt: '2026-11-18T12:00:00Z', includeDisposed: false,
  purchaseTotal: { cents: purchase, hasData: true }, bookValueTotal: { cents: null, hasData: false },
  coverage: { total: 2, priced: 1, valued: 0, excludedByLifecycle: 3, reasons: {} },
  licenses: { coverage: { total: 2, priced: 1, notTracked: 1 },
    recurringAnnual: bucket({ spendCents: 144000, allocatedCents: 72000, unattributedCents: 0, idleCents: 36000, allocatedToExcludedCents: 36000, licenses: 1, hasData: true }),
    oneTime: bucket() },
});
const rows = {
  items: [
    { assetId: 'a1', name: 'Laptop', assetTag: 'T1', lifecycleStatus: 'deployed', purchaseCostCents: 150000, bookValueCents: null,
      reason: 'no_depreciation_policy_assigned', agent: { hostname: 'LAPTOP-1' },
      license: { recurringAnnualCents: 36000, oneTimeCents: null, pricedSeats: 1, untrackedSeats: 0 } },
    { assetId: 'a2', name: 'Desk PC', assetTag: 'T2', lifecycleStatus: 'deployed', purchaseCostCents: null, bookValueCents: null,
      reason: 'no_purchase_record', agent: null, license: { recurringAnnualCents: null, oneTimeCents: null, pricedSeats: 0, untrackedSeats: 1 } },
  ],
  total: 2, page: 1, pageSize: 50, totalPages: 1, hasNext: false,
};

beforeEach(() => {
  [authFetch, generateItamReport, downloadItamReport, fetchLicenses, createLicense, updateLicense, showToast].forEach(m => m.mockReset());
  authFetch.mockImplementation(async (url: string, init?: { tenantId?: string }) =>
    ok(String(url).includes('/summary') ? summary(init?.tenantId || 'own', 150000) : rows));
});

describe('Costs tab', () => {
  it('shows totals, not-tracked figures, the coverage banner and per-asset rows', async () => {
    render(<CostsPanel tenantId="tenant-a" />);
    expect(await screen.findByText('$1,500.00', { selector: 'p' })).toBeTruthy();
    expect(screen.getByText('$1,440.00')).toBeTruthy();
    expect(screen.getAllByText('Not tracked').length).toBeGreaterThanOrEqual(2);
    const banner = screen.getByRole('note', { name: 'Coverage' });
    expect(banner.textContent).toContain('3 disposed or retired assets are left out');
    expect(banner.textContent).toContain('1 license has no cost');
    expect(banner.textContent).toContain('$360.00 of license cost sits on seats of disposed or retired assets');
    const table = within(screen.getByRole('region', { name: 'Costs by asset' }));
    expect(table.getByText('LAPTOP-1')).toBeTruthy();
    expect(table.getByText('$360.00')).toBeTruthy();
    expect(table.getByText('No depreciation policy on its model')).toBeTruthy();
    expect(authFetch.mock.calls.every(([, init]) => init?.tenantId === 'tenant-a')).toBe(true);
  });

  it('exports the endpoint_costs report for the tenant it started in', async () => {
    generateItamReport.mockResolvedValue({ filename: 'itam_report_endpoint_costs.csv', rowCount: 2, truncated: false });
    render(<CostsPanel tenantId="tenant-a" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(downloadItamReport).toHaveBeenCalledWith('itam_report_endpoint_costs.csv'));
    expect(generateItamReport).toHaveBeenCalledWith('prebuilt', 'endpoint_costs', 'csv', 'tenant-a');
    expect(showToast).toHaveBeenCalledWith('Exported 2 assets', 'success');
  });

  it('asks a Platform Owner for a tenant and drops an answer for a tenant no longer shown', async () => {
    const { rerender } = render(<CostsPanel needsTenant tenantId={null} />);
    expect(screen.getByRole('status').textContent).toContain('Select a tenant');
    expect(authFetch).not.toHaveBeenCalled();
    let release: (v: unknown) => void = () => {};
    authFetch.mockImplementation(async (url: string, init?: { tenantId?: string }) => (init?.tenantId === 'slow'
      ? new Promise(r => { release = r; }) : ok(String(url).includes('/summary') ? summary('fast', 99900) : rows)));
    rerender(<CostsPanel tenantId="slow" />);
    rerender(<CostsPanel tenantId="fast" />);
    expect(await screen.findByText('$999.00', { selector: 'p' })).toBeTruthy();
    release(ok(summary('slow', 123400)));
    await new Promise(r => setTimeout(r, 0));
    expect(screen.queryByText('$1,234.00')).toBeNull();
  });
});

describe('License cost entry', () => {
  it('creates a license with whole cents and a basis, and refuses a bad amount', async () => {
    fetchLicenses.mockResolvedValue([]);
    createLicense.mockResolvedValue({});
    render(<LicensesPanel />);
    fireEvent.click(await screen.findByRole('button', { name: 'Add License' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Office' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Cost' }), { target: { value: '12.345' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(createLicense).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('Enter the cost as an amount, e.g. 1299.99.', 'error');
    fireEvent.change(screen.getByRole('textbox', { name: 'Cost' }), { target: { value: '$1,299.99' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Billing Basis' }), { target: { value: 'monthly' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createLicense).toHaveBeenCalledTimes(1));
    expect(createLicense.mock.calls[0][0]).toMatchObject({ name: 'Office', costCents: 129999, costPeriod: 'monthly' });
  });

  it('shows the cost or Not tracked, changes it and removes it', async () => {
    fetchLicenses.mockResolvedValue([
      { id: 'l1', tenantId: 't', name: 'Office', seatCount: 5, seatsAvailable: 4, costCents: 129900, costPeriod: 'annual' },
      { id: 'l2', tenantId: 't', name: 'Free tool', seatCount: 9, seatsAvailable: 9 },
    ]);
    updateLicense.mockResolvedValue({});
    render(<LicensesPanel />);
    expect(await screen.findByText('$1,299.00')).toBeTruthy();
    expect(screen.getByText('per year')).toBeTruthy();
    expect(screen.getByText('Not tracked')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Set cost of Office' }));
    expect((screen.getByRole('textbox', { name: 'Cost' }) as HTMLInputElement).value).toBe('1299.00');
    fireEvent.change(screen.getByRole('textbox', { name: 'Cost' }), { target: { value: '1500' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Cost' }));
    await waitFor(() => expect(updateLicense).toHaveBeenCalledWith('l1', { costCents: 150000, costPeriod: 'annual' }));
    fireEvent.click(screen.getByRole('button', { name: 'Set cost of Office' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove cost' }));
    await waitFor(() => expect(updateLicense).toHaveBeenLastCalledWith('l1', { costCents: null }));
  });

  it('parses amounts to whole cents without float rounding', () => {
    expect([parseAmountToCents('0.1'), parseAmountToCents('1,299.99'), parseAmountToCents('$5'), parseAmountToCents(' 19.90 ')])
      .toEqual([10, 129999, 500, 1990]);
    expect([parseAmountToCents(''), parseAmountToCents('1.234'), parseAmountToCents('-5'), parseAmountToCents('abc')]).toEqual([null, null, null, null]);
    expect(centsToAmount(129905)).toBe('1299.05');
    expect(formatMaybeCents(null)).toBe('Not tracked');
    expect(formatMaybeCents(0)).toBe('$0.00');
  });
});
