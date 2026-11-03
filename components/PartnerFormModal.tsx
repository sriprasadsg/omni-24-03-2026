import React, { useId, useState } from 'react';
import featureSwitches from '../shared/tenant-feature-switches.json';
import {
  appointPartner,
  updatePartner,
  PartnerApiError,
  type PartnerSummary,
  type UpdatePartnerInput,
} from '../services/partnerApi';
import { showToast } from '../utils/toast';
import { AlertTriangleIcon, CheckCircleIcon } from './icons';
import Modal from './Modal';
import { PartnerScreenPicker } from './PartnerScreenPicker';

/**
 * Phase 87 (PART-01, PART-03; 87-UI-SPEC section 1, Appoint / Edit partner modal): one form, two titles.
 * Appoint also takes the first partner administrator, who is emailed an invite (D-17). Edit sends only the
 * fields that changed, shows the handed-out floor (D-07) and displays the server's refusal verbatim. The
 * floor and the other limits here are advisory; the server enforces them.
 */

const MAX_POOL = 1_000_000;
const MAX_NAME = 100;
const ALWAYS_INCLUDED = 'screen:dashboard';
const ALL_SCREENS = 'all';
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const SWITCHES: string[] = (featureSwitches.groups as { features: { permission: string }[] }[])
  .flatMap(g => g.features.map(f => f.permission))
  .filter(p => p !== ALWAYS_INCLUDED);

const INPUT =
  'w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 min-h-10 text-sm text-gray-900 dark:text-white disabled:opacity-60';
const LABEL = 'block text-sm font-semibold text-gray-900 dark:text-white';
const HELPER = 'text-xs text-gray-500 dark:text-gray-400';
const FIELD_ERROR = 'text-xs text-red-600 dark:text-red-400';
const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';
const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';

/** `YYYY-MM-DD` of a stored instant, read straight from the string so no timezone shifts the day. */
const dayOf = (iso: string | null | undefined): string => (iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(0, 10) : '');

const ticked = (list: string[]): string[] => list.filter(s => s !== ALWAYS_INCLUDED && s !== ALL_SCREENS);
const initialCeiling = (p?: PartnerSummary): string[] => {
  if (!p) return [];
  const list = p.screenCeiling ?? [];
  return p.unrestricted || list.includes(ALL_SCREENS) ? [...SWITCHES] : ticked(list);
};
const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every(x => b.includes(x));

export interface PartnerFormModalProps {
  mode: 'appoint' | 'edit';
  partner?: PartnerSummary;
  onClose: () => void;
  /** Called once the server accepted the change, so the table can refetch. The modal closes itself separately. */
  onSaved: () => void;
}

export const PartnerFormModal: React.FC<PartnerFormModalProps> = ({ mode, partner, onClose, onSaved }) => {
  const uid = useId();
  const edit = mode === 'edit' && !!partner;
  const handedOut = partner && Number.isFinite(partner.allocated) ? partner.allocated : 0;

  const [name, setName] = useState(edit ? partner!.name : '');
  const [pool, setPool] = useState(edit ? String(partner!.poolSize) : '');
  const [expiresOn, setExpiresOn] = useState(edit ? dayOf(partner!.expiresAt) : '');
  const [ceiling, setCeiling] = useState<string[]>(() => initialCeiling(edit ? partner : undefined));
  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [appointed, setAppointed] = useState<{ name: string; email: string } | null>(null);

  const touch = (field: string) => setTouched(prev => ({ ...prev, [field]: true }));

  const trimmedName = name.trim();
  const poolNumber = /^\d+$/.test(pool.trim()) ? Number(pool.trim()) : NaN;
  const errors: Record<string, string | null> = {
    name: trimmedName.length >= 1 && trimmedName.length <= MAX_NAME ? null : 'Enter a partner name.',
    pool:
      !Number.isInteger(poolNumber) || poolNumber < 1 || poolNumber > MAX_POOL
        ? 'Enter a pool between 1 and 1,000,000 seats.'
        : edit && poolNumber < handedOut
          ? `The pool can't be smaller than the ${handedOut} seats already handed out. Ask the partner to take seats back first.`
          : null,
    adminName: edit || adminName.trim() ? null : 'Enter a name for the administrator.',
    adminEmail: edit || EMAIL.test(adminEmail.trim()) ? null : 'Enter a valid email address.',
  };
  const valid = Object.values(errors).every(e => e === null);

  const selected = ticked(ceiling);
  const original = edit ? initialCeiling(partner) : [];
  const everything = SWITCHES.every(s => selected.includes(s));
  const ceilingChanged = !sameSet(selected, original);
  const changes: UpdatePartnerInput = {};
  if (edit) {
    if (trimmedName !== partner!.name) changes.name = trimmedName;
    if (poolNumber !== partner!.poolSize) changes.poolSize = poolNumber;
    if (expiresOn !== dayOf(partner!.expiresAt)) changes.expiresAt = expiresOn ? `${expiresOn}T23:59:59Z` : null;
    if (ceilingChanged) changes.screenCeiling = everything ? [ALL_SCREENS] : selected;
  }
  const dirty = Object.keys(changes).length > 0;

  const failure = (e: unknown, action: string): string => {
    if (e instanceof PartnerApiError) {
      // A 409 is a named refusal (pool below handed out, name or email not available): its text is the message.
      if (e.status === 409) return e.message;
      return `Couldn't ${action}: ${e.message.replace(/\.+$/, '')}. Try again.`;
    }
    return `Couldn't ${action}. Check your connection and try again.`;
  };

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (saving || !valid || (edit && !dirty)) return;
    setSaving(true);
    setError(null);
    try {
      if (edit) {
        await updatePartner(partner!.id, changes);
        showToast('Partner saved.', 'success');
        onSaved();
        onClose();
        return;
      }
      const email = adminEmail.trim();
      const result = await appointPartner({
        name: trimmedName,
        poolSize: poolNumber,
        ...(expiresOn ? { expiresAt: `${expiresOn}T23:59:59Z` } : {}),
        screenCeiling: everything ? [ALL_SCREENS] : selected,
        adminName: adminName.trim(),
        adminEmail: email,
      });
      onSaved();
      if (result.emailSent === false) {
        setAppointed({ name: trimmedName, email });
        setSaving(false);
        return;
      }
      showToast(`Partner appointed. An invite was sent to ${email}.`, 'success');
      onClose();
    } catch (e) {
      setError(failure(e, edit ? 'save this partner' : 'appoint this partner'));
      setSaving(false);
    }
  };

  const field = (key: string, label: string, helper: React.ReactNode, input: (props: Record<string, unknown>) => React.ReactNode) => {
    const id = `${uid}-${key}`;
    const shown = touched[key] ? errors[key] : null;
    const describedBy = [helper ? `${id}-help` : '', shown ? `${id}-err` : ''].filter(Boolean).join(' ') || undefined;
    return (
      <div className="space-y-1">
        <label htmlFor={id} className={LABEL}>{label}</label>
        {input({ id, 'aria-describedby': describedBy, 'aria-invalid': shown ? true : undefined, 'aria-required': true, disabled: saving, onBlur: () => touch(key) })}
        {helper && <div id={`${id}-help`} className={`${HELPER} break-words`}>{helper}</div>}
        {shown && <p id={`${id}-err`} role="alert" className={`${FIELD_ERROR} break-words`}>{shown}</p>}
      </div>
    );
  };

  if (appointed) {
    return (
      <Modal
        isOpen
        onClose={onClose}
        size="lg"
        title="Partner appointed"
        closeOnBackdrop={false}
        footer={<button type="button" className={PRIMARY_BUTTON} onClick={onClose}>Done</button>}
      >
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-700 dark:text-green-300">
            <CheckCircleIcon size={20} aria-hidden="true" />
            <p className="text-sm font-semibold break-words">{`${appointed.name} was appointed.`}</p>
          </div>
          <div role="status" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
            <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p className="break-words">
              {`The invite email couldn't be sent. Email is not configured on this platform. Set a password for ${appointed.email} in User Management, then share it with them directly.`}
            </p>
          </div>
        </div>
      </Modal>
    );
  }

  const title = edit ? `Edit ${partner!.name}` : 'Appoint a partner';
  const submitLabel = edit ? (saving ? 'Saving...' : 'Save partner') : saving ? 'Appointing...' : 'Appoint partner';

  return (
    <Modal
      isOpen
      onClose={onClose}
      size="lg"
      title={<span className="block whitespace-normal break-words">{title}</span>}
      closeOnBackdrop={false}
      closeOnEsc={!saving}
      showClose={!saving}
      footer={
        <>
          <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={saving}>Cancel</button>
          <button
            type="submit"
            form={`${uid}-form`}
            className={PRIMARY_BUTTON}
            disabled={saving || !valid || (edit && !dirty)}
          >
            {submitLabel}
          </button>
        </>
      }
    >
      <form id={`${uid}-form`} onSubmit={submit} noValidate className="space-y-6" aria-busy={saving}>
        {field('name', 'Partner name', 'The name staff and customers recognise.', props => (
          <input type="text" autoComplete="off" autoFocus={!edit} maxLength={MAX_NAME} className={INPUT} value={name}
                 onChange={e => setName(e.target.value)} {...props} />
        ))}
        {field(
          'pool',
          'Seat pool',
          <>
            <p>How many agent seats this partner can hand out in total.</p>
            {edit && (
              <p>{`${handedOut} ${handedOut === 1 ? 'seat is' : 'seats are'} handed out, so the pool can't go below ${handedOut}.`}</p>
            )}
          </>,
          props => (
            <input type="number" inputMode="numeric" min={edit ? handedOut : 1} max={MAX_POOL} step={1} className={INPUT}
                   value={pool} onChange={e => setPool(e.target.value)} {...props} />
          ),
        )}
        <div className="space-y-1">
          <label htmlFor={`${uid}-expires`} className={LABEL}>Pool expires on</label>
          <input id={`${uid}-expires`} type="date" className={INPUT} value={expiresOn} disabled={saving}
                 aria-describedby={`${uid}-expires-help`} onChange={e => setExpiresOn(e.target.value)} />
          <p id={`${uid}-expires-help`} className={`${HELPER} break-words`}>
            Leave empty for no expiry. After this date the partner can't create customers or hand out seats. Customers keep their seats: agents already enrolled keep working and new agents wait for approval.
          </p>
        </div>
        <fieldset className="space-y-2" disabled={saving}>
          <legend className={LABEL}>Screens this partner may sell</legend>
          <p className={`${HELPER} break-words`}>
            A partner can only switch these screens on for its customers. Screens a customer already has stay on if you remove them here.
          </p>
          <PartnerScreenPicker mode="ceiling" value={ceiling} onChange={setCeiling} disabled={saving} />
        </fieldset>
        {!edit && (
          <fieldset className="space-y-4">
            <legend className={LABEL}>First partner administrator</legend>
            <p className={`${HELPER} break-words`}>
              We email this person a link to set a password. The link works for 7 days. They then invite their own colleagues.
            </p>
            {field('adminName', 'Name', null, props => (
              <input type="text" autoComplete="off" className={INPUT} value={adminName}
                     onChange={e => setAdminName(e.target.value)} {...props} />
            ))}
            {field('adminEmail', 'Email address', null, props => (
              <input type="email" autoComplete="email" className={`${INPUT} break-all`} value={adminEmail}
                     onChange={e => setAdminEmail(e.target.value)} {...props} />
            ))}
          </fieldset>
        )}
        {error && (
          <div role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
            <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p className="break-words">{error}</p>
          </div>
        )}
      </form>
    </Modal>
  );
};

export default PartnerFormModal;
