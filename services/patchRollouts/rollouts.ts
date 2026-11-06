import { API_BASE, authFetch } from '../apiService';
import type { RolloutCard, RolloutPage, WindowStrip } from './types';

/**
 * The Rollouts tab calls (84-09 routes under /api/patch-rollouts). The server decides every control: the page carries
 * the flags, each card carries canResume and canCancel, and the browser infers nothing from a role. A non-2xx answer
 * becomes a RolloutApiError whose `detail` is the server's sentence (empty when the body had none), so a screen shows
 * the sentence or its own fallback.
 */

export class RolloutApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
        super(detail || `Request failed (${status})`);
        this.name = 'RolloutApiError';
        this.status = status;
        this.detail = detail;
    }
}

export async function rolloutFailure(res: Response): Promise<RolloutApiError> {
    let detail = '';
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
    } catch { /* non-JSON error body */ }
    return new RolloutApiError(res.status, detail);
}

async function getJson<T>(url: string): Promise<T> {
    const res = await authFetch(url);
    if (!res.ok) throw await rolloutFailure(res);
    return res.json();
}

/** `tenantId` is the organization platform staff entered from Tenants; a tenant role never sends one. */
const withTenant = (url: string, tenantId?: string | null) =>
    tenantId ? `${url}${url.includes('?') ? '&' : '?'}tenantId=${encodeURIComponent(tenantId)}` : url;

export interface RolloutQuery {
    offset?: number;
    limit?: number;
    tenantId?: string | null;
}

/** GET /api/patch-rollouts?offset=&limit=[&tenantId=]: the cards, the window strip, the flags and the attention count. */
export async function fetchRollouts({ offset = 0, limit = 10, tenantId }: RolloutQuery = {}): Promise<RolloutPage> {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    return getJson(withTenant(`${API_BASE}/patch-rollouts?${params.toString()}`, tenantId));
}

/** GET /api/patch-rollouts/{id}: one card, read again after an action. */
export async function fetchRollout(id: string, tenantId?: string | null): Promise<RolloutCard> {
    return getJson(withTenant(`${API_BASE}/patch-rollouts/${encodeURIComponent(id)}`, tenantId));
}

/** GET /api/patch-rollouts/window: open, closed or none, in the organization's time zone. */
export async function fetchWindowStrip(tenantId?: string | null): Promise<WindowStrip> {
    return getJson(withTenant(`${API_BASE}/patch-rollouts/window`, tenantId));
}
