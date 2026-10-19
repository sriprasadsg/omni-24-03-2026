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

/** GET /api/roles[?tenantId=]: built-in roles plus the selected tenant's custom roles. */
export async function fetchRoles(tenantId?: string | null): Promise<ApiRole[]> {
    const res = await authFetch(withTenant(`${API_BASE}/roles`, tenantId));
    if (!res.ok) throw await failure(res, 'Could not load roles');
    return res.json();
}

/** GET /api/roles/{role_id}/visibility: the server's answer, rendered as delivered (SC3). */
export async function fetchRoleVisibility(roleId: string, tenantId?: string | null): Promise<RoleVisibility> {
    const res = await authFetch(withTenant(`${API_BASE}/roles/${encodeURIComponent(roleId)}/visibility`, tenantId));
    if (!res.ok) throw await failure(res, 'Could not load role visibility');
    return res.json();
}

/** A non-OK role write/catalogue response. `message` is the server detail, empty when it gave none. */
export class RoleApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.name = 'RoleApiError';
        this.status = status;
    }
}

async function apiError(res: Response): Promise<RoleApiError> {
    let detail = '';
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
    } catch { /* non-JSON error body */ }
    return new RoleApiError(res.status, detail);
}

export interface PermissionCatalogue { permissions: string[]; superAdmin: boolean; }

/** GET /api/roles/permission-catalogue: what the current editor may grant (D-02, with the D-11 closure). */
export async function fetchPermissionCatalogue(tenantId?: string | null): Promise<PermissionCatalogue> {
    const res = await authFetch(withTenant(`${API_BASE}/roles/permission-catalogue`, tenantId));
    if (!res.ok) throw await apiError(res);
    return res.json();
}

export interface CreateRoleBody { name: string; description: string; permissions: string[]; tenantId?: string | null; }

/** POST /api/roles: create a custom role (D-01). */
export async function createRole(body: CreateRoleBody): Promise<ApiRole> {
    const res = await authFetch(`${API_BASE}/roles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw await apiError(res);
    return res.json();
}

/** PUT /api/roles/{id}: edit description and permissions only; the name never changes (D-13). */
export async function updateRole(
    id: string,
    body: { description?: string; permissions?: string[] },
    tenantId?: string | null,
): Promise<ApiRole> {
    const res = await authFetch(withTenant(`${API_BASE}/roles/${encodeURIComponent(id)}`, tenantId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw await apiError(res);
    return res.json();
}
