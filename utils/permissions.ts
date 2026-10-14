import type { Permission, Tenant, User } from '../types';

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
 * the server delivered in `currentUser.permissions`, narrowed to the tenant's
 * enabled features. An empty list means no access: the role list is never
 * consulted. Super-admin role names, and a delivered `*`, get everything.
 */
export function derivePermissionState(
  currentUser: User | null,
  tenants: Tenant[],
): { enabledFeatures: Permission[]; hasPermission: (permission: Permission) => boolean } {
  if (!currentUser) return { enabledFeatures: [], hasPermission: () => false };
  const delivered: Permission[] = Array.isArray(currentUser.permissions) ? currentUser.permissions : [];
  // The server delivers ["*"] for the super-admin tier; honour that however the role is spelled.
  if (isSuperAdminRoleName(currentUser.role) || delivered.includes('*' as Permission)) {
    return { enabledFeatures: [], hasPermission: () => true };
  }

  // Platform staff (spec C1) are not narrowed by the Platform tenant's (empty) feature list.
  const tenant = isPlatformRoleName(currentUser.role) ? undefined : tenants.find(t => t.id === currentUser.tenantId);
  const enabled = tenant ? new Set<Permission>(tenant.enabledFeatures ?? []) : null;
  const enabledFeatures = enabled ? delivered.filter(p => enabled.has(p)) : delivered;

  const hasPermission = (permission: Permission): boolean => {
    if (enabledFeatures.includes('all' as Permission)) return true;
    return enabledFeatures.includes(permission);
  };
  return { enabledFeatures, hasPermission };
}
