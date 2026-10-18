import type { AppView, Permission, User } from '../types';
import { NAV_GROUPS, catalogueFor, viewForHash } from './catalogueAccess';
import { isPlatformRoleName, isSuperAdminRoleName, screenAllowed } from './permissions';

/**
 * Phase 77 (D-05, D-06, D-12): the one place that decides whether the signed-in user may see a
 * view, and which view they land on. The only inputs are the manifest (shared/catalogue-access.json,
 * read through catalogueAccess) and the permission list the server delivered; the server already
 * applied the D-11 closure and the tenant's feature switches, so there is no client-side rule here.
 */

export type ViewDenial = {
  allowed: false;
  reason: 'role' | 'switched_off' | 'unmapped';
  label: string;
  permission?: Permission;
};
export type ViewAccess = { allowed: true } | ViewDenial;

/** D-12: the landing view is the first allowed of these, then the first allowed sidebar item. */
export const LANDING_PREFERENCE: readonly AppView[] = ['dashboard', 'itam'];

type Has = (permission: Permission) => boolean;

export function evaluateViewAccess(view: AppView, user: User | null, has: Has): ViewAccess {
  const entry = catalogueFor(view);
  // A view with no manifest entry is denied for everyone, Super Admin included (76 IN-04).
  if (!entry) return { allowed: false, reason: 'unmapped', label: String(view) };
  if (user && isSuperAdminRoleName(user.role)) return { allowed: true };
  if (has('*' as Permission)) return { allowed: true };
  const platform = !!user && isPlatformRoleName(user.role);
  if (!has(entry.permission)) {
    if (!platform && has(`screen-off:${view}` as Permission)) {
      return { allowed: false, reason: 'switched_off', label: entry.label };
    }
    return { allowed: false, reason: 'role', label: entry.label, permission: entry.permission };
  }
  // Platform roles skip the per-tenant screen switches (backend tenant_features).
  if (!platform && !screenAllowed(view, has)) {
    return { allowed: false, reason: 'switched_off', label: entry.label };
  }
  return { allowed: true };
}

/** True once the server has delivered a permission list for this user (or the role needs none). */
export function permissionsKnown(user: User | null): boolean {
  return !!user && (isSuperAdminRoleName(user.role) || Array.isArray(user.permissions));
}

/** D-06/D-12: the view to land on, or null when the user can see no screen at all. */
export function landingView(user: User | null, has: Has): AppView | null {
  if (!user) return null;
  const preferred = LANDING_PREFERENCE.find(view => evaluateViewAccess(view, user, has).allowed);
  if (preferred) return preferred;
  // Manifest array order, never sorted: two roles with the same allowed set land on the same view.
  const first = NAV_GROUPS.flatMap(group => group.items).find(item => evaluateViewAccess(item.view, user, has).allowed);
  return first ? first.view : null;
}

export function hasAnyScreen(user: User | null, has: Has): boolean {
  return landingView(user, has) !== null;
}

// Friendlier URL aliases (#assets, #helpdesk, ...) that differ from the view name.
const HASH_ALIASES: Record<string, AppView> = {
  assets: 'assetManagement',
  agents: 'agents',
  patching: 'patchManagement',
  security: 'security',
  compliance: 'compliance',
  aigovernance: 'aiGovernance',
  tickets: 'internalTickets',
  helpdesk: 'internalTickets',
};

/** The view a URL hash names (alias first, then the manifest, case-insensitive), or undefined. */
export function resolveHashView(hash: string): AppView | undefined {
  const wanted = (hash ?? '').replace(/^#/, '').toLowerCase();
  if (!wanted) return undefined;
  return HASH_ALIASES[wanted] ?? viewForHash(wanted);
}
