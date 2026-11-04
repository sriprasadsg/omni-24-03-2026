import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  PartnerApiError,
  fetchPartnerTeam,
  inviteColleague,
  resendColleagueInvite,
  type PartnerStaffRole,
  type PartnerTeamMember,
} from '../services/partnerApi';
import { partnerRoleLabel } from '../utils/permissions';
import { showToast } from '../utils/toast';
import { AlertTriangleIcon, MailIcon } from './icons';
import Modal from './Modal';
import { StaffStatusChip } from './PartnerStatusChip';

/**
 * Phase 87 (PART-02, D-17; 87-UI-SPEC section 2, Team section): a partner administrator's view of the team and
 * the Invite colleague dialog. The panel owns its own load, so the portal mounts it for the administrator only
 * and a viewer never asks for the team at all. Every server string is rendered as React text; the invite link
 * and token are never shown (the server does not send them and this screen has no place for them).
 */

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
const ROW_BUTTON =
  'inline-flex items-center gap-1 min-h-8 px-2 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2 ' +
  'disabled:opacity-60 disabled:no-underline';
const MUTED = 'text-xs text-gray-500 dark:text-gray-400';
const TH = 'px-6 py-4 text-left text-xs font-normal text-gray-500 dark:text-gray-400';
const TD = 'px-6 py-4 align-top text-sm text-gray-900 dark:text-white';

const ROLE_HELPER: Record<PartnerStaffRole, string> = {
  partner_admin: 'Can create customers, change seats and invite colleagues. Must set up two-step verification.',
  partner_viewer: "Can look at the pool, customers and usage. Can't change anything.",
};

/** Named refusals (409, 422) are shown as the server worded them; anything else gets the generic sentence. */
function inviteFailure(e: unknown): string {
  if (e instanceof PartnerApiError) {
    if (e.status === 409 || e.status === 422) return e.message;
    return `Couldn't send this invite: ${e.message.replace(/\.+$/, '')}. Try again.`;
  }
  return "Couldn't send this invite. Check your connection and try again.";
}

/** Wide screens get the table, narrower ones stacked cards. Wide when it cannot be asked. */
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

const pending = (m: PartnerTeamMember) => m.status === 'invited' || m.status === 'invite_expired';

export interface InviteColleagueModalProps {
  onClose: () => void;
  /** Reload the team: called after the server accepted the invite (even when the email could not be sent). */
  onInvited: () => void;
}

export const InviteColleagueModal: React.FC<InviteColleagueModalProps> = ({ onClose, onInvited }) => {
  const uid = useId();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<PartnerStaffRole>('partner_admin');
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notSent, setNotSent] = useState(false);
  const busy = useRef(false);

  const errors: Record<string, string | null> = {
    name: name.trim() ? null : 'Enter a name for your colleague.',
    email: EMAIL.test(email.trim()) ? null : 'Enter a valid email address.',
  };
  const valid = Object.values(errors).every(e => e === null);

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (busy.current || saving || !valid || notSent) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    const address = email.trim();
    try {
      const result = await inviteColleague({ name: name.trim(), email: address, role });
      onInvited();
      if (result.emailSent === false) {
        setNotSent(true);
        return;
      }
      showToast(`Invite sent to ${address}. The link works for 7 days.`, 'success');
      onClose();
    } catch (e) {
      setError(inviteFailure(e));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };

  const field = (key: 'name' | 'email', label: string, input: (props: Record<string, unknown>) => React.ReactNode) => {
    const id = `${uid}-${key}`;
    const shown = touched[key] ? errors[key] : null;
    return (
      <div className="space-y-1">
        <label htmlFor={id} className={LABEL}>{label}</label>
        {input({
          id, 'aria-describedby': shown ? `${id}-err` : undefined, 'aria-invalid': shown ? true : undefined, 'aria-required': true,
          disabled: saving, onBlur: () => setTouched(prev => ({ ...prev, [key]: true })),
        })}
        {shown && <p id={`${id}-err`} role="alert" className={`${FIELD_ERROR} break-words`}>{shown}</p>}
      </div>
    );
  };

  const formId = `${uid}-form`;
  return (
    <Modal
      isOpen
      onClose={onClose}
      size="md"
      title="Invite a colleague"
      closeOnBackdrop={false}
      closeOnEsc={!saving}
      showClose={!saving}
      footer={
        notSent ? (
          <button type="button" className={PRIMARY_BUTTON} onClick={onClose}>Done</button>
        ) : (
          <>
            <button type="button" className={SECONDARY_BUTTON} onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" form={formId} className={PRIMARY_BUTTON} disabled={saving || !valid}>
              {saving ? 'Sending...' : 'Send invite'}
            </button>
          </>
        )
      }
    >
      {notSent ? (
        <div role="status" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200">
          <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
          <p className="break-words">The invite email couldn't be sent. Ask your platform administrator for help.</p>
        </div>
      ) : (
        <form id={formId} onSubmit={submit} noValidate className="space-y-4" aria-busy={saving}>
          {field('name', 'Name', props => (
            <input type="text" autoComplete="off" autoFocus className={INPUT} value={name} onChange={e => setName(e.target.value)} {...props} />
          ))}
          {field('email', 'Email address', props => (
            <input type="email" autoComplete="email" className={`${INPUT} break-all`} value={email} onChange={e => setEmail(e.target.value)} {...props} />
          ))}
          <div className="space-y-1">
            <label htmlFor={`${uid}-role`} className={LABEL}>Role</label>
            <select id={`${uid}-role`} className={INPUT} value={role} disabled={saving} aria-describedby={`${uid}-role-help`}
                    onChange={e => setRole(e.target.value as PartnerStaffRole)}>
              <option value="partner_admin">{partnerRoleLabel('partner_admin')}</option>
              <option value="partner_viewer">{partnerRoleLabel('partner_viewer')}</option>
            </select>
            <p id={`${uid}-role-help`} className={`${HELPER} break-words`}>{ROLE_HELPER[role]}</p>
          </div>
          {error && (
            <div role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
              <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
              <p className="break-words">{error}</p>
            </div>
          )}
        </form>
      )}
    </Modal>
  );
};

export const PartnerTeamPanel: React.FC = () => {
  const uid = useId();
  const [members, setMembers] = useState<PartnerTeamMember[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [resending, setResending] = useState<string | null>(null);
  const alive = useRef(true);
  const wide = useWideLayout();

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  // Only the newest request applies, and a quiet reload that fails keeps what is on screen (87 WR-11).
  const loadSeq = useRef(0);
  const load = useCallback(async (showSkeleton: boolean) => {
    const mine = ++loadSeq.current;
    if (showSkeleton) setMembers(null);
    setLoadError(false);
    try {
      const list = await fetchPartnerTeam();
      if (alive.current && mine === loadSeq.current) setMembers(list);
    } catch {
      if (!alive.current || mine !== loadSeq.current) return;
      setLoadError(true);
      if (showSkeleton) setMembers(null);
    }
  }, []);

  useEffect(() => { void load(true); }, [load]);

  const resend = async (m: PartnerTeamMember) => {
    if (resending) return;
    setResending(m.id);
    try {
      const result = await resendColleagueInvite(m.id);
      if (result.emailSent === false) {
        showToast("The invite email couldn't be sent. Ask your platform administrator for help.", 'error');
      } else {
        showToast(`Invite sent to ${m.email}.`, 'success');
      }
      void load(false);
    } catch (e) {
      showToast(
        e instanceof PartnerApiError && (e.status === 409 || e.status === 422)
          ? e.message
          : "Couldn't send the invite again. Check your connection and try again.",
        'error',
      );
    } finally {
      if (alive.current) setResending(null);
    }
  };

  const loading = members === null && !loadError;
  const list = members ?? [];
  const resendButton = (m: PartnerTeamMember) =>
    pending(m) ? (
      <button type="button" className={ROW_BUTTON} disabled={resending !== null} onClick={() => { void resend(m); }}
              aria-label={`Resend invite to ${m.email}`}>
        {resending === m.id ? 'Sending...' : 'Resend invite'}
      </button>
    ) : null;

  return (
    <section aria-labelledby={`${uid}-team-title`} aria-busy={loading} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id={`${uid}-team-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">Team</h2>
        <button type="button" className={SECONDARY_BUTTON} onClick={() => setInviting(true)}>
          <MailIcon size={16} aria-hidden="true" />
          Invite colleague
        </button>
      </div>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Partner administrators create customers and change seats. Partner viewers can only look.
      </p>

      {loadError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300">
          <AlertTriangleIcon size={16} aria-hidden="true" />
          <span>Couldn't load your team. Check your connection and try again.</span>
          <button type="button" className={SECONDARY_BUTTON} onClick={() => { void load(true); }}>Try again</button>
        </div>
      )}

      {(!loadError || members !== null) && (
        <div className="card overflow-hidden">
          {wide ? (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-white/10">
                  <th scope="col" className={TH}>Name</th>
                  <th scope="col" className={TH}>Email</th>
                  <th scope="col" className={TH}>Role</th>
                  <th scope="col" className={TH}>Status</th>
                  <th scope="col" className={TH}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-white/10">
                {loading && [0, 1, 2].map(i => (
                  <tr key={i} data-skeleton>
                    <td colSpan={5} className="px-6 py-4"><div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-white/10" /></td>
                  </tr>
                ))}
                {list.map(m => (
                  <tr key={m.id}>
                    <td className={`${TD} font-semibold break-words`}>{m.name}</td>
                    <td className={`${TD} break-all`}>{m.email}</td>
                    <td className={TD}>{partnerRoleLabel(m.role)}</td>
                    <td className={TD}><StaffStatusChip status={m.status} /></td>
                    <td className={TD}>{resendButton(m)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          ) : (
          <ul className="divide-y divide-gray-200 dark:divide-white/10">
            {loading && [0, 1, 2].map(i => (
              <li key={i} data-skeleton className="p-4"><div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-white/10" /></li>
            ))}
            {list.map(m => (
              <li key={m.id} aria-label={m.name} className="space-y-3 p-4 text-sm text-gray-900 dark:text-white">
                <p className="font-semibold break-words">{m.name}</p>
                <dl className="space-y-2">
                  <div><dt className={MUTED}>Email</dt><dd className="break-all">{m.email}</dd></div>
                  <div><dt className={MUTED}>Role</dt><dd>{partnerRoleLabel(m.role)}</dd></div>
                  <div><dt className={MUTED}>Status</dt><dd><StaffStatusChip status={m.status} /></dd></div>
                </dl>
                {resendButton(m)}
              </li>
            ))}
          </ul>
          )}
        </div>
      )}

      {inviting && <InviteColleagueModal onClose={() => setInviting(false)} onInvited={() => { void load(false); }} />}
    </section>
  );
};

export default PartnerTeamPanel;
