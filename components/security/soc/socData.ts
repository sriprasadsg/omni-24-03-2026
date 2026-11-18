// Data helpers for the Security Operations Center console (Security Overview) and Alert Management:
// GET /api/security/soc/summary and /alerts (backend/soc_service.py), the analyst actions
// (backend/soc_actions.py) and Alert Management's /api/alerts/queue.

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info'];
export type SocRange = '1h' | '24h' | '7d' | '30d';
export const SOC_RANGES: { key: SocRange; label: string; long: string }[] = [
    { key: '1h', label: '1h', long: 'hour' }, { key: '24h', label: '24h', long: '24 hours' },
    { key: '7d', label: '7d', long: '7 days' }, { key: '30d', label: '30d', long: '30 days' },
];
export type AlertStatus = 'open' | 'acknowledged' | 'closed';
export type Resolution = 'resolved' | 'false_positive' | 'benign' | 'approved';
export type QueueStatus = 'active' | 'open' | 'acknowledged' | 'closed' | 'all';
export type AlertAction = 'acknowledge' | 'assign' | 'unassign' | 'close' | 'reopen' | 'archive';

export interface SocAlert {
    id: string; source: 'security' | 'legacy'; type: string; typeLabel: string; severity: Severity;
    title: string; description: string; status: AlertStatus; resolution: Resolution | null;
    tenantId?: string | null; agentId?: string | null; hostname?: string | null;
    createdAt?: string | null; lastSeenAt?: string | null; occurrences: number; assignee?: string | null;
    acknowledgedAt?: string | null; acknowledgedBy?: string | null; closedAt?: string | null; closedBy?: string | null;
    closeNote?: string | null; autoClosed?: boolean; caseId?: string | null; mitre: string[]; evidence: Record<string, unknown>;
    origin?: { ip?: string; hostname?: string } | null;
    incidentId?: string | null;
    rules?: { id: string; name: string }[]; suggestedResponse?: { action: string; rule: string } | null;
    risk?: number; importance?: Importance; threatIntel?: ThreatIntelHit[];
    sla?: { ackDue: string | null; closeDue: string; ackBreached: boolean; closeBreached: boolean } | null;
    aiTriage?: AiTriage | null;
}
export type TriageStep = 'acknowledge' | 'close_false_positive' | 'close_benign' | 'isolate_host' | 'quarantine_file'
    | 'block_ip' | 'open_case' | 'approve_process' | 'investigate';
export interface AiTriage {
    summary: string; likelyCause?: string; seriousness?: 'low' | 'medium' | 'high' | 'critical' | null; why?: string;
    nextSteps: TriageStep[]; model: string; at: string; by: string;
}
export const STEP_LABEL: Record<TriageStep, string> = {
    acknowledge: 'Acknowledge', close_false_positive: 'Close as false positive', close_benign: 'Close as benign',
    isolate_host: 'Isolate host', quarantine_file: 'Quarantine file', block_ip: 'Block IP', open_case: 'Open a case',
    approve_process: 'Approve the process', investigate: 'Look into it further',
};
export const triageAlert = (fetcher: Fetcher, alertId: string) =>
    send<AiTriage>(fetcher, `/api/security/soc/alerts/${encodeURIComponent(alertId)}/triage`, 'POST', undefined, 'The AI explanation failed');
export type SeverityCounts = Record<Severity, number>;
export type Importance = 'low' | 'medium' | 'high' | 'critical';
export const IMPORTANCE: Importance[] = ['low', 'medium', 'high', 'critical'];
export interface ThreatIntelHit { value: string; kind: string; source: string; malware?: string | null }
export interface FeedStatus { feeds: { source: string; ok: boolean; count?: number; at?: string; error?: string | null; needsKey?: boolean }[]; indicators: number }
export interface AlertContextInfo {
    risk: number; user?: string | null; indicators: { sha256?: string | null; ip?: string | null }; threatIntel: ThreatIntelHit[]; feeds: FeedStatus;
    host: { agentId?: string | null; enrolled: boolean; hostname?: string | null; ip?: string | null; os?: string | null; lastSeen?: string | null;
        status?: string | null; agentVersion?: string | null; importance: Importance; owner?: string | null; otherActiveAlerts: number };
}
export const fetchAlertContext = async (fetcher: Fetcher, alertId: string): Promise<AlertContextInfo> => {
    const res = await fetcher(`/api/security/soc/alerts/${encodeURIComponent(alertId)}/context`);
    if (!res.ok) throw await failure(res, 'The context could not be loaded');
    const body = await res.json();
    if (!body?.host) throw new Error('The context could not be loaded: unexpected answer from the server');
    return body;
};
export const setEndpointContext = (fetcher: Fetcher, agentId: string, importance: Importance, owner: string) =>
    send<{ importance: Importance; owner: string | null }>(fetcher, `/api/security/soc/endpoints/${encodeURIComponent(agentId)}/context`, 'PUT', { importance, owner: owner || null }, 'The endpoint was not updated');
export const FEED_NAME: Record<string, string> = { feodo: 'Feodo Tracker (botnet IPs)', threatfox: 'ThreatFox (IPs, domains, hashes)' };
export interface TrendPoint extends SeverityCounts { t: string }
export interface SocSummary {
    generatedAt: string; range: SocRange; rangeSeconds: number; bucketSeconds: number; truncated?: boolean;
    kpis: {
        active: number; open: number; activeBySeverity: SeverityCounts; newInRange: number; newPrevious: number;
        occurrencesInRange: number; timeToAcknowledge: { seconds: number | null; count: number };
        timeToClose: { seconds: number | null; count: number };
        endpointsWithActive: number; removedWithActive: number; endpointsOnline: number; endpoints: number; ackOverdue?: number; closeOverdue?: number;
    };
    trend: TrendPoint[];
    byType: { type: string; label: string; active: number; inRange: number; lastSeen: string | null }[];
    endpoints: ({ agentId: string | null; hostname: string; online: boolean; known: boolean; active: number; lastAlertAt: string | null; risk?: number } & SeverityCounts)[];
    users?: { user: string; risk: number; active: number }[];
    workload?: { assignee: string | null; active: number; overdue: number }[];
    threatIntel?: FeedStatus | null;
    mitre: { technique: string; name: string; tactic: string; count: number }[];
    sources: { type: string; label: string; lastAlertAt: string | null; total: number }[];
    coverage: { check: string; label: string; agents: number }[];
    counts: { openCases?: number; siemRules?: number; activeHunts?: number; activeIncidents?: number };
}
export interface AlertPage { items: SocAlert[]; total: number; limit: number; offset: number }
export interface QueueQuery { status: QueueStatus; severity?: Severity | ''; type?: string; agentId?: string; q?: string; limit?: number; offset?: number; sort?: 'severity' | 'risk' }
export interface Approval { id: string; tenantId?: string; process: string; agentId: string | null; hostname?: string | null; reason?: string; approvedBy?: string; approvedAt?: string }

type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;
const SOC = '/api/security/soc';

const failure = async (res: Response, what: string): Promise<Error> => {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`;
    return new Error(`${what}: ${detail}`);
};

const send = async <T>(fetcher: Fetcher, url: string, method: string, body: unknown, what: string): Promise<T> => {
    const res = await fetcher(url, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!res.ok) throw await failure(res, what);
    return res.json();
};

export const fetchSocSummary = async (fetcher: Fetcher, range: SocRange): Promise<SocSummary> => {
    const res = await fetcher(`${SOC}/summary?range=${range}`);
    if (!res.ok) throw await failure(res, 'Security overview could not be loaded');
    const body = await res.json();
    if (!body?.kpis || !Array.isArray(body.trend)) throw new Error('Security overview could not be loaded: unexpected answer from the server');
    return body;
};

const queueParams = (query: QueueQuery): string => {
    const params = new URLSearchParams({ status: query.status, limit: String(query.limit ?? 50), offset: String(query.offset ?? 0) });
    if (query.severity) params.set('severity', query.severity);
    if (query.type) params.set('type', query.type);
    if (query.agentId) params.set('agentId', query.agentId);
    if (query.q?.trim()) params.set('q', query.q.trim());
    if (query.sort === 'risk') params.set('sort', 'risk');
    return params.toString();
};

export const fetchSocAlerts = async (fetcher: Fetcher, query: QueueQuery): Promise<AlertPage> => {
    const res = await fetcher(`${SOC}/alerts?${queueParams(query)}`);
    if (!res.ok) throw await failure(res, 'Alerts could not be loaded');
    return res.json();
};

/** Alert Management's list: the same alerts, under Alert Management's own permission. */
export const fetchAlertQueue = async (fetcher: Fetcher, query: Omit<QueueQuery, 'type' | 'agentId'>): Promise<AlertPage> => {
    const res = await fetcher(`/api/alerts/queue?${queueParams({ limit: 200, ...query })}`);
    if (!res.ok) throw await failure(res, 'Alerts could not be loaded');
    return res.json();
};

export const actOnAlert = (fetcher: Fetcher, id: string, body: { action: AlertAction; resolution?: Resolution; note?: string; assignee?: string }) =>
    send<SocAlert>(fetcher, `${SOC}/alerts/${encodeURIComponent(id)}`, 'PATCH', body, 'The alert was not changed');

export const bulkAct = (fetcher: Fetcher, ids: string[], action: 'acknowledge' | 'close' | 'archive', resolution?: Resolution, base = `${SOC}/alerts`) =>
    send<{ matched: number; modified: number }>(fetcher, `${base}/bulk`, 'POST', { ids, action, ...(resolution ? { resolution } : {}) }, 'The alerts were not changed');

export const caseFromAlert = (fetcher: Fetcher, id: string) =>
    send<{ case: { id: string; title: string } & Record<string, unknown>; created: boolean }>(fetcher, `${SOC}/alerts/${encodeURIComponent(id)}/case`, 'POST', undefined, 'No case was opened');

export const approveAiProcess = (fetcher: Fetcher, id: string, allEndpoints: boolean, reason?: string) =>
    send<{ approval: Approval; closed: number }>(fetcher, `${SOC}/alerts/${encodeURIComponent(id)}/approve`, 'POST', { allEndpoints, ...(reason ? { reason } : {}) }, 'The process was not approved');

export const fetchApprovals = async (fetcher: Fetcher): Promise<Approval[]> => {
    const res = await fetcher(`${SOC}/approved-ai`);
    if (!res.ok) throw await failure(res, 'Approved AI processes could not be loaded');
    return (await res.json()).items ?? [];
};

export const revokeApproval = (fetcher: Fetcher, id: string) =>
    send<{ success: boolean }>(fetcher, `${SOC}/approved-ai/${encodeURIComponent(id)}`, 'DELETE', undefined, 'The approval was not removed');

export type ResponseAction = 'isolate_host' | 'quarantine_file' | 'block_ip' | 'kill_process';
export type BlockTtl = '1h' | '24h' | '7d';
export interface ResponseOption {
    action: ResponseAction; label: string; available: boolean; reason: string | null;
    target: { host: string; path?: string | null; ip?: string | null; pid?: number | null; exe?: string | null };
}
export interface ResponseRecord {
    actionId: string; action: ResponseAction | string; label: string; state: string; stateText: string; reason?: string | null;
    requestedBy?: string | null; createdAt?: string | null; blockedUntil?: string | null; revertsAt?: string | null;
    keptIsolated: boolean; canUndo: boolean; canKeepIsolated: boolean;
}
export interface ResponseInfo { options: ResponseOption[]; history: ResponseRecord[]; host: string; isolated: boolean; canRespond: boolean }

export const fetchResponse = async (fetcher: Fetcher, alertId: string): Promise<ResponseInfo> => {
    const res = await fetcher(`${SOC}/alerts/${encodeURIComponent(alertId)}/response`);
    if (!res.ok) throw await failure(res, 'Response actions could not be loaded');
    const body = await res.json();
    if (!Array.isArray(body?.options)) throw new Error('Response actions could not be loaded: unexpected answer from the server');
    return body;
};

export const respondToAlert = (fetcher: Fetcher, alertId: string, action: ResponseAction, ttl?: BlockTtl) =>
    send<{ actionId: string; status: string }>(fetcher, `${SOC}/alerts/${encodeURIComponent(alertId)}/respond`, 'POST',
        { action, ...(ttl ? { ttl } : {}) }, 'The action was not sent');

export const undoResponse = (fetcher: Fetcher, alertId: string, actionId: string) =>
    send<{ status: string }>(fetcher, `${SOC}/alerts/${encodeURIComponent(alertId)}/response/${encodeURIComponent(actionId)}/undo`, 'POST', undefined, 'It was not undone');

export const keepIsolated = (fetcher: Fetcher, alertId: string, actionId: string) =>
    send<{ status: string }>(fetcher, `${SOC}/alerts/${encodeURIComponent(alertId)}/response/${encodeURIComponent(actionId)}/keep-isolated`, 'POST', undefined, 'The isolation was not kept');

const TTL_WORDS: Record<BlockTtl, string> = { '1h': '1 hour', '24h': '24 hours', '7d': '7 days' };

/** What an action will do, in the words the confirmation shows. */
export const responseImpact = (o: ResponseOption, ttl: BlockTtl): string => {
    const host = o.target.host;
    switch (o.action) {
        case 'isolate_host': return `Cuts ${host} off from every network connection except the Omni-Agent server. It reconnects by itself after 4 hours unless someone keeps it isolated.`;
        case 'quarantine_file': return `Moves ${o.target.path} on ${host} into quarantine so it cannot run. It can be restored.`;
        case 'block_ip': return `Blocks traffic between ${host} and ${o.target.ip} for ${TTL_WORDS[ttl]}. The block lifts by itself.`;
        default: return `Ends ${o.target.exe} (process ${o.target.pid}) on ${host}. Only that program is ended.`;
    }
};

export interface SocIncident {
    id: string; tenantId?: string | null; agentId?: string | null; hostname?: string | null; title: string; severity: Severity;
    status: AlertStatus; resolution: Resolution | null; alertCount: number; grouping: boolean; startedAt?: string | null;
    lastAlertAt?: string | null; tactics: string[]; techniques: string[]; assignee?: string | null;
    acknowledgedAt?: string | null; acknowledgedBy?: string | null; closedAt?: string | null; closedBy?: string | null;
    closeNote?: string | null; caseId?: string | null; autonomyIncidentId?: string | null; aiSummary?: AiTriage | null;
}
export interface IncidentDetail extends SocIncident { timeline: SocAlert[]; closedAlerts?: number }
export interface IncidentPage { items: SocIncident[]; total: number; limit: number; offset: number }

export const fetchIncidents = async (fetcher: Fetcher, status: QueueStatus, offset = 0): Promise<IncidentPage> => {
    const res = await fetcher(`${SOC}/incidents?status=${status}&limit=50&offset=${offset}`);
    if (!res.ok) throw await failure(res, 'Incidents could not be loaded');
    const body = await res.json();
    if (!Array.isArray(body?.items)) throw new Error('Incidents could not be loaded: unexpected answer from the server');
    return body;
};

export const fetchIncident = async (fetcher: Fetcher, id: string): Promise<IncidentDetail> => {
    const res = await fetcher(`${SOC}/incidents/${encodeURIComponent(id)}`);
    if (!res.ok) throw await failure(res, 'The incident could not be loaded');
    return res.json();
};

export const actOnIncident = (fetcher: Fetcher, id: string, body: { action: Exclude<AlertAction, 'archive'>; resolution?: Resolution; note?: string; closeAlerts?: boolean }) =>
    send<IncidentDetail>(fetcher, `${SOC}/incidents/${encodeURIComponent(id)}`, 'PATCH', body, 'The incident was not changed');

export const triageIncident = (fetcher: Fetcher, id: string) =>
    send<AiTriage>(fetcher, `${SOC}/incidents/${encodeURIComponent(id)}/triage`, 'POST', undefined, 'The AI summary failed');

export const caseFromIncident = (fetcher: Fetcher, id: string) =>
    send<{ case: { id: string; title: string } & Record<string, unknown>; created: boolean }>(fetcher, `${SOC}/incidents/${encodeURIComponent(id)}/case`, 'POST', undefined, 'No case was opened');

// ATT&CK coverage (backend/soc_mitre.py).
export type CoverageLevel = 'detected' | 'rule' | 'none';
export interface CoverageTechnique {
    id: string; name: string; level: CoverageLevel; seen: number; active: number; ruleCount: number; subTechniques: string[];
    detections: { type: string; label: string; check: string; technique: string; what: string; endpoints: number }[];
    rules: { name: string; severity?: string | null; technique: string; library: boolean }[];
}
export interface MitreCoverage {
    generatedAt: string; range: SocRange; endpoints: number; siemLogs: number; siemLogDays: number;
    tactics: { id: string; name: string; techniques: CoverageTechnique[] }[];
    totals: { techniques: number; detected: number; ruleOnly: number; none: number; seen: number };
    checks: { type: string; label: string; check: string; endpoints: number; techniques: string[] }[];
}
export const fetchCoverage = async (fetcher: Fetcher, range: SocRange): Promise<MitreCoverage> => {
    const res = await fetcher(`${SOC}/mitre-coverage?range=${range}`);
    if (!res.ok) throw await failure(res, 'ATT&CK coverage could not be loaded');
    const body = await res.json();
    if (!Array.isArray(body?.tactics)) throw new Error('ATT&CK coverage could not be loaded: unexpected answer from the server');
    return body;
};

// Severity is a status scale: fixed hues in both themes (validated with the dataviz validator for
// colour-blind and normal-vision separation), always shown with an icon and a label.
export const SEVERITY_META: Record<Severity, { label: string; hex: string; swatch: string; text: string; chip: string }> = {
    critical: { label: 'Critical', hex: '#c81e1e', swatch: 'bg-[#c81e1e]', text: 'text-red-700 dark:text-red-300', chip: 'bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-500/10 dark:text-red-200 dark:ring-red-400/25' },
    high: { label: 'High', hex: '#ea6a12', swatch: 'bg-[#ea6a12]', text: 'text-orange-700 dark:text-orange-300', chip: 'bg-orange-50 text-orange-800 ring-orange-600/20 dark:bg-orange-500/10 dark:text-orange-200 dark:ring-orange-400/25' },
    medium: { label: 'Medium', hex: '#f2b705', swatch: 'bg-[#f2b705]', text: 'text-amber-700 dark:text-amber-300', chip: 'bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-400/25' },
    low: { label: 'Low', hex: '#4f7fe0', swatch: 'bg-[#4f7fe0]', text: 'text-blue-700 dark:text-blue-300', chip: 'bg-blue-50 text-blue-800 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-200 dark:ring-blue-400/25' },
    info: { label: 'Info', hex: '#4f7fe0', swatch: 'bg-[#4f7fe0]', text: 'text-gray-600 dark:text-gray-300', chip: 'bg-gray-100 text-gray-700 ring-gray-500/20 dark:bg-white/[0.06] dark:text-gray-300 dark:ring-white/10' },
};
/** The trend stacks four bands; "info" alerts count with "low". */
export const TREND_BANDS: Severity[] = ['critical', 'high', 'medium', 'low'];

export const RESOLUTION_LABEL: Record<Resolution, string> = {
    resolved: 'Resolved', false_positive: 'False positive', benign: 'Benign', approved: 'Approved',
};
export const STATUS_LABEL: Record<AlertStatus, string> = { open: 'Open', acknowledged: 'Acknowledged', closed: 'Closed' };

/** "4 min", "3 h 10 min", "2 d 4 h": how long analysts took. */
export const formatDuration = (seconds: number | null | undefined): string => {
    if (seconds == null || !Number.isFinite(seconds)) return '—';
    const s = Math.max(0, Math.round(seconds));
    if (s < 60) return `${s} s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m} min`;
    const h = Math.floor(m / 60);
    if (h < 48) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
    const d = Math.floor(h / 24);
    return h % 24 ? `${d} d ${h % 24} h` : `${d} d`;
};

/** "just now", "12 min ago", "5 h ago", "3 d ago" for an ISO time; "Never" without one. */
export const formatSince = (iso: string | null | undefined, now: number = Date.now()): string => {
    if (!iso) return 'Never';
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return '—';
    const s = Math.max(0, Math.round((now - t) / 1000));
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 172800) return `${Math.floor(s / 3600)} h ago`;
    return `${Math.floor(s / 86400)} d ago`;
};

export const formatWhen = (iso: string | null | undefined): string => {
    if (!iso) return '—';
    const t = new Date(iso);
    return Number.isNaN(t.getTime()) ? '—' : t.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

/** Change of new alerts against the previous range, in percent; null when there is nothing to compare. */
export const newAlertDelta = (now: number, before: number): number | null => (before > 0 ? ((now - before) / before) * 100 : null);

export const endpointName = (alert: Pick<SocAlert, 'hostname' | 'agentId'>): string =>
    alert.hostname || (alert.agentId ? `Removed endpoint (${alert.agentId.replace(/^agent-/, '').slice(0, 8)})` : 'No endpoint');
