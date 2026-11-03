import React, { useEffect, useId, useState } from 'react';
import {
  fetchDirectCustomers,
  moveCustomer,
  PartnerApiError,
  type DirectCustomer,
  type PartnerCustomerRow,
  type PartnerSummary,
} from '../services/partnerApi';
import { showToast } from '../utils/toast';
import { AlertTriangleIcon } from './icons';
import Modal from './Modal';

/**
 * Phase 87 (PART-07; D-11, D-18, D-19; 87-UI-SPEC section 1): move a customer between partners or to direct
 * (`move`), or take a direct customer into a partner (`add`). The seat consequence is shown before the click
 * and a target that cannot fit the seats disables submit. That check is advisory: the server decides, and a
 * lost race shows the server's own 409 text with its free count.
 */

const DIRECT = '__direct__';
const FILTER_FROM = 21;

const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';
const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const INPUT =
  'w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 min-h-10 text-sm text-gray-900 dark:text-white disabled:opacity-60';
const LABEL = 'block text-sm font-semibold text-gray-900 dark:text-white';

const seats = (n: number) => `${n} ${n === 1 ? 'seat' : 'seats'}`;

/** Server 409s (pool full, race lost) are the message; other failures are wrapped. */
function failureText(e: unknown): string {
  if (e instanceof PartnerApiError) {
    return e.status === 409 ? e.message : `Couldn't move this customer: ${e.message.replace(/\.+$/, '')}. Try again.`;
  }
  return "Couldn't move this customer. Check your connection and try again.";
}

type Directs = { status: 'loading' } | { status: 'error' } | { status: 'ready'; rows: DirectCustomer[] };

export interface PartnerMoveCustomerModalProps {
  mode: 'move' | 'add';
  /** Move: the partner the customer is with now. Add: the partner the organization is added to. */
  partner: PartnerSummary;
  /** Move mode only. */
  customer?: PartnerCustomerRow;
  /** Every partner, to offer as a target in move mode. */
  partners: PartnerSummary[];
  onClose: () => void;
  /** Called once the server accepted the move, so the screen can refetch. */
  onMoved: () => void;
}

export const PartnerMoveCustomerModal: React.FC<PartnerMoveCustomerModalProps> = ({
  mode, partner, customer, partners, onClose, onMoved,
}) => {
  const uid = useId();
  const add = mode === 'add';
  const [target, setTarget] = useState('');
  const [orgId, setOrgId] = useState('');
  const [filter, setFilter] = useState('');
  const [directs, setDirects] = useState<Directs>({ status: 'loading' });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!add) return;
    let live = true;
    fetchDirectCustomers()
      .then(rows => { if (live) setDirects({ status: 'ready', rows }); })
      .catch(() => { if (live) setDirects({ status: 'error' }); });
    return () => { live = false; };
  }, [add]);

  const targets = partners.filter(p => p.id !== partner.id && p.status === 'active');
  const rows = directs.status === 'ready' ? directs.rows : [];
  const chosenOrg = rows.find(r => r.id === orgId);

  const name = add ? chosenOrg?.name : customer?.name;
  const assigned = add ? chosenOrg?.seatsAssigned : customer?.seatsAssigned;
  const toDirect = !add && target === DIRECT;
  const toPartner = add ? partner : targets.find(p => p.id === target);
  const chosen = add ? !!chosenOrg : target !== '' && (toDirect || !!toPartner);
  const fits = !chosen || toDirect || !toPartner || assigned === undefined || assigned <= toPartner.free;

  let consequence: string | null = null;
  if (chosen && fits && name !== undefined && assigned !== undefined) {
    if (toDirect) {
      consequence = `${name} becomes a direct customer and keeps its ${assigned} seats as its own licence. The seats return to ${partner.name}'s pool.`;
    } else if (toPartner) {
      consequence = add
        ? `${name} keeps its ${assigned} seats. They are taken from ${toPartner.name}'s pool (${toPartner.free} free).`
        : `${name} keeps its ${assigned} seats. They are taken from ${toPartner.name}'s pool (${toPartner.free} free) and returned to ${partner.name}'s pool.`;
    }
  }
  const noFit =
    chosen && !fits && toPartner && name !== undefined && assigned !== undefined
      ? `${toPartner.name} has ${toPartner.free} seats free and ${name} needs ${assigned}. Increase ${toPartner.name}'s pool first.`
      : null;

  const subject = add ? chosenOrg : customer;
  const canSubmit = !pending && chosen && fits && !!subject;

  const submit = async () => {
    if (!canSubmit || !subject) return;
    setPending(true);
    setError(null);
    try {
      await moveCustomer(subject.id, toDirect ? null : (toPartner as PartnerSummary).id);
      showToast(toDirect ? `${subject.name} is now a direct customer.` : `${subject.name} moved to ${(toPartner as PartnerSummary).name}.`, 'success');
      onMoved();
      onClose();
    } catch (e) {
      setError(failureText(e));
      setPending(false);
    }
  };

  const title = add ? `Add an organization to ${partner.name}` : `Move ${customer?.name ?? ''}`;
  const visibleRows = filter.trim() ? rows.filter(r => r.name.toLowerCase().includes(filter.trim().toLowerCase())) : rows;

  return (
    <Modal
      isOpen
      onClose={onClose}
      size="lg"
      title={<span className="block whitespace-normal break-words">{title}</span>}
      closeOnBackdrop={false}
      closeOnEsc={!pending}
      showClose={!pending}
      footer={
        <>
          <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>Cancel</button>
          <button type="button" className={PRIMARY_BUTTON} onClick={submit} disabled={!canSubmit}>
            {pending ? 'Moving...' : 'Move customer'}
          </button>
        </>
      }
    >
      <div className="space-y-4" aria-busy={pending}>
        {!add && customer && (
          <div className="space-y-1 rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-900 dark:border-white/10 dark:bg-white/[0.04] dark:text-white">
            <p className="font-semibold break-words">{`Currently with ${partner.name}`}</p>
            <p className="tabular-nums">{`${customer.seatsAssigned} seats assigned, ${customer.seatsUsed} in use`}</p>
          </div>
        )}

        {!add && (
          <div className="space-y-1">
            <label htmlFor={`${uid}-target`} className={LABEL}>Move to</label>
            <select id={`${uid}-target`} className={INPUT} value={target} disabled={pending} onChange={e => setTarget(e.target.value)}>
              <option value="">Choose where to move it</option>
              {targets.map(p => <option key={p.id} value={p.id}>{`${p.name} (${p.free} free)`}</option>)}
              <option value={DIRECT}>No partner (direct customer)</option>
            </select>
          </div>
        )}

        {add && directs.status === 'loading' && <div className="h-4 w-1/2 animate-pulse rounded bg-gray-200 dark:bg-white/10" />}
        {add && directs.status === 'error' && (
          <div role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
            <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p>Couldn't load the organizations. Check your connection and try again.</p>
          </div>
        )}
        {add && directs.status === 'ready' && rows.length === 0 && (
          <p className="text-xs text-gray-500 dark:text-gray-400">Every organization already has a partner.</p>
        )}
        {add && directs.status === 'ready' && rows.length > 0 && (
          <div className="space-y-2">
            {rows.length >= FILTER_FROM && (
              <div className="space-y-1">
                <label htmlFor={`${uid}-filter`} className={LABEL}>Filter organizations</label>
                <input id={`${uid}-filter`} type="search" className={INPUT} value={filter} disabled={pending} onChange={e => setFilter(e.target.value)} />
              </div>
            )}
            <div className="space-y-1">
              <label htmlFor={`${uid}-org`} className={LABEL}>Organization</label>
              <select id={`${uid}-org`} className={INPUT} value={orgId} disabled={pending} onChange={e => setOrgId(e.target.value)}>
                <option value="">Choose an organization</option>
                {visibleRows.map(r => <option key={r.id} value={r.id}>{`${r.name} (${seats(r.seatsAssigned)})`}</option>)}
              </select>
            </div>
          </div>
        )}

        {add && chosenOrg && (
          <div className="space-y-1 rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-900 dark:border-white/10 dark:bg-white/[0.04] dark:text-white">
            <p className="font-semibold break-words">{`${chosenOrg.name} is a direct customer`}</p>
            <p className="tabular-nums">{`${seats(chosenOrg.seatsAssigned)} assigned`}</p>
          </div>
        )}

        {consequence && <p className="text-sm text-gray-700 dark:text-gray-300 break-words">{consequence}</p>}
        {noFit && <p role="alert" className="text-sm text-red-600 dark:text-red-400 break-words">{noFit}</p>}

        <div role="status" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
          <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
          <p>This is recorded in the audit log with your name. Screens the customer already has stay on, even if this partner may not sell them.</p>
        </div>

        {error && (
          <div role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
            <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p className="break-words">{error}</p>
          </div>
        )}
      </div>
    </Modal>
  );
};

export default PartnerMoveCustomerModal;
