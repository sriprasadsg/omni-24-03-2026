import React from 'react';
import { AlertTriangleIcon, CheckCircleIcon, ClockIcon, MailIcon, PauseCircleIcon } from './icons';

/**
 * Phase 87 (87-UI-SPEC, Color): the partner status, pool expiry and staff invite chips. The anatomy and
 * tone classes are the Phase 81/82 chip ones, copied rather than imported across feature folders; no tone
 * is added. Every chip pairs a 12px aria-hidden icon with visible text, so colour is never the only signal.
 */

const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border';
const GREEN = 'bg-green-50 text-green-800 border-green-200 dark:bg-green-400/10 dark:text-green-200 dark:border-green-400/25';
const AMBER = 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25';
const RED = 'bg-red-50 text-red-700 border-red-200 dark:bg-red-400/10 dark:text-red-300 dark:border-red-400/25';
const NEUTRAL = 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-white/[0.06] dark:text-gray-200 dark:border-white/10';

const DAY_MS = 24 * 60 * 60 * 1000;
/** A pool expiring within this many days gets the amber chip. */
const EXPIRY_WARNING_DAYS = 30;

const Chip: React.FC<{ label: string; Icon: React.FC<any>; classes: string }> = ({ label, Icon, classes }) => (
  <span className={`${CHIP_BASE} ${classes}`}>
    <Icon size={12} aria-hidden="true" />
    {label}
  </span>
);

export type PartnerStatusKind = 'active' | 'suspended';

const PARTNER_CHIPS: Record<PartnerStatusKind, { label: string; Icon: React.FC<any>; classes: string }> = {
  active: { label: 'Active', Icon: CheckCircleIcon, classes: GREEN },
  suspended: { label: 'Suspended', Icon: PauseCircleIcon, classes: AMBER },
};

/** The partner's standing: Active (green) or Suspended (amber). As on the server, anything but active reads Suspended. */
export const PartnerStatusChip: React.FC<{ kind: PartnerStatusKind }> = ({ kind }) => (
  <Chip {...PARTNER_CHIPS[kind === 'active' ? 'active' : 'suspended']} />
);

/** Whole days from `now` to `iso`, rounded up (negative or zero once it has passed); null with no usable date. */
export function daysUntil(iso: string | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null;
  const when = new Date(iso).getTime();
  if (Number.isNaN(when)) return null;
  return Math.ceil((when - now.getTime()) / DAY_MS);
}

/** 'Mon D, YYYY' for a stored date, '' when there is none. Callers wrap it in <time dateTime={iso}>.
 *  The day is read in UTC: the form stores a chosen day as 23:59:59Z, and the edit form and the CSV
 *  read it back as that UTC day, so every view shows the same day (87 WR-09). */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return '';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '';
  return when.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

/**
 * The pool's expiry: Expired (red) once past, `Expires in {n} days` (amber) within 30 days, and nothing
 * for a later date or no expiry (the page prints `No expiry` as plain text).
 */
export const PoolExpiryChip: React.FC<{ expiresAt?: string | null; now?: Date }> = ({ expiresAt, now }) => {
  const reference = now ?? new Date();
  const when = expiresAt ? new Date(expiresAt).getTime() : NaN;
  if (Number.isNaN(when)) return null;
  if (when <= reference.getTime()) return <Chip label="Expired" Icon={AlertTriangleIcon} classes={RED} />;
  const days = daysUntil(expiresAt, reference);
  if (days === null || days > EXPIRY_WARNING_DAYS) return null;
  return <Chip label={`Expires in ${days} ${days === 1 ? 'day' : 'days'}`} Icon={ClockIcon} classes={AMBER} />;
};

export type StaffStatusKind = 'active' | 'invited' | 'invite_expired';

const STAFF_CHIPS: Record<StaffStatusKind, { label: string; Icon: React.FC<any>; classes: string }> = {
  active: { label: 'Active', Icon: CheckCircleIcon, classes: GREEN },
  invited: { label: 'Invited', Icon: MailIcon, classes: NEUTRAL },
  invite_expired: { label: 'Invite expired', Icon: ClockIcon, classes: AMBER },
};

/** A colleague's standing: Active once they have signed in, Invited while the link is open, Invite expired after it. */
export const StaffStatusChip: React.FC<{ status: StaffStatusKind }> = ({ status }) =>
  STAFF_CHIPS[status] ? <Chip {...STAFF_CHIPS[status]} /> : null;
