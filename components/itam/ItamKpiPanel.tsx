import React, { useEffect, useState } from 'react';
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend, BarChart, Bar, XAxis, YAxis,
} from 'recharts';
import { fetchItamKpis, ItamKpis } from '../../services/apiService';
import { DollarSignIcon, PieChartIcon, CalendarDaysIcon, AlertTriangleIcon } from '../icons';

// Phase 72 Plan 07: the Reports tab's KPI tile grid (ITAM-REP-04, D-16/D-17/D-18).
// Clones CXODashboard.tsx's recharts usage — no new charting dependency.

// Phase 78 (UI-SPEC Copywriting Contract, R6): every new string in one English
// constant so tests assert against a single source. Not in itamI18n.tsx: none
// of the existing tile strings are translated.
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

export const ITAM_KPI_COPY = {
  notTracked: 'Not tracked',
  notTrackedHint: 'Assets need a purchase price, a purchase date and an asset model with a useful life to be valued.',
  nothingActive: 'No active assets',
  valued: (x: number, y: number) => `Valued ${x} of ${y} ${plural(y, 'asset', 'assets')}`,
  excluded: (n: number) => `${n} disposed or retired ${plural(n, 'asset', 'assets')} not counted`,
  selectTenantHeading: 'Select a tenant',
  selectTenantBody: 'Asset values and reports cover one organization at a time. Open a tenant from Tenants, then come back to Reports.',
  goToTenants: 'Go to Tenants',
  reportsSelectTenantNote: 'Select a tenant to run these reports. They cover one organization at a time.',
};

interface ItamKpiPanelProps {
  onDrillDown: (reportKey: string) => void;
  // Phase 78 D-13/D-14: the selected tenant (Platform Owner) or the user's own.
  tenantId?: string | null;
  needsTenant?: boolean;
  onGoToTenants?: () => void;
}

// Segment colours for pie/bar series — first entry is the tenant accent
// (matches the console's default cyan; ItamKpiPanel takes no accent prop
// per this plan's locked signature, so it uses the same default the rest
// of the un-branded console renders with).
const CHART_COLORS = ['#0891b2', '#6366f1', '#ec4899', '#f59e0b', '#10b981', '#f43f5e', '#8b5cf6'];

function formatCurrency(cents: number): string {
  return `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

interface KpiTileProps {
  title: string;
  icon: React.ReactNode;
  loading: boolean;
  hasData: boolean;
  drilldownReportKey: string;
  entity: string;
  tab: string;
  onDrillDown: (reportKey: string) => void;
  children?: React.ReactNode;
}

// Per UI-SPEC element E6: Loading… while in flight, "No data yet" + an
// entity/tab-specific next step when the KPI reports hasData=false (or the
// whole fetch failed) — never a fabricated 0% or 100%, and never a
// dashboard-wide error banner for a single tile's failure.
function KpiTile({ title, icon, loading, hasData, drilldownReportKey, entity, tab, onDrillDown, children }: KpiTileProps) {
  return (
    <button
      type="button"
      onClick={() => onDrillDown(drilldownReportKey)}
      aria-label={`${title} — view report`}
      className="text-left w-full bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 hover:border-cyan-600 transition-colors"
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="p-2 rounded-lg bg-cyan-100 dark:bg-cyan-900/20 flex-shrink-0">
          <span className="text-cyan-500">{icon}</span>
        </div>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h4>
      </div>
      {loading && <p className="text-gray-600 dark:text-gray-400 text-sm">Loading…</p>}
      {!loading && !hasData && (
        <div>
          <h5 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">No data yet</h5>
          <p className="text-gray-500 text-xs">Add {entity} from the {tab} tab to see this here.</p>
        </div>
      )}
      {!loading && hasData && children}
    </button>
  );
}

export function ItamKpiPanel({ onDrillDown, tenantId }: ItamKpiPanelProps) {
  const [data, setData] = useState<ItamKpis | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // R3: never leave the previous tenant's figures on screen while the new request runs.
    setData(null);
    setFailed(false);
    setLoading(true);
    fetchItamKpis(tenantId)
      .then((kpis) => { if (!cancelled) setData(kpis); })
      .catch(() => { if (!cancelled) setFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tenantId]);

  const assetValue = data?.assetValue;
  // UI-SPEC section 2: an older response without the new fields still renders.
  const valued = assetValue?.valuedCount ?? 0;
  const inScope = assetValue?.inScopeAssetCount ?? assetValue?.assetCount ?? 0;
  const bookValue = assetValue?.totalBookValueCents;
  const licenseUtilization = data?.licenseUtilization;
  const warrantyExpirations = data?.warrantyExpirations;
  const overdue = data?.overdue;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <KpiTile
        title="Total Asset Value"
        icon={<DollarSignIcon size={18} />}
        loading={loading}
        hasData={!failed && !!assetValue?.hasData}
        drilldownReportKey={assetValue?.drilldownReportKey || 'asset_value'}
        entity="an asset"
        tab="Catalog"
        onDrillDown={onDrillDown}
      >
        {assetValue?.hasData && (
          <>
            <div id="itam-kpi-asset-value-summary" className="mb-2">
              {typeof bookValue === 'number' ? (
                <p className="text-2xl font-semibold text-gray-900 dark:text-white mb-1">{formatCurrency(bookValue)}</p>
              ) : (
                <p className="text-2xl font-semibold text-gray-500 dark:text-gray-400 mb-1">{ITAM_KPI_COPY.notTracked}</p>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-400">{ITAM_KPI_COPY.valued(valued, inScope)}</p>
              {typeof bookValue !== 'number' && inScope > 0 && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{ITAM_KPI_COPY.notTrackedHint}</p>
              )}
            </div>
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={assetValue.statusBreakdown} dataKey="count" nameKey="label" innerRadius={20} outerRadius={40}>
                    {assetValue.statusBreakdown.map((entry, idx) => (
                      <Cell key={entry.status} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  {/* itemSorter overrides recharts' default alphabetical-by-name
                      legend sort so the legend visually preserves the same
                      payload order the Pie data (and this KPI's segments) render in. */}
                  <Legend wrapperStyle={{ fontSize: '10px' }} itemSorter={() => 0} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </KpiTile>

      <KpiTile
        title="License Seat Utilization"
        icon={<PieChartIcon size={18} />}
        loading={loading}
        hasData={!failed && !!licenseUtilization?.hasData}
        drilldownReportKey={licenseUtilization?.drilldownReportKey || 'license_utilization'}
        entity="a software license"
        tab="Licenses & Consumables"
        onDrillDown={onDrillDown}
      >
        {licenseUtilization?.hasData && (
          <>
            <p className="text-2xl font-semibold text-gray-900 dark:text-white mb-1">{licenseUtilization.utilizationPercent}%</p>
            <p className="text-xs text-gray-500 mb-2">{licenseUtilization.seatsAssigned} / {licenseUtilization.seatsTotal} seats assigned</p>
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Assigned', value: licenseUtilization.seatsAssigned ?? 0 },
                      { name: 'Available', value: licenseUtilization.seatsAvailable ?? 0 },
                    ]}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={20}
                    outerRadius={40}
                  >
                    <Cell fill={CHART_COLORS[0]} />
                    <Cell fill={CHART_COLORS[1]} />
                  </Pie>
                  <Tooltip />
                  {/* itemSorter overrides recharts' default alphabetical-by-name
                      legend sort so the legend visually preserves the same
                      payload order the Pie data (and this KPI's segments) render in. */}
                  <Legend wrapperStyle={{ fontSize: '10px' }} itemSorter={() => 0} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </KpiTile>

      <KpiTile
        title="Warranty Expirations"
        icon={<CalendarDaysIcon size={18} />}
        loading={loading}
        hasData={!failed && !!warrantyExpirations?.hasData}
        drilldownReportKey={warrantyExpirations?.drilldownReportKey || 'warranty_expiring'}
        entity="an asset with a warranty"
        tab="Procurement & Finance"
        onDrillDown={onDrillDown}
      >
        {warrantyExpirations?.hasData && (
          <>
            <p className="text-2xl font-semibold text-gray-900 dark:text-white mb-1">{warrantyExpirations.expiringSoonCount} expiring soon</p>
            <p className="text-xs text-gray-500 mb-2">{warrantyExpirations.expiredCount} expired</p>
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={warrantyExpirations.timeline}>
                  <XAxis dataKey="month" tick={false} axisLine={false} tickLine={false} />
                  <YAxis hide />
                  <Tooltip />
                  <Bar dataKey="count" fill={CHART_COLORS[0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </KpiTile>

      <KpiTile
        title="Overdue Audits & Check-ins"
        icon={<AlertTriangleIcon size={18} />}
        loading={loading}
        hasData={!failed && !!overdue?.hasData}
        drilldownReportKey={overdue?.drilldownReportKey || 'overdue_audits'}
        entity="an asset"
        tab="Catalog"
        onDrillDown={onDrillDown}
      >
        {overdue?.hasData && (
          <>
            <p className="text-2xl font-semibold text-red-600 dark:text-red-400 mb-1">{overdue.totalCount} overdue</p>
            <div className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400 mt-2">
              <span><span className="text-gray-900 dark:text-white font-semibold">{overdue.overdueAuditCount}</span> audits</span>
              <span><span className="text-gray-900 dark:text-white font-semibold">{overdue.overdueCheckinCount}</span> check-ins</span>
            </div>
          </>
        )}
      </KpiTile>
    </div>
  );
}
