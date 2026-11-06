import { API_BASE, authFetch } from '../apiService';
import { failure } from '../autonomousOpsApi';
import type { ApprovalCard, ApprovalLineKind, LineDecisionResult } from './types';

/**
 * The rollout approval calls of Needs your decision (84-10 routes under /api/autonomous-ops). The server decides every
 * control: each line carries canApprove and canDeny, and the browser infers nothing from a role.
 *
 * DEV-1 (UI-SPEC Planning Deviations, pending the user's review): Approve and Deny on a rollout line call the rollout
 * line routes below, one request per line, instead of the per-action approve route the spec names. The engine behind
 * them is the same approvals engine, once per computer, under the same permission, session, stop and expiry rules.
 *
 * A non-2xx answer becomes an AutonomousOpsApiError whose `detail` is the server's sentence (a 409 line answer carries
 * `detail` beside the full LineDecisionResult), the same error type the incident cards already handle.
 */

export interface RolloutCardPage {
    items: ApprovalCard[];
    total: number;
    offset: number;
    limit: number;
    /** Set while automatic actions are stopped: the browser then disables Approve. */
    stopped: { scope: 'tenant' | 'platform' } | null;
    /** The server's clock at the read (ISO): deadlines are compared against it, not the browser's. */
    serverNow?: string | null;
    /** The section's `{k} rollout rings` text, empty when there is no card. */
    countText?: string;
}

export interface RolloutCardQuery {
    offset?: number;
    limit?: number;
    /** Platform staff acting on one organization. Tenant roles never send it. */
    tenantId?: string | null;
}

/** GET /api/autonomous-ops/rollout-cards?offset=&limit=[&tenantId=]: one card per ring with a step waiting for a person. */
export async function fetchRolloutCards({ offset = 0, limit = 10, tenantId }: RolloutCardQuery = {}): Promise<RolloutCardPage> {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (tenantId) params.set('tenantId', tenantId);
    const res = await authFetch(`${API_BASE}/autonomous-ops/rollout-cards?${params.toString()}`);
    if (!res.ok) throw await failure(res);
    return res.json();
}

async function postLine(
    action: 'approve' | 'deny', rolloutId: string, ring: string, line: ApprovalLineKind,
    tenantId?: string | null, reason?: string,
): Promise<LineDecisionResult> {
    const path = [rolloutId, ring, line].map(encodeURIComponent).join('/');
    const query = tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
    const res = await authFetch(`${API_BASE}/autonomous-ops/rollout-lines/${path}/${action}${query}`, {
        method: 'POST',
        body: JSON.stringify(reason ? { reason } : {}),
    });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** POST /rollout-lines/{rolloutId}/{ring}/{line}/approve: one line of one ring, once. 409 when decided, expired or stopped. */
export const approveLine = (rolloutId: string, ring: string, line: ApprovalLineKind, tenantId?: string | null) =>
    postLine('approve', rolloutId, ring, line, tenantId);

/** POST /rollout-lines/{rolloutId}/{ring}/{line}/deny: nothing is sent and the rollout halts at the ring. Allowed during a stop. */
export const denyLine = (rolloutId: string, ring: string, line: ApprovalLineKind, tenantId?: string | null, reason?: string) =>
    postLine('deny', rolloutId, ring, line, tenantId, reason);
