import type { Permission, Tenant, User } from '../types';

// RED-phase placeholder: replaced by the real implementation in the GREEN commit.
export function isSuperAdminRoleName(_role?: string | null): boolean {
  return false;
}

export function derivePermissionState(
  _currentUser: User | null,
  _tenants: Tenant[],
): { enabledFeatures: Permission[]; hasPermission: (permission: Permission) => boolean } {
  return { enabledFeatures: [], hasPermission: () => false };
}
