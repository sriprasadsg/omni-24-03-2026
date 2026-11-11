import React, { useEffect, useId, useRef, useState } from 'react';
import {
  PLAN_KEYS,
  PartnerApiError,
  changeCustomerPlan,
  extendCustomerTrial,
  type PartnerCustomerRow,
} from '../services/partnerApi';
import { showToast } from '../utils/toast';
import Modal from './Modal';
import { ErrorBlock, partnerFailureText } from './PartnerCustomerModals';
import { daysUntil, formatDay } from './PartnerStatusChip';

/**
 * Phase 88 (LIC-02, LIC-03; D-13, D-15, D-22; 88-UI-SPEC S10): a partner administrator moves one customer to
 * another plan among the plans the Super Admin lets this partner sell, and extends a Free trial by whole days.
 * The ceiling, ownership, the viewer refusal and the trial rules are enforced by the server (88-03, 88-10);
 * this modal only shows them and words the refusals. Seats are never touched here: a plan change keeps them.
 */

const MAX_DAYS = 365;
const DEFAULT_DAYS = '7';
const BAD_DAYS = 'Enter a whole number of days from 1 to 365.';

const INPUT =
  'w-full min-h-10 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white disabled:opacity-60';
const LABEL = 'block text-sm font-semibold text-gray-900 dark:text-white';
const HELPER = 'text-xs text-gray-500 dark:text-gray-400 break-words';
const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';
const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';

export interface PartnerPlanModalProps {
  /** The live row, so a refetch after a refusal updates the current plan and trial shown here. */
  customer: PartnerCustomerRow;
  /** The plans this partner may set (the overview's planCeiling). */
  planCeiling: string[];
  onClose: () => void;
  /** Reload the overview: called after a success and after any answer from the server. */
  onRefetch: () => void;
}

/** The trial line: an open trial with its days left, an ended one, or nothing running. */
function trialStatus(iso: string | null | undefined): string {
  const day = formatDay(iso);
  if (!iso || !day) return 'No free trial is running.';
  const left = daysUntil(iso);
  return left !== null && left > 0 ? `Trial ends ${day}: ${left} ${left === 1 ? 'day' : 'days'} left` : `Trial ended ${day}`;
}

export const PartnerPlanModal: React.FC<PartnerPlanModalProps> = ({ customer, planCeiling, onClose, onRefetch }) => {
  const uid = useId();
  const current = customer.plan ?? '';
  const [selected, setSelected] = useState(current);
  const [daysText, setDaysText] = useState(DEFAULT_DAYS);
  const [busy, setBusy] = useState<'save' | 'extend' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const lock = useRef(false);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  // After a refetch moved the customer to another plan, the select follows it; a message already shown stays.
  useEffect(() => { setSelected(current); }, [current]);

  // The current plan is always listed, even outside the ceiling (the Super Admin can have set it).
  const options = [...(current ? [current] : []), ...PLAN_KEYS.filter(k => planCeiling.includes(k) && k !== current)];
  const days = /^\d+$/.test(daysText.trim()) ? Number(daysText.trim()) : NaN;
  const daysOk = Number.isInteger(days) && days >= 1 && days <= MAX_DAYS;
  const canSave = !busy && !!selected && selected !== current;

  const failure = (e: unknown, action: string): string => {
    if (e instanceof PartnerApiError) {
      if (e.code === 'plan_outside_ceiling') return `${selected} is not one of the plans you can sell.`;
      if (e.code === 'plan_changed') return "This customer's plan changed while you were saving. Check the plan and try again.";
      if (e.code === 'invalid_days') return BAD_DAYS;
    }
    return partnerFailureText(e, action);
  };

  /** One request at a time; any answer from the server (a refusal too) refreshes the portal's rows. */
  const run = async (kind: 'save' | 'extend', work: () => Promise<boolean>, action: string) => {
    if (lock.current || busy) return;
    lock.current = true;
    setBusy(kind);
    setError(null);
    try {
      if (await work()) return;
    } catch (e) {
      setError(failure(e, action));
      if (e instanceof PartnerApiError) onRefetch();
    } finally {
      lock.current = false;
      if (alive.current) setBusy(null);
    }
  };

  const save = (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!canSave) return;
    void run('save', async () => {
      await changeCustomerPlan(customer.id, selected);
      showToast(`${customer.name} is now on the ${selected} plan.`, 'success');
      onRefetch();
      onClose();
      return true;
    }, 'save the plan');
  };

  const extend = () => {
    if (!daysOk) return;
    void run('extend', async () => {
      const row = await extendCustomerTrial(customer.id, days);
      const end = formatDay(row?.trialEndsAt);
      showToast(end ? `Trial extended. ${customer.name}'s trial now ends ${end}.` : `Trial extended for ${customer.name}.`, 'success');
      onRefetch();
      return false;
    }, 'extend the trial');
  };

  const formId = `${uid}-form`;
  return (
    <Modal
      isOpen
      onClose={onClose}
      size="md"
      title={<span className="block whitespace-normal break-words">{`Plan for ${customer.name}`}</span>}
      closeOnBackdrop={!busy}
      closeOnEsc={!busy}
      showClose={!busy}
      footer={
        <>
          <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={!!busy}>Cancel</button>
          <button type="submit" form={formId} className={PRIMARY_BUTTON} disabled={!canSave}>
            {busy === 'save' ? 'Saving...' : 'Save plan'}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={save} noValidate className="space-y-4" aria-busy={!!busy}>
        <div className="space-y-1">
          <label htmlFor={`${uid}-plan`} className={LABEL}>Plan</label>
          <select id={`${uid}-plan`} className={INPUT} value={selected} disabled={!!busy} aria-describedby={`${uid}-plan-help`}
                  onChange={e => setSelected(e.target.value)}>
            {!current && <option value="" disabled>Choose a plan</option>}
            {options.map(key => <option key={key} value={key}>{key === current ? `${key} (current)` : key}</option>)}
          </select>
          <p id={`${uid}-plan-help`} className={HELPER}>
            Seats stay as you assigned them. Screens the customer already has stay on; the plan limits which screens you can add from now on. A customer gets one free trial: moving back to Free after a paid plan gives no new trial.
          </p>
          {planCeiling.length === 0 && (
            <p className={HELPER}>Your platform administrator hasn't chosen any plans you can sell.</p>
          )}
        </div>
        {current === 'Free' ? (
          <fieldset className="space-y-2" disabled={!!busy}>
            <legend className={LABEL}>Free trial</legend>
            <p className="text-sm text-gray-900 dark:text-white break-words">{trialStatus(customer.trialEndsAt)}</p>
            <div className="space-y-1">
              <label htmlFor={`${uid}-days`} className={LABEL}>Extend trial by (days)</label>
              <input id={`${uid}-days`} type="number" inputMode="numeric" min={1} max={MAX_DAYS} step={1} className={INPUT}
                     value={daysText} aria-invalid={daysOk ? undefined : true} aria-describedby={daysOk ? undefined : `${uid}-days-err`}
                     onChange={e => setDaysText(e.target.value)}
                     onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); extend(); } }} />
              {!daysOk && <p id={`${uid}-days-err`} role="alert" className="text-xs text-red-600 dark:text-red-400 break-words">{BAD_DAYS}</p>}
            </div>
            <button type="button" className={SECONDARY_BUTTON} disabled={!!busy || !daysOk} onClick={extend}>
              {busy === 'extend' ? 'Extending...' : 'Extend trial'}
            </button>
          </fieldset>
        ) : (
          <p className={HELPER}>Only a Free trial can be extended.</p>
        )}
        {error && <ErrorBlock>{error}</ErrorBlock>}
      </form>
    </Modal>
  );
};

export default PartnerPlanModal;
