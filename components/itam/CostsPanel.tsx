import React, { useEffect, useRef, useState } from 'react';
import { DollarSignIcon } from '../icons';
import { downloadItamReport, generateItamReport } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { ITAM_KPI_COPY, SELECT_TENANT_RE } from './ItamKpiPanel';
import { NOT_TRACKED, formatCents, formatMaybeCents } from './money';
import {
  COSTS_REPORT_KEY, REASON_TEXT, fetchCostAssets, fetchCostSummary, type CostPage, type CostRow, type CostSummary, type LicenseBucket,
} from './costsData';

// Phase 80 (COST-08): the ITAM console's Costs tab. Organization totals and the per-asset breakdown come from
// /api/itam/costs (the same computation as the KPI tile and the Asset value report); the export goes through
// the report registry's endpoint_costs report, which holds exactly these rows. Missing figures read "Not tracked".

const card = 'bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700';
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const licenseCell = (row: CostRow, key: 'recurringAnnualCents' | 'oneTimeCents') => {
  const lic = row.license;
  if (lic && typeof lic[key] === 'number') return formatCents(lic[key] as number);
  return lic?.untrackedSeats ? NOT_TRACKED : '—';
};

function Tile({ title, value, note }: { title: string; value: string; note: string }) {
  const missing = value === NOT_TRACKED;
  return (
    <div className={`${card} p-4`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
        <DollarSignIcon size={14} />{title}
      </p>
      <p className={`mt-2 ${missing ? 'text-base text-gray-500 dark:text-gray-400' : 'text-2xl font-semibold text-gray-900 dark:text-white'}`}>{value}</p>
      <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{note}</p>
    </div>
  );
}

const bucketNote = (b: LicenseBucket | undefined, what: string) => (b?.hasData
  ? `${plural(b.licenses, 'license', 'licenses')}; ${formatCents(b.allocatedCents ?? 0)} on endpoints, ${formatCents(b.unattributedCents ?? 0)} on users, ${formatCents(b.idleCents ?? 0)} on unassigned seats`
  : `No license has a ${what} cost yet. Set one under Licenses.`);

interface CostsPanelProps {
  tenantId?: string | null;
  needsTenant?: boolean;
  onGoToTenants?: () => void;
}

export function CostsPanel({ tenantId, needsTenant, onGoToTenants }: CostsPanelProps) {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [page, setPage] = useState<CostPage | null>(null);
  const [pageNo, setPageNo] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [tenantRejected, setTenantRejected] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => { setPageNo(1); }, [tenantId]);

  useEffect(() => {
    const mine = ++seq.current;
    // Never leave the previous tenant's (or page's) figures on screen while the new request runs.
    setSummary(null); setPage(null); setError(null); setTenantRejected(false);
    if (needsTenant) return;
    Promise.all([fetchCostSummary(tenantId), fetchCostAssets(pageNo, tenantId)])
      .then(([s, p]) => { if (mine === seq.current) { setSummary(s); setPage(p); } })
      .catch((e: unknown) => {
        if (mine !== seq.current) return;
        const msg = e instanceof Error ? e.message : '';
        if (SELECT_TENANT_RE.test(msg)) setTenantRejected(true); else setError(msg || 'The costs could not be loaded');
      });
  }, [tenantId, needsTenant, pageNo]);

  const exportAs = async (format: 'csv' | 'pdf' | 'xlsx') => {
    const forTenant = tenantId;
    setExporting(format);
    try {
      const out = await generateItamReport('prebuilt', COSTS_REPORT_KEY, format, forTenant);
      await downloadItamReport(out.filename);
      showToast(`Exported ${plural(out.rowCount, 'asset', 'assets')}${out.truncated ? ' (cut at the report limit)' : ''}`, 'success');
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'The export failed', 'error');
    } finally {
      setExporting(null);
    }
  };

  if (needsTenant || tenantRejected) {
    return (
      <div role="status" className={`${card} p-8 text-center`}>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">{ITAM_KPI_COPY.selectTenantHeading}</h4>
        <p className="text-sm text-gray-600 dark:text-gray-400 max-w-prose mx-auto mt-1">Costs cover one organization at a time. Open a tenant from Tenants, then come back to Costs.</p>
        {onGoToTenants && (
          <button type="button" onClick={onGoToTenants} className="text-xs font-semibold text-cyan-600 dark:text-cyan-400 hover:underline py-2 mt-2">{ITAM_KPI_COPY.goToTenants}</button>
        )}
      </div>
    );
  }
  if (error) return <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>;
  if (!summary || !page) return <p className="text-sm text-gray-600 dark:text-gray-400" aria-busy="true">Loading costs…</p>;

  const cov = summary.coverage;
  const lic = summary.licenses;
  const unpriced = cov.total - cov.priced;
  const unvalued = cov.total - cov.valued;
  const totalPages = page.totalPages ?? 1;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Tile title="Purchase cost" value={formatMaybeCents(summary.purchaseTotal.cents)} note={`${cov.priced} of ${plural(cov.total, 'active asset', 'active assets')} have a purchase cost`} />
        <Tile title="Book value today" value={formatMaybeCents(summary.bookValueTotal.cents)} note={`${cov.valued} of ${plural(cov.total, 'active asset', 'active assets')} can be valued`} />
        <Tile title="License spend per year" value={formatMaybeCents(lic?.recurringAnnual.spendCents)} note={bucketNote(lic?.recurringAnnual, 'recurring')} />
        <Tile title="One-time license spend" value={formatMaybeCents(lic?.oneTime.spendCents)} note={bucketNote(lic?.oneTime, 'one-time')} />
      </div>

      <div role="note" aria-label="Coverage" className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-100 space-y-1">
        <p>
          {unpriced > 0 ? `${plural(unpriced, 'asset has', 'assets have')} no purchase cost and ` : 'Every active asset has a purchase cost; '}
          {unvalued > 0 ? `${plural(unvalued, 'asset', 'assets')} cannot be valued, so they show as "${NOT_TRACKED}", not $0.` : 'every one can be valued.'}
        </p>
        <p>
          {cov.excludedByLifecycle > 0
            ? `${plural(cov.excludedByLifecycle, 'disposed or retired asset is', 'disposed or retired assets are')} left out of these totals and the table.`
            : 'Disposed and retired assets are left out of these totals and the table.'}
          {lic && lic.coverage.notTracked > 0 ? ` ${plural(lic.coverage.notTracked, 'license has', 'licenses have')} no cost and ${lic.coverage.notTracked === 1 ? 'is' : 'are'} not counted.` : ''}
          {lic && ((lic.recurringAnnual.allocatedToExcludedCents ?? 0) + (lic.oneTime.allocatedToExcludedCents ?? 0)) > 0
            ? ` ${formatCents((lic.recurringAnnual.allocatedToExcludedCents ?? 0) + (lic.oneTime.allocatedToExcludedCents ?? 0))} of license cost sits on seats of disposed or retired assets.` : ''}
        </p>
      </div>

      <section aria-label="Costs by asset" className={`${card} p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Costs by asset <span className="font-normal text-gray-500">· {plural(page.total, 'asset', 'assets')}, highest book value first</span></h3>
          <div className="flex gap-2" role="group" aria-label="Export">
            {(['csv', 'xlsx', 'pdf'] as const).map(f => (
              <button key={f} type="button" disabled={!!exporting || page.total === 0} onClick={() => exportAs(f)}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50">
                {exporting === f ? 'Exporting…' : `Export ${f.toUpperCase()}`}
              </button>
            ))}
          </div>
        </div>
        {page.total === 0 ? <p className="text-sm text-gray-600 dark:text-gray-400 py-6 text-center">No active assets.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs border-b border-gray-200 dark:border-gray-700">
                  {['Asset', 'Endpoint', 'Purchase cost', 'Book value', 'License / year', 'License one-time', 'Why not valued'].map(h => <th key={h} scope="col" className="py-2 pr-4 whitespace-nowrap">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {page.items.map(r => (
                  <tr key={r.assetId} className="border-b border-gray-200 dark:border-gray-800">
                    <td className="py-2 pr-4 text-gray-900 dark:text-white"><span className="font-medium">{r.name || r.assetId}</span>{r.assetTag && <span className="ml-2 text-xs text-gray-500">{r.assetTag}</span>}</td>
                    <td className="py-2 pr-4 text-gray-700 dark:text-gray-300">{r.agent?.hostname || '—'}</td>
                    <td className="py-2 pr-4 tabular-nums text-gray-700 dark:text-gray-300">{formatMaybeCents(r.purchaseCostCents)}</td>
                    <td className="py-2 pr-4 tabular-nums text-gray-700 dark:text-gray-300">{formatMaybeCents(r.bookValueCents)}</td>
                    <td className="py-2 pr-4 tabular-nums text-gray-700 dark:text-gray-300">{licenseCell(r, 'recurringAnnualCents')}</td>
                    <td className="py-2 pr-4 tabular-nums text-gray-700 dark:text-gray-300">{licenseCell(r, 'oneTimeCents')}</td>
                    <td className="py-2 pr-4 text-xs text-gray-600 dark:text-gray-400">{r.reason ? (REASON_TEXT[r.reason] || r.reason) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalPages > 1 && (
          <nav aria-label="Pages" className="flex items-center justify-end gap-2 mt-3 text-xs">
            <button type="button" disabled={pageNo <= 1} onClick={() => setPageNo(n => n - 1)} className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50">Previous</button>
            <span className="text-gray-600 dark:text-gray-400">Page {pageNo} of {totalPages}</span>
            <button type="button" disabled={!page.hasNext} onClick={() => setPageNo(n => n + 1)} className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50">Next</button>
          </nav>
        )}
      </section>
    </div>
  );
}
