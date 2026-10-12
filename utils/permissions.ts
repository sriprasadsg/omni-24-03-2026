import type { Permission, Tenant, User } from '../types';

const SUPER_ADMIN_ROLE_NAMES = new Set(['super admin', 'superadmin', 'super_admin', 'platform-admin']);

/** True for the role names the UI treats as super admin (Phase 77 unifies the rest). */
export function isSuperAdminRoleName(role?: string | null): boolean {
  return SUPER_ADMIN_ROLE_NAMES.has((role ?? '').trim().toLowerCase());
}

/**
 * What the signed-in user may see (D-17). The only source is the permission list
 * the server delivered in `currentUser.permissions`, narrowed to the tenant's
 * enabled features. An empty list means no access: the role list is never
 * consulted. Super-admin role names get everything.
 */
export function derivePermissionState(
  currentUser: User | null,
  tenants: Tenant[],
): { enabledFeatures: Permission[]; hasPermission: (permission: Permission) => boolean } {
  if (!currentUser) return { enabledFeatures: [], hasPermission: () => false };
  if (isSuperAdminRoleName(currentUser.role)) {
    return { enabledFeatures: [], hasPermission: () => true };
  }

  const delivered: Permission[] = Array.isArray(currentUser.permissions) ? currentUser.permissions : [];
  const tenant = tenants.find(t => t.id === currentUser.tenantId);
  const enabled = tenant ? new Set<Permission>(tenant.enabledFeatures ?? []) : null;
  const enabledFeatures = enabled ? delivered.filter(p => enabled.has(p)) : delivered;

  const hasPermission = (permission: Permission): boolean => {
    if (enabledFeatures.includes('all' as Permission)) return true;
    return enabledFeatures.includes(permission);
  };
  return { enabledFeatures, hasPermission };
}
