import React, { useState } from 'react';
import { PartnerApiError, reinstatePartner, suspendPartner, type PartnerSummary } from '../services/partnerApi';
import { showToast } from '../utils/toast';
import { AlertTriangleIcon } from './icons';
import Modal from './Modal';

/**
 * Phase 87 (PART-01, D-15; 87-UI-SPEC section 1): the Suspend and Reinstate confirmations. Suspend is the one
 * red button on the screen because it signs every partner user out; Reinstate is accent. Both are recorded in
 * the audit log by the server. While the request is in flight both buttons are disabled and Esc is ignored,
 * so one click sends one request.
 */

const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';
const DANGER_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';

/** `Couldn't {action}: {server message}. Try again.`, or the connection fallback when there is no server message. */
function failureText(e: unknown, action: string): string {
  if (e instanceof PartnerApiError) return `Couldn't ${action}: ${e.message.replace(/\.+$/, '')}. Try again.`;
  return `Couldn't ${action}. Check your connection and try again.`;
}

export interface PartnerStatusDialogProps {
  partner: PartnerSummary;
  onClose: () => void;
  /** Called once the server accepted the change, so the table can refetch. */
  onDone: () => void;
}

interface DialogConfig {
  title: string;
  body: string;
  audit: boolean;
  confirm: string;
  pending: string;
  action: string;
  buttonClass: string;
  toast: string;
  run: () => Promise<unknown>;
}

const StatusDialog: React.FC<{ config: DialogConfig } & PartnerStatusDialogProps> = ({ config, onClose, onDone }) => {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await config.run();
      showToast(config.toast, 'success');
      onDone();
      onClose();
    } catch (e) {
      setError(failureText(e, config.action));
      setPending(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      size="md"
      title={<span className="block whitespace-normal break-words">{config.title}</span>}
      showClose={false}
      closeOnBackdrop={false}
      closeOnEsc={!pending}
      footer={
        <>
          <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={pending}>Cancel</button>
          <button type="button" className={config.buttonClass} onClick={confirm} disabled={pending}>
            {pending ? config.pending : config.confirm}
          </button>
        </>
      }
    >
      <div className="space-y-4" aria-busy={pending}>
        <p className="text-sm text-gray-700 dark:text-gray-300 break-words">{config.body}</p>
        {config.audit && (
          <div role="status" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
            <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p>This is recorded in the audit log with your name.</p>
          </div>
        )}
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

export const SuspendPartnerDialog: React.FC<PartnerStatusDialogProps> = ({ partner, onClose, onDone }) => (
  <StatusDialog
    onClose={onClose}
    onDone={onDone}
    partner={partner}
    config={{
      title: `Suspend ${partner.name}?`,
      body: "Everyone at this partner is signed out now and can't sign in until you reinstate it. Its customers are not affected: they keep their seats and keep running.",
      audit: true,
      confirm: 'Suspend partner',
      pending: 'Suspending...',
      action: 'suspend this partner',
      buttonClass: DANGER_BUTTON,
      toast: `${partner.name} is suspended.`,
      run: () => suspendPartner(partner.id),
    }}
  />
);

export const ReinstatePartnerDialog: React.FC<PartnerStatusDialogProps> = ({ partner, onClose, onDone }) => (
  <StatusDialog
    onClose={onClose}
    onDone={onDone}
    partner={partner}
    config={{
      title: `Reinstate ${partner.name}?`,
      body: 'Its staff can sign in again. Seats, customers and the pool are unchanged.',
      audit: false,
      confirm: 'Reinstate partner',
      pending: 'Reinstating...',
      action: 'reinstate this partner',
      buttonClass: PRIMARY_BUTTON,
      toast: `${partner.name} is reinstated.`,
      run: () => reinstatePartner(partner.id),
    }}
  />
);
