/**
 * Phase 72 (plan 72-07) ItamKpiPanel — the Reports tab's four-tile KPI grid
 * (ITAM-REP-04, D-16/D-17/D-18):
 *  1. Four tiles render for a fully-populated payload.
 *  2. Loading… shows per-tile while the fetch is in flight.
 *  3. hasData=false (or a rejected fetch) degrades a tile to "No data yet"
 *     plus its entity/tab next-step copy — never a fabricated 0%/100%.
 *  4. A populated tile shows its computed value plus its recharts chart.
 *  5. Status-breakdown segments render in payload order, never re-sorted.
 *  6. Clicking a tile calls onDrillDown with that KPI's drilldownReportKey.
 *  7. Every tile is a real button element.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const fetchItamKpis = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchItamKpis: (...args: unknown[]) => fetchItamKpis(...args),
}));

import { ItamKpiPanel, ITAM_KPI_COPY } from '../../components/itam/ItamKpiPanel';

// recharts' ResponsiveContainer needs a real ResizeObserver plus a sized
// container to render its children under jsdom (jsdom's layout engine always
// reports 0x0, and ResponsiveContainer renders nothing until it measures a
// positive width/height). A stub ResizeObserver plus a fixed
// getBoundingClientRect lets the real Pie/Bar/Legend markup render so the
// segment-order test can assert on rendered text rather than SVG geometry.
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  global.ResizeObserver = StubResizeObserver;
  Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({
      width: 300, height: 300, top: 0, left: 0, bottom: 300, right: 300, x: 0, y: 0, toJSON: () => undefined,
    }),
  });
});

function emptyKpi(drilldownReportKey: string) {
  return { hasData: false, drilldownReportKey };
}

function fullKpis(overrides: Record<string, any> = {}) {
  return {
    assetValue: {
      hasData: true,
      totalBookValueCents: 500000,
      assetCount: 12,
      inScopeAssetCount: 11,
      valuedCount: 10,
      withoutPolicyCount: 2,
      statusBreakdown: [
        { status: 'in_stock', label: 'In_stock', count: 3 },
        { status: 'deployed', label: 'Deployed', count: 8 },
        { status: 'retired', label: 'Retired', count: 1 },
      ],
      drilldownReportKey: 'asset_value',
    },
    licenseUtilization: {
      hasData: true,
      seatsTotal: 10,
      seatsAssigned: 6,
      seatsAvailable: 4,
      utilizationPercent: 60,
      drilldownReportKey: 'license_utilization',
    },
    warrantyExpirations: {
      hasData: true,
      alertWindowDays: 30,
      expiringSoonCount: 2,
      expiredCount: 1,
      timeline: [{ month: '2026-08', count: 1 }, { month: '2026-09', count: 1 }],
      drilldownReportKey: 'warranty_expiring',
    },
    overdue: {
      hasData: true,
      overdueAuditCount: 3,
      overdueCheckinCount: 2,
      totalCount: 5,
      drilldownReportKey: 'overdue_audits',
    },
    ...overrides,
  };
}

describe('ItamKpiPanel', () => {
  beforeEach(() => {
    fetchItamKpis.mockReset();
  });

  it('renders four tiles for a fully-populated payload', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis());
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());
    expect(screen.getByText('License Seat Utilization')).toBeInTheDocument();
    expect(screen.getByText('Warranty Expirations')).toBeInTheDocument();
    expect(screen.getByText('Overdue Audits & Check-ins')).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(4);
  });

  it('shows the Loading… convention on each tile while the fetch is in flight', () => {
    fetchItamKpis.mockReturnValue(new Promise(() => {}));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    expect(screen.getAllByText('Loading…')).toHaveLength(4);
  });

  it('a KPI payload with hasData false renders "No data yet" and never a fabricated 0% or 100%', async () => {
    fetchItamKpis.mockResolvedValue({
      assetValue: emptyKpi('asset_value'),
      licenseUtilization: emptyKpi('license_utilization'),
      warrantyExpirations: emptyKpi('warranty_expiring'),
      overdue: emptyKpi('overdue_audits'),
    });
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByText('No data yet')).toHaveLength(4));
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/100%/)).not.toBeInTheDocument();
  });

  it('a licence tile with no licences renders the empty state rather than a zero or hundred percent', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis({ licenseUtilization: emptyKpi('license_utilization') }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(
      screen.getByText('Add a software license from the Licenses & Consumables tab to see this here.')
    ).toBeInTheDocument());
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
    expect(screen.queryByText('100%')).not.toBeInTheDocument();
  });

  it('a populated asset-value tile renders its total plus a chart of the status breakdown', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis());
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('$5,000')).toBeInTheDocument());
    expect(screen.getByText('Valued 10 of 11 assets')).toBeInTheDocument();
    expect(screen.queryByText('12 assets')).not.toBeInTheDocument();
  });

  // Phase 78 plan 02 (D-13, D-14): the selected tenant travels with the KPI
  // request and an unknown book value is "Not tracked", never a fabricated $0.
  it('passes the tenantId prop to fetchItamKpis, and undefined when none is given', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis());
    const { unmount } = render(<ItamKpiPanel onDrillDown={vi.fn()} tenantId="t-1" />);
    await waitFor(() => expect(fetchItamKpis).toHaveBeenCalledWith('t-1'));
    unmount();

    fetchItamKpis.mockClear();
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(fetchItamKpis).toHaveBeenCalledTimes(1));
    expect(fetchItamKpis.mock.calls[0][0]).toBeUndefined();
  });

  it('a null book value renders "Not tracked" and "Valued 0 of 12 assets", never $0', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis({
      assetValue: {
        hasData: true,
        totalBookValueCents: null,
        assetCount: 12,
        inScopeAssetCount: 12,
        valuedCount: 0,
        withoutPolicyCount: 12,
        statusBreakdown: [{ status: 'deployed', label: 'Deployed', count: 12 }],
        drilldownReportKey: 'asset_value',
      },
    }));
    const { container } = render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Not tracked')).toBeInTheDocument());
    expect(screen.getByText('Valued 0 of 12 assets')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\$0/);
  });

  it('a valued total shows the Valued line from valuedCount and inScopeAssetCount', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis({
      assetValue: {
        hasData: true,
        totalBookValueCents: 500000,
        assetCount: 12,
        inScopeAssetCount: 12,
        valuedCount: 10,
        withoutPolicyCount: 2,
        statusBreakdown: [{ status: 'deployed', label: 'Deployed', count: 12 }],
        drilldownReportKey: 'asset_value',
      },
    }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('$5,000')).toBeInTheDocument());
    expect(screen.getByText('Valued 10 of 12 assets')).toBeInTheDocument();
  });

  it('uses the singular "asset" when the in-scope count is 1', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis({
      assetValue: {
        hasData: true,
        totalBookValueCents: 12300,
        assetCount: 1,
        inScopeAssetCount: 1,
        valuedCount: 1,
        withoutPolicyCount: 0,
        statusBreakdown: [{ status: 'deployed', label: 'Deployed', count: 1 }],
        drilldownReportKey: 'asset_value',
      },
    }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Valued 1 of 1 asset')).toBeInTheDocument());
  });

  it('an older response without valuedCount and inScopeAssetCount still renders', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis({
      assetValue: {
        hasData: true,
        totalBookValueCents: 500000,
        assetCount: 12,
        withoutPolicyCount: 2,
        statusBreakdown: [{ status: 'deployed', label: 'Deployed', count: 12 }],
        drilldownReportKey: 'asset_value',
      },
    }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Valued 0 of 12 assets')).toBeInTheDocument());
  });

  it('renders the status-breakdown segments in the payload array order, never re-sorted by count', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis({
      assetValue: {
        hasData: true,
        totalBookValueCents: 100,
        assetCount: 3,
        withoutPolicyCount: 0,
        statusBreakdown: [
          { status: 'retired', label: 'Retired', count: 1 },
          { status: 'deployed', label: 'Deployed', count: 8 },
          { status: 'in_stock', label: 'In_stock', count: 3 },
        ],
        drilldownReportKey: 'asset_value',
      },
    }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Retired')).toBeInTheDocument());
    const legendItems = screen.getAllByText(/^(Retired|Deployed|In_stock)$/);
    expect(legendItems.map((el) => el.textContent)).toEqual(['Retired', 'Deployed', 'In_stock']);
  });

  it('a rejected fetch leaves every tile in its empty state and renders no dashboard-wide error banner', async () => {
    fetchItamKpis.mockRejectedValue(new Error('boom'));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByText('No data yet')).toHaveLength(4));
    expect(screen.queryByText('boom')).not.toBeInTheDocument();
  });

  it("clicking a tile invokes onDrillDown with that tile's drilldownReportKey", async () => {
    const onDrillDown = vi.fn();
    fetchItamKpis.mockResolvedValue(fullKpis());
    render(<ItamKpiPanel onDrillDown={onDrillDown} />);

    await waitFor(() => expect(screen.getByText('Total Asset Value')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Total Asset Value/i }));
    expect(onDrillDown).toHaveBeenCalledWith('asset_value');

    fireEvent.click(screen.getByRole('button', { name: /License Seat Utilization/i }));
    expect(onDrillDown).toHaveBeenCalledWith('license_utilization');

    fireEvent.click(screen.getByRole('button', { name: /Warranty Expirations/i }));
    expect(onDrillDown).toHaveBeenCalledWith('warranty_expiring');

    fireEvent.click(screen.getByRole('button', { name: /Overdue Audits/i }));
    expect(onDrillDown).toHaveBeenCalledWith('overdue_audits');
  });

  it('each tile is reachable as a button element so keyboard activation works', async () => {
    fetchItamKpis.mockResolvedValue(fullKpis());
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByRole('button')).toHaveLength(4));
    screen.getAllByRole('button').forEach((btn) => expect(btn.tagName).toBe('BUTTON'));
  });
  // Phase 78 plan 02 Task 2: remaining tile states, Select-a-tenant block, tenant reset.
  function assetValueKpi(over: Record<string, any>) {
    return fullKpis({
      assetValue: {
        hasData: true,
        totalBookValueCents: 500000,
        assetCount: 12,
        inScopeAssetCount: 12,
        valuedCount: 12,
        withoutPolicyCount: 0,
        statusBreakdown: [{ status: 'deployed', label: 'Deployed', count: 12 }],
        drilldownReportKey: 'asset_value',
        ...over,
      },
    });
  }

  it('shows the excluded line for disposed or retired assets, plural and singular, and none when counts match', async () => {
    fetchItamKpis.mockResolvedValue(assetValueKpi({ assetCount: 12, inScopeAssetCount: 9, valuedCount: 9 }));
    const first = render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('3 disposed or retired assets not counted')).toBeInTheDocument());
    first.unmount();

    fetchItamKpis.mockResolvedValue(assetValueKpi({ assetCount: 2, inScopeAssetCount: 1, valuedCount: 1 }));
    const second = render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('1 disposed or retired asset not counted')).toBeInTheDocument());
    second.unmount();

    fetchItamKpis.mockResolvedValue(assetValueKpi({ assetCount: 12, inScopeAssetCount: 12 }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Valued 12 of 12 assets')).toBeInTheDocument());
    expect(screen.queryByText(/disposed or retired/)).not.toBeInTheDocument();
  });

  it('when every asset is disposed or retired the tile says "No active assets" and still shows the excluded line', async () => {
    fetchItamKpis.mockResolvedValue(assetValueKpi({
      totalBookValueCents: null, assetCount: 3, inScopeAssetCount: 0, valuedCount: 0,
    }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Not tracked')).toBeInTheDocument());
    expect(screen.getByText('No active assets')).toBeInTheDocument();
    expect(screen.queryByText(/^Valued /)).not.toBeInTheDocument();
    expect(screen.getByText('3 disposed or retired assets not counted')).toBeInTheDocument();
  });

  it('needsTenant replaces the grid with a Select a tenant status block and sends no request', () => {
    render(<ItamKpiPanel onDrillDown={vi.fn()} needsTenant />);

    const block = screen.getByRole('status');
    expect(block).toHaveTextContent('Select a tenant');
    expect(block).toHaveTextContent(ITAM_KPI_COPY.selectTenantBody);
    expect(screen.queryByText('Total Asset Value')).not.toBeInTheDocument();
    expect(screen.queryByText('License Seat Utilization')).not.toBeInTheDocument();
    expect(screen.queryByText('Warranty Expirations')).not.toBeInTheDocument();
    expect(screen.queryByText('Overdue Audits & Check-ins')).not.toBeInTheDocument();
    expect(fetchItamKpis).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Go to Tenants' })).not.toBeInTheDocument();
  });

  it('shows Go to Tenants only when a handler is supplied and calls it on click', () => {
    const onGoToTenants = vi.fn();
    render(<ItamKpiPanel onDrillDown={vi.fn()} needsTenant onGoToTenants={onGoToTenants} />);

    fireEvent.click(screen.getByRole('button', { name: 'Go to Tenants' }));
    expect(onGoToTenants).toHaveBeenCalledTimes(1);
  });

  it('a rejection starting "Select a tenant" shows the Select block; any other failure keeps the No data yet tiles', async () => {
    fetchItamKpis.mockRejectedValue(new Error('Select a tenant: ITAM figures cover one organization at a time.'));
    const first = render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Select a tenant'));
    expect(screen.queryByText('No data yet')).not.toBeInTheDocument();
    first.unmount();

    fetchItamKpis.mockRejectedValue(new Error('boom'));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByText('No data yet')).toHaveLength(4));
    expect(screen.queryByText('boom')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('a rejection starting "Unknown tenant" shows the same Select block, not the generic failure tiles', async () => {
    fetchItamKpis.mockRejectedValue(new Error('Unknown tenant: the selected organization does not exist.'));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Select a tenant'));
    expect(screen.queryByText('No data yet')).not.toBeInTheDocument();
    expect(screen.queryByText(/Unknown tenant/)).not.toBeInTheDocument();
  });

  it('a tenant change clears the previous figure, shows Loading, and ignores a late response for the old tenant', async () => {
    let resolveT1: (v: unknown) => void = () => {};
    let resolveT2: (v: unknown) => void = () => {};
    fetchItamKpis.mockImplementation((tenant?: string) => new Promise((resolve) => {
      if (tenant === 't-1') resolveT1 = resolve; else resolveT2 = resolve;
    }));

    const { rerender } = render(<ItamKpiPanel onDrillDown={vi.fn()} tenantId="t-1" />);
    resolveT1(assetValueKpi({ totalBookValueCents: 111100 }));
    await waitFor(() => expect(screen.getByText('$1,111')).toBeInTheDocument());

    rerender(<ItamKpiPanel onDrillDown={vi.fn()} tenantId="t-2" />);
    expect(screen.queryByText('$1,111')).not.toBeInTheDocument();
    expect(screen.getAllByText('Loading…')).toHaveLength(4);

    resolveT2(assetValueKpi({ totalBookValueCents: 222200 }));
    await waitFor(() => expect(screen.getByText('$2,222')).toBeInTheDocument());
    expect(fetchItamKpis).toHaveBeenLastCalledWith('t-2');
  });

  it('a response for the older tenant that arrives after the switch is never rendered', async () => {
    let resolveT1: (v: unknown) => void = () => {};
    let resolveT2: (v: unknown) => void = () => {};
    fetchItamKpis.mockImplementation((tenant?: string) => new Promise((resolve) => {
      if (tenant === 't-1') resolveT1 = resolve; else resolveT2 = resolve;
    }));

    const { rerender } = render(<ItamKpiPanel onDrillDown={vi.fn()} tenantId="t-1" />);
    rerender(<ItamKpiPanel onDrillDown={vi.fn()} tenantId="t-2" />);
    resolveT1(assetValueKpi({ totalBookValueCents: 111100 }));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText('$1,111')).not.toBeInTheDocument();
    expect(screen.getAllByText('Loading…')).toHaveLength(4);

    resolveT2(assetValueKpi({ totalBookValueCents: 222200 }));
    await waitFor(() => expect(screen.getByText('$2,222')).toBeInTheDocument());
    expect(screen.queryByText('$1,111')).not.toBeInTheDocument();
  });

  it('the Total Asset Value button is described by the summary holding the figure and the Valued line', async () => {
    fetchItamKpis.mockResolvedValue(assetValueKpi({ valuedCount: 10 }));
    render(<ItamKpiPanel onDrillDown={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('$5,000')).toBeInTheDocument());
    const button = screen.getByRole('button', { name: /Total Asset Value/i });
    expect(button).toHaveAttribute('aria-describedby', 'itam-kpi-asset-value-summary');
    const summary = document.getElementById('itam-kpi-asset-value-summary');
    expect(summary).not.toBeNull();
    expect(summary).toHaveTextContent('$5,000');
    expect(summary).toHaveTextContent('Valued 10 of 12 assets');
  });

  it('new lines never truncate and the Select block body is max-w-prose', async () => {
    fetchItamKpis.mockResolvedValue(assetValueKpi({
      totalBookValueCents: null, assetCount: 5, inScopeAssetCount: 4, valuedCount: 0,
    }));
    const tile = render(<ItamKpiPanel onDrillDown={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Not tracked')).toBeInTheDocument());
    const summary = document.getElementById('itam-kpi-asset-value-summary') as HTMLElement;
    expect(summary.innerHTML).not.toMatch(/truncate|text-ellipsis/);
    tile.unmount();

    render(<ItamKpiPanel onDrillDown={vi.fn()} needsTenant onGoToTenants={vi.fn()} />);
    const block = screen.getByRole('status');
    expect(block.innerHTML).not.toMatch(/truncate|text-ellipsis/);
    expect(screen.getByText(ITAM_KPI_COPY.selectTenantBody)).toHaveClass('max-w-prose');
  });
});
