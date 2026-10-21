/**
 * Compliance screen:
 *  - Generate report: the endpoints answer { success, report: { filename } }; the screen read a top-level
 *    filename and reported every generated report as an "unexpected response".
 *  - A control that was added or imported shows up without a page reload.
 *  - Add / import / AI audit failures carry the server's reason.
 *  - A failed refresh keeps the frameworks on screen (the fetch answers [] on failure).
 *  - Tiles total every framework's controls; controls filter by status; a framework's docs link is not
 *    nested inside its row button; form fields are labelled.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { ComplianceDashboard } from '../../components/ComplianceDashboard';
import { UserContext } from '../../contexts/UserContext';
import { showToast } from '../../utils/toast';
import type { ComplianceFramework } from '../../types';

const json = (body: unknown, status = 200) =>
  ({ ok: status >= 200 && status < 300, status, headers: new Headers(), json: async () => body }) as Response;

const control = { id: 'CC1.1', name: 'Integrity and ethics', description: 'Tone at the top', category: 'Control Environment', status: 'Implemented', lastReviewed: '2026-10-01', evidence: [] };
const soc2 = { id: 'soc2', name: 'SOC 2 (Type II)', shortName: 'SOC 2', description: 'Trust services criteria', status: 'Pending', progress: 40, controls: [control] } as unknown as ComplianceFramework;

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  vi.mocked(showToast).mockReset();
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

/** Answers by method + path; anything else gets an empty list. */
function routes(table: Record<string, () => Response>) {
  fetchMock.mockImplementation(async (url: string, opts: RequestInit = {}) => {
    const key = `${opts.method || 'GET'} ${new URL(url, 'http://x').pathname}`;
    return table[key] ? table[key]() : json([]);
  });
}

function renderScreen() {
  const user = { id: 'u', name: 'Ava', email: 'ava@x.test', role: 'Tenant Admin', tenantId: 't' } as any;
  return render(
    <UserContext.Provider value={{ currentUser: user, hasPermission: () => true } as any}>
      <ComplianceDashboard complianceFrameworks={[soc2]} assets={[]} assetComplianceData={[]} />
    </UserContext.Provider>,
  );
}

const toasts = () => vi.mocked(showToast).mock.calls.map(([msg, type]) => `${type}: ${msg}`);

describe('Compliance screen', () => {
  it('a generated report is reported as generated', async () => {
    routes({ 'POST /api/compliance/reports/generate': () => json({ success: true, report: { filename: 'soc2_20261021.csv' } }) });
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Generate report/i }));
    await waitFor(() => expect(toasts()).toContain('success: CSV report generated successfully!'));
    expect(toasts().some(t => t.startsWith('error'))).toBe(false);
  });

  it('an added control shows without a reload', async () => {
    const added = { id: 'CC9.9', name: 'Vendor offboarding', description: '', category: 'General', status: 'Not Implemented', lastReviewed: '2026-10-21', evidence: [] };
    routes({
      'POST /api/compliance/soc2/controls': () => json(added),
      'GET /api/compliance': () => json([{ ...soc2, controls: [control, added] }]),
    });
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Add control/i }));
    fireEvent.change(screen.getByPlaceholderText('e.g., CC1.1'), { target: { value: 'CC9.9' } });
    fireEvent.change(screen.getByPlaceholderText('Control Name'), { target: { value: 'Vendor offboarding' } });
    fireEvent.submit(document.getElementById('add-control-form')!);
    expect(await screen.findByText('Vendor offboarding')).toBeTruthy();
  });

  it("a refused control says why", async () => {
    routes({ 'POST /api/compliance/soc2/controls': () => json({ detail: 'Not authorized to add controls to this framework via ReBAC' }, 403) });
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Add control/i }));
    fireEvent.change(screen.getByPlaceholderText('e.g., CC1.1'), { target: { value: 'CC9.9' } });
    fireEvent.change(screen.getByPlaceholderText('Control Name'), { target: { value: 'Vendor offboarding' } });
    fireEvent.submit(document.getElementById('add-control-form')!);
    await waitFor(() => expect(toasts()).toContain('error: Failed to add control: Not authorized to add controls to this framework via ReBAC'));
  });

  it('a failed import says why', async () => {
    routes({ 'POST /api/compliance/soc2/import': () => json({ detail: 'openpyxl is required for Excel import. Install it or upload a CSV.' }, 422) });
    const { container } = renderScreen();
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'controls.xlsx')] } });
    await waitFor(() => expect(toasts()).toContain('error: Import failed: openpyxl is required for Excel import. Install it or upload a CSV.'));
  });

  it('totals the controls of every framework', () => {
    const risky = { ...control, id: 'CC2.1', name: 'Board oversight', status: 'At Risk' };
    const gdpr = { id: 'gdpr', name: 'General Data Protection Regulation', shortName: 'GDPR', description: '', status: 'At Risk', progress: 10, controls: [risky] } as unknown as ComplianceFramework;
    render(
      <UserContext.Provider value={{ currentUser: { id: 'u' }, hasPermission: () => true } as any}>
        <ComplianceDashboard complianceFrameworks={[soc2, gdpr]} assets={[]} assetComplianceData={[]} />
      </UserContext.Provider>,
    );
    expect(within(screen.getByRole('group', { name: 'Frameworks' })).getByText('2')).toBeTruthy();
    expect(within(screen.getByRole('group', { name: 'Controls implemented' })).getByText('of 2')).toBeTruthy();
    expect(within(screen.getByRole('group', { name: 'Controls at risk' })).getByText('1')).toBeTruthy();
  });

  it('filters controls by status, with a count on each status', () => {
    const risky = { ...control, id: 'CC2.1', name: 'Board oversight', status: 'At Risk' };
    const fw = { ...soc2, controls: [control, risky] } as unknown as ComplianceFramework;
    render(
      <UserContext.Provider value={{ currentUser: { id: 'u' }, hasPermission: () => true } as any}>
        <ComplianceDashboard complianceFrameworks={[fw]} assets={[]} assetComplianceData={[]} />
      </UserContext.Provider>,
    );
    const filter = screen.getByRole('group', { name: 'Filter by status' });
    fireEvent.click(within(filter).getByRole('button', { name: /At Risk/ }));
    expect(within(filter).getByRole('button', { name: /At Risk/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Board oversight')).toBeTruthy();
    expect(screen.queryByText('Integrity and ethics')).toBeNull();
  });

  it('a framework row and its docs link are separate controls', () => {
    renderScreen();
    const docs = screen.getByRole('link', { name: 'SOC 2 official documentation' });
    expect(docs.closest('button')).toBeNull();
    expect(screen.getByRole('button', { name: /SOC 2 \(Type II\)/ })).toHaveAttribute('aria-current', 'true');
  });

  it('form fields are labelled', () => {
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Add control/i }));
    expect(screen.getByLabelText('Control ID')).toBeTruthy();
    fireEvent.click(screen.getByTitle('Add a compliance framework'));
    fireEvent.click(screen.getByRole('button', { name: 'Custom framework' }));
    expect(screen.getByLabelText('Framework name *')).toBeTruthy();
  });

  it('a failed refresh keeps the frameworks on screen', async () => {
    routes({
      'POST /api/compliance/soc2/controls': () => json({ id: 'CC9.9' }),
      'GET /api/compliance': () => json({ detail: 'boom' }, 500),
    });
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Add control/i }));
    fireEvent.change(screen.getByPlaceholderText('e.g., CC1.1'), { target: { value: 'CC9.9' } });
    fireEvent.change(screen.getByPlaceholderText('Control Name'), { target: { value: 'Vendor offboarding' } });
    fireEvent.submit(document.getElementById('add-control-form')!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, o]) => String(u).endsWith('/api/compliance') && !(o as RequestInit)?.method)).toBe(true));
    expect(screen.getByText('Integrity and ethics')).toBeTruthy();
    expect(screen.getAllByText('SOC 2').length).toBeGreaterThan(0);
  });
});
