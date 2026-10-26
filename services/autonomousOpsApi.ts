import { API_BASE, authFetch } from './apiService';

/** Which slice of the activity list to request. `simulation` and `all` are not states. */
export type AutonomousOpsBucket =
    | 'all' | 'pending' | 'done' | 'undone' | 'failed' | 'refused' | 'suggested' | 'simulation';

/** The bucket a row belongs to. `control` rows (stop and resume events) appear under All only. */
export type AutonomousOpsRowBucket = Exclude<AutonomousOpsBucket, 'all'> | 'control';

export type AutonomousOpsControlEvent =
    | 'stop_pressed' | 'stop_cleared' | 'platform_stop_pressed' | 'platform_stop_cleared'
    | 'breaker_tripped' | 'level_restored';

/** One activity entry as the server delivers it. Every string is rendered as text. */
export interface AutonomousOpsRow {
    id: string;
    bucket: AutonomousOpsRowBucket;
    state: string;
    createdAt: string;
    actionLabel: string;
    classLine: 'Automatic' | 'Needs approval' | null;
    reasonText: string;
    ruleId: string | null;
    host: string | null;
    target: string | null;
    resultText: string | null;
    controlEvent: AutonomousOpsControlEvent | null;
}

export interface AutonomousOpsCounts {
    pending: number; done: number; undone: number; failed: number;
    refused: number; suggested: number; simulation: number;
}

export interface AutonomousOpsActionsPage {
    items: AutonomousOpsRow[];
    nextCursor: string | null;
    counts?: AutonomousOpsCounts;
    total?: number;
}

export interface StopView {
    scope: 'tenant' | 'platform';
    by: string;
    at: string;
    reason: string | null;
}

export type AutonomousOpsLevel = 'off' | 'suggest' | 'undoable_auto';

export interface AutonomousOpsStatus {
    tenantId: string;
    tenantName: string;
    scope: 'tenant';
    platformTenant: boolean;
    eligible: boolean;
    levelReadable: boolean;
    level: AutonomousOpsLevel;
    maxLevel: AutonomousOpsLevel;
    previousLevel: string | null;
    shadow: { effective: boolean; source: 'deployment' | 'tenant' | null };
    stop: { tenant: StopView | null; platform: StopView | null };
    canStop: boolean;
    canResume: boolean;
    canStopPlatform: boolean;
    canResumePlatform: boolean;
}

export interface PlatformAutonomousOpsStatus {
    scope: 'platform';
    stop: { platform: StopView | null };
    tenantStopsCount: number;
    canStopPlatform: boolean;
    canResumePlatform: boolean;
}

export interface ActionsQuery {
    bucket: AutonomousOpsBucket;
    cursor?: string | null;
    limit?: number;
    /** Platform staff viewing one organization. Tenant roles never send it. */
    tenantId?: string | null;
}

/** A non-OK response. `detail` is the server's message, empty when it gave none. */
export class AutonomousOpsApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
        super(detail || `Autonomous Ops request failed (${status})`);
        this.name = 'AutonomousOpsApiError';
        this.status = status;
        this.detail = detail;
    }
}

async function failure(res: Response): Promise<AutonomousOpsApiError> {
    let detail = '';
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
    } catch { /* non-JSON error body */ }
    return new AutonomousOpsApiError(res.status, detail);
}

const withTenant = (url: string, tenantId?: string | null) =>
    tenantId ? `${url}?tenantId=${encodeURIComponent(tenantId)}` : url;

function actionsUrl(base: string, q: ActionsQuery, includeTenant: boolean): string {
    const params = new URLSearchParams();
    params.set('bucket', q.bucket);
    params.set('limit', String(q.limit ?? 25));
    if (q.cursor) params.set('cursor', q.cursor);
    if (includeTenant && q.tenantId) params.set('tenantId', q.tenantId);
    return `${base}?${params.toString()}`;
}

async function getJson<T>(url: string): Promise<T> {
    const res = await authFetch(url);
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** GET /api/autonomous-ops/status[?tenantId=] */
export function fetchAutonomousOpsStatus(tenantId?: string | null): Promise<AutonomousOpsStatus> {
    return getJson(withTenant(`${API_BASE}/autonomous-ops/status`, tenantId));
}

/** GET /api/autonomous-ops/actions?bucket=&limit=&cursor=[&tenantId=] */
export function fetchAutonomousOpsActions(q: ActionsQuery): Promise<AutonomousOpsActionsPage> {
    return getJson(actionsUrl(`${API_BASE}/autonomous-ops/actions`, q, true));
}

/** GET /api/platform/autonomous-ops/status (Super Admin, no tenant selected) */
export function fetchPlatformAutonomousOpsStatus(): Promise<PlatformAutonomousOpsStatus> {
    return getJson(`${API_BASE}/platform/autonomous-ops/status`);
}

/** GET /api/platform/autonomous-ops/actions?bucket=&limit=&cursor= (platform-scope control rows) */
export function fetchPlatformAutonomousOpsActions(q: Omit<ActionsQuery, 'tenantId'>): Promise<AutonomousOpsActionsPage> {
    return getJson(actionsUrl(`${API_BASE}/platform/autonomous-ops/actions`, q, false));
}
