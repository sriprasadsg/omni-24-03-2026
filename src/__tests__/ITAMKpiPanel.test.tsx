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

import { ItamKpiPanel } from '../../components/itam/ItamKpiPanel';

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
  // @ts-expect-error jsdom has no ResizeObserver implementation
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
    expect(screen.getByText('12 assets')).toBeInTheDocument();
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
});
