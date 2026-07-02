
import {
    User, Role, Tenant, Metric, Alert, ComplianceFramework, AiSystem, Asset, Patch, SecurityCase,
    Playbook, SecurityEvent, CloudAccount, CSPMFinding, Notification, AuditLog, Integration, AlertRule,
    Agent, DatabaseSettings, LlmSettings, DataSource, Sbom, SoftwareComponent, AgentUpgradeJob,
    PatchDeploymentJob, VulnerabilityScanJob, LogEntry, UebaFinding, ModelExperiment, RegisteredModel,
    AutomationPolicy, SastFinding, CodeRepository, ApiDocEndpoint, IncidentImpactGraph, SensitiveDataFinding,
    AttackPath, ServiceTemplate, ProvisionedService, DoraMetrics, ChaosExperiment, ProactiveInsight,
    Trace, ServiceMap, NetworkDevice, ThreatIntelResult, NewUserPayload, NewTenantPayload, AgentPlatform,
    SubscriptionTier, Permission, PlaybookExecutionStep, AgenticStep, AgentHealth, ModelStage,
    AiModel, AiPolicy, DastScan, DeviceTrustScore, UserSessionRisk, CryptographicInventory, VoiceBotSettings,
    Risk, Vendor, TrustProfile, AccessRequest, ComplianceScorePayload
} from '../types';

export type {
    User, Role, Tenant, Metric, Alert, ComplianceFramework, AiSystem, Asset, Patch, SecurityCase,
    Playbook, SecurityEvent, CloudAccount, CSPMFinding, Notification, AuditLog, Integration, AlertRule,
    Agent, DatabaseSettings, LlmSettings, DataSource, Sbom, SoftwareComponent, AgentUpgradeJob,
    PatchDeploymentJob, VulnerabilityScanJob, LogEntry, UebaFinding, ModelExperiment, RegisteredModel,
    AutomationPolicy, SastFinding, CodeRepository, ApiDocEndpoint, IncidentImpactGraph, SensitiveDataFinding,
    AttackPath, ServiceTemplate, ProvisionedService, DoraMetrics, ChaosExperiment, ProactiveInsight,
    Trace, ServiceMap, NetworkDevice, ThreatIntelResult, NewUserPayload, NewTenantPayload, AgentPlatform,
    SubscriptionTier, Permission, PlaybookExecutionStep, AgenticStep, AgentHealth, ModelStage,
    AiModel, AiPolicy, DastScan, DeviceTrustScore, UserSessionRisk, CryptographicInventory, VoiceBotSettings,
    ComplianceScorePayload
};
// Helper to ensure severity strings are consistent (e.g., "critical" -> "Critical")
const normalizeSeverity = (severity: any): any => {
    if (typeof severity !== 'string') return 'Low';
    return severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase();
};


// Use relative path so Vite proxy handles it correctly
export const API_BASE = '/api';


// --- SBOM / DevSecOps API ---

export const fetchSboms = async (): Promise<Sbom[]> => {
    try {
        const res = await authFetch(`${API_BASE}/sboms`);
        if (!res.ok) {
            console.error(`[fetchSboms] HTTP ${res.status}: ${res.statusText}`);
            return [];
        }
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (err) {
        console.error('[fetchSboms] Request failed:', err);
        return [];
    }
};

export const fetchSoftwareComponents = async (): Promise<SoftwareComponent[]> => {
    try {
        const res = await authFetch(`${API_BASE}/sboms/components`);
        if (!res.ok) throw new Error("Failed to fetch components");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch { return []; }
};

export const uploadSbom = async (file: File): Promise<{ newSbom: Sbom, newComponents: SoftwareComponent[] }> => {
    const formData = new FormData();
    formData.append('file', file);

    const res = await authFetch(`${API_BASE}/sboms/upload`, {
        method: 'POST',
        body: formData
    });

    if (!res.ok) throw new Error("Failed to upload SBOM");
    const data = await res.json();
    // Context: Backend returns { success: true, sbom: ..., components: [...] }
    return { newSbom: data.sbom, newComponents: data.components };
};



// Track active refresh request to prevent multiple simultaneous refreshes
let refreshPromise: Promise<string> | null = null;
// Backoff: after any refresh failure, skip proactive retries for 30 s
let _lastRefreshFailTime = 0;
// Once set, the session is dead — stop all refresh attempts
let _sessionEnding = false;
const _REFRESH_BACKOFF_MS = 30_000;

// Decode JWT expiry without a library. Returns seconds until expiry (negative = already expired).
function jwtSecondsUntilExpiry(token: string): number {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        if (!payload.exp) return Infinity;
        return payload.exp - Math.floor(Date.now() / 1000);
    } catch {
        return Infinity;
    }
}

function _canAttemptRefresh(): boolean {
    return !_sessionEnding && (Date.now() - _lastRefreshFailTime > _REFRESH_BACKOFF_MS);
}

function _expireSession(): void {
    if (_sessionEnding) return;
    _sessionEnding = true;
    stopTokenRefreshCycle();
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('refresh_token');
    setTimeout(() => { window.location.href = '/login'; }, 50);
}

// Helper function to refresh the access token
async function refreshAccessToken(): Promise<string> {
    if (_sessionEnding) throw new Error('Session ended');
    if (refreshPromise) return refreshPromise;

    refreshPromise = (async () => {
        try {
            const refreshToken = sessionStorage.getItem('refresh_token');
            if (!refreshToken) {
                _lastRefreshFailTime = Date.now();
                throw new Error('No refresh token available');
            }

            const response = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (!response.ok) {
                _lastRefreshFailTime = Date.now();
                if (response.status === 401 || response.status === 403) {
                    // Refresh token is invalid or expired — end the session cleanly
                    _expireSession();
                }
                throw new Error(`Refresh failed: ${response.status}`);
            }

            const data = await response.json();
            if (data.success && data.access_token) {
                _lastRefreshFailTime = 0; // reset backoff on success
                sessionStorage.setItem('token', data.access_token);
                if (data.refresh_token) {
                    sessionStorage.setItem('refresh_token', data.refresh_token);
                }
                return data.access_token;
            }

            _lastRefreshFailTime = Date.now();
            throw new Error('Invalid refresh response');
        } finally {
            refreshPromise = null;
        }
    })();

    return refreshPromise;
}

// Background refresh timer handle — cleared on logout
let _refreshTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * Schedule a proactive token refresh ~5 minutes before the current token expires.
 * Call this after login and after each successful refresh so the cycle self-perpetuates.
 */
export function startTokenRefreshCycle(): void {
    if (_refreshTimer !== null) {
        clearTimeout(_refreshTimer);
        _refreshTimer = null;
    }
    const token = sessionStorage.getItem('token');
    if (!token || !sessionStorage.getItem('refresh_token')) return;

    const secondsUntilExpiry = jwtSecondsUntilExpiry(token);
    const delayMs = Math.max((secondsUntilExpiry - 300) * 1000, 5000);

    _refreshTimer = setTimeout(async () => {
        _refreshTimer = null;
        try {
            await refreshAccessToken();
            startTokenRefreshCycle();
        } catch {
            // Refresh failed — _expireSession() already called if 401/403
        }
    }, delayMs);
}

export function stopTokenRefreshCycle(): void {
    if (_refreshTimer !== null) {
        clearTimeout(_refreshTimer);
        _refreshTimer = null;
    }
}

// Helper for Authenticated Requests
export async function authFetch(url: string, options: RequestInit & { tenantId?: string } = {}): Promise<Response> {
    if (_sessionEnding) throw new Error('Session ended');
    const { tenantId, signal: rawSignal, ...restOptions } = options as RequestInit & { tenantId?: string };
    // Guard: only forward signal if it is actually an AbortSignal (callers sometimes pass event objects)
    const fetchOptions: RequestInit = rawSignal instanceof AbortSignal
        ? { ...restOptions, signal: rawSignal }
        : restOptions;

    const makeRequest = async (token: string | null) => {
        const isFormData = fetchOptions.body instanceof FormData;
        const headers = {
            ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
            ...(fetchOptions.headers || {}),
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
        } as HeadersInit;
        return await fetch(url, { ...fetchOptions, headers });
    };

    let token = sessionStorage.getItem('token');

    // Proactively refresh if token expires within 5 minutes — but only when not in backoff
    if (token && jwtSecondsUntilExpiry(token) < 300 && _canAttemptRefresh()) {
        try {
            token = await refreshAccessToken();
        } catch {
            // Backoff is set; fall through with the current token
        }
    }

    let response = await makeRequest(token);

    // On 401, attempt one refresh (if allowed by backoff) then retry
    if (response.status === 401) {
        if (!_canAttemptRefresh()) {
            // Already know refresh is broken — end the session now
            _expireSession();
            throw new Error('Session expired');
        }
        try {
            const newToken = await refreshAccessToken();
            response = await makeRequest(newToken);
        } catch {
            _expireSession();
            throw new Error('Session expired');
        }
    }

    return response;
}

// Initialize local state as empty (only arrays still used as a write-through cache)
let USERS: User[] = [];
let ROLES: Role[] = [];
let TENANTS: Tenant[] = [];
let ALERTS: Alert[] = [];
let COMPLIANCE_FRAMEWORKS: ComplianceFramework[] = [];
let AI_SYSTEMS: AiSystem[] = [];
let ASSETS: Asset[] = [];
let PATCHES: Patch[] = [];
let SECURITY_CASES: SecurityCase[] = [];
let PLAYBOOKS: Playbook[] = [];
let SECURITY_EVENTS: SecurityEvent[] = [];
let CLOUD_ACCOUNTS: CloudAccount[] = [];
let NOTIFICATIONS: Notification[] = [];
let INTEGRATIONS: Integration[] = [];
let ALERT_RULES: AlertRule[] = [];
let AGENTS: Agent[] = [];
let DATABASE_SETTINGS: DatabaseSettings | null = null;
let LLM_SETTINGS: LlmSettings | null = null;
let DATA_SOURCES: DataSource[] = [];
let AGENT_UPGRADE_JOBS: AgentUpgradeJob[] = [];
let VULNERABILITY_SCAN_JOBS: VulnerabilityScanJob[] = [];
const REGISTERED_MODELS: RegisteredModel[] = [];
let AUTOMATION_POLICIES: AutomationPolicy[] = [];
const NETWORK_DEVICES: NetworkDevice[] = [];

export const checkBackendHealth = async (): Promise<boolean> => {
    try {
        // Use /health endpoint directly (proxied by Vite to backend)
        // NOT ${API_BASE}/health which would be /api/health
        const healthUrl = `/api/health?t=${Date.now()}`;
        // Increased timeout to 5000ms to be more resilient to backend lag
        const res = await fetch(healthUrl, { method: 'GET', signal: AbortSignal.timeout(5000) });
        return res.ok;
    } catch (e) {
        console.warn("Backend health check failed:", e);
        return false;
    }
};

export const mockDelay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// --- MFA / SSO Services ---
export const fetchMfaStatus = async () => {
    const res = await authFetch(`${API_BASE}/mfa/status`);
    if (!res.ok) throw new Error("Failed to fetch MFA status");
    return await res.json();
};

export const setupMfa = async () => {
    const res = await authFetch(`${API_BASE}/mfa/setup`, { method: 'POST' });
    if (!res.ok) throw new Error("Failed to initiate MFA setup");
    return await res.json();
};

export const verifyMfaSetup = async (code: string) => {
    const res = await authFetch(`${API_BASE}/mfa/verify-setup`, {
        method: 'POST',
        body: JSON.stringify({ totp_code: code })
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "MFA verification failed");
    }
    return await res.json();
};

export const disableMfa = async (code: string) => {
    const res = await authFetch(`${API_BASE}/mfa/disable`, {
        method: 'POST',
        body: JSON.stringify({ totp_code: code })
    });
    if (!res.ok) throw new Error("Failed to disable MFA");
    return await res.json();
};

export const fetchSsoProviders = async () => {
    try {
        const res = await fetch(`${API_BASE}/sso/providers`);
        if (!res.ok) return { providers: [] };
        return await res.json();
    } catch { return { providers: [] }; }
};
// Helper for offline caching
const fetchWithCache = async <T>(key: string, endpoint: string, initialData: T, updateLocalVar: (data: T) => void): Promise<T> => {
    try {
        const res = await authFetch(`${API_BASE}${endpoint}`); // Use authFetch
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const data = await res.json();

        // Defensive: handle paginated responses or wrapped objects
        const items = (data && typeof data === 'object' && 'items' in data) ? data.items : data;

        sessionStorage.setItem(`omni_cache_${key}`, JSON.stringify(items));
        updateLocalVar(items);
        return items;
    } catch (e) {
        // If 401, it's already handled by authFetch redirect. 
        // For other errors (offline), fallback to cache or return empty.
        console.warn(`Backend offline or error for ${key}`, e);
        const cached = sessionStorage.getItem(`omni_cache_${key}`);
        if (cached) {
            try {
                const data = JSON.parse(cached);
                updateLocalVar(data);
                return data;
            } catch {
                return [] as any;
            }
        }
        return (Array.isArray(initialData) ? [] : initialData) as T;
    }
};

// ... Fetchers ...

// --- Authentication ---
export const login = async (username: string, password: string): Promise<any> => {
    // We don't use authFetch here because we don't not need a token to login
    const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: username, password }),
    });

    if (res.status === 429) {
        throw new Error('Too many login attempts. Please wait a moment and try again.');
    }
    if (!res.ok) {
        throw new Error('Invalid credentials');
    }

    const data = await res.json();
    if (data.access_token) {
        // Reset session-expiry flags so re-login within the same tab works
        _sessionEnding = false;
        _lastRefreshFailTime = 0;
        sessionStorage.setItem('token', data.access_token);
    }
    return data;
};

export const fetchCurrentUser = async (): Promise<any> => {
    try {
        const token = sessionStorage.getItem('token');
        if (!token) return null;

        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });

        if (!res.ok) {
            // Token invalid or expired - just return null, don't redirect/reload
            if (res.status === 401) {
                sessionStorage.removeItem('token');
            }
            return null;
        }
        return await res.json();
    } catch (e) {
        console.warn("No active session or token expired");
        return null;
    }
};

// --- Fetchers ---
export const fetchUsers = async () => {
    return fetchWithCache('users', '/users', [], (data) => { USERS = data; });
};
export const fetchRoles = async () => {
    return fetchWithCache('roles', '/roles', [], (data) => { ROLES = data; });
};
export const fetchTenants = async () => {
    return fetchWithCache('tenants', '/tenants', [], (data) => { TENANTS = data; });
};
const _METRIC_TYPE_MAP: Record<string, string> = {
    cpu: 'cpu', 'sys-cpu': 'cpu',
    memory: 'memory', mem: 'memory', 'sys-mem': 'memory',
    disk: 'disk', 'sys-disk': 'disk',
    network: 'network', net: 'network', 'sys-net': 'network',
    security: 'security_event', security_event: 'security_event',
};

function _inferMetricType(raw: any): 'cpu' | 'memory' | 'disk' | 'network' | 'security_event' {
    type MT = 'cpu' | 'memory' | 'disk' | 'network' | 'security_event';
    const valid: MT[] = ['cpu', 'memory', 'disk', 'network', 'security_event'];
    const resolve = (s: string): MT => valid.includes(s as MT) ? (s as MT) : 'cpu';
    if (raw.type && _METRIC_TYPE_MAP[raw.type]) return resolve(_METRIC_TYPE_MAP[raw.type]);
    const key = (raw.id ?? raw.name ?? '').toLowerCase().replace(/[^a-z0-9]/g, '_');
    for (const [pattern, type] of Object.entries(_METRIC_TYPE_MAP)) {
        if (key.includes(pattern)) return resolve(type);
    }
    return 'cpu';
}

export const fetchMetrics = async () => {
    try {
        const res = await authFetch(`${API_BASE}/metrics`);
        if (!res.ok) return [];
        const raw: any[] = await res.json();
        return raw.map((m: any) => ({
            id:         m.id ?? m.name,
            title:      m.title ?? m.name ?? m.id,
            value:      m.value != null ? `${m.value}${m.unit ?? ''}` : (m.formatted_value ?? '—'),
            change:     m.change ?? m.delta ?? '0%',
            changeType: m.changeType ?? (m.trend === 'up' ? 'increase' : 'decrease'),
            type:       _inferMetricType(m),
            data:       m.data ?? [],
        }));
    } catch { return []; }
};
// ── Security Intelligence Connectors ─────────────────────────────────────────

export const fetchSecurityIntelStatus = async () => {
    const res = await authFetch(`${API_BASE}/security-intel/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
};

export const saveSecurityIntelConfig = async (provider: string, api_key: string) => {
    const res = await authFetch(`${API_BASE}/security-intel/config`, {
        method: 'POST',
        body: JSON.stringify({ provider, api_key }),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    return res.json();
};

export const testSecurityIntelProvider = async (provider: string) => {
    const res = await authFetch(`${API_BASE}/security-intel/test/${provider}`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
};

export const syncSecurityIntelProvider = async (provider: string) => {
    const res = await authFetch(`${API_BASE}/security-intel/sync/${provider}`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
};

export const pushSecurityIntelToAgents = async () => {
    const res = await authFetch(`${API_BASE}/security-intel/push-to-agents`, { method: 'POST' });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    return res.json();
};

export const fetchAlerts = async (tenantId?: string) => {
    try {
        const res = await authFetch(`${API_BASE}/alerts`, { tenantId } as any);
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        const raw: Alert[] = data.items ? data.items : data;
        ALERTS = raw.map(a => ({
            ...a,
            severity: normalizeSeverity(a.severity)
        }));
        return ALERTS;
    } catch { return []; }
};

export const bulkAcknowledgeAlerts = async (ids: string[]): Promise<{ matched: number; modified: number }> => {
    const res = await authFetch(`${API_BASE}/alerts/bulk`, {
        method: 'PATCH',
        body: JSON.stringify({ ids, patch: { acknowledged: true, status: 'acknowledged' } }),
    });
    if (!res.ok) throw new Error(`Bulk acknowledge failed: HTTP ${res.status}`);
    return res.json();
};

export const bulkDismissAlerts = async (ids: string[]): Promise<{ matched: number; modified: number }> => {
    const res = await authFetch(`${API_BASE}/alerts/bulk`, {
        method: 'PATCH',
        body: JSON.stringify({ ids, patch: { status: 'dismissed' } }),
    });
    if (!res.ok) throw new Error(`Bulk dismiss failed: HTTP ${res.status}`);
    return res.json();
};

export const bulkDeleteAlerts = async (ids: string[]): Promise<{ deleted: number }> => {
    const res = await authFetch(`${API_BASE}/alerts/bulk`, {
        method: 'DELETE',
        body: JSON.stringify(ids),
    });
    if (!res.ok) throw new Error(`Bulk delete failed: HTTP ${res.status}`);
    return res.json();
};
export const fetchComplianceFrameworks = async () => {
    try {
        const res = await authFetch(`${API_BASE}/compliance`);
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        COMPLIANCE_FRAMEWORKS = data.items ? data.items : data;
        return COMPLIANCE_FRAMEWORKS;
    } catch { return []; }
};
// Fetches compliance report for a specific asset
export const fetchAssetCompliance = async (assetId: string): Promise<any> => {
    try {
        const response = await authFetch(`${API_BASE}/assets/${assetId}/compliance`);
        if (!response.ok) throw new Error('Failed to fetch asset compliance');
        return await response.json();
    } catch (err) {
        console.warn('Asset compliance data unavailable', err);
        return null;
    }
};

export const runAgentComplianceScan = async (agentId: string) => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/compliance/scan`, {
        method: 'POST'
    });
    if (!res.ok) throw new Error("Failed to trigger scan");
    return await res.json();
};

export const triggerEvidenceCollection = async (): Promise<any> => {
    const res = await authFetch(`${API_BASE}/compliance/collect-all`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to trigger evidence collection');
    return res.json();
};

export const fetchGlobalComplianceData = async (): Promise<any[]> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/evidence`);
        if (!res.ok) throw new Error("Failed");
        return await res.json();
    } catch {
        console.warn("Asset compliance data unavailable");
        return [];
    }
};

export const addComplianceFramework = async (data: {
    id?: string; name: string; shortName?: string; description?: string;
    category?: string; official_url?: string;
}) => {
    const res = await authFetch(`${API_BASE}/compliance`, {
        method: 'POST', body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? 'Failed to create framework');
    return res.json();
};

export const addComplianceControl = async (frameworkId: string, control: any) => {
    const res = await authFetch(`${API_BASE}/compliance/${frameworkId}/controls`, {
        method: 'POST',
        body: JSON.stringify(control)
    });
    if (!res.ok) throw new Error("Failed to add control");
    return await res.json();
};

// Compliance Exports
export const importComplianceControls = async (frameworkId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    const res = await authFetch(`${API_BASE}/compliance/${frameworkId}/import`, {
        method: 'POST',
        body: formData
    });

    if (!res.ok) throw new Error("Import failed");
    return await res.json();
};

export const runAIAuditor = async (frameworkId: string) => {
    const res = await authFetch(`${API_BASE}/compliance/audit-framework/${frameworkId}`, {
        method: 'POST'
    });
    if (!res.ok) throw new Error("AI Audit failed");
    return await res.json();
};

export const getJobs = async () => {
    try {
        const res = await authFetch(`${API_BASE}/jobs`);
        if (!res.ok) throw new Error("Failed");
        return await res.json();
    } catch {
        // Fallback or empty logic
        return [];
    }
};

export const uploadComplianceEvidence = async (assetId: string, controlId: string, file: File, description?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('control_id', controlId);
    if (description) {
        formData.append('description', description);
    }

    const res = await authFetch(`${API_BASE}/assets/${assetId}/compliance/evidence`, {
        method: 'POST',
        body: formData
    });

    if (!res.ok) throw new Error("Evidence upload failed");
    return await res.json();
};

export const deleteComplianceEvidence = async (assetId: string, controlId: string, evidenceId: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/assets/${assetId}/compliance/evidence/${evidenceId}`, {
        method: 'DELETE'
    });
    if (!res.ok) throw new Error("Evidence delete failed");
};

export const updateAssetComplianceStatus = async (
    assetId: string,
    controlId: string,
    status: 'Compliant' | 'Non-Compliant' | 'Pending_Evidence',
    notes?: string
): Promise<void> => {
    const res = await authFetch(`${API_BASE}/assets/${assetId}/compliance/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ control_id: controlId, status, notes: notes ?? '' }),
    });
    if (!res.ok) throw new Error(`Failed to update compliance status: ${res.status}`);
};

export const uploadControlEvidence = async (controlId: string, file: File, description: string, department: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('description', description);
    formData.append('department', department);
    const res = await authFetch(`${API_BASE}/compliance/controls/${encodeURIComponent(controlId)}/evidence`, {
        method: 'POST',
        body: formData,
    });
    if (!res.ok) throw new Error('Control evidence upload failed');
    return res.json();
};

export const getControlEvidence = async (controlId: string) => {
    const res = await authFetch(`${API_BASE}/compliance/controls/${encodeURIComponent(controlId)}/evidence`);
    if (!res.ok) throw new Error('Failed to fetch control evidence');
    return res.json();
};

export const deleteControlEvidence = async (controlId: string, evidenceId: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/compliance/controls/${encodeURIComponent(controlId)}/evidence/${evidenceId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Control evidence delete failed');
};

export interface ManifestEntry {
    filename: string;
    control_id: string;
}

export interface BulkUploadResult {
    success: boolean;
    committed: number;
    batch_id: string;
    evidence: any[];
}

export const uploadBulkEvidence = async (zipFile: File, manifest: ManifestEntry[]): Promise<BulkUploadResult> => {
    const formData = new FormData();
    formData.append('zip_file', zipFile);
    formData.append('manifest', JSON.stringify(manifest));
    const res = await authFetch(`${API_BASE}/compliance/evidence/bulk`, {
        method: 'POST',
        body: formData,
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const err: any = new Error('Bulk evidence upload failed');
        err.status = res.status;
        err.detail = body.detail;
        throw err;
    }
    return res.json();
};

export const fetchComplianceScore = async (): Promise<ComplianceScorePayload | null> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/score`);
        if (!res.ok) {
            console.error(`[fetchComplianceScore] HTTP ${res.status}: ${res.statusText}`);
            return null;
        }
        return await res.json() as ComplianceScorePayload;
    } catch (err) {
        console.error('[fetchComplianceScore] Request failed:', err);
        return null;
    }
};

export const fetchAiSystems = async () => {
    try {
        const res = await authFetch(`${API_BASE}/ai-systems`);
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        AI_SYSTEMS = data.items ? data.items : data;
        return AI_SYSTEMS;
    } catch { return []; }
};
export const fetchAssets = async (tenantId?: string) => {
    return fetchWithCache('assets', `/assets${tenantId ? `?tenantId=${tenantId}` : ''}`, ASSETS, (data) => { ASSETS = data; });
};

export const fetchAssetById = async (assetId: string): Promise<Asset | null> => {
    try {
        const res = await authFetch(`${API_BASE}/assets/${assetId}`);
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
};

export const fetchLogs = async () => {
    // fetchLogs: Get all system logs
    try {
        const res = await authFetch(`${API_BASE}/logs`);
        if (!res.ok) throw new Error("Failed to fetch logs");
        const data = await res.json();
        const logs = Array.isArray(data) ? data : [];
        return logs;
    } catch (e) {
        console.warn("Backend offline for logs", e);
        return [];
    }
};
export const fetchPatches = async () => {
    try {
        const res = await authFetch(`${API_BASE}/patches`);
        const data = await res.json();
        PATCHES = data.items ? data.items : data;
        return PATCHES;
    } catch (e) {
        console.warn("Backend offline for patches");
        return [];
    }
};
export const fetchSecurityCases = async () => {
    try {
        const res = await authFetch(`${API_BASE}/security-cases`);
        const data = await res.json();
        SECURITY_CASES = data.items ? data.items : data;
        return SECURITY_CASES;
    } catch (e) {
        console.warn("Backend offline for security cases");
        return [];
    }
};
export const fetchPlaybooks = async () => {
    try {
        const res = await authFetch(`${API_BASE}/playbooks`);
        const data = await res.json();
        PLAYBOOKS = data.items ? data.items : data;
        return PLAYBOOKS;
    } catch (e) {
        console.warn("Backend offline for playbooks");
        return [];
    }
};
export const fetchSecurityEvents = async () => {
    try {
        const res = await authFetch(`${API_BASE}/security-events`);
        const data = await res.json();
        const raw: any[] = data.items ? data.items : data;
        // Normalize OCSF-format events to frontend SecurityEvent shape
        SECURITY_EVENTS = raw.map((e: any) => ({
            id: e.id ?? e._id ?? crypto.randomUUID(),
            tenantId: e.tenantId ?? e.tenant_id ?? '',
            timestamp: e.timestamp ?? e.time ?? e.ingestedAt ?? new Date().toISOString(),
            severity: normalizeSeverity(e.severity ?? e.severity_id ?? 'Low'),
            description: e.description ?? e.message ?? e.class_name ?? e.category_name ?? 'Security Event',
            type: e.type ?? e.class_name ?? e.category_name ?? 'Unknown',
            source: {
                ip: e.source?.ip ?? e.actor?.user?.ip ?? e.src_ip ?? 'N/A',
                hostname: e.source?.hostname ?? e.actor?.user?.name ?? e.actor?.session?.uid ?? 'Unknown',
            },
            mitreAttack: e.mitreAttack ?? undefined,
            details: e.details ?? e.metadata ?? undefined,
        }));
        return SECURITY_EVENTS;
    } catch (e) {
        console.warn("Backend offline for security events");
        return [];
    }
};
export const fetchCloudAccounts = async () => {
    try {
        const res = await authFetch(`${API_BASE}/cloud-accounts`);
        const data = await res.json();
        CLOUD_ACCOUNTS = data.items ? data.items : data;
        return CLOUD_ACCOUNTS;
    } catch (e) {
        console.warn("Backend offline for cloud accounts");
        return [];
    }
};
export const fetchCspmFindings = async (tenantId?: string): Promise<CSPMFinding[]> => {
    try {
        const url = tenantId ? `${API_BASE}/cspm/findings?tenantId=${tenantId}` : `${API_BASE}/cspm/findings`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch CSPM findings');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for CSPM findings', e);
        return [];
    }
};
export const fetchNotifications = async () => {
    try {
        const res = await authFetch(`${API_BASE}/notifications`);
        const data = await res.json();
        NOTIFICATIONS = data.items ? data.items : data;
        return NOTIFICATIONS;
    } catch (e) {
        console.warn("Backend offline for notifications");
        return [];
    }
};
// fetchAuditLogs moved to bottom
export const fetchIntegrations = async () => {
    try {
        const res = await authFetch(`${API_BASE}/integrations/list`);
        const data = await res.json();
        INTEGRATIONS = data; // Update local cache
        return data;
    } catch (e) {
        console.warn("Backend offline for integrations");
        return [];
    }
};

export const fetchAlertRules = async (tenantId?: string): Promise<AlertRule[]> => {
    try {
        const url = tenantId ? `${API_BASE}/alert-rules?tenantId=${tenantId}` : `${API_BASE}/alert-rules`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch alert rules');
        const data = await res.json();
        const rules = Array.isArray(data) ? data : (data.items || []);
        ALERT_RULES = rules;
        return rules;
    } catch (e) {
        console.warn('Backend offline for alert rules', e);
        return [];
    }
};
export const fetchHistoricalData = async (tenantId?: string) => {
    try {
        const url = tenantId
            ? `${API_BASE}/analytics/historical?tenant_id=${tenantId}`
            : `${API_BASE}/analytics/historical`;
        const response = await authFetch(url);
        if (!response.ok) throw new Error('Failed to fetch analytics');
        return await response.json();
    } catch (error) {
        console.error('Error fetching historical analytics:', error);
        return null;
    }
};

export const fetchBiMetrics = async (tenantId?: string) => {
    try {
        const url = tenantId
            ? `${API_BASE}/analytics/bi?tenant_id=${tenantId}`
            : `${API_BASE}/analytics/bi`;
        const response = await authFetch(url);
        if (!response.ok) throw new Error('Failed to fetch BI metrics');
        return await response.json();
    } catch (error) {
        console.error('Error fetching BI metrics:', error);
        return null;
    }
};
export const fetchAgents = async (tenantId?: string) => {
    try {
        const url = tenantId ? `${API_BASE}/agents?tenantId=${tenantId}` : `${API_BASE}/agents`;
        const res = await authFetch(url, { tenantId } as any);
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();

        // Handle pagination: extract items if it's a paginated response
        const items = data.items ? data.items : data;

        AGENTS = items;
        sessionStorage.setItem('omni_cache_agents', JSON.stringify(items));
        return items;
    } catch (e) {
        console.warn("Backend offline for agents", e);
        const cached = sessionStorage.getItem(`omni_cache_agents`);
        if (cached) {
            const data = JSON.parse(cached);
            AGENTS = data;
            return data;
        }
        return [];
    }
};
export const fetchDatabaseSettings = async () => {
    try {
        const res = await authFetch(`${API_BASE}/settings/database`);
        return await res.json();
    } catch {
        return null;
    }
};
export const fetchLlmSettings = async () => {
    try {
        const res = await authFetch(`${API_BASE}/settings/llm`);
        return await res.json();
    } catch {
        return null;
    }
};
export const fetchDataSources = async (tenantId?: string): Promise<DataSource[]> => {
    try {
        const url = tenantId ? `${API_BASE}/data-sources?tenantId=${tenantId}` : `${API_BASE}/data-sources`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch data sources');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for data sources', e);
        return [];
    }
};

export const fetchAgentUpgradeJobs = async (tenantId?: string): Promise<AgentUpgradeJob[]> => {
    try {
        const url = tenantId ? `${API_BASE}/agents/upgrade-jobs?tenantId=${tenantId}` : `${API_BASE}/agents/upgrade-jobs`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch agent upgrade jobs');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for agent upgrade jobs', e);
        return [];
    }
};
export const fetchPatchDeploymentJobs = async () => {
    try {
        const response = await authFetch(`${API_BASE}/patches/deployment-jobs`);
        if (!response.ok) throw new Error('Failed to fetch deployment jobs');
        const data = await response.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (error) {
        console.error('Error fetching patch deployment jobs:', error);
        return [];
    }
};
export const fetchVulnerabilityScanJobs = async () => {
    try {
        const res = await authFetch(`${API_BASE}/vulnerability-scans`);
        if (!res.ok) throw new Error("Failed to fetch jobs");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch {
        return [];
    }
};

export const fetchUebaFindings = async (): Promise<UebaFinding[]> => {
    try {
        const res = await authFetch(`${API_BASE}/ueba/risk-scores`);
        if (!res.ok) throw new Error('Failed to fetch UEBA findings');
        const data = await res.json();
        const results = data.results || data;
        return Array.isArray(results) ? results : [];
    } catch (e) {
        console.warn('Backend offline for UEBA findings', e);
        return [];
    }
};
export const fetchModelExperiments = async (): Promise<ModelExperiment[]> => {
    try {
        const res = await authFetch(`${API_BASE}/mlops/history`);
        if (!res.ok) throw new Error('Failed to fetch model experiments');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for model experiments', e);
        return [];
    }
};
export const fetchRegisteredModels = async (): Promise<RegisteredModel[]> => {
    try {
        const res = await authFetch(`${API_BASE}/mlops/models`);
        if (!res.ok) throw new Error('Failed to fetch registered models');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for registered models', e);
        return [];
    }
};
// fetchAutomationPolicies moved to bottom
export const fetchSastFindings = async (): Promise<SastFinding[]> => {
    try {
        const res = await authFetch(`${API_BASE}/sast/vulnerabilities`);
        if (!res.ok) throw new Error('Failed to fetch SAST findings');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.vulnerabilities || data.items || []);
    } catch (e) {
        console.warn('Backend offline for SAST findings', e);
        return [];
    }
};
export const fetchCodeRepositories = async (): Promise<CodeRepository[]> => {
    try {
        const res = await authFetch(`${API_BASE}/sast/projects`);
        if (!res.ok) throw new Error('Failed to fetch code repositories');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for code repositories', e);
        return [];
    }
};
export const fetchApiDocs = async (): Promise<ApiDocEndpoint[]> => {
    try {
        const res = await authFetch(`${API_BASE}/developer-hub/endpoints`);
        if (!res.ok) throw new Error('Failed to fetch API docs');
        const data = await res.json();
        return Array.isArray(data) ? data : [];
    } catch (e) {
        console.warn('Backend offline for API docs', e);
        return [];
    }
};
export const fetchIncidentImpactGraph = async (id: string) => {
    try {
        const res = await authFetch(`${API_BASE}/security/incident-impact/${id}`);
        if (!res.ok) throw new Error("Failed");
        return await res.json();
    } catch (e) {
        console.warn("Backend offline or error", e);
        return null;
    }
};

export const analyzeIncident = async (type: 'alert' | 'case', id: string) => {
    try {
        const res = await authFetch(`${API_BASE}/agent/analyze`, {
            method: 'POST',
            body: JSON.stringify({ type, id })
        });
        if (!res.ok) throw new Error("AI Analysis Failed");
        return await res.json();
    } catch (e) {
        console.error("AI Analysis error", e);
        throw e;
    }
};

export const exportReport = async (type: string, format: 'csv' | 'pdf') => {
    try {
        const response = await authFetch(`${API_BASE}/reports/export?type=${encodeURIComponent(type)}&format=${format}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Export failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;

        // Try to get filename from Content-Disposition header
        const disposition = response.headers.get('Content-Disposition');
        let filename = `${type.replace(/\s+/g, '_').toLowerCase()}_report.${format}`;
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        return { success: true };
    } catch (error) {
        console.error('Export error:', error);
        throw error;
    }
};

export const fetchSensitiveDataFindings = async (): Promise<SensitiveDataFinding[]> => {
    try {
        const res = await authFetch(`${API_BASE}/dlp/incidents`);
        if (!res.ok) throw new Error('Failed to fetch sensitive data findings');
        const data = await res.json();
        const items = data.incidents || data;
        return Array.isArray(items) ? items : [];
    } catch (e) {
        console.warn('Backend offline for sensitive data findings', e);
        return [];
    }
};
export const fetchAttackPaths = async (tenantId?: string): Promise<AttackPath[]> => {
    try {
        const url = tenantId
            ? `${API_BASE}/security/attack-paths?tenant_id=${tenantId}`
            : `${API_BASE}/security/attack-paths`;
        const response = await authFetch(url);
        if (!response.ok) throw new Error('Failed to fetch attack paths');
        const data = await response.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (error) {
        console.error('Error fetching attack paths:', error);
        return [];
    }
};
export const fetchServiceTemplates = async (): Promise<ServiceTemplate[]> => {
    try {
        const res = await authFetch(`${API_BASE}/service-catalog/templates`);
        if (!res.ok) throw new Error('Failed to fetch service templates');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for service templates', e);
        return [];
    }
};
export const fetchProvisionedServices = async (tenantId?: string): Promise<ProvisionedService[]> => {
    try {
        const url = tenantId ? `${API_BASE}/service-catalog/provisioned?tenantId=${tenantId}` : `${API_BASE}/service-catalog/provisioned`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch provisioned services');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for provisioned services', e);
        return [];
    }
};
export const fetchDoraMetrics = async (tenantId?: string): Promise<DoraMetrics[]> => {
    try {
        const url = tenantId ? `${API_BASE}/dora/metrics?tenantId=${tenantId}` : `${API_BASE}/dora/metrics`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch DORA metrics');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for DORA metrics', e);
        return [];
    }
};
export const fetchChaosExperiments = async (): Promise<ChaosExperiment[]> => {
    try {
        const res = await authFetch(`${API_BASE}/chaos/experiments`);
        const data = await res.json();
        if (res.ok) return Array.isArray(data) ? data : (data.items || []);
        return [];
    } catch (e) {
        console.error("Error fetching chaos experiments", e);
        return [];
    }
};

export const createChaosExperiment = async (data: { name: string; type: string; target: string }): Promise<{ ok: boolean; status: number; data?: ChaosExperiment }> => {
    try {
        const res = await authFetch(`${API_BASE}/chaos/experiments`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
        if (res.status === 403) return { ok: false, status: 403 };
        const json = await res.json();
        return { ok: res.ok, status: res.status, data: json };
    } catch (e) {
        console.error("Error creating chaos experiment", e);
        return { ok: false, status: 500 };
    }
};

export const runChaosExperiment = async (id: string): Promise<{ ok: boolean; status: number; data?: any }> => {
    try {
        const res = await authFetch(`${API_BASE}/chaos/experiments/${encodeURIComponent(id)}/run`, {
            method: 'POST',
        });
        if (res.status === 403) return { ok: false, status: 403 };
        const json = await res.json().catch(() => ({}));
        return { ok: res.ok, status: res.status, data: json };
    } catch (e) {
        console.error("Error running chaos experiment", e);
        return { ok: false, status: 500 };
    }
};

export const propagateAntibody = async (threatData: { threat_type: string; indicator: string }): Promise<{ ok: boolean; status: number; data?: any }> => {
    try {
        const res = await authFetch(`${API_BASE}/swarm/propagate-antibody`, {
            method: 'POST',
            body: JSON.stringify(threatData),
        });
        if (res.status === 403) return { ok: false, status: 403 };
        const json = await res.json().catch(() => ({}));
        return { ok: res.ok, status: res.status, data: json };
    } catch (e) {
        console.error("Error propagating antibody", e);
        return { ok: false, status: 500 };
    }
};
export const fetchDastScans = async (): Promise<DastScan[]> => {
    try {
        const res = await authFetch(`${API_BASE}/dast/scans`);
        const data = await res.json();
        if (res.ok) return Array.isArray(data) ? data : (data.items || []);
        return [];
    } catch (e) {
        console.error("Error fetching DAST scans", e);
        return [];
    }
};

export const startDastScan = async (url: string): Promise<DastScan | null> => {
    try {
        const res = await authFetch(`${API_BASE}/dast/scans`, {
            method: 'POST',
            body: JSON.stringify({ url })
        });
        if (res.ok) return await res.json();
        return null;
    } catch (e) {
        console.error("Error starting DAST scan", e);
        return null;
    }
};

// --- Service Mesh API ---
export const fetchMeshServices = async () => {
    try {
        const res = await authFetch(`${API_BASE}/mesh/services`);
        const data = await res.json();
        if (res.ok) return Array.isArray(data) ? data : (data.items || []);
        return [];
    } catch (e) {
        console.error("Error fetching mesh services", e);
        return [];
    }
};

export const fetchMeshGraph = async () => {
    try {
        const res = await authFetch(`${API_BASE}/mesh/graph`);
        if (res.ok) return await res.json();
        return null;
    } catch (e) {
        console.error("Error fetching mesh graph", e);
        return null;
    }
};

export const fetchMeshMetrics = async () => {
    try {
        const res = await authFetch(`${API_BASE}/mesh/metrics`);
        const data = await res.json();
        if (res.ok) return Array.isArray(data) ? data : (data.items || []);
        return [];
    } catch (e) {
        console.error("Error fetching mesh metrics", e);
        return [];
    }
};

export const fetchProactiveInsights = async (tenantId?: string): Promise<ProactiveInsight[]> => {
    try {
        const url = tenantId ? `${API_BASE}/insights/proactive?tenantId=${tenantId}` : `${API_BASE}/insights/proactive`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch proactive insights');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for proactive insights', e);
        return [];
    }
};
// export const fetchTraces = async () => { return []; };
// export const fetchServiceMap = async () => { return null; };
export const fetchThreatIntelFeed = async (tenantId?: string): Promise<ThreatIntelResult[]> => {
    try {
        const url = tenantId ? `${API_BASE}/threat-intel/feed?tenant_id=${tenantId}` : `${API_BASE}/threat-intel/feed`;
        const res = await authFetch(url);
        if (!res.ok) throw new Error('Failed to fetch threat intel feed');
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn('Backend offline for threat intel feed', e);
        return [];
    }
};

// --- Governance / Risk / Vendor API ---

export const fetchRisks = async (): Promise<Risk[]> => {
    try {
        const res = await authFetch(`${API_BASE}/risks`);
        if (!res.ok) throw new Error("Failed to fetch risks");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching risks:", e);
        return [];
    }
};

export const createRisk = async (riskData: any): Promise<Risk> => {
    const res = await authFetch(`${API_BASE}/risks`, {
        method: 'POST',
        body: JSON.stringify(riskData)
    });
    if (!res.ok) throw new Error("Failed to create risk");
    return await res.json();
};

export const fetchVendors = async (): Promise<Vendor[]> => {
    try {
        const res = await authFetch(`${API_BASE}/vendors`);
        if (!res.ok) throw new Error("Failed to fetch vendors");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching vendors:", e);
        return [];
    }
};

export const createVendor = async (vendorData: any): Promise<Vendor> => {
    const res = await authFetch(`${API_BASE}/vendors`, {
        method: 'POST',
        body: JSON.stringify(vendorData)
    });
    if (!res.ok) throw new Error("Failed to create vendor");
    return await res.json();
};

export const fetchTrustProfile = async (): Promise<TrustProfile | null> => {
    try {
        const res = await authFetch(`${API_BASE}/trust-center/profile`);
        if (!res.ok) throw new Error("Failed to fetch trust profile");
        return await res.json();
    } catch (e) {
        console.error("Error fetching trust profile:", e);
        return null;
    }
};

export const fetchTrustRequests = async (): Promise<AccessRequest[]> => {
    try {
        const res = await authFetch(`${API_BASE}/trust-center/requests`);
        if (!res.ok) throw new Error("Failed to fetch trust requests");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching trust requests:", e);
        return [];
    }
};

export const updateTrustRequest = async (id: string, status: string, approvedBy: string): Promise<AccessRequest> => {
    const res = await authFetch(`${API_BASE}/trust-center/requests/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status, approved_by: approvedBy })
    });
    if (!res.ok) throw new Error("Failed to update trust request");
    return await res.json();
};


// New 2025 Feature: Live Metrics
export const fetchBusinessKpis = async () => {
    try {
        const res = await authFetch(`${API_BASE}/kpi/business-metrics`);
        if (!res.ok) throw new Error("Failed to fetch KPIs");
        return await res.json();
    } catch (e) {
        console.warn("Backend offline for KPIs — no fallback data shown");
        return null;
    }
};

export const fetchKpiSummary = async (tenantId?: string) => {
    try {
        const res = await authFetch(`${API_BASE}/kpi/summary`, { tenantId } as any);
        if (!res.ok) throw new Error("Failed to fetch KPI summary");
        return await res.json();
    } catch (e) {
        console.warn("Backend offline for KPI summary");
        return null;
    }
};

export const moveAgent = async (agentId: string, targetTenantId: string) => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/move`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targetTenantId })
    });

    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to move agent");
    }
    return await res.json();
};

export const linkAgentToAsset = async (agentId: string, assetId: string) => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/link`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assetId })
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to link agent to asset");
    }
    return await res.json();
};

export const linkAssetToAgent = async (assetId: string, agentId: string) => {
    const res = await authFetch(`${API_BASE}/assets/${assetId}/link`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agentId })
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to link asset to agent");
    }
    return await res.json();
};

export const fetchAssetMetrics = async (assetId: string, range: '1h' | '24h' | '7d' | '30d') => {
    try {
        const res = await authFetch(`${API_BASE}/assets/${assetId}/metrics?range=${range}`);
        if (!res.ok) throw new Error("Failed to fetch metrics");
        const data = await res.json();
        // Return just the metrics array, not the whole response
        return data.metrics || [];
    } catch (e) {
        console.warn("Backend offline or error, returning empty metrics");
        return [];
    }
};

export const triggerFrameworkScan = async (frameworkId: string) => {
    try {
        const response = await authFetch(`${API_BASE}/compliance-automation/collect-evidence`, {
            method: 'POST',
            body: JSON.stringify({
                framework_id: frameworkId,
                tenant_id: localStorage.getItem('tenantId') || 'default'
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const err = await response.json();
            return { success: false, message: err.detail || "Scan request failed" };
        }

        return await response.json();
    } catch (e) {
        console.error(e);
        return { success: false, message: "Network error or Backend offline" };
    }
};

export const createJob = async (jobData: any) => {
    try {
        const response = await authFetch(`${API_BASE}/jobs`, {
            method: 'POST',
            body: JSON.stringify(jobData),
            headers: {
                'Content-Type': 'application/json'
            }
        });
        if (!response.ok) throw new Error("Failed to create job");
        return await response.json();
    } catch (e) {
        console.error(e);
        throw e;
    }
};

// --- Mutators & Actions ---

export const addUser = async (user: NewUserPayload) => {
    try {
        // Generate a cryptographically random temporary password (not displayed to admin)
        const tempBytes = crypto.getRandomValues(new Uint8Array(16));
        const tempPassword = Array.from(tempBytes).map(b => b.toString(16).padStart(2, '0')).join('');
        const payload = {
            email: user.email,
            password: tempPassword,
            full_name: user.name,
            role: user.role,
            tenantId: user.tenantId
        };
        const response = await authFetch(`${API_BASE}/users`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const message = errorData.detail || "Failed to add user to database";
            console.error("Backend error:", message);
            throw new Error(message);
        }

        const createdUser = await response.json();

        // Modify local cache so fetch works smoothly 
        USERS = [...USERS, createdUser];
        return USERS;

    } catch (e) {
        console.warn("Backend offline or failed for addUser. Falling back to local mock.");
        const newUser: User = {
            id: `user-${Date.now()}`,
            ...user,
            avatar: `https://i.pravatar.cc/150?u=${user.email}`,
            status: 'Active'
        };
        USERS = [...USERS, newUser];
        return USERS;
    }
};

export const updateUser = async (userId: string, updates: Partial<User>) => {
    try {
        const payload = {
            full_name: updates.name,
            role: updates.role,
            password: updates.password
        };
        const response = await authFetch(`${API_BASE}/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Failed to update user");
        }

        const updatedUser = await response.json();
        USERS = USERS.map(u => u.id === userId ? updatedUser : u);
        return USERS;
    } catch (e) {
        console.warn("Backend update failed, falling back to local.");
        USERS = USERS.map(u => u.id === userId ? { ...u, ...updates } : u);
        return USERS;
    }
};

export const deleteUser = async (userId: string) => {
    try {
        const response = await authFetch(`${API_BASE}/users/${userId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Failed to delete user");
        }

        USERS = USERS.filter(u => u.id !== userId);
        return USERS;
    } catch (e) {
        console.warn("Backend delete failed, falling back to local.");
        USERS = USERS.filter(u => u.id !== userId);
        return USERS;
    }
};

export const signupNewUser = async (payload: { companyName: string; name: string; email: string; password: string }) => {
    try {
        const response = await fetch(`${API_BASE}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            // Add to local state
            USERS = [...USERS, data.user];
            TENANTS = [...TENANTS, data.tenant];
            return { success: true, user: data.user, tenant: data.tenant };
        }

        return { success: false, error: data.error || 'Signup failed' };
    } catch (error) {
        console.error('Signup error:', error);
        return { success: false, error: 'Network error. Please try again.' };
    }
};

// --- Sustainability API ---
export const fetchCarbonFootprint = async () => {
    try {
        const res = await authFetch(`${API_BASE}/sustainability/carbon-footprint`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const fetchSustainabilityMetrics = async () => {
    try {
        const res = await authFetch(`${API_BASE}/sustainability/metrics`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

// --- FinOps API ---
// --- FinOps API ---
export const fetchFinOpsCosts = async () => {
    try {
        const res = await authFetch(`${API_BASE}/finops/costs`);
        if (res.ok) return await res.json();
        return { snapshot: { currentMonthCost: 0 }, history: [], forecast: [] };
    } catch (e) { return { snapshot: { currentMonthCost: 0 }, history: [], forecast: [] }; }
};

export const fetchFinOpsRecommendations = async () => {
    try {
        const res = await authFetch(`${API_BASE}/finops/recommendations`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const updateFinOpsBudget = async (amount: number) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/budget/update?amount=${amount}`, { method: 'POST' });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
};

export const getFinOpsAnalysis = async (data: any) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/analysis`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error("Failed to generate analysis");
        return await res.json();
    } catch (e) {
        console.error("Error generating FinOps analysis", e);
        throw e;
    }
};

export const recalculateFinOpsCosts = async (tenantId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/recalculate/${tenantId}`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error("Failed to recalculate costs");
        return await res.json();
    } catch (e) {
        console.error("Error recalculating FinOps costs", e);
        throw e;
    }
};

// --- XAI API ---
export const fetchGlobalImportance = async (modelId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/xai/global/${modelId}`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const explainPrediction = async (modelId: string, inputData: any) => {
    try {
        const res = await authFetch(`${API_BASE}/xai/explain`, {
            method: 'POST',
            body: JSON.stringify({ model_id: modelId, input: inputData })
        });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
    return null;
};

// --- Simulation API ---
export const triggerProcessInjection = async (agentId: string, technique: string, target: string) => {
    try {
        const res = await authFetch(`${API_BASE}/simulation/process-injection`, {
            method: 'POST',
            body: JSON.stringify({ agentId, technique, target, tenantId: 'default' })
        });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
    return { success: false };
};

// --- Swarm API ---
export const startSwarmMission = async (goal: string) => {
    try {
        const res = await authFetch(`${API_BASE}/swarm/start`, {
            method: 'POST',
            body: JSON.stringify({ goal, priority: 'High' })
        });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
    return null;
};

export const fetchSwarmMissions = async () => {
    try {
        const res = await authFetch(`${API_BASE}/swarm/list`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

// --- Digital Twin API ---
export const simulateDigitalTwin = async (action: string, targetId: string, details: string) => {
    try {
        const res = await authFetch(`${API_BASE}/digital_twin/simulate`, {
            method: 'POST',
            body: JSON.stringify({ action_type: action, target_id: targetId, details })
        });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
    return null;
};

export const fetchDigitalTwinState = async () => {
    try {
        const res = await authFetch(`${API_BASE}/digital_twin/state`);
        if (res.ok) return await res.json();
        return null;
    } catch (e) { return null; }
};

// --- Stream Processing API ---
export const fetchStreamMetrics = async () => {
    try {
        const res = await authFetch(`${API_BASE}/stream/metrics`);
        if (res.ok) return await res.json();
        return { events_processed: 0, active_subscribers: 0 };
    } catch (e) { return { events_processed: 0, active_subscribers: 0 }; }
};

// --- Future Ops API ---
export const fetchCapacityPredictions = async () => {
    try {
        const res = await authFetch(`${API_BASE}/aiops/capacity-predictions`);
        if (res.ok) return await res.json();
        return { predictions: [] };
    } catch (e) { return { predictions: [] }; }
};

export const fetchLiveEvents = async () => {
    try {
        const res = await authFetch(`${API_BASE}/streaming/live-events`);
        if (res.ok) return await res.json();
        return { eventsPerSecond: 0 };
    } catch (e) { return { eventsPerSecond: 0 }; }
};

export const fetchMultiCloudCosts = async () => {
    try {
        const res = await authFetch(`${API_BASE}/multicloud/cost-optimization`);
        if (res.ok) return await res.json();
        return { recommendations: [] };
    } catch (e) { return { recommendations: [] }; }
};

export const fetchPrivacyConsent = async () => {
    try {
        const res = await authFetch(`${API_BASE}/privacy/consent-tracking`);
        if (res.ok) return await res.json();
        return {};
    } catch (e) { return {}; }
};

export const fetchBlockchainAudit = async () => {
    try {
        const res = await authFetch(`${API_BASE}/blockchain/audit-chain`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const fetchXdrHunts = async () => {
    try {
        const res = await authFetch(`${API_BASE}/xdr/automated-hunts`);
        if (res.ok) return await res.json();
        return {};
    } catch (e) { return {}; }
};

export const fetchXdrCorrelations = async (severity?: string) => {
    try {
        const url = severity ? `${API_BASE}/correlations/?severity=${severity}` : `${API_BASE}/correlations/`;
        const res = await authFetch(url);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const runXdrCorrelationAnalysis = async (timeWindowMinutes = 60) => {
    try {
        const res = await authFetch(`${API_BASE}/correlations/analyze`, {
            method: 'POST',
            body: JSON.stringify({ time_window_minutes: timeWindowMinutes }),
        });
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const fetchMdrPolicies = async () => {
    try {
        const res = await authFetch(`${API_BASE}/response/policies`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const fetchMdrHistory = async (limit = 100) => {
    try {
        const res = await authFetch(`${API_BASE}/response/history?limit=${limit}`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const fetchMdrQuarantine = async () => {
    try {
        const res = await authFetch(`${API_BASE}/response/quarantine`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) { return []; }
};

export const registerNewTenant = async (payload: NewTenantPayload) => {
    const res = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            companyName: payload.companyName,
            name: payload.name,
            email: payload.email,
            password: payload.password,
        }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
        throw new Error(data.detail || data.message || 'Signup failed');
    }
    // Store the JWT so the new session is authenticated immediately
    if (data.access_token) {
        sessionStorage.setItem('access_token', data.access_token);
        if (data.refresh_token) sessionStorage.setItem('refresh_token', data.refresh_token);
    }
    const newTenant: Tenant = { ...data.tenant, apiKeys: [] };
    const newUser: User = { ...data.user, password: '' };
    TENANTS = [...TENANTS, newTenant];
    USERS = [...USERS, newUser];
    return { success: true, newUser, newTenant };
};

export const addTenant = async (tenantData: { name: string; subscriptionTier?: string; enabledFeatures?: string[] }) => {
    try {
        const response = await authFetch(`${API_BASE}/tenants`, {
            method: 'POST',
            body: JSON.stringify({
                name: tenantData.name,
                subscriptionTier: tenantData.subscriptionTier || 'Enterprise',
                enabledFeatures: tenantData.enabledFeatures || [
                    "view:dashboard", "view:cxo_dashboard", "view:profile", "view:insights",
                    "view:tracing", "view:logs", "view:network", "view:agents", "view:assets",
                    "view:patching", "view:security", "view:cloud_security", "view:threat_hunting",
                    "view:dspm", "view:attack_path", "view:sbom", "view:persistence",
                    "view:vulnerabilities", "view:devsecops", "view:dora_metrics", "view:service_catalog",
                    "view:chaos", "view:compliance", "view:ai_governance", "view:security_audit",
                    "view:audit_log", "view:reporting", "view:automation", "view:finops",
                    "view:developer_hub", "view:advanced_bi", "view:llmops", "view:unified_ops",
                    "view:swarm", "manage:settings", "manage:tenants"
                ]
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Failed to create tenant");
        }

        const newTenant: Tenant = await response.json();

        // Update local cache
        TENANTS = [...TENANTS, newTenant];
        return newTenant;
    } catch (e) {
        console.error("Error creating tenant:", e);
        throw e;
    }
};

export const updateTenantFeatures = async (tenantId: string, features: Permission[], tier: SubscriptionTier) => {
    try {
        const res = await authFetch(`${API_BASE}/tenants/${tenantId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabledFeatures: features,
                subscriptionTier: tier
            })
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to update tenant");
        }

        const updatedTenant: Tenant = await res.json();

        // Update local cache after successful backend update
        const tenantIndex = TENANTS.findIndex(t => t.id === tenantId);
        if (tenantIndex > -1) {
            TENANTS[tenantIndex] = updatedTenant;
        }

        return updatedTenant;
    } catch (e) {
        console.error("Error updating tenant:", e);
        throw e;
    }
};

// Wrapper object to satisfy imports in new dashboards (DataWarehouse, Streaming, etc.)
export const apiService = {
    get: async (endpoint: string) => {
        const res = await authFetch(endpoint);
        if (!res.ok) throw new Error(`GET ${endpoint} failed: ${res.statusText}`);
        return await res.json();
    },
    post: async (endpoint: string, body: any) => {
        const res = await authFetch(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(`POST ${endpoint} failed: ${res.statusText}`);
        return await res.json();
    },
    put: async (endpoint: string, body: any) => {
        const res = await authFetch(endpoint, {
            method: 'PUT',
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(`PUT ${endpoint} failed: ${res.statusText}`);
        return await res.json();
    },
    patch: async (endpoint: string, body: any) => {
        const res = await authFetch(endpoint, {
            method: 'PATCH',
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(`PATCH ${endpoint} failed: ${res.statusText}`);
        return await res.json();
    },
    delete: async (endpoint: string) => {
        const res = await authFetch(endpoint, { method: 'DELETE' });
        if (!res.ok) throw new Error(`DELETE ${endpoint} failed: ${res.statusText}`);
        return await res.json();
    }
};


export const getTenantBranding = async (tenantId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/tenants/${tenantId}/branding`);
        if (!res.ok) throw new Error("Failed to fetch branding");
        return await res.json();
    } catch (e) {
        console.warn("Branding fetch failed", e);
        return {};
    }
};

export const deleteTenant = async (tenantId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/tenants/${tenantId}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to delete tenant");
        }

        // Update local cache only after successful deletion
        TENANTS = TENANTS.filter(t => t.id !== tenantId);
        USERS = USERS.filter(u => u.tenantId !== tenantId);

        return await res.json();
    } catch (e) {
        console.error("Error deleting tenant:", e);
        throw e;
    }
};

export const registerAgent = async (data: any) => {
    const res = await authFetch(`${API_BASE}/agents/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to register agent");
    }
    const result = await res.json();

    // Update local cache if needed (though usually we'd re-fetch)
    if (result.agent) {
        AGENTS = [...AGENTS, result.agent];
    }
    if (result.asset) {
        ASSETS = [...ASSETS, result.asset];
    }

    return { newAgent: result.agent, newAsset: result.asset };
};


// --- Tenant Voice Bot Settings ---
export const updateTenantVoiceBotSettings = async (tenantId: string, settings: VoiceBotSettings): Promise<Tenant> => {
    const res = await authFetch(`${API_BASE}/tenants/${tenantId}`, {
        method: 'PATCH',
        body: JSON.stringify({ voiceBotSettings: settings })
    });
    if (!res.ok) throw new Error("Failed to update tenant voice bot settings");
    return await res.json();
};

export const updateAgent = async (agent: Agent) => {
    try {
        const res = await authFetch(`${API_BASE}/agents/${agent.id}`, {
            method: 'PUT',
            body: JSON.stringify(agent)
        });
        if (!res.ok) throw new Error("Failed to update agent");
        const updated = await res.json();

        // Update local cache
        const index = AGENTS.findIndex(a => a.id === agent.id);
        if (index > -1) {
            AGENTS[index] = updated;
        }
        return updated;
    } catch (e) {
        console.warn("Backend offline for updateAgent");
        const index = AGENTS.findIndex(a => a.id === agent.id);
        if (index > -1) {
            AGENTS[index] = agent;
            return agent;
        }
        return agent;
    }
};

export const deleteAgent = async (agentId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/agents/${agentId}`, {
            method: 'DELETE'
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to delete agent");
        }
        return await res.json();
    } catch (e) {
        console.error("Error deleting agent:", e);
        throw e;
    }
};

export const quarantineAgent = async (agentId: string, reason: string) => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/quarantine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason, notify: true }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to quarantine agent');
    }
    return res.json();
};

export const releaseAgent = async (agentId: string) => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/release`, { method: 'POST' });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to release agent');
    }
    return res.json();
};

export const setAgentSoftwareExclusion = async (agentId: string, exclude: boolean) => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/software-exclusion`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exclude }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to update software exclusion');
    }
    return res.json();
};

export const runAgentDiagnostics = async (agentId: string): Promise<Agent> => {
    const res = await authFetch(`${API_BASE}/agents/${agentId}/diagnostics`, { method: 'POST' });
    if (!res.ok) throw new Error(`Diagnostics failed: ${res.status}`);
    const data = await res.json();
    // Merge the health result back into local AGENTS cache so UI reflects it immediately
    const agentIndex = AGENTS.findIndex(a => a.id === agentId);
    if (agentIndex !== -1) {
        AGENTS[agentIndex] = {
            ...AGENTS[agentIndex],
            health: data.health,
            status: data.status || AGENTS[agentIndex].status,
        };
        return AGENTS[agentIndex];
    }
    // Agent not in local cache yet — return a minimal object with the health data
    return { id: agentId, health: data.health, status: data.status } as unknown as Agent;
};

export const restartAgent = async (agentId: string): Promise<{ success: boolean; command_id?: string; error?: string }> => {
    try {
        const res = await authFetch(`${API_BASE}/agents/remote/${agentId}/restart`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            return { success: false, error: err.detail || `HTTP ${res.status}` };
        }
        return await res.json();
    } catch (e) {
        return { success: false, error: e instanceof Error ? e.message : 'Network error' };
    }
};

export const scheduleAgentUpgrade = async (agentIds: string[], targetVersion: string) => {
    const job: AgentUpgradeJob = {
        id: `job-${Date.now()}`,
        scheduledAt: new Date().toISOString(),
        startedAt: null,
        completedAt: null,
        targetVersion,
        status: 'Queued',
        agentIds,
        progress: 0,
        statusLog: []
    };
    AGENT_UPGRADE_JOBS = [job, ...AGENT_UPGRADE_JOBS];
    return job;
};

export const schedulePatchDeployment = async (patchIds: string[], assetIds: string[], deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string) => {
    try {
        const response = await authFetch(`${API_BASE}/patches/deploy`, {
            method: 'POST',
            body: JSON.stringify({
                patch_ids: patchIds,
                asset_ids: assetIds,
                deployment_type: deploymentType,
                schedule_time: scheduleTime,
                tenantId: localStorage.getItem('tenantId') || 'default'
            })
        });

        const data = await response.json();

        if (data.success) {
            return data.job;
        } else {
            throw new Error(data.error || 'Failed to schedule patch deployment');
        }
    } catch (error) {
        console.error('Error scheduling patch deployment:', error);
        throw error;
    }
};

export const scheduleVulnerabilityScan = async (assetIds: string[], scanType: 'Immediate' | 'Scheduled', scheduleTime?: string) => {
    try {
        const tenantId = localStorage.getItem('tenantId') || 'default';
        const res = await authFetch(`${API_BASE}/vulnerabilities/scan`, {
            method: 'POST',
            body: JSON.stringify({
                scan_type: scanType === 'Immediate' ? 'Full' : 'Scheduled',
                assets: assetIds,
                tenantId,
                ...(scheduleTime ? { schedule_time: scheduleTime } : {})
            })
        });
        if (!res.ok) throw new Error("Failed to schedule scan");
        const job = await res.json();
        VULNERABILITY_SCAN_JOBS = [job, ...VULNERABILITY_SCAN_JOBS];
        return job;
    } catch (e) {
        console.warn("Backend offline for scheduleVulnerabilityScan");
        throw e;
    }
};

export const runVulnerabilityScan = async (assetId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/assets/${assetId}/scan`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error("Failed to trigger scan");
        const data = await res.json();

        // Update local cache
        const index = ASSETS.findIndex(a => a.id === assetId);
        if (index > -1) {
            ASSETS[index].lastScanned = data.lastScanned;
        }
    } catch (e) {
        console.warn("Backend offline for runVulnerabilityScan");
    }
};

// Redundant mock updateUser removed to use the earlier implementation that supports backend sync.

export const resetPassword = async (_userId: string) => {
    return true;
};

export const generateApiKey = async (tenantId: string, name: string, userId: string) => {
    const res = await authFetch(`${API_BASE}/tenants/${tenantId}/api-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, userId }),
    });
    if (!res.ok) throw new Error(`Failed to generate API key: ${res.status}`);
    return res.json();
};

export const revokeApiKey = async (tenantId: string, keyId: string) => {
    const res = await authFetch(`${API_BASE}/tenants/${tenantId}/api-keys/${keyId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error(`Failed to revoke API key: ${res.status}`);
};

export const saveRole = async (role: Role) => {
    const index = ROLES.findIndex(r => r.id === role.id);
    if (index > -1) {
        ROLES[index] = role;
    } else {
        ROLES.push(role);
    }
    return role;
};

export const deleteRole = async (roleId: string) => {
    ROLES = ROLES.filter(r => r.id !== roleId);
};

export const updateSecurityCase = async (caseItem: SecurityCase) => {
    const index = SECURITY_CASES.findIndex(c => c.id === caseItem.id);
    if (index > -1) {
        SECURITY_CASES[index] = caseItem;
    } else {
        SECURITY_CASES.unshift(caseItem);
    }
    try {
        const res = await authFetch(`${API_BASE}/security-cases`, {
            method: caseItem.id.startsWith('case-') ? 'POST' : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(caseItem),
        });
        if (res.ok) return await res.json();
    } catch {
        // backend offline — local state already updated
    }
    return caseItem;
};





// --- AI Governance API ---

export const fetchAiModels = async (): Promise<AiModel[]> => {
    try {
        const res = await authFetch(`${API_BASE}/ai-governance/models`);
        if (!res.ok) throw new Error("Failed to fetch models");
        return await res.json();
    } catch { return []; }
};

export const registerAiModel = async (model: Partial<AiModel>) => {
    const res = await authFetch(`${API_BASE}/ai-governance/models`, {
        method: 'POST',
        body: JSON.stringify(model)
    });
    if (!res.ok) throw new Error("Failed to register model");
    return await res.json();
};

export const fetchAiPolicies = async (): Promise<AiPolicy[]> => {
    try {
        const res = await authFetch(`${API_BASE}/ai-governance/policies`);
        if (!res.ok) throw new Error("Failed to fetch policies");
        return await res.json();
    } catch { return []; }
};

export const createAiPolicy = async (policy: Partial<AiPolicy>) => {
    const res = await authFetch(`${API_BASE}/ai-governance/policies`, {
        method: 'POST',
        body: JSON.stringify(policy)
    });
    if (!res.ok) throw new Error("Failed to create policy");
    return await res.json();
};

export const checkModelCompliance = async (modelId: string): Promise<any> => {
    try {
        const res = await authFetch(`${API_BASE}/ai-governance/evaluate/${modelId}`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error("Failed");
        return await res.json();
    } catch (e) {
        console.error("Compliance check failed", e);
        return { error: "Failed to run compliance check" };
    }
};

export const checkModelComplianceExpert = async (modelId: string): Promise<any> => {
    try {
        const res = await authFetch(`${API_BASE}/ai-governance/expert-evaluate/${modelId}`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error("Expert scan failed");
        return await res.json();
    } catch (e) {
        console.error("Expert compliance check failed", e);
        return { error: "Failed to run expert compliance check" };
    }
};
// --- AI Governance API ---
// (Types are imported from ../types at the top of the file)

export const updateAiSystem = async (system: AiSystem) => {
    const index = AI_SYSTEMS.findIndex(s => s.id === system.id);
    if (index > -1) {
        AI_SYSTEMS[index] = system;
        return system;
    }
    return system;
};

export const addAiSystem = async (data: any, tenantId: string) => {
    const newSystem: AiSystem = {
        id: `ai-sys-${Date.now()}`,
        tenantId,
        ...data,
        lastAssessmentDate: new Date().toISOString().split('T')[0],
        fairnessMetrics: [],
        impactAssessment: { summary: 'Pending assessment.', initialRisks: [], mitigations: [] },
        risks: [],
        documentation: [],
        controls: { isEnabled: true, confidenceThreshold: 80, lastRetrainingTriggered: null },
        performanceData: [],
        securityAlerts: []
    };
    AI_SYSTEMS.push(newSystem);
    return newSystem;
};

export const promoteModel = async (modelId: string, toStage: ModelStage) => {
    const modelIndex = REGISTERED_MODELS.findIndex(m => m.id === modelId);
    if (modelIndex > -1) {
        REGISTERED_MODELS[modelIndex].stage = toStage;
        return REGISTERED_MODELS[modelIndex];
    }
    throw new Error("Model not found");
};

// --- Audit & Rollback ---

// --- Audit & Rollback ---

export const fetchAuditLogs = async () => {
    try {
        const res = await authFetch(`${API_BASE}/audit-logs`);
        if (!res.ok) throw new Error("Failed to fetch logs");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.warn("Backend audit logs unavailable");
        return [];
    }
};

export const rollbackChange = async (logId: string) => {
    const res = await authFetch(`${API_BASE}/audit/rollback/${logId}`, {
        method: 'POST'
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.message || "Rollback failed");
    }
    return await res.json();
};

export const fetchAutomationPolicies = async () => {
    try {
        const res = await authFetch(`${API_BASE}/automation-policies`);
        const data = await res.json();
        if (res.ok) return Array.isArray(data) ? data : (data.items || []);
    } catch (e) { /* fallback */ }
    return [];
};

export const updateAutomationPolicy = async (policy: AutomationPolicy) => {
    try {
        const res = await authFetch(`${API_BASE}/automation-policies`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(policy)
        });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn("Backend offline for updateAutomationPolicy");
    }
    const index = AUTOMATION_POLICIES.findIndex(p => p.id === policy.id);
    if (index > -1) AUTOMATION_POLICIES[index] = policy;
    return policy;
};

export const createAutomationPolicy = async (policy: Omit<AutomationPolicy, 'id'>): Promise<AutomationPolicy> => {
    try {
        const res = await authFetch(`${API_BASE}/automation-policies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(policy)
        });
        if (res.ok) {
            const created = await res.json();
            AUTOMATION_POLICIES = [created, ...AUTOMATION_POLICIES];
            return created;
        }
    } catch (e) {
        console.warn("Backend offline for createAutomationPolicy");
    }
    // Local fallback
    const newPolicy: AutomationPolicy = { ...policy, id: `policy-${Date.now()}` };
    AUTOMATION_POLICIES = [newPolicy, ...AUTOMATION_POLICIES];
    return newPolicy;
};




export const addNetworkDevice = async (data: any, tenantId: string) => {
    const newDevice: NetworkDevice = {
        id: `net-dev-${Date.now()}`,
        tenantId,
        ...data,
        status: 'Up',
        lastSeen: new Date().toISOString(),
        interfaces: [],
        configBackups: [],
        vulnerabilities: []
    };
    NETWORK_DEVICES.push(newDevice);
    return newDevice;
};

export const addCloudAccount = async (data: any, tenantId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/cloud-accounts`, {
            method: 'POST',
            body: JSON.stringify({
                provider: (data.provider || 'aws').toLowerCase(),
                name: data.name,
                account_id: data.accountId,
                credentials: data.credentials || {},
            }),
        });
        if (res.ok) {
            const saved = await res.json();
            const account: CloudAccount = {
                id: saved.id || `ca-${Date.now()}`,
                tenantId: saved.tenantId || tenantId,
                provider: data.provider,
                name: saved.name || data.name,
                accountId: data.accountId,
                status: 'Connected',
            };
            CLOUD_ACCOUNTS.push(account);
            return account;
        }
    } catch { /* backend offline — fall through to local */ }
    const local: CloudAccount = { id: `ca-${Date.now()}`, tenantId, ...data, status: 'Connected' };
    CLOUD_ACCOUNTS.push(local);
    return local;
};

export const saveAlertRule = async (rule: AlertRule): Promise<AlertRule> => {
    try {
        const isNew = !rule.id || ALERT_RULES.findIndex(r => r.id === rule.id) === -1;
        const method = isNew ? 'POST' : 'PUT';
        const url = isNew ? `${API_BASE}/alert-rules` : `${API_BASE}/alert-rules/${rule.id}`;
        const res = await authFetch(url, { method, body: JSON.stringify(rule) });
        if (res.ok) {
            const saved = await res.json();
            const index = ALERT_RULES.findIndex(r => r.id === saved.id);
            if (index > -1) ALERT_RULES[index] = saved; else ALERT_RULES.push(saved);
            return saved;
        }
    } catch (e) {
        console.warn('Backend offline for saveAlertRule', e);
    }
    const index = ALERT_RULES.findIndex(r => r.id === rule.id);
    if (index > -1) ALERT_RULES[index] = rule; else ALERT_RULES.push(rule);
    return rule;
};

export const deleteAlertRule = async (id: string): Promise<void> => {
    try {
        await authFetch(`${API_BASE}/alert-rules/${id}`, { method: 'DELETE' });
    } catch (e) {
        console.warn('Backend offline for deleteAlertRule', e);
    }
    ALERT_RULES = ALERT_RULES.filter(r => r.id !== id);
};

export const saveIntegration = async (integration: Integration) => {
    try {
        const res = await fetch(`${API_BASE}/data/integrations/${integration.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(integration)
        });
        if (res.ok) {
            const saved = await res.json();
            // Update local cache too
            const index = INTEGRATIONS.findIndex(i => i.id === integration.id);
            if (index > -1) INTEGRATIONS[index] = saved;
            return saved;
        }
        throw new Error("Backend returned error");
    } catch (e) {
        console.warn("Backend offline for saveIntegration");
        const index = INTEGRATIONS.findIndex(i => i.id === integration.id);
        if (index > -1) {
            INTEGRATIONS[index] = integration;
        }
        return integration;
    }
};
export const fetchInfrastructure = async (): Promise<{ db: DatabaseSettings | null, llm: LlmSettings | null }> => {
    try {
        const [dbRes, llmRes] = await Promise.all([
            authFetch(`${API_BASE}/settings/database`),
            authFetch(`${API_BASE}/settings/llm`)
        ]);

        const db = dbRes.ok ? await dbRes.json() : null;
        const llm = llmRes.ok ? await llmRes.json() : null;

        if (db && Object.keys(db).length > 0) DATABASE_SETTINGS = db;
        if (llm && Object.keys(llm).length > 0) LLM_SETTINGS = llm;

        return { db: DATABASE_SETTINGS, llm: LLM_SETTINGS };
    } catch (e) {
        console.error("Failed to fetch infrastructure settings:", e);
        return { db: DATABASE_SETTINGS, llm: LLM_SETTINGS };
    }
};

export const saveInfrastructure = async (updates: { db?: DatabaseSettings, llm?: LlmSettings }) => {
    try {
        if (updates.db) {
            const res = await authFetch(`${API_BASE}/settings/database`, {
                method: 'POST',
                body: JSON.stringify(updates.db)
            });
            if (res.ok) DATABASE_SETTINGS = updates.db;
            else console.error("Failed to save DB settings:", await res.text());
        }
        if (updates.llm) {
            const res = await authFetch(`${API_BASE}/settings/llm`, {
                method: 'POST',
                body: JSON.stringify(updates.llm)
            });
            if (res.ok) LLM_SETTINGS = updates.llm;
            else console.error("Failed to save LLM settings:", await res.text());
        }
    } catch (e) {
        console.error("Failed to save settings", e);
    }
    return { db: DATABASE_SETTINGS, llm: LLM_SETTINGS };
};

export const saveDataSource = async (source: DataSource): Promise<DataSource> => {
    try {
        const isNew = !source.id || DATA_SOURCES.findIndex(ds => ds.id === source.id) === -1;
        const method = isNew ? 'POST' : 'PUT';
        const url = isNew ? `${API_BASE}/data-sources` : `${API_BASE}/data-sources/${source.id}`;
        const res = await authFetch(url, { method, body: JSON.stringify(source) });
        if (res.ok) {
            const saved = await res.json();
            const index = DATA_SOURCES.findIndex(ds => ds.id === saved.id);
            if (index > -1) DATA_SOURCES[index] = saved; else DATA_SOURCES.push(saved);
            return saved;
        }
    } catch (e) {
        console.warn('Backend offline for saveDataSource', e);
    }
    const index = DATA_SOURCES.findIndex(ds => ds.id === source.id);
    if (index > -1) DATA_SOURCES[index] = source; else DATA_SOURCES.push(source);
    return source;
};

export const deleteDataSource = async (id: string): Promise<void> => {
    try {
        await authFetch(`${API_BASE}/data-sources/${id}`, { method: 'DELETE' });
    } catch (e) {
        console.warn('Backend offline for deleteDataSource', e);
    }
    DATA_SOURCES = DATA_SOURCES.filter(ds => ds.id !== id);
};

export const testDataSourceConnection = async (source: DataSource): Promise<{ message: string }> => {
    try {
        const res = await authFetch(`${API_BASE}/data-sources/${source.id}/test`, { method: 'POST' });
        if (res.ok) return await res.json();
        const err = await res.json().catch(() => ({ detail: 'Connection test failed' }));
        throw new Error(err.detail || 'Connection test failed');
    } catch (e: any) {
        if (e?.message?.startsWith('Connection')) throw e;
        console.warn('Backend offline for testDataSourceConnection', e);
        throw new Error('Backend offline — cannot test connection.');
    }
};

export const fetchIntegrationConfigs = async (): Promise<Integration[]> => {
    try {
        const response = await authFetch(`${API_BASE}/integrations/configs`);
        if (!response.ok) throw new Error('Failed to fetch integration configs');
        return await response.json();
    } catch (error) {
        console.error('Error fetching integration configs:', error);
        return [];
    }
};

export const saveIntegrationConfig = async (config: any): Promise<{ success: boolean; message: string }> => {
    try {
        const response = await authFetch(`${API_BASE}/integrations/config`, {
            method: 'POST',
            body: JSON.stringify(config)
        });
        if (!response.ok) throw new Error('Failed to save integration config');
        return await response.json();
    } catch (error) {
        console.error('Error saving integration config:', error);
        throw error;
    }
};

export const deleteIntegrationConfig = async (id: string): Promise<{ success: boolean; message: string }> => {
    try {
        const response = await authFetch(`${API_BASE}/integrations/config/${id}`, {
            method: 'DELETE',
        });
        if (!response.ok) throw new Error('Failed to delete integration config');
        return await response.json();
    } catch (error) {
        console.error('Error deleting integration config:', error);
        throw error;
    }
};

export const testSiemConnection = async (platform: string, config: any): Promise<{ success: boolean; error?: string; message?: string }> => {
    try {
        const response = await fetch(`${API_BASE}/integrations/siem/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform, config })
        });
        if (!response.ok) throw new Error('Failed to test SIEM connection');
        return await response.json();
    } catch (error) {
        console.error('Error testing SIEM connection:', error);
        throw error;
    }
};

export const testLlmConnection = async (settings: Record<string, string>) => {
    // Uses the backend proxy — the API key is never used client-side
    const res = await authFetch(`${API_BASE}/ai/test-connection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'LLM connection test failed');
    }
    return res.json();
};

export const fetchAiTools = async () => {
    const res = await authFetch(`${API_BASE}/settings/ai-tools`);
    return res.ok ? res.json() : [];
};

export const addAiTool = async (tool: Record<string, string>) => {
    const res = await authFetch(`${API_BASE}/settings/ai-tools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(tool),
    });
    if (!res.ok) throw new Error('Failed to add AI tool');
    return res.json();
};

export const deleteAiTool = async (toolId: string) => {
    const res = await authFetch(`${API_BASE}/settings/ai-tools/${toolId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete AI tool');
    return res.json();
};

export const testDatabaseConnection = async (settings: DatabaseSettings) => {
    const res = await authFetch(`${API_BASE}/settings/test-db-connection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Connection test failed');
    }
    return res.json();
};

export const fetchTraces = async (tenantId?: string): Promise<Trace[]> => {
    try {
        const url = tenantId
            ? `${API_BASE}/tracing/traces?tenant_id=${tenantId}`
            : `${API_BASE}/tracing/traces`;
        const response = await authFetch(url);
        if (!response.ok) throw new Error('Failed to fetch traces');
        const data = await response.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (error) {
        console.error('Error fetching traces:', error);
        return [];
    }
};

export const fetchServiceMap = async (tenantId?: string): Promise<ServiceMap | null> => {
    try {
        const url = tenantId
            ? `${API_BASE}/tracing/service-map?tenant_id=${tenantId}`
            : `${API_BASE}/tracing/service-map`;
        const response = await authFetch(url);
        if (!response.ok) throw new Error('Failed to fetch service map');
        return await response.json();
    } catch (error) {
        console.error('Error fetching service map:', error);
        return null;
    }
};


export const scanArtifactWithVirusTotal = async (artifact: string, type: 'ip' | 'hash' | 'domain'): Promise<ThreatIntelResult> => {
    try {
        const res = await authFetch(`${API_BASE}/threat-intel/scan`, {
            method: 'POST',
            body: JSON.stringify({ artifact, type }),
        });
        if (res.ok) {
            const data = await res.json();
            return {
                id: data.id || `vt-scan-${Date.now()}`,
                artifact: data.artifact || artifact,
                artifactType: data.artifact_type || type,
                source: data.source || 'VirusTotal',
                verdict: data.verdict || 'Unknown',
                detectionRatio: data.detection_ratio || '0/0',
                scanDate: data.scan_date || new Date().toISOString(),
                reportUrl: data.report_url || '',
            };
        }
    } catch (e) {
        console.error('scanArtifactWithVirusTotal failed:', e);
    }
    // Offline fallback — surface unknown rather than a false "Harmless"
    return {
        id: `vt-offline-${Date.now()}`,
        artifact,
        artifactType: type,
        source: 'VirusTotal',
        verdict: 'Unknown',
        detectionRatio: 'N/A',
        scanDate: new Date().toISOString(),
        reportUrl: '',
    };
};

// --- AI Functions (Mock or Real using GoogleGenAI) ---


export const generatePlaybook = async (prompt: string): Promise<Playbook> => {
    try {
        const res = await authFetch(`${API_BASE}/ai/generate-playbook`, {
            method: 'POST',
            body: JSON.stringify({ prompt })
        });
        if (!res.ok) throw new Error("Failed to generate playbook");
        return await res.json();
    } catch (e) {
        console.error("Error generating playbook:", e);
        throw e;
    }
};

export const generateRiskRemediationPlan = async function* (system: AiSystem, risk: any): AsyncGenerator<AgenticStep> {
    const prompt = `You are a security AI. Generate a step-by-step remediation plan for the following risk.
System: ${system?.name || 'Unknown'}
Risk: ${risk?.title || 'Unknown risk'}
Severity: ${risk?.severity || 'Unknown'}
Description: ${risk?.description || ''}

Respond with a JSON array of steps. Each step has: type ("goal"|"thought"|"action"|"observation"), content (string).`;

    try {
        const res = await authFetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            body: JSON.stringify({ message: prompt, context: { currentView: 'ai-governance' } }),
        });
        if (res.ok) {
            const data = await res.json();
            const raw: string = typeof data === 'string' ? data : (data.response || data.message || '');
            // Try to parse JSON array from AI response
            const match = raw.match(/\[[\s\S]*\]/);
            if (match) {
                try {
                    const steps: Array<{ type: string; content: string }> = JSON.parse(match[0]);
                    for (const step of steps) {
                        yield { ...step, timestamp: new Date().toISOString() } as AgenticStep;
                    }
                    return;
                } catch { /* fall through to text parsing */ }
            }
            // Fallback: emit AI response as a single observation step
            yield { type: 'observation', content: raw, timestamp: new Date().toISOString() } as AgenticStep;
            return;
        }
    } catch (e) {
        console.error('generateRiskRemediationPlan fetch failed:', e);
    }
    // Offline fallback — emit a goal so the UI isn't blank
    yield { type: 'goal', content: `Mitigate risk: ${risk?.title || 'Unknown'}`, timestamp: new Date().toISOString() } as AgenticStep;
    yield { type: 'observation', content: 'AI backend unavailable — manual review required.', timestamp: new Date().toISOString() } as AgenticStep;
};

export const generateAgenticPlan = async function* (agent: Agent): AsyncGenerator<AgenticStep> {
    const prompt =
        `You are an autonomous SOC agent. Generate a ReAct-style remediation plan for the following agent.\n` +
        `Agent: ${agent.hostname} (${agent.ipAddress}), status: ${agent.status}.\n` +
        `Return a JSON array of steps, each with "type" ("goal"|"thought"|"action"|"observation") and "content".`;

    try {
        const res = await authFetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            body: JSON.stringify({ message: prompt, context: { currentView: 'agent-detail' } }),
        });
        if (res.ok) {
            const data = await res.json();
            const raw: string = data.response || data.message || '';
            const match = raw.match(/\[[\s\S]*\]/);
            if (match) {
                try {
                    const steps: Array<{ type: string; content: string }> = JSON.parse(match[0]);
                    for (const step of steps) {
                        yield { ...step, timestamp: new Date().toISOString() } as AgenticStep;
                    }
                    return;
                } catch { /* fall through */ }
            }
            yield { type: 'observation', content: raw, timestamp: new Date().toISOString() } as AgenticStep;
            return;
        }
    } catch (e) {
        console.error('generateAgenticPlan fetch failed:', e);
    }
    // Offline fallback
    yield { type: 'goal', content: `Restore agent health on ${agent.hostname}`, timestamp: new Date().toISOString() } as AgenticStep;
    yield { type: 'observation', content: 'AI backend unavailable — manual review required.', timestamp: new Date().toISOString() } as AgenticStep;
};

// Strip VoiceBot-only annotations from AI chat responses used in analysis panels.
// [NAVIGATE:x] and [AUTO_CONTINUE] are chat/voice directives that must not appear in text UI.
// The degraded notice is extracted as a flag so the UI can render it as a proper banner.
function sanitizeAnalysisResponse(raw: string): { content: string; limitedMode: boolean } {
    const limitedMode = raw.includes('AI running in limited mode');
    const content = raw
        .replace(/\[?NAVIGATE:[\w-]+\]?/gi, '')
        .replace(/\[?AUTO_CONTINUE\]?/gi, '')
        .replace(/\n*⚠️ \*\*AI running in limited mode\*\*[\s\S]*/i, '')
        .trim();
    return { content, limitedMode };
}

export const fetchHealthAnalysis = async (metrics: Metric[], alerts: Alert[]) => {
    const summary = {
        metric_count: metrics.length,
        alert_count: alerts.length,
        critical_alerts: alerts.filter(a => a.severity === 'Critical').length,
        top_metrics: metrics.slice(0, 5).map(m => ({ title: m.title, value: m.value, change: m.change })),
    };
    try {
        const res = await authFetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            body: JSON.stringify({
                message: `Analyze this system health data and provide a concise assessment with actionable recommendations:\n${JSON.stringify(summary, null, 2)}`,
                context: { currentView: 'dashboard' },
            }),
        });
        if (res.ok) {
            const data = await res.json();
            const raw: string = data.response || data.message || '';
            const { content, limitedMode } = sanitizeAnalysisResponse(raw);
            return { analysis: content, recommendations: [], limitedMode };
        }
    } catch (e) { console.error('fetchHealthAnalysis failed:', e); }
    return { analysis: 'Health analysis unavailable — AI backend unreachable.', recommendations: [], limitedMode: false };
};

export const fetchSecurityAnalysis = async (events: SecurityEvent[]) => {
    const summary = {
        event_count: events.length,
        critical: events.filter(e => e.severity === 'Critical').length,
        high: events.filter(e => e.severity === 'High').length,
        types: [...new Set(events.map(e => e.type))].slice(0, 10),
        recent: events.slice(0, 3).map(e => ({ type: e.type, severity: e.severity, description: e.description })),
    };
    try {
        const res = await authFetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            body: JSON.stringify({
                message: `You are a security analyst. Analyze these security events and provide a threat assessment with prioritized recommendations:\n${JSON.stringify(summary, null, 2)}`,
                context: { currentView: 'vulnerabilities' },
            }),
        });
        if (res.ok) {
            const data = await res.json();
            const raw: string = data.response || data.message || '';
            const { content, limitedMode } = sanitizeAnalysisResponse(raw);
            return { analysis: content, recommendations: [], limitedMode };
        }
    } catch (e) { console.error('fetchSecurityAnalysis failed:', e); }
    return { analysis: 'Security analysis unavailable — AI backend unreachable.', recommendations: [], limitedMode: false };
};

export const generateCSPMRemediation = async (finding: CSPMFinding) => {
    try {
        const res = await authFetch(`${API_BASE}/ai/remediation/cspm`, {
            method: 'POST',
            body: JSON.stringify(finding)
        });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
    return { remediation: "Remediation plan unavailable" };
};

export const generateIacCode = async (finding: CSPMFinding) => {
    try {
        const res = await authFetch(`${API_BASE}/ai/remediation/iac`, {
            method: 'POST',
            body: JSON.stringify(finding)
        });
        if (res.ok) return await res.json();
    } catch (e) { console.error(e); }
    return { code: "# IaC code generation unavailable" };
};



export const getChatAssistantResponse = async (input: string, context: any): Promise<string> => {
    try {
        const res = await authFetch(`${API_BASE}/ai/chat`, {
            method: 'POST',
            body: JSON.stringify({ message: input, context })
        });
        if (res.ok) {
            const data = await res.json();
            return data.response;
        }
    } catch (e) {
        console.error("Error chatting with AI:", e);
    }
    return `AI assistant unavailable. You asked: "${input}".`;
};

/**
 * Stream AI chat response via SSE.
 * Calls onChunk for each text token, onDone when the stream ends,
 * onError if the connection fails.
 */
export const streamChatAssistantResponse = (
    input: string,
    context: any,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: string) => void
): (() => void) => {
    let cancelled = false;

    (async () => {
        try {
            const token = sessionStorage.getItem('token') || '';
            const res = await fetch(`${API_BASE}/ai/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ message: input, context }),
                credentials: 'include',
            });

            if (!res.ok || !res.body) {
                onError(`Server error ${res.status}`);
                return;
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (!cancelled) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() ?? '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const raw = line.slice(6).trim();
                    if (raw === '[DONE]') { onDone(); return; }
                    try {
                        const parsed = JSON.parse(raw);
                        if (parsed.error) { onError(parsed.error); return; }
                        if (parsed.chunk) onChunk(parsed.chunk);
                    } catch { /* ignore malformed SSE frame */ }
                }
            }
            onDone();
        } catch (e: any) {
            if (!cancelled) onError(e?.message ?? 'Stream connection failed');
        }
    })();

    return () => { cancelled = true; };
};

export const executePlaybook = async function* (playbookId: string, targetId: string, targetType: string): AsyncGenerator<PlaybookExecutionStep> {
    const ts = () => new Date().toISOString();
    yield { timestamp: ts(), message: `Initiating playbook ${playbookId} on ${targetType} ${targetId}…`, status: 'running' };
    let executionId: string | null = null;
    try {
        const res = await authFetch(`${API_BASE}/playbooks/${playbookId}/execute`, {
            method: 'POST',
            body: JSON.stringify({ target_id: targetId, target_type: targetType, executed_by: 'frontend' }),
        });
        if (!res.ok) {
            yield { timestamp: ts(), message: `Server returned ${res.status}`, status: 'error' };
            return;
        }
        const data = await res.json();
        executionId = data.execution_id ?? null;

        // If no execution_id returned, surface the final status and stop
        if (!executionId) {
            yield { timestamp: ts(), message: `Execution complete: ${data.status ?? 'ok'}`, status: data.status === 'error' ? 'error' : 'success' };
            return;
        }
    } catch (e) {
        yield { timestamp: ts(), message: `Execution failed: ${e instanceof Error ? e.message : 'Unknown error'}`, status: 'error' };
        return;
    }

    // Poll for step-by-step results using execution_id
    yield { timestamp: ts(), message: `Execution queued (id: ${executionId}) — streaming results…`, status: 'running' };
    const POLL_INTERVAL_MS = 1200;
    const MAX_POLLS = 120; // 2 minutes max
    let seenStepCount = 0;

    for (let poll = 0; poll < MAX_POLLS; poll++) {
        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
        try {
            const r = await authFetch(`${API_BASE}/playbooks/enhanced/executions/${executionId}`);
            if (!r.ok) break;
            const exec = await r.json();
            const steps: any[] = exec.steps ?? [];

            // Yield any steps we haven't surfaced yet
            for (let i = seenStepCount; i < steps.length; i++) {
                const step = steps[i];
                const stepStatus = step.status === 'completed' ? 'success'
                    : step.status === 'failed' ? 'error' : 'running';
                const detail = step.output ? ` → ${JSON.stringify(step.output).slice(0, 80)}` : '';
                yield { timestamp: step.started_at ?? ts(), message: `[${step.name ?? `Step ${step.index}`}] ${step.status}${detail}`, status: stepStatus };
            }
            seenStepCount = steps.length;

            const terminal = exec.status === 'completed' || exec.status === 'failed' || exec.status === 'error';
            if (terminal && seenStepCount === steps.length) {
                yield { timestamp: ts(), message: `Playbook ${exec.status}`, status: exec.status === 'completed' ? 'success' : 'error' };
                return;
            }
        } catch {
            // transient poll error — keep trying
        }
    }
    yield { timestamp: ts(), message: 'Polling timed out — check the execution log for results', status: 'error' };
};

export const togglePlaybook = async (playbookId: string): Promise<{ id: string; enabled: boolean } | null> => {
    try {
        const res = await authFetch(`${API_BASE}/playbooks/${playbookId}/toggle`, { method: 'PATCH' });
        if (res.ok) return await res.json();
    } catch (e) {
        console.error('togglePlaybook failed:', e);
    }
    return null;
};

export const createAlert = async (alert: Record<string, unknown>): Promise<Record<string, unknown> | null> => {
    try {
        const res = await authFetch(`${API_BASE}/alerts`, {
            method: 'POST',
            body: JSON.stringify(alert),
        });
        if (res.ok) return await res.json();
    } catch (e) {
        console.error('createAlert failed:', e);
    }
    return null;
};

export const assignAlert = async (alertId: string, assignedTo: string): Promise<boolean> => {
    try {
        const res = await authFetch(`${API_BASE}/alerts/${alertId}/assign`, {
            method: 'PATCH',
            body: JSON.stringify({ assigned_to: assignedTo }),
        });
        return res.ok;
    } catch (e) {
        console.error('assignAlert failed:', e);
        return false;
    }
};

export const submitAiFeedback = async (feedback: { prompt_id?: string; rating: number; helpful: boolean; comment?: string }): Promise<boolean> => {
    try {
        const res = await authFetch(`${API_BASE}/ai/feedback`, {
            method: 'POST',
            body: JSON.stringify(feedback),
        });
        return res.ok;
    } catch (e) {
        console.error('submitAiFeedback failed:', e);
        return false;
    }
};

export const recordCorrelationFalsePositive = async (correlationId: string): Promise<boolean> => {
    try {
        const res = await authFetch(`${API_BASE}/correlations/false-positive/${correlationId}`, {
            method: 'POST',
        });
        return res.ok;
    } catch (e) {
        console.error('recordCorrelationFalsePositive failed:', e);
        return false;
    }
};

// --- REAL BACKEND INTEGRATION METHODS ---

export const dispatchAgentTask = async (description: string, agentId: string = 'default') => {
    try {
        const res = await authFetch(`${API_BASE}/agent/dispatch`, {
            method: 'POST',
            body: JSON.stringify({ description, agentId })
        });
        return await res.json();
    } catch (e) {
        console.error("Agent Dispatch Failed", e);
        return { success: false, error: "Network Error" };
    }
};

export const pollAgentTask = async (taskId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/agent/tasks/${taskId}`);
        return await res.json();
    } catch (e) {
        return { status: "UNKNOWN" };
    }
};

export const ingestKnowledge = async (content: string, source: string) => {
    try {
        const res = await authFetch(`${API_BASE}/knowledge/ingest`, {
            method: 'POST',
            body: JSON.stringify({ content, source })
        });
        return await res.json();
    } catch (e) { return { success: false, error: e }; }
};

export const queryKnowledge = async (query: string) => {
    try {
        const res = await authFetch(`${API_BASE}/knowledge/query`, {
            method: 'POST',
            body: JSON.stringify({ query })
        });
        return await res.json();
    } catch (e) { return { success: false }; }
};

export const listPrompts = async () => {
    try {
        const res = await authFetch(`${API_BASE}/prompts`);
        if (!res.ok) return [];
        return await res.json();
    } catch (e) { return []; }
};

export const createPrompt = async (prompt: any) => {
    try {
        const res = await authFetch(`${API_BASE}/prompts`, {
            method: 'POST',
            body: JSON.stringify(prompt)
        });
        return await res.json();
    } catch (e) { return { success: false }; }
};

export const startRemoteSession = async (agentId: string, protocol: string, type: 'shell' | 'desktop' = 'shell') => {
    try {
        const res = await authFetch(`${API_BASE}/remote/session/start`, {
            method: 'POST',
            body: JSON.stringify({ agent_id: agentId, protocol, type })
        });
        return await res.json();
    } catch (e) {
        console.error("Error starting remote session:", e);
        return { error: e };
    }
};

export const triggerNetworkScan = async (agentId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/agents/${agentId}/discovery/scan`, {
            method: 'POST'
        });
        return await res.json();
    } catch (e) { console.error("Error triggering network scan", e); return { success: false }; }
};

export const triggerServerNetworkScan = async (scanAllNetworks: boolean = true, subnet?: string) => {
    try {
        let url = `${API_BASE}/network-devices/scan?scan_all_networks=${scanAllNetworks}`;
        if (subnet) {
            url += `&subnet=${subnet}`;
        }
        const res = await authFetch(url, {
            method: 'POST'
        });
        return await res.json();
    } catch (e) { console.error("Error triggering server network scan", e); return { success: false }; }
};

export const fetchNetworkSubnets = async (): Promise<string[]> => {
    try {
        const res = await authFetch(`${API_BASE}/network-devices/subnets`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching subnets", e);
        return [];
    }
};


export const fetchNetworkDevices = async () => {
    try {
        const res = await authFetch(`${API_BASE}/network-devices`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching network devices", e);
        return [];
    }
};
// --- Swarm Visualization ---
export const fetchSwarmTopology = async () => {
    try {
        const res = await authFetch(`${API_BASE}/swarm/topology`);
        if (!res.ok) throw new Error('Failed to fetch topology');
        return await res.json();
    } catch (e) {
        console.warn("Swarm topology fetch failed, returning empty");
        return { nodes: [], links: [] };
    }
};

// --- Notifications ---
export const getNotifications = async () => {
    try {
        const response = await authFetch(`${API_BASE}/notifications`);
        if (!response.ok) return [];
        return await response.json();
    } catch (err) {
        console.error("Error fetching notifications:", err);
        return [];
    }
};

// --- FinOps ---




// --- Compliance Reports ---
export const generateComplianceReport = async (frameworkId: string) => {
    const formData = new FormData();
    formData.append('framework_id', frameworkId);
    const res = await authFetch(`${API_BASE}/compliance/reports/generate`, { method: 'POST', body: formData });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Report generation failed' }));
        throw new Error(err.detail || 'Report generation failed');
    }
    return await res.json();
};

export const generateExcelComplianceReport = async (frameworkId: string) => {
    const formData = new FormData();
    formData.append('framework_id', frameworkId);
    const res = await authFetch(`${API_BASE}/compliance/reports/generate/excel`, { method: 'POST', body: formData });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Excel report generation failed' }));
        throw new Error(err.detail || 'Excel report generation failed');
    }
    return await res.json();
};

export const generatePDFComplianceReport = async (frameworkId: string) => {
    const formData = new FormData();
    formData.append('framework_id', frameworkId);
    const res = await authFetch(`${API_BASE}/compliance/reports/generate/pdf`, { method: 'POST', body: formData });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'PDF report generation failed' }));
        throw new Error(err.detail || 'PDF report generation failed');
    }
    return await res.json();
};

export const generateAllComplianceReport = async (format: 'csv' | 'excel') => {
    const res = await authFetch(`${API_BASE}/compliance/reports/generate/all/${format}`, { method: 'POST' });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'All-frameworks report generation failed' }));
        throw new Error(err.detail || 'All-frameworks report generation failed');
    }
    return await res.json();
};

export const fetchComplianceReports = async (frameworkId?: string) => {
    try {
        const url = frameworkId
            ? `${API_BASE}/compliance/reports?framework_id=${encodeURIComponent(frameworkId)}`
            : `${API_BASE}/compliance/reports`;
        const res = await authFetch(url);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching compliance reports:", e);
        return [];
    }
};

export const downloadComplianceReport = async (filename: string): Promise<void> => {
    const res = await authFetch(`${API_BASE}/compliance/reports/download/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error('Failed to download report');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
};

// --- Analytical Reports ---
export const fetchExecutiveSummaryReport = async () => {
    try {
        const res = await authFetch(`${API_BASE}/reports/executive-summary`);
        if (!res.ok) throw new Error('Failed');
        return await res.json();
    } catch (e) { console.error('Executive summary error', e); return null; }
};

export const fetchSlaReport = async (framework = 'SOC2') => {
    try {
        const res = await authFetch(`${API_BASE}/reports/sla-compliance?framework=${framework}`);
        if (!res.ok) throw new Error('Failed');
        return await res.json();
    } catch (e) { console.error('SLA report error', e); return null; }
};

export const fetchVulnerabilityExposureReport = async () => {
    try {
        const res = await authFetch(`${API_BASE}/reports/vulnerability-exposure`);
        if (!res.ok) throw new Error('Failed');
        return await res.json();
    } catch (e) { console.error('Vuln report error', e); return null; }
};

export const fetchChangeManagementReport = async () => {
    try {
        const res = await authFetch(`${API_BASE}/reports/change-management`);
        if (!res.ok) throw new Error('Failed');
        return await res.json();
    } catch (e) { console.error('Change mgmt report error', e); return null; }
};

// --- Security Simulations ---
export const triggerProcessInjectionSimulation = async (agentId: string, technique: string, target: string) => {
    try {
        const res = await fetch(`${API_BASE}/simulation/process-injection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId, technique, target })
        });
        return await res.json();
    } catch (e) {
        console.error("Error triggering simulation:", e);
        throw e;
    }
};

export const fetchSimulationHistory = async () => {
    try {
        const res = await fetch(`${API_BASE}/simulation/history`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching simulation history:", e);
        return [];
    }
};



export const fetchServicePricing = async () => {
    try {
        const res = await authFetch(`${API_BASE}/finops/pricing`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching pricing:", e);
        return [];
    }
};

export const updateServicePricing = async (pricing: any[]) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/pricing`, {
            method: 'POST',
            body: JSON.stringify(pricing)
        });
        return await res.json();
    } catch (e) {
        console.error("Error updating pricing:", e);
        throw e;
    }
};

export const createServicePricing = async (serviceData: any) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/pricing/service`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(serviceData)
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to create service");
        }

        return await res.json();
    } catch (e) {
        console.error("Error creating service:", e);
        throw e;
    }
};

export const updateSingleServicePricing = async (serviceId: string, updates: any) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/pricing/service/${serviceId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to update service");
        }

        return await res.json();
    } catch (e) {
        console.error("Error updating service:", e);
        throw e;
    }
};

export const deleteAsset = async (assetId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/assets/${assetId}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to delete asset");
        }

        return await res.json();
    } catch (e) {
        console.error("Error deleting asset:", e);
        throw e;
    }
};



export const deleteServicePricing = async (serviceId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/finops/pricing/service/${serviceId}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Failed to delete service");
        }

        return await res.json();
    } catch (e) {
        console.error("Error deleting service:", e);
        throw e;
    }
};



// --- Persistence Detection ---
export const triggerPersistenceScan = async (agentId: string) => {
    try {
        const res = await fetch(`${API_BASE}/persistence/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agentId })
        });
        return await res.json();
    } catch (e) {
        console.error("Error triggering persistence scan:", e);
        throw e;
    }
};

export const fetchPersistenceResults = async (agentId: string) => {
    try {
        const res = await fetch(`${API_BASE}/persistence/results/${agentId}`);
        if (res.ok) return await res.json();
        return { findings: [], count: 0 };
    } catch (e) {
        console.error("Error fetching persistence results:", e);
        return { findings: [], count: 0 };
    }
};

// --- System Health ---
export const fetchSystemRoutes = async () => {
    try {
        const res = await authFetch(`${API_BASE}/system/routes`);
        if (!res.ok) throw new Error("Failed to fetch routes");
        return await res.json();
    } catch (e) {
        console.warn("Backend offline for system routes");
        return [];
    }
};

export const remediateRoute = async (route: string, error: string) => {
    try {
        const res = await authFetch(`${API_BASE}/system/remediate`, {
            method: 'POST',
            body: JSON.stringify({ route, error })
        });
        if (!res.ok) throw new Error("Failed to remediate");
        return await res.json();
    } catch (e) {
        console.error("Remediation failed", e);
        throw e;
    }
};
export const fetchPendingApprovals = async (userEmail: string) => {
    try {
        const res = await authFetch(`${API_BASE}/approvals/pending?user_email=${encodeURIComponent(userEmail)}`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching pending approvals:", e);
        return [];
    }
};

export const fetchApprovalHistory = async () => {
    try {
        const res = await authFetch(`${API_BASE}/approvals/history`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching approval history:", e);
        return [];
    }
};

export const submitApprovalDecision = async (requestId: string, userEmail: string, decision: 'approve' | 'reject', comments: string) => {
    try {
        const res = await authFetch(`${API_BASE}/approvals/${requestId}/decide`, {
            method: 'POST',
            body: JSON.stringify({ user_email: userEmail, decision, comments })
        });
        return await res.json();
    } catch (e) {
        console.error("Error submitting approval decision:", e);
        throw e;
    }
};

export const markNotificationAsRead = async (notificationId: string) => {
    try {
        const response = await authFetch(`${API_BASE}/notifications/${notificationId}/read`, { method: 'PUT' });
        return await response.json();
    } catch (err) {
        console.error("Error marking notification read:", err);
        return { success: false };
    }
};

export const markAllNotificationsAsRead = async (notificationIds: string[]) => {
    try {
        const res = await authFetch(`${API_BASE}/notifications/read-all`, {
            method: 'PUT',
            body: JSON.stringify(notificationIds)
        });
        if (!res.ok) throw new Error("Failed to mark all as read");
        return await res.json();
    } catch (err) {
        console.error("Error marking all notifications read:", err);
        return { success: false };
    }
};

// Aliases for backward compatibility
export const markNotificationRead = markNotificationAsRead;
export const markAllNotificationsRead = markAllNotificationsAsRead;

export const deleteNotification = async (notificationId: string) => {
    try {
        const response = await authFetch(`${API_BASE}/notifications/${notificationId}`, { method: 'DELETE' });
        return await response.json();
    } catch (err) {
        console.error("Error deleting notification:", err);
        return { success: false };
    }
};

export const getNotificationConfig = async () => {
    try {
        const response = await authFetch(`${API_BASE}/notifications/config`);
        if (!response.ok) return [];
        return await response.json();
    } catch (err) {
        console.error("Error fetching notification config:", err);
        return [];
    }
};

export const updateNotificationConfig = async (config: any) => {
    try {
        const response = await authFetch(`${API_BASE}/notifications/config`, {
            method: 'POST',
            body: JSON.stringify(config),
        });
        return await response.json();
    } catch (err) {
        console.error("Error updating notification config:", err);
        return { success: false };
    }
};

// --- Maintenance Windows ---
export const getMaintenanceWindows = async (tenantId: string = "default") => {
    try {
        const response = await authFetch(`${API_BASE}/maintenance/windows?tenant_id=${tenantId}`);
        if (!response.ok) return [];
        const data = await response.json();
        return Array.isArray(data) ? data : [];
    } catch (err) {
        console.error("Error fetching maintenance windows:", err);
        return [];
    }
};

export const createMaintenanceWindow = async (windowData: any) => {
    try {
        const response = await authFetch(`${API_BASE}/maintenance/windows`, {
            method: 'POST',
            body: JSON.stringify(windowData)
        });
        return await response.json();
    } catch (err) {
        console.error("Error creating maintenance window:", err);
        return { success: false };
    }
};

export const deleteMaintenanceWindow = async (windowId: string) => {
    try {
        const response = await authFetch(`${API_BASE}/maintenance/windows/${windowId}`, {
            method: 'DELETE'
        });
        return await response.json();
    } catch (err) {
        console.error("Error deleting maintenance window:", err);
        return { success: false };
    }
};

export const checkMaintenanceStatus = async (tenantId: string = "default") => {
    try {
        const response = await authFetch(`${API_BASE}/maintenance/check?tenant_id=${tenantId}`);
        if (!response.ok) return { is_in_window: false };
        return await response.json();
    } catch (err) {
        console.error("Error checking maintenance status:", err);
        return { is_in_window: false };
    }
};



export const evaluateModelCompliance = async (modelId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/ai-governance/evaluate/${modelId}`, {
            method: 'POST'
        });
        return await res.json();
    } catch (e) {
        console.error("Error evaluating model compliance:", e);
        throw e;
    }
};





export const fetchNetworkTopologyImage = async (): Promise<Blob> => {
    try {
        const res = await authFetch(`${API_BASE}/network-devices/topology-image`);
        if (!res.ok) throw new Error("Failed to fetch topology image");
        return await res.blob();
    } catch (e) {
        console.error("Error fetching topology image:", e);
        throw e;
    }
};

// --- Zero Trust & Quantum Security ---

export const fetchDeviceTrustScores = async (): Promise<DeviceTrustScore[]> => {
    try {
        const res = await authFetch(`${API_BASE}/zero-trust/device-trust-scores`);
        const data = await res.json();
        if (!res.ok) throw new Error("Failed to fetch device trust scores");
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching device trust scores:", e);
        return [];
    }
};

export const fetchSessionRisks = async (): Promise<UserSessionRisk[]> => {
    try {
        const res = await authFetch(`${API_BASE}/zero-trust/session-risks`);
        if (!res.ok) throw new Error("Failed to fetch session risks");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch (e) {
        console.error("Error fetching session risks:", e);
        return [];
    }
};

export const fetchCryptoInventory = async (): Promise<CryptographicInventory[]> => {
    try {
        const res = await authFetch(`${API_BASE}/quantum-security/cryptographic-inventory`);
        if (!res.ok) throw new Error("Failed to fetch crypto inventory");
        return await res.json();
    } catch (e) {
        console.error("Error fetching crypto inventory:", e);
        return [];
    }
};
export const bulkUpdateAssets = async (assetIds: string[], updates: any) => {
    try {
        const res = await authFetch(`${API_BASE}/assets/bulk-update`, {
            method: 'POST',
            body: JSON.stringify({ assetIds, updates })
        });
        if (!res.ok) throw new Error("Bulk update failed");
        return await res.json();
    } catch (err) {
        console.error("Error in bulk asset update:", err);
        throw err;
    }
};

// ── Tasks ─────────────────────────────────────────────────────────────────────

export const fetchTasks = async () => {
    try {
        const res = await authFetch(`${API_BASE}/tasks`);
        if (!res.ok) throw new Error("Failed to fetch tasks");
        return await res.json();
    } catch (err) {
        console.error("Error fetching tasks:", err);
        return [];
    }
};

export const createTask = async (text: string, priority: string) => {
    const res = await authFetch(`${API_BASE}/tasks`, {
        method: 'POST',
        body: JSON.stringify({ text, priority }),
    });
    if (!res.ok) throw new Error("Failed to create task");
    return await res.json();
};

export const updateTask = async (id: number, updates: { completed?: boolean; text?: string; priority?: string }) => {
    const res = await authFetch(`${API_BASE}/tasks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error("Failed to update task");
    return await res.json();
};

export const deleteTask = async (id: number) => {
    const res = await authFetch(`${API_BASE}/tasks/${id}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 204) throw new Error("Failed to delete task");
};

// --- Feature Flags ---

export const fetchPlatformFeatures = async (): Promise<{
    tier: string;
    enabled: string[];
    locked: Record<string, string>;
    tier_order: Record<string, number>;
}> => {
    try {
        const res = await authFetch(`${API_BASE}/platform/features`);
        if (!res.ok) return { tier: 'Free', enabled: [], locked: {}, tier_order: {} };
        return res.json();
    } catch {
        return { tier: 'Free', enabled: [], locked: {}, tier_order: {} };
    }
};

// ── Internal Tickets ──────────────────────────────────────────────────────────

export const fetchTickets = async (params: Record<string, any> = {}) => {
    const qs = new URLSearchParams(params as any).toString();
    const res = await authFetch(`${API_BASE}/tickets${qs ? '?' + qs : ''}`);
    if (!res.ok) throw new Error("Failed to fetch tickets");
    return res.json();
};

export const fetchTicketStats = async (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    const res = await authFetch(`${API_BASE}/tickets/stats${qs ? '?' + qs : ''}`);
    if (!res.ok) throw new Error("Failed to fetch ticket stats");
    return res.json();
};

export const fetchTicket = async (id: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}`);
    if (!res.ok) throw new Error("Ticket not found");
    return res.json();
};

export const createTicket = async (data: Record<string, any>) => {
    const res = await authFetch(`${API_BASE}/tickets`, {
        method: 'POST', body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to create ticket");
    return res.json();
};

export const updateTicket = async (id: string, updates: Record<string, any>) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}`, {
        method: 'PATCH', body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error("Failed to update ticket");
    return res.json();
};

export const bulkUpdateTickets = async (ticketIds: string[], updates: Record<string, any>) => {
    const res = await authFetch(`${API_BASE}/tickets/bulk`, {
        method: 'POST', body: JSON.stringify({ ticket_ids: ticketIds, updates }),
    });
    if (!res.ok) throw new Error("Failed to bulk update tickets");
    return res.json();
};

export const deleteTicket = async (id: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error("Failed to delete ticket");
    return res.json();
};

// ── Comments ──────────────────────────────────────────────────────────────────

export const addTicketComment = async (id: string, text: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/comments`, {
        method: 'POST', body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("Failed to add comment");
    return res.json();
};

// ── History / audit trail ─────────────────────────────────────────────────────

export const fetchTicketHistory = async (id: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/history`);
    if (!res.ok) throw new Error("Failed to fetch history");
    return res.json();
};

// ── Attachments ───────────────────────────────────────────────────────────────

export const uploadTicketAttachment = async (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    const token = sessionStorage.getItem('token');
    const res = await fetch(`${API_BASE}/tickets/${id}/attachments`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
    });
    if (!res.ok) throw new Error("Failed to upload attachment");
    return res.json();
};

export const deleteTicketAttachment = async (ticketId: string, attachmentId: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${ticketId}/attachments/${attachmentId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error("Failed to delete attachment");
    return res.json();
};

export const getAttachmentUrl = (ticketId: string, storedAs: string) =>
    `${API_BASE}/tickets/${ticketId}/attachments/${storedAs}/download`;

// ── Linking ───────────────────────────────────────────────────────────────────

export const linkTickets = async (id: string, linkedId: string, linkType: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/links`, {
        method: 'POST', body: JSON.stringify({ linked_id: linkedId, link_type: linkType }),
    });
    if (!res.ok) throw new Error("Failed to link ticket");
    return res.json();
};

export const unlinkTickets = async (id: string, linkedId: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/links/${linkedId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error("Failed to unlink ticket");
    return res.json();
};

// ── Work log ──────────────────────────────────────────────────────────────────

export const logTicketWork = async (id: string, hours: number, description: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/work-log`, {
        method: 'POST', body: JSON.stringify({ hours, description }),
    });
    if (!res.ok) throw new Error("Failed to log work");
    return res.json();
};

// ── Escalation ────────────────────────────────────────────────────────────────

export const escalateTicket = async (id: string, reason: string = '') => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/escalate`, {
        method: 'POST', body: JSON.stringify({ reason }),
    });
    if (!res.ok) throw new Error("Failed to escalate ticket");
    return res.json();
};

// ── Approval ──────────────────────────────────────────────────────────────────

export const approveTicket = async (id: string, comment: string = '') => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/approve`, {
        method: 'POST', body: JSON.stringify({ comment }),
    });
    if (!res.ok) throw new Error("Failed to approve ticket");
    return res.json();
};

export const rejectTicket = async (id: string, reason: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/reject`, {
        method: 'POST', body: JSON.stringify({ reason }),
    });
    if (!res.ok) throw new Error("Failed to reject ticket");
    return res.json();
};

// ── Watchers ──────────────────────────────────────────────────────────────────

export const addTicketWatcher = async (id: string, email: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/watchers`, {
        method: 'POST', body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error("Failed to add watcher");
    return res.json();
};

export const removeTicketWatcher = async (id: string, email: string) => {
    const res = await authFetch(`${API_BASE}/tickets/${id}/watchers/${encodeURIComponent(email)}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error("Failed to remove watcher");
    return res.json();
};

// ── Templates ─────────────────────────────────────────────────────────────────

export const fetchTicketTemplates = async () => {
    const res = await authFetch(`${API_BASE}/tickets/templates/list`);
    if (!res.ok) return [];
    return res.json();
};

export const createTicketTemplate = async (data: Record<string, any>) => {
    const res = await authFetch(`${API_BASE}/tickets/templates`, {
        method: 'POST', body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to create template");
    return res.json();
};

export const updateTicketTemplate = async (id: string, data: Record<string, any>) => {
    const res = await authFetch(`${API_BASE}/tickets/templates/${id}`, {
        method: 'PATCH', body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to update template");
    return res.json();
};

export const deleteTicketTemplate = async (id: string) => {
    const res = await authFetch(`${API_BASE}/tickets/templates/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error("Failed to delete template");
    return res.json();
};

// ── Queue config ──────────────────────────────────────────────────────────────

export const fetchQueueConfig = async () => {
    const res = await authFetch(`${API_BASE}/tickets/queue/config`);
    if (!res.ok) return { rules: [] };
    return res.json();
};

export const saveQueueConfig = async (rules: any[]) => {
    const res = await authFetch(`${API_BASE}/tickets/queue/config`, {
        method: 'PUT', body: JSON.stringify({ rules }),
    });
    if (!res.ok) throw new Error("Failed to save queue config");
    return res.json();
};

// ── Custom field schema ───────────────────────────────────────────────────────

export const fetchTicketFieldSchema = async () => {
    const res = await authFetch(`${API_BASE}/tickets/schema/fields`);
    if (!res.ok) return { fields: [] };
    return res.json();
};

export const saveTicketFieldSchema = async (fields: any[]) => {
    const res = await authFetch(`${API_BASE}/tickets/schema/fields`, {
        method: 'PUT', body: JSON.stringify({ fields }),
    });
    if (!res.ok) throw new Error("Failed to save field schema");
    return res.json();
};

// ── Support Chat ──────────────────────────────────────────────────────────────

export const fetchSupportConversations = async (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    const res = await authFetch(`${API_BASE}/support/conversations${qs ? '?' + qs : ''}`);
    if (!res.ok) return [];
    return res.json();
};

export const startSupportConversation = async (data: {
    subject: string; message: string; chat_type: string;
    target_user_id?: string; target_user_name?: string;
    original_convo_id?: string; original_subject?: string;
    original_user_name?: string; original_user_email?: string;
}) => {
    const res = await authFetch(`${API_BASE}/support/conversations`, {
        method: 'POST', body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to start conversation');
    return res.json();
};

export const fetchTenantUsersForChat = async () => {
    try {
        const res = await authFetch(`${API_BASE}/support/tenant-users`);
        if (!res.ok) return [];
        return res.json();
    } catch { return []; }
};

export const fetchSupportConversation = async (id: string) => {
    const res = await authFetch(`${API_BASE}/support/conversations/${id}`);
    if (!res.ok) throw new Error('Conversation not found');
    return res.json();
};

export const sendSupportMessage = async (convoId: string, content: string) => {
    const res = await authFetch(`${API_BASE}/support/conversations/${convoId}/messages`, {
        method: 'POST', body: JSON.stringify({ content }),
    });
    if (!res.ok) throw new Error('Failed to send message');
    return res.json();
};

export const updateSupportStatus = async (convoId: string, status: string) => {
    const res = await authFetch(`${API_BASE}/support/conversations/${convoId}/status`, {
        method: 'PATCH', body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error('Failed to update status');
    return res.json();
};

export const markSupportConversationRead = async (convoId: string): Promise<void> => {
    try {
        await authFetch(`${API_BASE}/support/conversations/${convoId}/read`, { method: 'POST' });
    } catch { /* non-fatal */ }
};

export const fetchSupportPresence = async (usernames: string[]): Promise<Record<string, boolean>> => {
    try {
        const res = await authFetch(`${API_BASE}/support/presence?usernames=${encodeURIComponent(usernames.join(','))}`);
        if (!res.ok) return {};
        return res.json();
    } catch { return {}; }
};

export const fetchSupportUnreadCount = async (): Promise<number> => {
    try {
        const res = await authFetch(`${API_BASE}/support/unread-count`);
        if (!res.ok) return 0;
        const data = await res.json();
        return data.count ?? 0;
    } catch { return 0; }
};

export const fetchCustomYaraRules = async (): Promise<import('../types').CustomYaraRule[]> => {
    try {
        const res = await authFetch(`${API_BASE}/analysis/yara-rules`);
        if (!res.ok) return [];
        return res.json();
    } catch { return []; }
};

export const saveCustomYaraRule = async (rule: Partial<import('../types').CustomYaraRule>): Promise<import('../types').CustomYaraRule> => {
    const isNew = !rule.id;
    const method = isNew ? 'POST' : 'PUT';
    const url = isNew ? `${API_BASE}/analysis/yara-rules` : `${API_BASE}/analysis/yara-rules/${rule.id}`;
    const res = await authFetch(url, { method, body: JSON.stringify(rule) });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Save failed: HTTP ${res.status}`);
    }
    return res.json();
};

export const deleteCustomYaraRule = async (id: string): Promise<void> => {
    await authFetch(`${API_BASE}/analysis/yara-rules/${id}`, { method: 'DELETE' });
};

export const validateYaraRule = async (content: string): Promise<{ valid: boolean; error?: string }> => {
    try {
        const res = await authFetch(`${API_BASE}/analysis/yara-rules/validate`, {
            method: 'POST', body: JSON.stringify({ content }),
        });
        if (!res.ok) return { valid: false, error: 'Validation request failed' };
        return res.json();
    } catch { return { valid: false, error: 'Network error' }; }
};

// ── Compliance Remediation Tasks ──────────────────────────────────────────────

export const createRemediationTask = async (body: {
    title: string;
    control_id?: string;
    asset_id?: string;
    framework_id?: string;
    assignee?: string;
    assignee_type?: string;
    due_date?: string;
    description?: string;
    priority?: string;
}) => {
    const res = await authFetch(`${API_BASE}/compliance-remediation/tasks`, {
        method: 'POST',
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Failed to create remediation task: HTTP ${res.status}`);
    return res.json();
};

export const getRemediationTasks = async (status?: string): Promise<import('../types').RemediationTask[]> => {
    try {
        const url = status
            ? `${API_BASE}/compliance-remediation/tasks?status=${encodeURIComponent(status)}`
            : `${API_BASE}/compliance-remediation/tasks`;
        const res = await authFetch(url);
        if (!res.ok) return [];
        return res.json();
    } catch {
        return [];
    }
};

export const updateRemediationTask = async (
    id: string,
    updates: { status?: string; assignee?: string; due_date?: string; resolution_notes?: string; description?: string },
) => {
    const res = await authFetch(`${API_BASE}/compliance-remediation/tasks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error(`Failed to update remediation task: HTTP ${res.status}`);
    return res.json();
};

export const suggestRemediation = async (taskId: string): Promise<{ suggestion: string }> => {
    const res = await authFetch(`${API_BASE}/compliance-remediation/tasks/${taskId}/suggest`, {
        method: 'POST',
        body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(`Failed to get remediation suggestion: HTTP ${res.status}`);
    return res.json();
};

export const fetchStalenessThreshold = async (): Promise<{ thresholdDays: number }> => {
    try {
        const res = await authFetch(`${API_BASE}/settings/evidence-staleness`);
        if (!res.ok) return { thresholdDays: 7 };
        return await res.json();
    } catch {
        return { thresholdDays: 7 };
    }
};

export const saveStalenessThreshold = async (thresholdDays: number): Promise<void> => {
    const res = await authFetch(`${API_BASE}/settings/evidence-staleness`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thresholdDays }),
    });
    if (!res.ok) throw new Error('Failed to save staleness threshold');
};

export const fetchEvidenceAuditLog = async (evidenceId: string): Promise<{ entries: any[] }> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/evidence/${evidenceId}/audit-log`);
        if (!res.ok) return { entries: [] };
        return await res.json();
    } catch {
        return { entries: [] };
    }
};

export const fetchControlAuditLog = async (controlId: string): Promise<{ entries: any[] }> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/controls/${controlId}/audit-log`);
        if (!res.ok) return { entries: [] };
        return await res.json();
    } catch {
        return { entries: [] };
    }
};


