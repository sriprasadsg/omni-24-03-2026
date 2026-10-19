import { Role } from '../types';
import { API_BASE, authFetch } from './apiService';

/** A role as the server lists it: Role plus the server's built-in flag (D-18). */
export type ApiRole = Role & { builtIn?: boolean };

/** D-18: a role without the flag is treated as built-in (fail safe), never derived from isEditable. */
export const isBuiltInRole = (role: ApiRole): boolean => role.builtIn !== false;

export interface RoleVisibilityScreen { view: string; label: string; access: 'view' | 'manage'; }
export interface RoleVisibilitySwitchedOff { view: string; label: string; }
export interface RoleVisibilityGroup {
    id: string;
    title: string;
    total: number;
    visibleCount: number;
    screens: RoleVisibilityScreen[];
    switchedOff: RoleVisibilitySwitchedOff[];
}
export interface RoleVisibility {
    roleId: string;
    roleName: string;
    builtIn: boolean;
    basis: { kind: 'tenant' | 'no_tenant' | 'platform_role'; tenantId: string | null; tenantName: string | null };
    visibleCount: number;
    totalCount: number;
    groups: RoleVisibilityGroup[];
}

async function failure(res: Response, fallback: string): Promise<Error> {
    let detail = '';
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
    } catch { /* non-JSON error body */ }
    return new Error(detail || `${fallback} (${res.status})`);
}

const withTenant = (url: string, tenantId?: string | null) =>
    tenantId ? `${url}?tenantId=${encodeURIComponent(tenantId)}` : url;

/** GET /api/roles/{role_id}/visibility: the server's answer, rendered as delivered (SC3). */
export async function fetchRoleVisibility(roleId: string, tenantId?: string | null): Promise<RoleVisibility> {
    const res = await authFetch(withTenant(`${API_BASE}/roles/${encodeURIComponent(roleId)}/visibility`, tenantId));
    if (!res.ok) throw await failure(res, 'Could not load role visibility');
    return res.json();
}
