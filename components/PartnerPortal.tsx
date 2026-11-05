import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchPartnerOverview, type PartnerCustomerRow, type PartnerOverview } from '../services/partnerApi';
import { downloadCsv, toCsv } from '../utils/csvExport';
import { showToast } from '../utils/toast';
import { AlertTriangleIcon, BuildingIcon, DownloadIcon, InfoIcon, PlusIcon, RefreshCwIcon, SearchIcon } from './icons';
import { EmptyStateCard } from './AutonomousOpsActivityList';
import { PoolExpiryChip, daysUntil, formatDay } from './PartnerStatusChip';
import PartnerTeamPanel from './PartnerTeamPanel';
import { ChangeSeatsModal, ChooseScreensModal, CreateCustomerModal } from './PartnerCustomerModals';

/**
 * Phase 87 (PART-02, PART-04, PART-05, PART-06, PART-08; 87-UI-SPEC section 2): the Partner portal, the only
 * screen a partner user reaches. It shows the partner's seat pool, its customers' seats and agents, and the
 * CSV of exactly those facts (D-01: customer name, seats assigned, seats used, agents online, agents total,
 * licence expiry; nothing else is rendered, tooltipped or exported, and a customer name is never a link).
 * A viewer gets the same page with every write control removed rather than disabled (D-04). The server is the
 * authority on every limit; this page only displays them.
 */

const PAGE_SIZE = 25;
const SEARCH_FROM = 11;
const EXPIRY_NOTICE_DAYS = 30;
export const CSV_HEADERS = ['Customer', 'Seats assigned', 'Seats used', 'Agents online', 'Agents total', 'Licence expires'];

const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white ' +
  'hover:bg-primary-700 disabled:opacity-60';
const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const ROW_BUTTON =
  'inline-flex items-center gap-1 min-h-8 px-2 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2 ' +
  'disabled:opacity-60 disabled:no-underline';
const MUTED = 'text-xs text-gray-500 dark:text-gray-400';
const TH = 'px-6 py-4 text-left text-xs font-normal text-gray-500 dark:text-gray-400';
const TD = 'px-6 py-4 align-top text-sm text-gray-900 dark:text-white';
const SEARCH_INPUT =
  'w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 pl-9 pr-3 py-2 min-h-10 text-sm text-gray-900 dark:text-white';
const TRACK = 'h-2 w-full rounded-full bg-gray-200 dark:bg-white/10';

const isNum = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);
const fmt = (n: unknown): string => (isNum(n) ? n.toLocaleString('en-US') : '—');
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`;
const percent = (part: number, whole: number): number =>
  isNum(part) && isNum(whole) && whole > 0 ? Math.max(0, Math.min(100, Math.round((part / whole) * 100))) : 0;

/** `YYYY-MM-DD` of a stored instant, read from the string so no timezone shifts the day; empty when there is none. */
const dayOf = (iso: string | null | undefined): string => (iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(0, 10) : '');

const localToday = (): string => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

/** `partner-usage-{slug}-{YYYY-MM-DD}.csv`; the slug is lower case with runs of non-alphanumerics as one dash. */
export function csvFileName(partnerName: string): string {
  const slug = String(partnerName ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'partner';
  return `partner-usage-${slug}-${localToday()}.csv`;
}

const byName = (a: PartnerCustomerRow, b: PartnerCustomerRow) => String(a.name).localeCompare(String(b.name));

/** The six D-01 columns, one row per customer, name order. Nothing else a customer has can reach the file. */
export function usageCsv(customers: PartnerCustomerRow[]): string {
  const rows = [...customers].sort(byName).map(c => [
    c.name, c.seatsAssigned, c.seatsUsed, c.agentsOnline, c.agentsTotal, dayOf(c.licenseExpiresAt),
  ]);
  return toCsv(CSV_HEADERS, rows);
}

/** Wide screens get the table, narrower ones stacked cards (the Phase 81 pattern). Wide when it cannot be asked. */
function useWideLayout(): boolean {
  const query = '(min-width: 1024px)';
  const read = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : true);
  const [wide, setWide] = useState(read);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const list = window.matchMedia(query);
    const onChange = () => setWide(list.matches);
    list.addEventListener?.('change', onChange);
    return () => list.removeEventListener?.('change', onChange);
  }, []);
  return wide;
}

const UsedCell: React.FC<{ customer: PartnerCustomerRow }> = ({ customer }) => (
  <div className="space-y-1">
    <p className="tabular-nums">{fmt(customer.seatsUsed)}</p>
    <div role="img" aria-label={`${customer.seatsUsed} of ${customer.seatsAssigned} seats used`} className={TRACK}>
      <div className="h-2 rounded-full bg-primary-600" style={{ width: `${percent(customer.seatsUsed, customer.seatsAssigned)}%` }} />
    </div>
  </div>
);

const ExpiryCell: React.FC<{ iso: string | null | undefined }> = ({ iso }) => {
  const day = formatDay(iso);
  if (!iso || !day) return <span className="text-gray-500 dark:text-gray-400">No expiry</span>;
  return (
    <span className="flex flex-wrap items-center gap-2">
      <time dateTime={iso} title={iso}>{day}</time>
      {new Date(iso).getTime() <= Date.now() && <PoolExpiryChip expiresAt={iso} />}
    </span>
  );
};

const agentsText = (c: PartnerCustomerRow) => `${fmt(c.agentsOnline)} online of ${fmt(c.agentsTotal)}`;

const Tile: React.FC<{ label: string; loading: boolean; value?: React.ReactNode; helper?: string; small?: boolean }> = ({
  label, loading, value, helper, small,
}) => (
  <div className="space-y-1">
    <p className="text-xs font-semibold text-gray-600 dark:text-gray-300">{label}</p>
    {loading ? (
      <div data-skeleton className="h-8 w-16 animate-pulse rounded bg-gray-200 dark:bg-white/10" />
    ) : (
      <p className={`${small ? 'text-lg' : 'text-3xl'} font-semibold leading-tight tabular-nums break-words text-gray-900 dark:text-white`}>{value}</p>
    )}
    {helper && !loading && <p className={MUTED}>{helper}</p>}
  </div>
);

type Modal = { kind: 'create' } | { kind: 'seats'; customer: PartnerCustomerRow } | { kind: 'screens'; customer: PartnerCustomerRow };

export const PartnerPortal: React.FC = () => {
  const uid = useId();
  const [data, setData] = useState<PartnerOverview | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [exporting, setExporting] = useState(false);
  const [modal, setModal] = useState<Modal | null>(null);
  const alive = useRef(true);
  const wide = useWideLayout();

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  /** The first load shows skeletons; every later reload is quiet and never moves focus. */
  // Only the newest request applies, and a quiet reload that fails keeps what is on screen (87 WR-11).
  const loadSeq = useRef(0);
  const load = useCallback(async (showSkeleton: boolean) => {
    const mine = ++loadSeq.current;
    if (showSkeleton) setData(null);
    setLoadError(false);
    try {
      const next = await fetchPartnerOverview();
      if (alive.current && mine === loadSeq.current) setData(next);
    } catch {
      if (!alive.current || mine !== loadSeq.current) return;
      setLoadError(true);
      if (showSkeleton) setData(null);
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);

  const exportCsv = async () => {
    if (!data || exporting) return;
    setExporting(true);
    try {
      await Promise.resolve();
      await downloadCsv(csvFileName(data.partner?.name), usageCsv(data.customers ?? []));
    } catch {
      showToast("Couldn't export usage. Try again.", 'error');
    } finally {
      if (alive.current) setExporting(false);
    }
  };

  const loading = data === null && !loadError;
  const isViewer = data?.role === 'viewer';
  const isAdmin = !isViewer;
  const pool = data?.pool;
  const now = new Date();
  const expired = !!pool && (pool.expired === true || (!!pool.expiresAt && new Date(pool.expiresAt).getTime() <= now.getTime()));
  const daysLeft = pool && !expired ? daysUntil(pool.expiresAt, now) : null;
  const expiringSoon = daysLeft !== null && daysLeft <= EXPIRY_NOTICE_DAYS;
  const noFree = !!pool && !expired && !(pool.free > 0);
  const bannerId = `${uid}-expired`;
  const noFreeId = `${uid}-nofree`;
  const createDisabled = loading || loadError || expired || noFree;
  const createReason = expired ? bannerId : noFree ? noFreeId : undefined;

  const customers = [...(data?.customers ?? [])].sort(byName);
  // A dialog shows the live row, so the refetch after a refusal updates its figures (87 WR-10).
  const liveCustomer = (c: PartnerCustomerRow) => customers.find(x => x.id === c.id) ?? c;
  const needle = query.trim().toLowerCase();
  const matches = needle ? customers.filter(c => String(c.name).toLowerCase().includes(needle)) : customers;
  const visible = matches.slice(0, limit);
  const showSearch = customers.length >= SEARCH_FROM;
  const refetch = () => { void load(false); };

  const rowActions = (c: PartnerCustomerRow) => {
    const open = modal && 'customer' in modal && modal.customer.id === c.id;
    return (
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ROW_BUTTON} disabled={!!open} onClick={() => setModal({ kind: 'seats', customer: c })} aria-label={`Change seats for ${c.name}`}>
          Change seats
        </button>
        <button type="button" className={ROW_BUTTON} disabled={!!open} onClick={() => setModal({ kind: 'screens', customer: c })} aria-label={`Choose screens for ${c.name}`}>
          Choose screens
        </button>
      </div>
    );
  };

  const emptySearch = (
    <>
      <span className="break-words">{`No customers match "${query.trim()}".`}</span>{' '}
      <button type="button" className={ROW_BUTTON} onClick={() => setQuery('')}>Clear search</button>
    </>
  );

  const renderTable = () => (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead>
          <tr className="border-b border-gray-200 dark:border-white/10">
            {/* Minimums sum to 900px so the admin's table fits 1280px with the sidebar open (922px of
                card); the UI-SPEC's 1,048px could not, against its own no-scroll-at-1280 check. */}
            <th scope="col" className={`${TH} min-w-[200px]`}>Customer</th>
            <th scope="col" className={`${TH} min-w-[140px]`}>Seats used</th>
            <th scope="col" className={`${TH} min-w-[120px]`}>Seats assigned</th>
            <th scope="col" className={`${TH} min-w-[150px]`}>Agents</th>
            <th scope="col" className={`${TH} min-w-[130px]`}>Licence expires</th>
            {isAdmin && <th scope="col" className={`${TH} min-w-[160px]`}>Actions</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-white/10">
          {loading && [0, 1, 2, 3].map(i => (
            <tr key={i} data-skeleton>
              <td colSpan={isAdmin ? 6 : 5} className="px-6 py-4"><div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-white/10" /></td>
            </tr>
          ))}
          {visible.map(c => (
            <tr key={c.id}>
              <td className={`${TD} font-semibold break-words`}>{c.name}</td>
              <td className={TD}><UsedCell customer={c} /></td>
              <td className={`${TD} tabular-nums`}>{fmt(c.seatsAssigned)}</td>
              <td className={`${TD} tabular-nums`}>{agentsText(c)}</td>
              <td className={TD}><ExpiryCell iso={c.licenseExpiresAt} /></td>
              {isAdmin && <td className={TD}>{rowActions(c)}</td>}
            </tr>
          ))}
          {!loading && needle && matches.length === 0 && (
            <tr><td colSpan={isAdmin ? 6 : 5} className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">{emptySearch}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  const renderCards = () => (
    <ul className="divide-y divide-gray-200 dark:divide-white/10">
      {loading && [0, 1, 2, 3].map(i => (
        <li key={i} data-skeleton className="p-4"><div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-white/10" /></li>
      ))}
      {visible.map(c => (
        <li key={c.id} aria-label={c.name} className="space-y-4 p-4 text-sm text-gray-900 dark:text-white">
          <p className="font-semibold break-words">{c.name}</p>
          <dl className="space-y-2">
            <div><dt className={MUTED}>Seats used</dt><dd><UsedCell customer={c} /></dd></div>
            <div><dt className={MUTED}>Seats assigned</dt><dd className="tabular-nums">{fmt(c.seatsAssigned)}</dd></div>
            <div><dt className={MUTED}>Agents</dt><dd className="tabular-nums">{agentsText(c)}</dd></div>
            <div><dt className={MUTED}>Licence expires</dt><dd><ExpiryCell iso={c.licenseExpiresAt} /></dd></div>
          </dl>
          {isAdmin && rowActions(c)}
        </li>
      ))}
      {!loading && needle && matches.length === 0 && <li className="p-4 text-sm text-gray-600 dark:text-gray-300">{emptySearch}</li>}
    </ul>
  );

  const createButton = (
    <button type="button" className={PRIMARY_BUTTON} disabled={createDisabled} aria-describedby={createReason} onClick={() => setModal({ kind: 'create' })}>
      <PlusIcon size={16} aria-hidden="true" />
      Create customer
    </button>
  );

  const empty = !!data && customers.length === 0;

  return (
    <div className="container mx-auto space-y-6 p-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold leading-tight text-gray-900 dark:text-white">Partner portal</h1>
            {data?.partner?.name && <p className="text-sm text-gray-600 dark:text-gray-400 break-words">{data.partner.name}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={SECONDARY_BUTTON} disabled={loading || loadError || exporting} onClick={() => { void exportCsv(); }}>
              <DownloadIcon size={16} aria-hidden="true" />
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
            {!isViewer && createButton}
          </div>
        </div>
        {isViewer && <p className={MUTED}>You have read-only access. Ask a partner administrator to make changes.</p>}
        {!isViewer && noFree && (
          <p id={noFreeId} className={MUTED}>You have no free seats. Ask the platform administrator for a larger pool.</p>
        )}
      </header>

      {loadError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
          <AlertTriangleIcon size={16} aria-hidden="true" />
          <span>Couldn't load your customers. Check your connection and try again.</span>
          <button type="button" className={SECONDARY_BUTTON} onClick={() => { void load(true); }}>Try again</button>
        </div>
      )}

      {expired && pool && (
        <div id={bannerId} role="status" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
          <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
          <p className="break-words">
            {`Your seat pool expired on ${formatDay(pool.expiresAt)}. You can't create customers or hand out seats until the platform administrator renews it. Your customers keep working with the seats they have.`}
          </p>
        </div>
      )}
      {expiringSoon && pool && (
        <div role="status" className="flex gap-2 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 dark:border-blue-400/25 dark:bg-blue-400/10 dark:text-blue-200">
          <InfoIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
          <p className="break-words">{`Your seat pool expires on ${formatDay(pool.expiresAt)}.`}</p>
        </div>
      )}

      {(!loadError || data !== null) && (
        <section aria-labelledby={`${uid}-pool-title`} aria-busy={loading} className="space-y-4">
          <h2 id={`${uid}-pool-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">Seat pool</h2>
          <div className="card space-y-6 p-6">
            <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
              <Tile label="Pool size" loading={loading} value={fmt(pool?.size)} />
              <Tile label="Handed out" loading={loading} value={fmt(pool?.handedOut)}
                    helper={`${percent(pool?.handedOut ?? 0, pool?.size ?? 0)}% of the pool`} />
              <Tile label="Free" loading={loading} value={fmt(pool?.free)}
                    helper={expired ? "Can't be handed out after expiry" : 'Available to hand out'} />
              <Tile label="Pool expires" loading={loading} small
                    value={pool?.expiresAt && formatDay(pool.expiresAt) ? <time dateTime={pool.expiresAt} title={pool.expiresAt}>{formatDay(pool.expiresAt)}</time> : 'No expiry'}
                    helper={expired ? 'Expired' : daysLeft !== null ? `${daysLeft} ${daysLeft === 1 ? 'day' : 'days'} left` : 'Never'} />
            </div>
            {loading ? (
              <div className={TRACK} aria-hidden="true" />
            ) : (
              <div role="img" aria-label={`${pool?.handedOut ?? 0} of ${pool?.size ?? 0} seats handed out`} className={TRACK}>
                <div className="h-2 rounded-full bg-primary-600" style={{ width: `${percent(pool?.handedOut ?? 0, pool?.size ?? 0)}%` }} />
              </div>
            )}
          </div>
        </section>
      )}

      {(!loadError || data !== null) && (
        <section aria-labelledby={`${uid}-customers-title`} aria-busy={loading} className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 id={`${uid}-customers-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">Customers</h2>
            {data && (
              <div className="flex flex-wrap items-center gap-4">
                <p className={MUTED}>{plural(customers.length, 'customer', 'customers')}</p>
                <button type="button" className={ROW_BUTTON} onClick={refetch}>
                  <RefreshCwIcon size={14} aria-hidden="true" />
                  Refresh customers
                </button>
              </div>
            )}
          </div>
          {showSearch && (
            <div className="relative max-w-xs">
              <SearchIcon size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input type="search" aria-label="Search customers" placeholder="Search customers" value={query}
                     onChange={e => { setQuery(e.target.value); setLimit(PAGE_SIZE); }} className={SEARCH_INPUT} />
            </div>
          )}
          {empty ? (
            <div className="card">
              <EmptyStateCard icon={BuildingIcon} heading="No customers yet">
                <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">
                  {isViewer
                    ? 'Your customers appear here once a partner administrator creates them.'
                    : `Create your first customer, give it some of your ${fmt(pool?.free)} free seats and invite its administrator.`}
                </p>
                {!isViewer && createButton}
              </EmptyStateCard>
            </div>
          ) : (
            <div className="card overflow-hidden" aria-busy={loading}>{wide ? renderTable() : renderCards()}</div>
          )}
          {matches.length > limit && (
            <button type="button" className={SECONDARY_BUTTON} onClick={() => setLimit(l => l + PAGE_SIZE)}>Show more customers</button>
          )}
        </section>
      )}

      {data && isAdmin && <PartnerTeamPanel />}

      {modal?.kind === 'create' && (
        <CreateCustomerModal
          free={pool?.free ?? 0}
          ceiling={data?.ceiling ?? []}
          unrestricted={!!data?.unrestricted}
          onClose={() => setModal(null)}
          onRefetch={refetch}
        />
      )}
      {modal?.kind === 'seats' && (
        <ChangeSeatsModal customer={liveCustomer(modal.customer)} free={pool?.free ?? 0} expired={expired} onClose={() => setModal(null)} onRefetch={refetch} />
      )}
      {modal?.kind === 'screens' && (
        <ChooseScreensModal customer={liveCustomer(modal.customer)} onClose={() => setModal(null)} onRefetch={refetch} />
      )}
    </div>
  );
};

export default PartnerPortal;
