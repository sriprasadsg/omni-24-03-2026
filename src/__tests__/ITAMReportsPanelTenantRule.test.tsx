/**
 * Phase 78 plan 14: custom reports follow the one-tenant rule (D-13 and D-14 amended 2026-11-17,
 * gap G-78-WR02, threats T-78-36 and T-78-37):
 *  - the five custom report API functions send X-Tenant-ID when given a tenant and none when not;
 *  - the saved-reports list reloads on a tenant switch, never shows the previous tenant's
 *    definitions, and drops a late list response for the previous tenant;
 *  - a save or delete started for one tenant does nothing when it completes in another;
 *  - a platform user with no tenant sees the custom section explained and disabled and sends no
 *    custom request (D-14 amended).
 */
import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';

const fetchItamPrebuiltReports = vi.fn();
const runItamPrebuiltReport = vi.fn();
const generateItamReport = vi.fn();
const downloadItamReport = vi.fn();
const fetchItamReportFields = vi.fn();
const listItamCustomReports = vi.fn();
const saveItamCustomReport = vi.fn();
const deleteItamCustomReport = vi.fn();
const previewItamCustomReport = vi.fn();
const runItamCustomReport = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchItamPrebuiltReports: (...args: unknown[]) => fetchItamPrebuiltReports(...args),
  runItamPrebuiltReport: (...args: unknown[]) => runItamPrebuiltReport(...args),
  generateItamReport: (...args: unknown[]) => generateItamReport(...args),
  downloadItamReport: (...args: unknown[]) => downloadItamReport(...args),
  fetchItamReportFields: (...args: unknown[]) => fetchItamReportFields(...args),
  listItamCustomReports: (...args: unknown[]) => listItamCustomReports(...args),
  saveItamCustomReport: (...args: unknown[]) => saveItamCustomReport(...args),
  deleteItamCustomReport: (...args: unknown[]) => deleteItamCustomReport(...args),
  previewItamCustomReport: (...args: unknown[]) => previewItamCustomReport(...args),
  runItamCustomReport: (...args: unknown[]) => runItamCustomReport(...args),
}));

const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...args: unknown[]) => showToast(...args) }));

import { ReportsPanel } from '../../components/itam/ReportsPanel';
import { ITAM_KPI_COPY } from '../../components/itam/ItamKpiPanel';

const PREBUILT_METAS = [{ key: 'asset_value', title: 'Asset Value', description: 'Book value per asset' }];
const FIELD_CATALOG = [{ key: 'asset.assetTag', label: 'Asset Tag', entity: 'asset', type: 'text' }];

function savedReport(id: string, name: string) {
  return { id, name, columns: ['asset.assetTag'], filters: [], createdAt: '2026-11-17T00:00:00.000Z', createdBy: 'admin' };
}

function resultFor(title: string, value: string) {
  return {
    key: 'k', title, columns: ['Asset Tag'], rows: [{ 'Asset Tag': value }],
    rowCount: 1, page: 1, pageSize: 50, totalPages: 1, truncated: false,
  };
}

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

// Runs fn, then lets React flush whatever a late response writes before absence is asserted.
async function settle(fn: () => void) {
  await act(async () => {
    fn();
    await new Promise((r) => setTimeout(r, 20));
  });
}

type PanelProps = ComponentProps<typeof ReportsPanel>;

async function renderPanel(props: PanelProps = {}) {
  const view = render(<ReportsPanel {...props} />);
  await screen.findByText('Pre-built Reports');
  return view;
}

function resetMocks() {
  [fetchItamPrebuiltReports, runItamPrebuiltReport, generateItamReport, downloadItamReport,
    fetchItamReportFields, listItamCustomReports, saveItamCustomReport, deleteItamCustomReport,
    previewItamCustomReport, runItamCustomReport, showToast].forEach((fn) => fn.mockReset());
  fetchItamPrebuiltReports.mockResolvedValue(PREBUILT_METAS);
  listItamCustomReports.mockResolvedValue([]);
  fetchItamReportFields.mockResolvedValue(FIELD_CATALOG);
}

describe('custom report transport carries the tenant', () => {
  const DEFINITION = { name: 'Mine', columns: ['asset.assetTag'], filters: [] };
  type Api = typeof import('../../services/apiService');
  const calls: Record<string, (api: Api, tenant?: string) => Promise<unknown>> = {
    list: (api, t) => api.listItamCustomReports(t),
    save: (api, t) => api.saveItamCustomReport(DEFINITION, t),
    delete: (api, t) => api.deleteItamCustomReport('c-1', t),
    preview: (api, t) => api.previewItamCustomReport(DEFINITION, 1, 50, t),
    run: (api, t) => api.runItamCustomReport('c-1', 1, 50, t),
  };

  async function sentHeaders(name: string, tenant?: string) {
    const api = await vi.importActual<Api>('../../services/apiService');
    const fetchStub = vi.fn(() => Promise.resolve(new Response('[]', { status: 200 })));
    vi.stubGlobal('fetch', fetchStub);
    await calls[name](api, tenant);
    expect(fetchStub).toHaveBeenCalledTimes(1);
    const init = (fetchStub.mock.calls[0] as unknown as [string, RequestInit])[1];
    return init.headers as Record<string, string>;
  }

  afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

  it.each(Object.keys(calls))('%s sends X-Tenant-ID with the given tenant', async (name) => {
    expect((await sentHeaders(name, 't-1'))['X-Tenant-ID']).toBe('t-1');
  });

  it.each(Object.keys(calls))('%s sends no X-Tenant-ID without a tenant', async (name) => {
    expect(await sentHeaders(name)).not.toHaveProperty('X-Tenant-ID');
  });
});

describe('ReportsPanel custom section under the tenant rule', () => {
  beforeEach(resetMocks);

  async function openBuilderAndPickColumn() {
    fireEvent.click(screen.getByRole('button', { name: /Create Custom Report/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Asset Tag' }));
  }

  async function saveFromBuilder(name: string) {
    await openBuilderAndPickColumn();
    fireEvent.change(screen.getByLabelText('Report Name'), { target: { value: name } });
    fireEvent.click(screen.getByRole('button', { name: /Save Report/ }));
  }

  it('loads the saved list for the selected tenant', async () => {
    await renderPanel({ tenantId: 't-1' });
    await waitFor(() => expect(listItamCustomReports).toHaveBeenCalledWith('t-1'));
  });

  it('saves a builder report for the selected tenant', async () => {
    saveItamCustomReport.mockResolvedValue(savedReport('c-9', 'Mine'));
    runItamCustomReport.mockResolvedValue(resultFor('Mine', 'IT-1'));
    await renderPanel({ tenantId: 't-1' });
    await saveFromBuilder('Mine');
    await waitFor(() => expect(saveItamCustomReport)
      .toHaveBeenCalledWith(expect.objectContaining({ name: 'Mine' }), 't-1'));
  });

  it('previews a builder report for the selected tenant', async () => {
    previewItamCustomReport.mockResolvedValue(resultFor('Custom Report', 'IT-P'));
    await renderPanel({ tenantId: 't-1' });
    await openBuilderAndPickColumn();
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(previewItamCustomReport)
      .toHaveBeenCalledWith(expect.objectContaining({ columns: ['asset.assetTag'] }), 1, 50, 't-1'));
  });

  it("hides the previous tenant's saved list at once and shows the new tenant's when it loads", async () => {
    const second = deferred<ReturnType<typeof savedReport>[]>();
    listItamCustomReports
      .mockResolvedValueOnce([savedReport('a', 'A report')])
      .mockReturnValue(second.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });
    expect(await screen.findByText('A report')).toBeInTheDocument();

    rerender(<ReportsPanel tenantId="t-2" />);
    await waitFor(() => expect(screen.queryByText('A report')).not.toBeInTheDocument());
    await settle(() => second.resolve([savedReport('b', 'B report')]));
    expect(await screen.findByText('B report')).toBeInTheDocument();
  });

  it('drops a saved-list response for the previous tenant that resolves after the switch', async () => {
    const first = deferred<ReturnType<typeof savedReport>[]>();
    listItamCustomReports
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue([savedReport('b', 'B report')]);
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    rerender(<ReportsPanel tenantId="t-2" />);
    expect(await screen.findByText('B report')).toBeInTheDocument();
    await settle(() => first.resolve([savedReport('a', 'A report')]));

    expect(screen.queryByText('A report')).not.toBeInTheDocument();
    expect(screen.getByText('B report')).toBeInTheDocument();
  });

  it('a save that completes after a tenant switch neither reloads the list, runs the report nor toasts', async () => {
    const held = deferred();
    saveItamCustomReport.mockReturnValueOnce(held.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });
    await saveFromBuilder('Mine');
    await waitFor(() => expect(saveItamCustomReport).toHaveBeenCalledTimes(1));

    rerender(<ReportsPanel tenantId="t-2" />);
    await waitFor(() => expect(listItamCustomReports).toHaveBeenLastCalledWith('t-2'));
    const listCallsAfterSwitch = listItamCustomReports.mock.calls.length;
    await settle(() => held.resolve(savedReport('c-9', 'Mine')));

    expect(runItamCustomReport).not.toHaveBeenCalled();
    expect(listItamCustomReports).toHaveBeenCalledTimes(listCallsAfterSwitch);
    expect(showToast).not.toHaveBeenCalledWith('Report saved.', 'success');
  });

  it('a confirmed delete that completes after a tenant switch raises no toast', async () => {
    listItamCustomReports
      .mockResolvedValueOnce([savedReport('c-1', 'My report')])
      .mockResolvedValue([]);
    const held = deferred();
    deleteItamCustomReport.mockReturnValueOnce(held.promise);
    const { rerender } = await renderPanel({ tenantId: 't-1' });

    fireEvent.click(await screen.findByRole('button', { name: 'Delete My report' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteItamCustomReport).toHaveBeenCalledWith('c-1', 't-1'));

    rerender(<ReportsPanel tenantId="t-2" />);
    await waitFor(() => expect(listItamCustomReports).toHaveBeenLastCalledWith('t-2'));
    const listCallsAfterSwitch = listItamCustomReports.mock.calls.length;
    await settle(() => held.resolve(undefined));

    expect(showToast).not.toHaveBeenCalledWith('Report deleted.', 'success');
    expect(listItamCustomReports).toHaveBeenCalledTimes(listCallsAfterSwitch);
  });
});

describe('custom section with no tenant', () => {
  beforeEach(resetMocks);

  const NOTE = ITAM_KPI_COPY.customReportsSelectTenantNote;
  const createButton = () => screen.getByRole('button', { name: /Create Custom Report/ });

  it('sends no custom request, shows the described note and disables Create Custom Report', async () => {
    await renderPanel({ needsTenant: true });
    const note = await screen.findByText(NOTE);
    expect(note).toHaveAttribute('role', 'status');
    expect(screen.queryByText('No custom reports yet')).not.toBeInTheDocument();
    expect(createButton()).toBeDisabled();
    expect(createButton()).toHaveAttribute('aria-describedby', note.id);
    fireEvent.click(createButton());
    expect(screen.queryByLabelText('Report Name')).not.toBeInTheDocument();
    expect(listItamCustomReports).not.toHaveBeenCalled();
  });

  it('switching to no tenant hides the list and the open builder and sends no new request', async () => {
    listItamCustomReports.mockResolvedValue([savedReport('a', 'A report')]);
    const { rerender } = await renderPanel({ tenantId: 't-1' });
    expect(await screen.findByText('A report')).toBeInTheDocument();
    fireEvent.click(createButton());
    expect(await screen.findByLabelText('Report Name')).toBeInTheDocument();
    const listCalls = listItamCustomReports.mock.calls.length;

    rerender(<ReportsPanel needsTenant />);
    expect(await screen.findByText(NOTE)).toBeInTheDocument();
    expect(screen.queryByText('A report')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Report Name')).not.toBeInTheDocument();
    expect(listItamCustomReports).toHaveBeenCalledTimes(listCalls);
  });

  it('choosing a tenant again loads its list, enables Create Custom Report and removes the note', async () => {
    const { rerender } = await renderPanel({ needsTenant: true });
    expect(await screen.findByText(NOTE)).toBeInTheDocument();

    rerender(<ReportsPanel tenantId="t-3" />);
    await waitFor(() => expect(listItamCustomReports).toHaveBeenCalledWith('t-3'));
    expect(createButton()).toBeEnabled();
    expect(screen.queryByText(NOTE)).not.toBeInTheDocument();
  });

  it('a tenant user sees no custom note and an enabled Create Custom Report', async () => {
    await renderPanel();
    await screen.findByText('No custom reports yet');
    expect(screen.queryByText(NOTE)).not.toBeInTheDocument();
    expect(createButton()).toBeEnabled();
    expect(listItamCustomReports).toHaveBeenCalledWith(undefined);
  });
});

describe('a Select a tenant rejection on the Reports tab (Phase 78 plan 15)', () => {
  beforeEach(resetMocks);

  const REJECTION = 'Select a tenant: ITAM figures cover one organization at a time.';
  const PREBUILT_NOTE = ITAM_KPI_COPY.reportsSelectTenantNote;
  const CUSTOM_NOTE = ITAM_KPI_COPY.customReportsSelectTenantNote;
  const runButton = () => screen.getByRole('button', { name: 'Run Report' });
  const createButton = () => screen.getByRole('button', { name: /Create Custom Report/ });

  it('a saved-list rejection puts the tab into the no-tenant state without a toast', async () => {
    listItamCustomReports.mockRejectedValue(new Error(REJECTION));
    await renderPanel({ tenantId: 't-1' });
    expect(await screen.findByText(PREBUILT_NOTE)).toBeInTheDocument();
    expect(runButton()).toBeDisabled();
    expect(screen.getByText(CUSTOM_NOTE)).toBeInTheDocument();
    expect(createButton()).toBeDisabled();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('a pre-built run rejection puts the tab into the no-tenant state without a toast', async () => {
    runItamPrebuiltReport.mockRejectedValue(new Error(REJECTION));
    await renderPanel({ tenantId: 't-1' });
    await waitFor(() => expect(listItamCustomReports).toHaveBeenCalled());
    fireEvent.click(runButton());
    expect(await screen.findByText(PREBUILT_NOTE)).toBeInTheDocument();
    expect(runButton()).toBeDisabled();
    expect(screen.queryByRole('heading', { name: 'Asset Value', level: 3 })).not.toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('an export rejection puts the tab into the no-tenant state without a toast', async () => {
    runItamPrebuiltReport.mockResolvedValue(resultFor('Asset Value', 'TAG-1'));
    generateItamReport.mockRejectedValue(new Error(REJECTION));
    await renderPanel({ tenantId: 't-1' });
    fireEvent.click(runButton());
    fireEvent.click(await screen.findByRole('button', { name: /Export CSV/ }));
    expect(await screen.findByText(PREBUILT_NOTE)).toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('any other rejection still raises its toast and leaves Run Report enabled', async () => {
    runItamPrebuiltReport.mockRejectedValue(new Error('boom'));
    await renderPanel({ tenantId: 't-1' });
    fireEvent.click(runButton());
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('boom', 'error'));
    expect(runButton()).toBeEnabled();
    expect(screen.queryByText(PREBUILT_NOTE)).not.toBeInTheDocument();
  });

  it('a tenant change clears the rejected state so the next tenant is enabled', async () => {
    listItamCustomReports.mockRejectedValueOnce(new Error(REJECTION));
    const { rerender } = await renderPanel({ tenantId: 't-1' });
    expect(await screen.findByText(PREBUILT_NOTE)).toBeInTheDocument();

    rerender(<ReportsPanel tenantId="t-2" />);
    await waitFor(() => expect(listItamCustomReports).toHaveBeenCalledWith('t-2'));
    await waitFor(() => expect(runButton()).toBeEnabled());
    expect(screen.queryByText(PREBUILT_NOTE)).not.toBeInTheDocument();
    expect(showToast).not.toHaveBeenCalled();
  });
});
