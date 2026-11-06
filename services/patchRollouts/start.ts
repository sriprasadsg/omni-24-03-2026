import { API_BASE, authFetch } from '../apiService';
import { RolloutApiError } from './rollouts';
import type {
    DraftPayload, PendingPatchPage, Preflight, PreflightRow, StartRequest, StartResult,
} from './types';

/**
 * The Start rollout calls (84-09 routes under /api/patch-rollouts): the pending-patch picker, the check before
 * starting (reads only), Start itself and the draft from a vulnerability suggestion (reads only). A non-2xx answer
 * becomes a RolloutApiError; a failed Start is a StartApiError that also carries the server's `code` (409
 * `already_in_rollout`) and the check's `rows` (422 when something blocks). `tenantId` is the organization platform
 * staff entered from Tenants; a tenant role never sends one.
 */

export class StartApiError extends RolloutApiError {
    /** `already_in_rollout` when another rollout took a computer first, else null. */
    code: string | null;
    /** The preflight rows of a 422, empty otherwise. */
    rows: PreflightRow[];
    constructor(status: number, detail: string, code: string | null, rows: PreflightRow[]) {
        super(status, detail);
        this.name = 'StartApiError';
        this.code = code;
        this.rows = rows;
    }
}

async function startFailure(res: Response): Promise<StartApiError> {
    let detail = '';
    let code: string | null = null;
    let rows: PreflightRow[] = [];
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
        code = typeof body?.code === 'string' ? body.code : null;
        rows = Array.isArray(body?.rows) ? body.rows : [];
    } catch { /* non-JSON error body */ }
    return new StartApiError(res.status, detail, code, rows);
}

const withTenant = (params: URLSearchParams, tenantId?: string | null) => {
    if (tenantId) params.set('tenantId', tenantId);
    const text = params.toString();
    return text ? `?${text}` : '';
};

export interface PendingQuery {
    offset?: number;
    limit?: number;
    search?: string;
    tenantId?: string | null;
}

/** GET /api/patch-rollouts/pending-patches: 50 per page, searched by id or title. */
export async function fetchPendingPatches({ offset = 0, limit = 50, search = '', tenantId }: PendingQuery = {}): Promise<PendingPatchPage> {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    params.set('offset', String(offset));
    params.set('limit', String(limit));
    const res = await authFetch(`${API_BASE}/patch-rollouts/pending-patches${withTenant(params, tenantId)}`);
    if (!res.ok) throw await startFailure(res);
    return res.json();
}

/** POST /api/patch-rollouts/preflight: one row per check and whether Start is possible. Nothing is stored. */
export async function postPreflight(patchIds: string[], tenantId?: string | null): Promise<Preflight> {
    const res = await authFetch(`${API_BASE}/patch-rollouts/preflight${withTenant(new URLSearchParams(), tenantId)}`, {
        method: 'POST',
        body: JSON.stringify({ patchIds }),
    });
    if (!res.ok) throw await startFailure(res);
    return res.json();
}

/** POST /api/patch-rollouts: starts the rollout. The server runs the same check again before it claims anything. */
export async function startRollout({ name, patchIds }: StartRequest, tenantId?: string | null): Promise<StartResult> {
    const res = await authFetch(`${API_BASE}/patch-rollouts${withTenant(new URLSearchParams(), tenantId)}`, {
        method: 'POST',
        body: JSON.stringify({ name, patchIds }),
    });
    if (!res.ok) throw await startFailure(res);
    return res.json();
}

/** GET /api/patch-rollouts/draft?suggestion=: a vulnerability suggestion as a name and a patch list. Stores nothing. */
export async function fetchDraft(suggestionId: string, tenantId?: string | null): Promise<DraftPayload> {
    const params = new URLSearchParams({ suggestion: suggestionId });
    const res = await authFetch(`${API_BASE}/patch-rollouts/draft${withTenant(params, tenantId)}`);
    if (!res.ok) throw await startFailure(res);
    return res.json();
}
