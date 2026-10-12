import type { Permission, Tenant, User } from '../types';

/**
 * Mirrors the backend normalizer (RBACService._normalize_role): lower-case, trim,
 * spaces and hyphens to underscores; `superadmin` and `platform_admin` fold into
 * `super_admin`. Keep the two in step.
 */
function normalizeRoleName(role?: string | null): string {
  const normalized = (role ?? '').trim().toLowerCase().replace(/[ -]/g, '_');
  return normalized === 'superadmin' || normalized === 'platform_admin' ? 'super_admin' : normalized;
}

/** True for every spelling of the super-admin role the backend accepts (Phase 77 unifies the rest). */
export function isSuperAdminRoleName(role?: string | null): boolean {
  return normalizeRoleName(role) === 'super_admin';
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

  const tenant = tenants.find(t => t.id === currentUser.tenantId);
  const enabled = tenant ? new Set<Permission>(tenant.enabledFeatures ?? []) : null;
  const enabledFeatures = enabled ? delivered.filter(p => enabled.has(p)) : delivered;

  const hasPermission = (permission: Permission): boolean => {
    if (enabledFeatures.includes('all' as Permission)) return true;
    return enabledFeatures.includes(permission);
  };
  return { enabledFeatures, hasPermission };
}
