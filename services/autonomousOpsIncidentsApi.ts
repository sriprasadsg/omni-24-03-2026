import { API_BASE, authFetch } from './apiService';
import { failure, getJson, withTenant } from './autonomousOpsApi';
import type { AutonomousOpsRow } from './autonomousOpsApi';

/**
 * The Needs your decision cards (83-18 payload, 83-19 screen). The server decides every control: a line
 * carries `canApprove`, `canDeny` and `canConfirmIsolation`, and the browser infers nothing from a role.
 * Every string in a card is agent or server text and is rendered as React text only.
 */

export type IncidentStepState = 'pending' | 'done' | 'failed' | 'skipped';

export interface IncidentStep {
    label: string;
    state: IncidentStepState;
}

/** A kill line that belongs to a quarantine: `retry` kills then tries the quarantine again, `kill_only` only kills. */
export interface IncidentChain {
    mode: 'retry' | 'kill_only';
    steps: IncidentStep[];
    path: string | null;
    process: { name: string | null; pid: number | null };
}

/** The Activity chip a line takes: the same buckets as an Activity row. */
export type IncidentLineBucket = 'pending' | 'done' | 'failed' | 'refused' | 'undone' | 'suggested';

export interface IncidentAction {
    id: string;
    state: string;
    bucket: IncidentLineBucket;
    command: string;
    label: string;
    target: string | null;
    reason: string | null;
    ruleId: string | null;
    /** What happens (a waiting line) or what happens without a decision (an unconfirmed isolation). `{at}` is filled in the browser. */
    consequenceText: string | null;
    /** The blue info block of a kill-then-quarantine or kill-only line. */
    notice: string | null;
    /** Null while waiting. `{at}` is filled in the browser. */
    result: string | null;
    needsPerson: boolean;
    createdAt: string | null;
    expiresAt: string | null;
    revertsAt: string | null;
    chain: IncidentChain | null;
    canApprove: boolean;
    canDeny: boolean;
    canConfirmIsolation: boolean;
    confirmedAt: string | null;
    confirmedBy: string | null;
    /** A block line: when the block ends, used to fill `{until}` in its result. */
    blockedUntil?: string | null;
}

export interface IncidentCard {
    /** The incident id: the card is `<article id="approval-{id}">`. */
    id: string;
    host: string | null;
    startedAt: string | null;
    alertCount: number;
    deadlineAt: string | null;
    deadlineKind: 'expires' | 'reverts' | null;
    actionCount: number;
    actions: IncidentAction[];
}

export interface IncidentPage {
    items: IncidentCard[];
    total: number;
    offset: number;
    limit: number;
    /** Set while automatic actions are stopped: the browser then disables Approve and Confirm isolation. */
    stopped: { scope: 'tenant' | 'platform' } | null;
}

export interface IncidentQuery {
    offset?: number;
    limit?: number;
    /** Platform staff acting on one organization. Tenant roles never send it. */
    tenantId?: string | null;
}

/** GET /api/autonomous-ops/incidents?offset=&limit=[&tenantId=]: view access; a view-only caller gets every flag false. */
export function fetchIncidents({ offset = 0, limit = 10, tenantId }: IncidentQuery = {}): Promise<IncidentPage> {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (tenantId) params.set('tenantId', tenantId);
    return getJson(`${API_BASE}/autonomous-ops/incidents?${params.toString()}`);
}

/** The answer of a decision: the refreshed Activity row of that action. */
export interface DecisionResult {
    status: 'dispatched' | 'denied' | 'confirmed';
    action: AutonomousOpsRow;
}

async function postDecision(action: string, id: string, tenantId?: string | null): Promise<DecisionResult> {
    const url = withTenant(`${API_BASE}/autonomous-ops/actions/${encodeURIComponent(id)}/${action}`, tenantId);
    const res = await authFetch(url, { method: 'POST', body: JSON.stringify({}) });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** POST /actions/{id}/approve: single use. 409 when it was decided, expired, or automatic actions are stopped. */
export const approveAction = (id: string, tenantId?: string | null) => postDecision('approve', id, tenantId);

/** POST /actions/{id}/deny: nothing is sent to the host. Still allowed during a stop. */
export const denyAction = (id: string, tenantId?: string | null) => postDecision('deny', id, tenantId);

/** POST /actions/{id}/confirm-isolation: keeps the computer isolated until a person restores it. Single use. */
export const confirmIsolation = (id: string, tenantId?: string | null) => postDecision('confirm-isolation', id, tenantId);
