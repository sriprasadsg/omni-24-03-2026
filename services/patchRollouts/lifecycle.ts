import { API_BASE, authFetch } from '../apiService';
import { rolloutFailure } from './rollouts';

/**
 * Resume and Cancel for a halted rollout (84-16 routes under /api/patch-rollouts). Both need manage:patches in a signed-in
 * session; the server decides who sees the buttons (canResume, canCancel) and checks again here. A non-2xx answer becomes
 * a RolloutApiError: 403 (no permission), 404, 409 (`not halted`, `a revert is running`) and 422 (`a reason is required`)
 * carry the status and the server's sentence in `detail`. `tenantId` is the organization platform staff entered from
 * Tenants; a tenant role never sends one.
 */

/** `status` is `resumed` or `still_halted` for Resume and `cancelled` for Cancel; `ring` is the ring's name. */
export interface LifecycleResult {
    status: 'resumed' | 'still_halted' | 'cancelled';
    /** The halt reason now stored (Resume that stayed halted); empty otherwise. */
    reason: string;
    ring: string;
}

const withTenant = (url: string, tenantId?: string | null) =>
    tenantId ? `${url}?tenantId=${encodeURIComponent(tenantId)}` : url;

async function post(path: string, body: unknown, tenantId?: string | null): Promise<LifecycleResult> {
    const res = await authFetch(withTenant(`${API_BASE}/patch-rollouts/${path}`, tenantId), {
        method: 'POST',
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!res.ok) throw await rolloutFailure(res);
    return res.json();
}

/** POST /api/patch-rollouts/{id}/resume: runs the halted ring's health check again; only a green check continues. */
export async function resumeRollout(id: string, reason: string, tenantId?: string | null): Promise<LifecycleResult> {
    return post(`${encodeURIComponent(id)}/resume`, { reason }, tenantId);
}

/** POST /api/patch-rollouts/{id}/cancel: ends a halted rollout; patched computers keep their patches. */
export async function cancelRollout(id: string, tenantId?: string | null): Promise<LifecycleResult> {
    return post(`${encodeURIComponent(id)}/cancel`, undefined, tenantId);
}
