import type { Permission, User } from '../types';
import featureSwitches from '../shared/tenant-feature-switches.json';

// The tenant feature switches (spec C6), as backend/tenant_features.is_switchable reads them:
// a switch's own permission, or any permission on the resource of a view:X switch.
const SWITCHABLE = new Set<string>(featureSwitches.groups.flatMap(g => g.features.map(f => f.permission)));
const SWITCHED_VIEW_RESOURCES = new Set([...SWITCHABLE].filter(p => p.startsWith('view:')).map(p => p.slice('view:'.length)));

/**
 * True unless the server marked `view` as a switched-off screen for this tenant user
 * (`screen-off:<view>`, backend tenant_features.hidden_screens): a sidebar item whose permission
 * other items share, or that no permission switch covers, has its own screen switch. Callers skip
 * it for platform roles.
 */
export function screenAllowed(view: string, hasPermission: (permission: Permission) => boolean): boolean {
  return !hasPermission(`screen-off:${view}` as Permission);
}

// Screens whose routes serve other screens too: switched off, they are hidden but still answer.
const HIDE_ONLY_SCREENS = new Set(featureSwitches.groups.flatMap(g => g.features)
  .filter(f => (f as { hideOnly?: boolean }).hideOnly).map(f => f.permission.slice('screen:'.length)));

/**
 * False when the tenant's switches take `view` (which needs `permission`) away from this user: the
 * permission is switch-governed and neither it nor its manage: twin was delivered, or the server
 * marked the screen off and refuses its routes (hide-only screens keep them). App skips the startup
 * fetches the server would only answer with 403. Callers skip it for platform roles.
 */
export function switchedOnFor(view: string, permission: string, hasPermission: (permission: Permission) => boolean): boolean {
  const manageTwin = permission.replace(/^view:/, 'manage:');
  if (isTenantSwitchable(permission) && !hasPermission(permission as Permission) && !hasPermission(manageTwin as Permission)) {
    return false;
  }
  return HIDE_ONLY_SCREENS.has(view) || screenAllowed(view, hasPermission);
}

/**
 * True when a Super Admin's per-tenant feature switch decides whether a tenant user holds `permission`,
 * or (given the sidebar `view`) whether the user sees that item through its screen switch.
 */
export function isTenantSwitchable(permission: string, view?: string): boolean {
  const colon = permission.indexOf(':');
  return SWITCHABLE.has(permission) || (colon >= 0 && SWITCHED_VIEW_RESOURCES.has(permission.slice(colon + 1)))
    || (!!view && SWITCHABLE.has(`screen:${view}`));
}

/**
 * Mirrors the backend normalizer (rbac_defaults.normalize_role): lower-case, trim,
 * spaces and hyphens to underscores; `superadmin`, `platform_admin` and
 * `platform_owner` fold into `super_admin`. Keep the two in step.
 */
function normalizeRoleName(role?: string | null): string {
  const normalized = (role ?? '').trim().toLowerCase().replace(/[ -]/g, '_');
  return ['superadmin', 'platform_admin', 'platform_owner'].includes(normalized) ? 'super_admin' : normalized;
}

/** True for every spelling of the super-admin role the backend accepts (Phase 77 unifies the rest). */
export function isSuperAdminRoleName(role?: string | null): boolean {
  return normalizeRoleName(role) === 'super_admin';
}

export type PlatformTier = 'owner' | 'support' | 'billing';
const PLATFORM_TIERS: Record<string, PlatformTier> = {
  super_admin: 'owner', platform_support: 'support', platform_billing: 'billing',
};

/** The platform role tier (spec C1), or null for a tenant role. Mirrors rbac_defaults.platform_tier. */
export function platformTier(role?: string | null): PlatformTier | null {
  return PLATFORM_TIERS[normalizeRoleName(role)] ?? null;
}

export function isPlatformRoleName(role?: string | null): boolean {
  return platformTier(role) !== null;
}

/** The tenant that holds every platform account; its users must hold a platform role. */
export const PLATFORM_TENANT_ID = 'platform-admin';

/** How a role is shown: the super-admin role reads "Platform Owner". */
export function roleLabel(role: string): string {
  return platformTier(role) === 'owner' ? 'Platform Owner' : role;
}

/**
 * What the signed-in user may see (D-17). The only source is the permission list
 * the server delivered in `currentUser.permissions`; the server has already removed
 * what the tenant's feature switches turn off (spec C6, backend/tenant_features.py),
 * so the client applies no second, different rule. An empty list means no access:
 * the role list is never consulted. Super-admin role names, and a delivered `*`,
 * get everything.
 */
export function derivePermissionState(
  currentUser: User | null,
): { enabledFeatures: Permission[]; hasPermission: (permission: Permission) => boolean } {
  if (!currentUser) return { enabledFeatures: [], hasPermission: () => false };
  const delivered: Permission[] = Array.isArray(currentUser.permissions) ? currentUser.permissions : [];
  // The server delivers ["*"] for the super-admin tier; honour that however the role is spelled.
  if (isSuperAdminRoleName(currentUser.role) || delivered.includes('*' as Permission)) {
    return { enabledFeatures: [], hasPermission: () => true };
  }

  const enabledFeatures = delivered;
  const hasPermission = (permission: Permission): boolean => {
    if (enabledFeatures.includes('all' as Permission)) return true;
    return enabledFeatures.includes(permission);
  };
  return { enabledFeatures, hasPermission };
}
