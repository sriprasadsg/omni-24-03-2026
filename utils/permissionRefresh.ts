import type { AppView, User } from '../types';
import { derivePermissionState } from './permissions';
import { evaluateViewAccess } from './viewAccess';

/**
 * Phase 77 (ACC-08, D-08): helpers behind "a role edit applies without a re-login". A 403 on a
 * fetch the client believed allowed, or a window focus, re-reads the permission list. The client
 * never widens access from a refresh: an error keeps the last delivered set (PROH-77-05).
 */

export const PERMISSION_DENIED_EVENT = 'omni:permission-denied';
export const PERMISSION_DENIED_WINDOW_MS = 15000;

/** 'changed' = a new list was applied, 'same' = nothing differs, 'error' = the last set was kept. */
export type RefreshResult = 'changed' | 'same' | 'error';

/** A plain 403 (not an MFA gate, not an auth endpoint) means the delivered permissions may be stale. */
export function shouldSignalPermissionDenied(url: string, status: number, mfaHeader: string | null): boolean {
  return status === 403 && !mfaHeader && !String(url).includes('/api/auth/');
}

let windowTimer: ReturnType<typeof setTimeout> | null = null;
let pending = false;

function closeWindow(): void {
  windowTimer = null;
  if (pending) {
    pending = false;
    window.dispatchEvent(new Event(PERMISSION_DENIED_EVENT));
  }
}

/**
 * Leading-plus-trailing debounce: the first denial in a window refreshes at once and opens a
 * PERMISSION_DENIED_WINDOW_MS window; denials inside the open window only mark a pending refresh,
 * dispatched once when the window ends. Every 403 is followed by a refresh within one window, and
 * a burst costs at most two refreshes.
 */
export function notifyPermissionDenied(): void {
  if (windowTimer !== null) {
    pending = true;
    return;
  }
  window.dispatchEvent(new Event(PERMISSION_DENIED_EVENT));
  windowTimer = setTimeout(closeWindow, PERMISSION_DENIED_WINDOW_MS);
}

export function _resetPermissionDeniedForTests(): void {
  if (windowTimer !== null) clearTimeout(windowTimer);
  windowTimer = null;
  pending = false;
}

/** Order-insensitive equality of two permission lists. */
export function samePermissionSet(a: readonly string[], b: readonly string[]): boolean {
  return [...a].sort().join('|') === [...b].sort().join('|');
}

/**
 * The periodic refresh: re-read permissions first, then reload data only when the refresh did not
 * already reload it. A data load started beside the refresh would run with the old list and could
 * finish last, overwriting the reload made with the new one (77 WR-08). A failed refresh still
 * loads with the kept list (77 WR-09).
 */
export async function refreshThenLoad(refresh: () => Promise<RefreshResult>, load: () => void): Promise<void> {
  let result: RefreshResult;
  try {
    result = await refresh();
  } catch {
    result = 'error';
  }
  if (result !== 'changed') load();
}

/** True when the view was allowed for `before` and is denied for `after` (a removal, never an addition). */
export function lostAccess(view: AppView, before: User | null, after: User | null): boolean {
  const was = evaluateViewAccess(view, before, derivePermissionState(before).hasPermission).allowed;
  const now = evaluateViewAccess(view, after, derivePermissionState(after).hasPermission).allowed;
  return was && !now;
}
