import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  fetchPartners,
  fetchPartnerCustomers,
  type PartnerCustomerRow,
  type PartnerSummary,
} from '../services/partnerApi';
import { AlertTriangleIcon, BuildingIcon, ChevronRightIcon, PlusIcon, SearchIcon } from './icons';
import { PartnerStatusChip, PoolExpiryChip, formatDay } from './PartnerStatusChip';
import { EmptyStateCard } from './AutonomousOpsActivityList';
import PartnerFormModal from './PartnerFormModal';
import { ReinstatePartnerDialog, SuspendPartnerDialog } from './PartnerStatusDialogs';
import PartnerMoveCustomerModal from './PartnerMoveCustomerModal';

/**
 * Phase 87 (PART-01, PART-07; 87-UI-SPEC section 1): the Super Admin Partners screen. A table of partners
 * with each pool's handed-out figure, expiry, screen count and status, a per-partner disclosure of its
 * customers (seats and usage only, D-01), and the four dialogs that act on a partner. Every server string
 * is rendered as React text. The server is the authority on every limit; this screen only displays them.
 */

const PAGE_SIZE = 25;
const PAGING_FROM = 50;
const SEARCH_FROM = 11;
const DASHBOARD_SCREEN = 'screen:dashboard';

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
const INPUT =
  'w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 pl-9 pr-3 py-2 min-h-10 text-sm text-gray-900 dark:text-white';

const isNum = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);
const fmt = (n: unknown): string => (isNum(n) ? n.toLocaleString('en-US') : '—');
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`;

/** Wide screens get the table; narrower ones stacked cards (the Phase 81 pattern). Wide when it cannot be asked. */
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

/** The ceiling count the table shows: the Overview screen is always included, so it is not counted. */
function screenText(p: PartnerSummary): string {
  if (p.unrestricted || (p.screenCeiling ?? []).includes('all')) return 'All screens';
  if (!Array.isArray(p.screenCeiling)) return '—';
  const count = p.screenCeiling.filter(s => s !== DASHBOARD_SCREEN).length;
  return plural(count, 'screen', 'screens');
}

type CustomersState = { status: 'loading' } | { status: 'error' } | { status: 'ready'; rows: PartnerCustomerRow[] };

type Modal =
  | { kind: 'form'; mode: 'appoint' }
  | { kind: 'form'; mode: 'edit'; partner: PartnerSummary }
  | { kind: 'suspend'; partner: PartnerSummary }
  | { kind: 'reinstate'; partner: PartnerSummary }
  | { kind: 'move'; mode: 'move'; partner: PartnerSummary; customer: PartnerCustomerRow }
  | { kind: 'move'; mode: 'add'; partner: PartnerSummary };

const PoolCell: React.FC<{ partner: PartnerSummary }> = ({ partner }) => {
  if (!isNum(partner.allocated) || !isNum(partner.poolSize)) return <p>—</p>;
  const pct = partner.poolSize > 0 ? Math.min(100, Math.round((partner.allocated / partner.poolSize) * 100)) : 0;
  return (
    <div className="space-y-1">
      <p className="tabular-nums">{`${fmt(partner.allocated)} of ${fmt(partner.poolSize)} handed out`}</p>
      <div
        role="img"
        aria-label={`${partner.allocated} of ${partner.poolSize} seats handed out`}
        className="h-2 w-full rounded-full bg-gray-200 dark:bg-white/10"
      >
        <div className="h-2 rounded-full bg-primary-600" style={{ width: `${pct}%` }} />
      </div>
      <p className={`${MUTED} tabular-nums`}>{`${fmt(partner.free)} free`}</p>
    </div>
  );
};

/** A pool shows Expired and the 30-day warning; a customer licence only Expired (UI-SPEC Color). */
const ExpiryCell: React.FC<{ iso: string | null | undefined; warn?: boolean }> = ({ iso, warn = true }) => {
  const day = formatDay(iso);
  if (!iso || !day) return <span className="text-gray-500 dark:text-gray-400">No expiry</span>;
  const lapsed = new Date(iso).getTime() <= Date.now();
  return (
    <span className="flex flex-wrap items-center gap-2">
      <time dateTime={iso} title={iso}>{day}</time>
      {(warn || lapsed) && <PoolExpiryChip expiresAt={iso} />}
    </span>
  );
};

const NameBlock: React.FC<{ partner: PartnerSummary }> = ({ partner }) => (
  <>
    <p className="font-semibold break-words">{partner.name}</p>
    <p className={MUTED}>{isNum(partner.customerCount) ? plural(partner.customerCount, 'customer', 'customers') : '—'}</p>
  </>
);

interface ActionProps {
  partner: PartnerSummary;
  expanded: boolean;
  controlsId: string;
  busy: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onStatus: () => void;
}

const RowActions: React.FC<ActionProps> = ({ partner, expanded, controlsId, busy, onToggle, onEdit, onStatus }) => {
  const suspended = partner.status !== 'active';
  return (
    <div className="flex flex-wrap gap-2">
      <button type="button" className={ROW_BUTTON} disabled={busy} onClick={onEdit} aria-label={`Edit ${partner.name}`}>
        Edit partner
      </button>
      <button
        type="button"
        className={ROW_BUTTON}
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={controlsId}
        aria-label={`${expanded ? 'Hide' : 'Show'} customers of ${partner.name}`}
      >
        <ChevronRightIcon size={14} aria-hidden="true" className={expanded ? 'rotate-90' : ''} />
        {expanded ? 'Hide customers' : 'Show customers'}
      </button>
      <button
        type="button"
        className={ROW_BUTTON}
        disabled={busy}
        onClick={onStatus}
        aria-label={`${suspended ? 'Reinstate' : 'Suspend'} ${partner.name}`}
      >
        {suspended ? 'Reinstate partner' : 'Suspend partner'}
      </button>
    </div>
  );
};

interface CustomersProps {
  id: string;
  partner: PartnerSummary;
  state: CustomersState | undefined;
  onRetry: () => void;
  onMove: (customer: PartnerCustomerRow) => void;
  onAdd: () => void;
}

const CustomersPanel: React.FC<CustomersProps> = ({ id, partner, state, onRetry, onMove, onAdd }) => (
  <div id={id} className="space-y-4" aria-busy={state?.status === 'loading'}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white break-words">{`Customers of ${partner.name}`}</h3>
      <button type="button" className={SECONDARY_BUTTON} onClick={onAdd}>
        <PlusIcon size={16} aria-hidden="true" />
        Add an existing organization
      </button>
    </div>
    {(!state || state.status === 'loading') && <div className="h-4 w-1/2 animate-pulse rounded bg-gray-200 dark:bg-white/10" />}
    {state?.status === 'error' && (
      <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-700 dark:text-red-300">
        <AlertTriangleIcon size={16} aria-hidden="true" />
        <span>Couldn't load the customers. Check your connection and try again.</span>
        <button type="button" className={SECONDARY_BUTTON} onClick={onRetry}>Try again</button>
      </div>
    )}
    {state?.status === 'ready' && state.rows.length === 0 && (
      <p className={MUTED}>This partner has no customers yet.</p>
    )}
    {state?.status === 'ready' && state.rows.length > 0 && (
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr>
              {['Customer', 'Seats used', 'Seats assigned', 'Agents online', 'Licence expires'].map(h => (
                <th key={h} scope="col" className="py-2 pr-4 text-left text-xs font-normal text-gray-500 dark:text-gray-400">{h}</th>
              ))}
              <th scope="col" className="py-2 text-left text-xs font-normal text-gray-500 dark:text-gray-400">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-white/10">
            {state.rows.map(c => (
                <tr key={c.id}>
                  <td className="py-2 pr-4 font-semibold break-words">{c.name}</td>
                  <td className="py-2 pr-4 tabular-nums">{fmt(c.seatsUsed)}</td>
                  <td className="py-2 pr-4 tabular-nums">{fmt(c.seatsAssigned)}</td>
                  <td className="py-2 pr-4 tabular-nums">{isNum(c.agentsOnline) && isNum(c.agentsTotal) ? `${c.agentsOnline} of ${c.agentsTotal}` : '—'}</td>
                  <td className="py-2 pr-4"><ExpiryCell iso={c.licenseExpiresAt} warn={false} /></td>
                  <td className="py-2">
                    <button type="button" className={ROW_BUTTON} aria-label={`Move ${c.name}`} onClick={() => onMove(c)}>
                      Move customer
                    </button>
                  </td>
                </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

export const PartnersDashboard: React.FC = () => {
  const uid = useId();
  const wide = useWideLayout();
  const [partners, setPartners] = useState<PartnerSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [customers, setCustomers] = useState<Record<string, CustomersState>>({});
  const [modal, setModal] = useState<Modal | null>(null);
  const alive = useRef(true);
  const expandedRef = useRef(expanded);
  expandedRef.current = expanded;

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  // Only the newest request applies, and a quiet reload that fails keeps what is on screen (87 WR-11).
  const loadSeq = useRef(0);
  const load = useCallback(async (showSkeleton: boolean) => {
    const mine = ++loadSeq.current;
    if (showSkeleton) setPartners(null);
    setLoadError(false);
    try {
      const list = await fetchPartners();
      if (alive.current && mine === loadSeq.current) setPartners(list);
    } catch {
      if (!alive.current || mine !== loadSeq.current) return;
      setLoadError(true);
      if (showSkeleton) setPartners(null);
    }
  }, []);

  const loadCustomers = useCallback(async (partnerId: string) => {
    setCustomers(prev => ({ ...prev, [partnerId]: { status: 'loading' } }));
    try {
      const rows = await fetchPartnerCustomers(partnerId);
      if (alive.current) setCustomers(prev => ({ ...prev, [partnerId]: { status: 'ready', rows } }));
    } catch {
      if (alive.current) setCustomers(prev => ({ ...prev, [partnerId]: { status: 'error' } }));
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);

  /** After any success: refetch the table and the customers of every open partner (seats moved between them),
   *  and forget the customers of closed ones, so opening one later loads it again (87 WR-08). */
  const refreshAll = useCallback(() => {
    void load(false);
    const open = expandedRef.current;
    setCustomers(prev => Object.fromEntries(Object.entries(prev).filter(([id]) => open.has(id))));
    open.forEach(id => { void loadCustomers(id); });
  }, [load, loadCustomers]);

  const toggle = (partner: PartnerSummary) => {
    const open = expanded.has(partner.id);
    setExpanded(prev => {
      const next = new Set(prev);
      if (open) next.delete(partner.id); else next.add(partner.id);
      return next;
    });
    if (!open && !customers[partner.id]) void loadCustomers(partner.id);
  };

  const closeModal = () => setModal(null);
  // Dialogs show the live rows, so a refetch after a refusal updates their figures (87 WR-10).
  const livePartner = (p: PartnerSummary) => partners?.find(x => x.id === p.id) ?? p;
  const liveCustomer = (partnerId: string, c: PartnerCustomerRow) => {
    const state = customers[partnerId];
    return (state?.status === 'ready' ? state.rows.find(x => x.id === c.id) : undefined) ?? c;
  };
  const appoint = () => setModal({ kind: 'form', mode: 'appoint' });

  const sorted = [...(partners ?? [])].sort((a, b) => String(a.name).localeCompare(String(b.name)));
  const needle = query.trim().toLowerCase();
  const matches = needle ? sorted.filter(p => String(p.name).toLowerCase().includes(needle)) : sorted;
  const paged = sorted.length >= PAGING_FROM;
  const visible = paged ? matches.slice(0, limit) : matches;
  const loading = partners === null && !loadError;
  const showSearch = sorted.length >= SEARCH_FROM;

  const rowProps = (p: PartnerSummary): ActionProps => ({
    partner: p,
    expanded: expanded.has(p.id),
    controlsId: `${uid}-customers-${p.id}`,
    busy: customers[p.id]?.status === 'loading',
    onToggle: () => toggle(p),
    onEdit: () => setModal({ kind: 'form', mode: 'edit', partner: p }),
    onStatus: () => setModal({ kind: p.status === 'active' ? 'suspend' : 'reinstate', partner: p }),
  });

  const panel = (p: PartnerSummary) => (
    <CustomersPanel
      id={`${uid}-customers-${p.id}`}
      partner={p}
      state={customers[p.id]}
      onRetry={() => { void loadCustomers(p.id); }}
      onMove={customer => setModal({ kind: 'move', mode: 'move', partner: p, customer })}
      onAdd={() => setModal({ kind: 'move', mode: 'add', partner: p })}
    />
  );

  const renderTable = () => (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead>
          <tr className="border-b border-gray-200 dark:border-white/10">
            {/* Minimums sum to 900px so the table fits 1280px with the sidebar open (922px of card),
                as the Partner portal's customers table does. */}
            <th scope="col" className={`${TH} min-w-[190px]`}>Partner</th>
            <th scope="col" className={`${TH} min-w-[170px]`}>Pool</th>
            <th scope="col" className={`${TH} min-w-[130px]`}>Expires</th>
            <th scope="col" className={`${TH} min-w-[110px]`}>Screens</th>
            <th scope="col" className={`${TH} min-w-[110px]`}>Status</th>
            <th scope="col" className={`${TH} min-w-[190px]`}>Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-white/10">
          {loading && [0, 1, 2, 3].map(i => (
            <tr key={i} data-skeleton>
              <td colSpan={6} className="px-6 py-4"><div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-white/10" /></td>
            </tr>
          ))}
          {visible.map(p => (
            <React.Fragment key={p.id}>
              <tr>
                <td className={TD}><NameBlock partner={p} /></td>
                <td className={TD}><PoolCell partner={p} /></td>
                <td className={TD}><ExpiryCell iso={p.expiresAt} /></td>
                <td className={`${TD} tabular-nums`}>{screenText(p)}</td>
                <td className={TD}><PartnerStatusChip kind={p.status} /></td>
                <td className={TD}><RowActions {...rowProps(p)} /></td>
              </tr>
              {expanded.has(p.id) && (
                <tr className="bg-gray-50 dark:bg-white/[0.03]">
                  <td colSpan={6} className="px-6 py-4">{panel(p)}</td>
                </tr>
              )}
            </React.Fragment>
          ))}
          {!loading && needle && matches.length === 0 && (
            <tr>
              <td colSpan={6} className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">
                <span className="break-words">{`No partners match "${query.trim()}".`}</span>{' '}
                <button type="button" className={ROW_BUTTON} onClick={() => setQuery('')}>Clear search</button>
              </td>
            </tr>
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
      {visible.map(p => (
        <li key={p.id} aria-label={p.name} className="space-y-4 p-4 text-sm text-gray-900 dark:text-white">
          <NameBlock partner={p} />
          <dl className="space-y-2">
            <div><dt className={MUTED}>Pool</dt><dd><PoolCell partner={p} /></dd></div>
            <div><dt className={MUTED}>Expires</dt><dd><ExpiryCell iso={p.expiresAt} /></dd></div>
            <div><dt className={MUTED}>Screens</dt><dd className="tabular-nums">{screenText(p)}</dd></div>
            <div><dt className={MUTED}>Status</dt><dd><PartnerStatusChip kind={p.status} /></dd></div>
          </dl>
          <RowActions {...rowProps(p)} />
          {expanded.has(p.id) && panel(p)}
        </li>
      ))}
      {!loading && needle && matches.length === 0 && (
        <li className="p-4 text-sm text-gray-600 dark:text-gray-300">
          <span className="break-words">{`No partners match "${query.trim()}".`}</span>{' '}
          <button type="button" className={ROW_BUTTON} onClick={() => setQuery('')}>Clear search</button>
        </li>
      )}
    </ul>
  );

  const empty = partners !== null && partners.length === 0;

  return (
    <div className="container mx-auto space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold leading-tight text-gray-900 dark:text-white">Partners</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Appoint partners, give each a pool of agent seats and set which screens they may sell.
          </p>
        </div>
        <button type="button" className={PRIMARY_BUTTON} onClick={appoint}>
          <PlusIcon size={16} aria-hidden="true" />
          Appoint partner
        </button>
      </header>

      {loadError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
          <AlertTriangleIcon size={16} aria-hidden="true" />
          <span>Couldn't load partners. Check your connection and try again.</span>
          <button type="button" className={SECONDARY_BUTTON} onClick={() => { void load(true); }}>Try again</button>
        </div>
      )}

      {empty && (
        <div className="card">
          <EmptyStateCard icon={BuildingIcon} heading="No partners yet">
            <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">
              Appoint a partner to give a dealer or reseller its own pool of seats. Its staff then create and manage their own customers.
            </p>
            <button type="button" className={PRIMARY_BUTTON} onClick={appoint}>Appoint partner</button>
          </EmptyStateCard>
        </div>
      )}

      {(!loadError || partners !== null) && !empty && (
        <section className="space-y-4" aria-label="Partners">
          <div className="flex flex-wrap items-center gap-4">
            {partners !== null && (
              <p className={MUTED}>{plural(partners.length, 'partner', 'partners')}</p>
            )}
            {showSearch && (
              <div className="relative max-w-xs flex-1">
                <SearchIcon size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="search"
                  aria-label="Search partners"
                  placeholder="Search partners"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  className={INPUT}
                />
              </div>
            )}
          </div>
          <div className="card overflow-hidden" aria-busy={loading}>
            {wide ? renderTable() : renderCards()}
          </div>
          {paged && matches.length > limit && (
            <button type="button" className={SECONDARY_BUTTON} onClick={() => setLimit(l => l + PAGE_SIZE)}>
              Show more partners
            </button>
          )}
        </section>
      )}

      {modal?.kind === 'form' && (
        <PartnerFormModal
          mode={modal.mode}
          partner={modal.mode === 'edit' ? livePartner(modal.partner) : undefined}
          onClose={closeModal}
          onSaved={refreshAll}
        />
      )}
      {modal?.kind === 'suspend' && <SuspendPartnerDialog partner={livePartner(modal.partner)} onClose={closeModal} onDone={refreshAll} />}
      {modal?.kind === 'reinstate' && <ReinstatePartnerDialog partner={livePartner(modal.partner)} onClose={closeModal} onDone={refreshAll} />}
      {modal?.kind === 'move' && (
        <PartnerMoveCustomerModal
          mode={modal.mode}
          partner={livePartner(modal.partner)}
          customer={modal.mode === 'move' ? liveCustomer(modal.partner.id, modal.customer) : undefined}
          partners={partners ?? []}
          onClose={closeModal}
          onMoved={refreshAll}
        />
      )}
    </div>
  );
};

export default PartnersDashboard;
