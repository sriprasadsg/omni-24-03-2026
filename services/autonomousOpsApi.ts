import { API_BASE, authFetch } from './apiService';

/** Which slice of the activity list to request. `simulation` and `all` are not states. */
export type AutonomousOpsBucket =
    | 'all' | 'pending' | 'done' | 'undone' | 'failed' | 'refused' | 'suggested' | 'simulation' | 'platform_health';

/** The bucket a row belongs to. `control` rows (stop and resume events) appear under All only. */
export type AutonomousOpsRowBucket = Exclude<AutonomousOpsBucket, 'all'> | 'control';

export type AutonomousOpsControlEvent =
    | 'stop_pressed' | 'stop_cleared' | 'platform_stop_pressed' | 'platform_stop_cleared'
    | 'breaker_tripped' | 'level_restored'
    | 'two_signal_on' | 'two_signal_off' | 'block_length_changed' | 'watched_services_changed';

/** Where a suggestion row sends the viewer: the Patching and File Integrity screens. */
export type AutonomousOpsOpenView = 'patchManagement' | 'fimMonitoring';

export type AutonomousOpsSuggestionKind = 'single_signal' | 'vulnerability' | 'file_change' | 'correlation';

/** One listed item of a grouped suggestion: a vulnerability has cve and package, a file change has path. */
export interface AutonomousOpsSuggestionItem {
    cve?: string;
    package?: string;
    path?: string;
}

/** A suggestion as the server groups it: one row per host per kind, at most 10 items, `count` is the true total. */
export interface AutonomousOpsSuggestion {
    kind: AutonomousOpsSuggestionKind;
    count: number;
    items: AutonomousOpsSuggestionItem[];
    openView: AutonomousOpsOpenView | null;
}

/** One activity entry as the server delivers it. Every string is rendered as text. */
export interface AutonomousOpsRow {
    id: string;
    bucket: AutonomousOpsRowBucket;
    state: string;
    createdAt: string;
    actionLabel: string;
    classLine: 'Automatic' | 'Needs approval' | 'Suggestion only' | null;
    reasonText: string;
    ruleId: string | null;
    host: string | null;
    target: string | null;
    resultText: string | null;
    controlEvent: AutonomousOpsControlEvent | null;
    /** Platform-health rows only (Phase 82): the Activity chip and where the event came from. */
    healthChip?: AutonomousOpsHealthRowChip | null;
    source?: string | null;
    /** Phase 83: the server decides these; a missing key reads as false or empty. */
    canUndo?: boolean;
    undoHint?: string | null;
    /** Pending rows: the incident whose card holds the decision. */
    incidentId?: string | null;
    /** Block rows: when the block ends (ISO), used to fill the time in the result text. */
    blockedUntil?: string | null;
    suggestion?: AutonomousOpsSuggestion | null;
}

/** The Activity chip of a platform-health row, chosen by the server. */
export type AutonomousOpsHealthRowChip = 'healthy' | 'notice' | 'warning' | 'critical' | 'paged' | 'skipped';

export interface AutonomousOpsCounts {
    pending: number; done: number; undone: number; failed: number;
    refused: number; suggested: number; simulation: number;
    /** Present only on the Super Admin's platform route. */
    platform_health?: number;
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
    /** What the watchdog reports; null when the server could not compute it. */
    health?: PlatformHealthSummary | null;
}

export type WatchdogState = 'not_installed' | 'running' | 'silent';

/** `none`: no channel configured. `failing`: the last test or delivery failed. `untested`: configured, never delivered. */
export type OnCallChannelStatus = 'working' | 'untested' | 'none' | 'failing';

/** The compact health summary carried on the shared status poller (82-08). */
export interface PlatformHealthSummary {
    watchdog: WatchdogState;
    lastSeenAt: string | null;
    /** Null while the watchdog is not installed. */
    channel: OnCallChannelStatus | null;
    /** Text only when the channel is failing; URLs already replaced by the server, 300 characters at most. */
    channelError: string | null;
}

export type ServiceId = 'mongod' | 'omni-backend' | 'nginx' | 'ollama';
export type ServiceState =
    | 'healthy' | 'checking' | 'down' | 'restarting' | 'gave_up' | 'expected_off' | 'unexpected_running';

export interface PlatformHealthService {
    id: ServiceId | string;
    name: string;
    unit: string;
    state: ServiceState | null;
    since: string | null;
    failedChecks: number | null;
    restartsInWindow: number | null;
    nextRestartAt: string | null;
    budgetReturnsAt: string | null;
    pagedAt: string | null;
    waitingOn: string | null;
    detail: string | null;
    stale: boolean;
}

export interface PlatformHealthCert {
    path: string | null;
    notAfter: string | null;
    daysLeft: number | null;
    rung: number | null;
    pinned: boolean;
    error: string | null;
    stale: boolean;
}

export interface PlatformHealthDisk {
    mount: string;
    paths: string[];
    usedPct: number | null;
    freeBytes: number | null;
    totalBytes: number | null;
    rung: number | null;
    forecast: { state: string; days: number | null; rung: number | null } | null;
    stale: boolean;
}

export interface PlatformHealthOnCall {
    type: 'none' | 'pagerduty' | 'webhook' | null;
    heartbeatConfigured: boolean;
    status: 'working' | 'not_working' | 'not_tested' | 'not_set_up';
    last: { at: string; ok: boolean; error: string | null } | null;
}

export interface PlatformHealthTestAlert {
    id: string;
    requestedAt: string | null;
    requestedBy: string | null;
    state: 'pending' | 'delivered' | 'failed';
    sentAt: string | null;
    error: string | null;
}

/** GET /api/platform/autonomous-ops/health (82-08). Every value the watchdog could not read is null. */
export interface PlatformHealthDocument {
    updatedAt: string | null;
    host: string | null;
    watchdog: {
        state: WatchdogState;
        lastSeenAt: string | null;
        firstSeenAt: string | null;
        cadenceSeconds: number;
        silentAfterSeconds: number;
    };
    installChecklist: { path: string; url: string | null };
    stop: { effective: boolean; source: 'file' | 'database' | 'cache' | 'none' };
    services: PlatformHealthService[];
    certs: PlatformHealthCert[];
    disks: PlatformHealthDisk[];
    oncall: PlatformHealthOnCall;
    testAlert: PlatformHealthTestAlert | null;
}

/** One organization and retention type waiting for a Super Admin (82-10). */
export interface RetentionReviewItem {
    tenantId: string;
    tenantName: string;
    type: string;
    label: string;
    collection: string;
    days: number;
    previousDays: number | null;
    /** Null when there is no usable count (see countError). */
    count: number | null;
    countError: string | null;
    countedAt: string | null;
    reason: 'first_run' | 'shortened';
}

export interface RetentionLastRun {
    at: string | null;
    trigger: string | null;
    counted: number;
    deleted: number;
    tenants: number;
    error: string | null;
    stoppedEarly: boolean;
}

/** Why the counted set is not complete (82-15). `tenants` is the organizations concerned and can be 0 for stopped_early. */
export type RetentionIncompleteReason = 'stopped_early' | 'tenant_failed' | 'not_reached';

export interface RetentionIncomplete {
    reason: RetentionIncompleteReason;
    tenants: number;
}

/** GET /api/platform/autonomous-ops/retention/review?offset=&limit=25 (82-10). */
export interface RetentionReview {
    mode: 'running' | 'counting_only' | 'deleting_nightly';
    notCountedYet: boolean;
    nextRun: string;
    lastRun: RetentionLastRun | null;
    countedAt: string | null;
    reviewToken: string;
    totals: { records: number; tenants: number; rows: number; uncountable: number };
    items: RetentionReviewItem[];
    total: number;
    nextOffset: number | null;
    /** Null when every organization was counted; set when a confirmation would be refused (82-15). */
    incomplete: RetentionIncomplete | null;
}

/** POST /api/platform/autonomous-ops/retention/confirm. */
export interface ConfirmRetentionResult {
    confirmed: { rows: number; records: number; tenants: number };
}

export interface ActionsQuery {
    bucket: AutonomousOpsBucket;
    cursor?: string | null;
    limit?: number;
    /** Platform staff viewing one organization. Tenant roles never send it. */
    tenantId?: string | null;
}

/**
 * A non-OK response. `detail` is the server's message, empty when it gave none; `by` is who holds
 * the stop on a 409 (already masked by the server for tenant viewers, D-25).
 */
export class AutonomousOpsApiError extends Error {
    status: number;
    detail: string;
    by: string | null;
    constructor(status: number, detail: string, by: string | null = null) {
        super(detail || `Autonomous Ops request failed (${status})`);
        this.name = 'AutonomousOpsApiError';
        this.status = status;
        this.detail = detail;
        this.by = by;
    }
}

async function failure(res: Response): Promise<AutonomousOpsApiError> {
    let detail = '';
    let by: string | null = null;
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
        by = typeof body?.by === 'string' && body.by ? body.by : null;
    } catch { /* non-JSON error body */ }
    return new AutonomousOpsApiError(res.status, detail, by);
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

export interface StopRequest {
    /** Optional on a stop, required on a resume. Blank text is not sent. */
    reason?: string | null;
    /** Platform staff acting on one organization. Tenant roles never send it. */
    tenantId?: string | null;
}

async function postStop(url: string, reason?: string | null): Promise<unknown> {
    const trimmed = (reason ?? '').trim();
    const res = await authFetch(url, { method: 'POST', body: JSON.stringify(trimmed ? { reason: trimmed } : {}) });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** POST /api/autonomous-ops/stop[?tenantId=]: 409 {detail, by} when it is already stopped. */
export async function pressStop({ reason, tenantId }: StopRequest): Promise<AutonomousOpsStatus> {
    return await postStop(withTenant(`${API_BASE}/autonomous-ops/stop`, tenantId), reason) as AutonomousOpsStatus;
}

/** POST /api/autonomous-ops/resume[?tenantId=]: needs a reason; 403 when only a platform administrator may clear it. */
export async function resumeStop({ reason, tenantId }: StopRequest): Promise<AutonomousOpsStatus> {
    return await postStop(withTenant(`${API_BASE}/autonomous-ops/resume`, tenantId), reason) as AutonomousOpsStatus;
}

/** POST /api/platform/autonomous-ops/stop (Super Admin: every organization) */
export async function pressPlatformStop({ reason }: Pick<StopRequest, 'reason'>): Promise<PlatformAutonomousOpsStatus> {
    return await postStop(`${API_BASE}/platform/autonomous-ops/stop`, reason) as PlatformAutonomousOpsStatus;
}

/** POST /api/platform/autonomous-ops/resume (Super Admin) */
export async function resumePlatformStop({ reason }: Pick<StopRequest, 'reason'>): Promise<PlatformAutonomousOpsStatus> {
    return await postStop(`${API_BASE}/platform/autonomous-ops/resume`, reason) as PlatformAutonomousOpsStatus;
}

/** GET /api/platform/autonomous-ops/health (Super Admin) */
export function fetchPlatformHealth(): Promise<PlatformHealthDocument> {
    return getJson(`${API_BASE}/platform/autonomous-ops/health`);
}

/** POST /api/platform/autonomous-ops/health/test-alert: asks the watchdog to send one test message. */
export async function requestTestAlert(): Promise<{ testAlert: PlatformHealthTestAlert }> {
    const res = await authFetch(`${API_BASE}/platform/autonomous-ops/health/test-alert`, { method: 'POST', body: JSON.stringify({}) });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** GET /api/platform/autonomous-ops/retention/review?offset=&limit=25 */
export function fetchRetentionReview(offset = 0): Promise<RetentionReview> {
    const params = new URLSearchParams({ offset: String(offset), limit: '25' });
    return getJson(`${API_BASE}/platform/autonomous-ops/retention/review?${params.toString()}`);
}

/** POST /api/platform/autonomous-ops/retention/confirm: 409 when the counts changed or not every organization has been counted, 403 for anyone but a platform administrator. */
export async function confirmRetention(reviewToken: string): Promise<ConfirmRetentionResult> {
    const res = await authFetch(`${API_BASE}/platform/autonomous-ops/retention/confirm`, {
        method: 'POST', body: JSON.stringify({ reviewToken }),
    });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** The answer of an undo: the refreshed row, and whether this undo tripped the circuit breaker. */
export interface UndoResult {
    status: 'undone';
    action: AutonomousOpsRow;
    breakerTripped: boolean;
}

/** POST /api/autonomous-ops/actions/{id}/undo[?tenantId=]: 409 {detail} when the action cannot be undone now. */
export async function undoAutonomousOpsAction(id: string, tenantId?: string | null): Promise<UndoResult> {
    const url = withTenant(`${API_BASE}/autonomous-ops/actions/${encodeURIComponent(id)}/undo`, tenantId);
    const res = await authFetch(url, { method: 'POST', body: JSON.stringify({}) });
    if (!res.ok) throw await failure(res);
    return res.json();
}
