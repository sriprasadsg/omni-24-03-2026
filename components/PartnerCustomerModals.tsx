import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  PartnerApiError,
  changeCustomerSeats,
  createPartnerCustomer,
  fetchCustomerFeatures,
  saveCustomerFeatures,
  type CustomerFeatures,
  type PartnerCustomerRow,
} from '../services/partnerApi';
import { showToast } from '../utils/toast';
import { AlertTriangleIcon, CheckCircleIcon, ChevronRightIcon } from './icons';
import Modal from './Modal';
import { PartnerScreenPicker } from './PartnerScreenPicker';

/**
 * Phase 87 (PART-02, PART-04, PART-06; 87-UI-SPEC section 2): the three modals a partner administrator uses
 * on a customer: Create customer (D-09), Change seats and Choose screens (D-10, D-19). Every floor, ceiling
 * and refusal is stated in the contract's words. The limits shown here are advisory: the server enforces
 * them, so a refusal (409 or 422) is shown verbatim and the portal refetches. The portal never shows an
 * invite link, a token or a registration key; the only customer facts used are the D-01 ones.
 */

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_NAME = 100;
const ALWAYS_INCLUDED = 'screen:dashboard';

const INPUT =
  'w-full min-h-10 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white disabled:opacity-60';
const LABEL = 'block text-sm font-semibold text-gray-900 dark:text-white';
const HELPER = 'text-xs text-gray-500 dark:text-gray-400';
const FIELD_ERROR = 'text-xs text-red-600 dark:text-red-400';
const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';
const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';

const seats = (n: number) => `${n} ${n === 1 ? 'seat' : 'seats'}`;
const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every(x => b.includes(x));
const titleOf = (text: string) => <span className="block whitespace-normal break-words">{text}</span>;

/**
 * A named refusal (409, 422) is shown as the server worded it; any other server message is wrapped as
 * `Couldn't {action}: {message}. Try again.`; with no server message the connection fallback is used.
 */
export function partnerFailureText(e: unknown, action: string): string {
  if (e instanceof PartnerApiError) {
    if (e.status === 409 || e.status === 422) return e.message;
    return `Couldn't ${action}: ${e.message.replace(/\.+$/, '')}. Try again.`;
  }
  return `Couldn't ${action}. Check your connection and try again.`;
}

export const ErrorBlock: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
    <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
    <p className="break-words">{children}</p>
  </div>
);

const AmberBlock: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div role="status" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
    <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
    <p className="break-words">{children}</p>
  </div>
);

interface ModalFooterProps {
  formId: string;
  pending: boolean;
  disabled: boolean;
  label: string;
  pendingLabel: string;
  onCancel: () => void;
}

const Footer: React.FC<ModalFooterProps> = ({ formId, pending, disabled, label, pendingLabel, onCancel }) => (
  <>
    <button type="button" className={SECONDARY_BUTTON} onClick={onCancel} disabled={pending}>Cancel</button>
    <button type="submit" form={formId} className={PRIMARY_BUTTON} disabled={pending || disabled}>
      {pending ? pendingLabel : label}
    </button>
  </>
);

// ---------------------------------------------------------------------------------------------------------
// Create customer
// ---------------------------------------------------------------------------------------------------------

export interface CreateCustomerModalProps {
  /** Seats the partner can still hand out; the seats field is bounded 1 to this. */
  free: number;
  ceiling: string[];
  unrestricted: boolean;
  onClose: () => void;
  /** Reload the overview: called after a success and after any answer from the server. */
  onRefetch: () => void;
}

export const CreateCustomerModal: React.FC<CreateCustomerModalProps> = ({ free, ceiling, unrestricted, onClose, onRefetch }) => {
  const uid = useId();
  const [name, setName] = useState('');
  const [seatText, setSeatText] = useState('');
  const [adminName, setAdminName] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [screens, setScreens] = useState<string[]>([]);
  const [showScreens, setShowScreens] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ name: string; seats: number; email: string } | null>(null);
  const busy = useRef(false);

  const seatNumber = /^\d+$/.test(seatText.trim()) ? Number(seatText.trim()) : NaN;
  const errors: Record<string, string | null> = {
    name: name.trim().length >= 1 && name.trim().length <= MAX_NAME ? null : 'Enter a customer name.',
    seats: Number.isInteger(seatNumber) && seatNumber >= 1 && seatNumber <= free
      ? null : `Enter a whole number of seats between 1 and ${free}.`,
    adminName: adminName.trim() ? null : 'Enter a name for the administrator.',
    adminEmail: EMAIL.test(adminEmail.trim()) ? null : 'Enter a valid email address.',
  };
  const valid = Object.values(errors).every(e => e === null);
  const chosen = screens.filter(s => s !== ALWAYS_INCLUDED);

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (busy.current || saving || !valid) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    const customerName = name.trim();
    const email = adminEmail.trim();
    try {
      const result = await createPartnerCustomer({
        name: customerName,
        seats: seatNumber,
        ...(chosen.length > 0 ? { enabledFeatures: chosen } : {}),
        adminName: adminName.trim(),
        adminEmail: email,
      });
      onRefetch();
      if (result.emailSent === false) {
        setCreated({ name: customerName, seats: seatNumber, email });
        return;
      }
      showToast(`${customerName} was created. An invite was sent to ${email}.`, 'success');
      onClose();
    } catch (e) {
      setError(partnerFailureText(e, 'create this customer'));
      if (e instanceof PartnerApiError) onRefetch();
    } finally {
      busy.current = false;
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
        {input({
          id, 'aria-describedby': describedBy, 'aria-invalid': shown ? true : undefined, 'aria-required': true,
          disabled: saving, onBlur: () => setTouched(prev => ({ ...prev, [key]: true })),
        })}
        {helper && <div id={`${id}-help`} className={`${HELPER} break-words`}>{helper}</div>}
        {shown && <p id={`${id}-err`} role="alert" className={`${FIELD_ERROR} break-words`}>{shown}</p>}
      </div>
    );
  };

  if (created) {
    return (
      <Modal isOpen onClose={onClose} size="lg" title="Customer created" closeOnBackdrop={false}
             footer={<button type="button" className={PRIMARY_BUTTON} onClick={onClose}>Done</button>}>
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-700 dark:text-green-300">
            <CheckCircleIcon size={20} aria-hidden="true" />
            <p className="text-sm font-semibold break-words">{`${created.name} was created with ${created.seats} seats.`}</p>
          </div>
          <AmberBlock>
            {`The invite email couldn't be sent. Ask your platform administrator to share sign-in details with ${created.email}.`}
          </AmberBlock>
        </div>
      </Modal>
    );
  }

  const formId = `${uid}-form`;
  const screensId = `${uid}-screens`;
  return (
    <Modal
      isOpen
      onClose={onClose}
      size="lg"
      title="Create a customer"
      closeOnBackdrop={false}
      closeOnEsc={!saving}
      showClose={!saving}
      footer={<Footer formId={formId} pending={saving} disabled={!valid} label="Create customer" pendingLabel="Creating..." onCancel={onClose} />}
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-6" aria-busy={saving}>
        <fieldset className="space-y-4">
          <legend className={LABEL}>Customer</legend>
          {field('name', 'Customer name', null, props => (
            <input type="text" autoComplete="off" autoFocus maxLength={MAX_NAME} className={INPUT} value={name}
                   onChange={e => setName(e.target.value)} {...props} />
          ))}
          {field('seats', 'Seats', `Taken from your pool. You have ${seats(free)} free.`, props => (
            <input type="number" inputMode="numeric" min={1} max={free} step={1} className={INPUT} value={seatText}
                   onChange={e => setSeatText(e.target.value)} {...props} />
          ))}
        </fieldset>
        <fieldset className="space-y-4">
          <legend className={LABEL}>First administrator</legend>
          <div className={`${HELPER} space-y-1 break-words`}>
            <p>We email this person a link to set a password. The link works for 7 days. They then run the organization.</p>
            <p>They get the same rights as the administrator of any organization on the platform.</p>
          </div>
          {field('adminName', 'Name', null, props => (
            <input type="text" autoComplete="off" className={INPUT} value={adminName} onChange={e => setAdminName(e.target.value)} {...props} />
          ))}
          {field('adminEmail', 'Email address', null, props => (
            <input type="email" autoComplete="email" className={`${INPUT} break-all`} value={adminEmail}
                   onChange={e => setAdminEmail(e.target.value)} {...props} />
          ))}
        </fieldset>
        <fieldset className="space-y-2" disabled={saving}>
          <legend className={LABEL}>Screens</legend>
          <button type="button" className={SECONDARY_BUTTON} aria-expanded={showScreens} aria-controls={screensId}
                  onClick={() => setShowScreens(open => !open)}>
            <ChevronRightIcon size={16} aria-hidden="true" className={showScreens ? 'rotate-90' : ''} />
            Choose screens
          </button>
          {!showScreens && (
            <p className={HELPER}>
              {chosen.length === 0 ? 'Dashboard only. You can add more later.' : `${chosen.length} ${chosen.length === 1 ? 'screen' : 'screens'} selected`}
            </p>
          )}
          {showScreens && (
            <div id={screensId}>
              <PartnerScreenPicker mode="customer" ceiling={ceiling} unrestricted={unrestricted} value={screens} onChange={setScreens} disabled={saving} />
            </div>
          )}
        </fieldset>
        {error && <ErrorBlock>{error}</ErrorBlock>}
      </form>
    </Modal>
  );
};

// ---------------------------------------------------------------------------------------------------------
// Change seats
// ---------------------------------------------------------------------------------------------------------

export interface ChangeSeatsModalProps {
  customer: PartnerCustomerRow;
  /** Seats free in the partner's pool right now. */
  free: number;
  expired: boolean;
  onClose: () => void;
  onRefetch: () => void;
}

export const ChangeSeatsModal: React.FC<ChangeSeatsModalProps> = ({ customer, free, expired, onClose, onRefetch }) => {
  const uid = useId();
  const used = customer.seatsUsed;
  const assigned = customer.seatsAssigned;
  const max = assigned + Math.max(0, free);
  const [text, setText] = useState(String(assigned));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);

  const n = /^\d+$/.test(text.trim()) ? Number(text.trim()) : NaN;
  const changed = text !== String(assigned);
  const problem = !Number.isInteger(n)
    ? 'Enter a whole number of seats.'
    : n < used
      ? `${customer.name} uses ${seats(used)} now. You can't set fewer.`
      : n > max
        ? `Your pool has ${seats(free)} free, so the most you can set is ${max}.`
        : null;
  const delta = Number.isInteger(n) ? n - assigned : 0;
  const liveLine = delta > 0 ? `Takes ${delta} more ${delta === 1 ? 'seat' : 'seats'} from your pool.`
    : delta < 0 ? `Returns ${-delta} ${-delta === 1 ? 'seat' : 'seats'} to your pool.` : 'No change.';
  const canSave = !expired && !problem && delta !== 0;

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (busy.current || saving || !canSave) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    try {
      await changeCustomerSeats(customer.id, n);
      showToast(`Seats saved. ${customer.name} now has ${seats(n)}.`, 'success');
      onRefetch();
      onClose();
    } catch (e) {
      setError(partnerFailureText(e, 'save seats'));
      if (e instanceof PartnerApiError) onRefetch();
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };

  const formId = `${uid}-form`;
  const shownProblem = changed && problem;
  return (
    <Modal
      isOpen
      onClose={onClose}
      size="sm"
      title={titleOf(`Change seats for ${customer.name}`)}
      closeOnBackdrop={!saving}
      closeOnEsc={!saving}
      showClose={!saving}
      footer={<Footer formId={formId} pending={saving} disabled={!canSave} label="Save seats" pendingLabel="Saving..." onCancel={onClose} />}
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4" aria-busy={saving}>
        <div className="space-y-1 text-sm text-gray-900 dark:text-white">
          <p className="tabular-nums">{`${seats(used)} in use`}</p>
          <p className="tabular-nums">{`${free} free in your pool`}</p>
          <p className="tabular-nums">{`${assigned} assigned now`}</p>
        </div>
        {expired && <AmberBlock>Your seat pool has expired, so seats can't be changed.</AmberBlock>}
        <div className="space-y-1">
          <label htmlFor={`${uid}-seats`} className={LABEL}>Seats</label>
          <input id={`${uid}-seats`} type="number" inputMode="numeric" min={used} max={max} step={1} className={INPUT}
                 value={text} disabled={saving || expired} aria-required aria-invalid={shownProblem ? true : undefined}
                 aria-describedby={`${uid}-help ${uid}-live${shownProblem ? ` ${uid}-err` : ''}`}
                 onChange={e => setText(e.target.value)} />
          <p id={`${uid}-help`} className={`${HELPER} break-words`}>
            {`You can set between ${used} and ${max} seats. ${used} ${used === 1 ? 'seat is' : 'seats are'} in use, so this customer can't go below that. Running agents are never cut off.`}
          </p>
          {!shownProblem && <p id={`${uid}-live`} className={`${HELPER} break-words`}>{liveLine}</p>}
          {shownProblem && <p id={`${uid}-err`} role="alert" className={`${FIELD_ERROR} break-words`}>{problem}</p>}
        </div>
        {error && <ErrorBlock>{error}</ErrorBlock>}
      </form>
    </Modal>
  );
};

// ---------------------------------------------------------------------------------------------------------
// Choose screens
// ---------------------------------------------------------------------------------------------------------

export interface ChooseScreensModalProps {
  customer: PartnerCustomerRow;
  onClose: () => void;
  onRefetch: () => void;
}

export const ChooseScreensModal: React.FC<ChooseScreensModalProps> = ({ customer, onClose, onRefetch }) => {
  const uid = useId();
  const [features, setFeatures] = useState<CustomerFeatures | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [value, setValue] = useState<string[]>([]);
  const [original, setOriginal] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const busy = useRef(false);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  /** Load what the customer has and the partner's ceiling; a quiet reload keeps the picker on screen. */
  const load = useCallback(async (quiet: boolean) => {
    if (!quiet) { setFeatures(null); setLoadError(false); }
    try {
      const next = await fetchCustomerFeatures(customer.id);
      if (!alive.current) return;
      setFeatures(next);
      setValue(next.enabledFeatures ?? []);
      setOriginal(next.enabledFeatures ?? []);
      setLoadError(false);
    } catch {
      if (alive.current && !quiet) setLoadError(true);
    }
  }, [customer.id]);

  useEffect(() => { void load(false); }, [load]);

  const ceiling = features?.ceiling ?? [];
  const nothingToSell = !!features && !features.unrestricted && !ceiling.includes('all')
    && ceiling.filter(s => s !== ALWAYS_INCLUDED).length === 0;
  const dirty = !sameSet(value, original);

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (busy.current || saving || !features || !dirty || nothingToSell) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    try {
      await saveCustomerFeatures(customer.id, value);
      showToast(`Screens saved for ${customer.name}.`, 'success');
      onRefetch();
      onClose();
    } catch (e) {
      setError(partnerFailureText(e, 'save screens'));
      if (e instanceof PartnerApiError) {
        onRefetch();
        await load(true);
      }
    } finally {
      busy.current = false;
      if (alive.current) setSaving(false);
    }
  };

  const formId = `${uid}-form`;
  return (
    <Modal
      isOpen
      onClose={onClose}
      size="lg"
      title={titleOf(`Screens for ${customer.name}`)}
      closeOnBackdrop={!saving}
      closeOnEsc={!saving}
      showClose={!saving}
      footer={<Footer formId={formId} pending={saving} disabled={!features || !dirty || nothingToSell} label="Save screens" pendingLabel="Saving..." onCancel={onClose} />}
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4" aria-busy={saving || (!features && !loadError)}>
        {!features && !loadError && (
          <div className="space-y-2" aria-hidden="true">
            {[0, 1, 2, 3, 4].map(i => (
              <div key={i} data-skeleton className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-white/10" />
            ))}
          </div>
        )}
        {loadError && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
            <AlertTriangleIcon size={16} aria-hidden="true" />
            <span>Couldn't load the screens. Check your connection and try again.</span>
            <button type="button" className={SECONDARY_BUTTON} onClick={() => { void load(false); }}>Try again</button>
          </div>
        )}
        {features && (
          <PartnerScreenPicker mode="customer" ceiling={ceiling} unrestricted={features.unrestricted} kept={features.kept}
                               value={value} onChange={setValue} disabled={saving} />
        )}
        {error && <ErrorBlock>{error}</ErrorBlock>}
      </form>
    </Modal>
  );
};
