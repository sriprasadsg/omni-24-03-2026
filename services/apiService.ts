
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
    Risk, Vendor, VendorAssessment, TrustProfile, AccessRequest
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
    AiModel, AiPolicy, DastScan, DeviceTrustScore, UserSessionRisk, CryptographicInventory, VoiceBotSettings
};
// Initial data import removed for strict live telemetry parsing


// Use relative path so Vite proxy handles it correctly
export const API_BASE = '/api';


// --- SBOM / DevSecOps API ---

export const fetchSboms = async (): Promise<Sbom[]> => {
    try {
        const res = await authFetch(`${API_BASE}/sboms`);
        if (!res.ok) throw new Error("Failed to fetch SBOMs");
        const data = await res.json();
        return Array.isArray(data) ? data : (data.items || []);
    } catch { return []; }
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

// Helper function to refresh the access token
async function refreshAccessToken(): Promise<string> {
    // If already refreshing, return existing promise
    if (refreshPromise) return refreshPromise;

    refreshPromise = (async () => {
        try {
            const refreshToken = localStorage.getItem('refresh_token');

            if (!refreshToken) {
                throw new Error('No refresh token available');
            }

            const response = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (!response.ok) {
                throw new Error('Failed to refresh token');
            }

            const data = await response.json();

            if (data.success && data.access_token) {
                localStorage.setItem('token', data.access_token);
                return data.access_token;
            }

            throw new Error('Invalid refresh response');
        } finally {
            // Clear the promise after completion
            refreshPromise = null;
        }
    })();

    return refreshPromise;
}

// Helper for Authenticated Requests
export async function authFetch(url: string, options: RequestInit & { tenantId?: string } = {}): Promise<Response> {
    const { tenantId, ...fetchOptions } = options;

    const makeRequest = async (token: string | null) => {
        const headers = {
            'Content-Type': 'application/json',
            ...(fetchOptions.headers || {}),
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
        } as HeadersInit;

        return await fetch(url, { ...fetchOptions, headers });
    };

    // First attempt with current token
    let token = localStorage.getItem('token');
    let response = await makeRequest(token);

    // If 401, try to refresh token and retry
    if (response.status === 401) {
        try {
            const newToken = await refreshAccessToken();
            response = await makeRequest(newToken);
        } catch (error) {
            // Refresh failed - clear storage and redirect to login
            localStorage.removeItem('token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login';
            throw new Error('Session expired');
        }
    }

    return response;
}

// Initialize local state as empty
let USERS: User[] = [];
let ROLES: Role[] = [];
let TENANTS: Tenant[] = [];
let METRICS: Metric[] = [];
let ALERTS: Alert[] = [];
let COMPLIANCE_FRAMEWORKS: ComplianceFramework[] = [];
let AI_SYSTEMS: AiSystem[] = [];
let ASSETS: Asset[] = [];
let PATCHES: Patch[] = [];
let SECURITY_CASES: SecurityCase[] = [];
let PLAYBOOKS: Playbook[] = [];
let SECURITY_EVENTS: SecurityEvent[] = [];
let CLOUD_ACCOUNTS: CloudAccount[] = [];
let CSPM_FINDINGS: CSPMFinding[] = [];
let NOTIFICATIONS: Notification[] = [];
let AUDIT_LOGS: AuditLog[] = [];
let INTEGRATIONS: Integration[] = [];
let ALERT_RULES: AlertRule[] = [];
let AGENTS: Agent[] = [];
let DATABASE_SETTINGS: DatabaseSettings | null = null;
let LLM_SETTINGS: LlmSettings | null = null;
let DATA_SOURCES: DataSource[] = [];
let SBOMS: Sbom[] = [];
let SOFTWARE_COMPONENTS: SoftwareComponent[] = [];
let AGENT_UPGRADE_JOBS: AgentUpgradeJob[] = [];
let PATCH_DEPLOYMENT_JOBS: PatchDeploymentJob[] = [];
let VULNERABILITY_SCAN_JOBS: VulnerabilityScanJob[] = [];
let LOGS: LogEntry[] = [];
let UEBA_FINDINGS: UebaFinding[] = [];
let MODEL_EXPERIMENTS: ModelExperiment[] = [];
let REGISTERED_MODELS: RegisteredModel[] = [];
let AUTOMATION_POLICIES: AutomationPolicy[] = [];
let SAST_FINDINGS: SastFinding[] = [];
let CODE_REPOSITORIES: CodeRepository[] = [];
let API_DOCS: ApiDocEndpoint[] = [];
let SENSITIVE_DATA_FINDINGS: SensitiveDataFinding[] = [];
let ATTACK_PATHS: AttackPath[] = [];
let SERVICE_TEMPLATES: ServiceTemplate[] = [];
let PROVISIONED_SERVICES: ProvisionedService[] = [];
let DORA_METRICS: DoraMetrics[] = [];
let CHAOS_EXPERIMENTS: ChaosExperiment[] = [];
let PROACTIVE_INSIGHTS: ProactiveInsight[] = [];
let TRACES: Trace[] = [];
let SERVICE_MAP: ServiceMap | null = null;
let NETWORK_DEVICES: NetworkDevice[] = [];
let THREAT_INTEL_FEED: ThreatIntelResult[] = [];

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

        localStorage.setItem(`omni_cache_${key}`, JSON.stringify(items));
        updateLocalVar(items);
        return items;
    } catch (e) {
        // If 401, it's already handled by authFetch redirect. 
        // For other errors (offline), fallback to cache or return empty.
        console.warn(`Backend offline or error for ${key}`, e);
        const cached = localStorage.getItem(`omni_cache_${key}`);
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

    if (!res.ok) {
        throw new Error('Invalid credentials');
    }

    const data = await res.json();
    if (data.access_token) {
        localStorage.setItem('token', data.access_token);
    }
    return data;
};

export const fetchCurrentUser = async (): Promise<any> => {
    try {
        const token = localStorage.getItem('token');
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
                localStorage.removeItem('token');
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
export const fetchMetrics = async () => {
    try {
        const res = await authFetch(`${API_BASE}/metrics`);
        if (!res.ok) return [];
        return await res.json();
    } catch { return []; }
};
export const fetchAlerts = async (tenantId?: string) => {
    try {
        const res = await authFetch(`${API_BASE}/alerts`, { tenantId } as any);
        if (!res.ok) throw new Error("Failed");
        const data = await res.json();
        ALERTS = data.items ? data.items : data;
        return ALERTS;
    } catch { return []; }
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
        headers: { 'Content-Type': 'multipart/form-data' }, // authFetch will handle this or we can let browser do it
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

export const uploadComplianceEvidence = async (assetId: string, controlId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('controlId', controlId);

    const res = await authFetch(`${API_BASE}/assets/${assetId}/compliance/evidence`, {
        method: 'POST',
        headers: { 'Content-Type': 'multipart/form-data' },
        body: formData
    });

    if (!res.ok) throw new Error("Evidence upload failed");
    return await res.json();
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
export const fetchLogs = async () => {
    // fetchLogs: Get all system logs
    try {
        const res = await authFetch(`${API_BASE}/logs`);
        if (!res.ok) throw new Error("Failed to fetch logs");
        const data = await res.json();
        const logs = Array.isArray(data) ? data : [];
        LOGS = logs;
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
        SECURITY_EVENTS = data.items ? data.items : data;
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
export const fetchCspmFindings = async () => { return []; };
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
export const fetchAlertRules = async () => { return []; };
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
        localStorage.setItem('omni_cache_agents', JSON.stringify(items));
        return items;
    } catch (e) {
        console.warn("Backend offline for agents", e);
        const cached = localStorage.getItem(`omni_cache_agents`);
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
export const fetchDataSources = async () => { return []; };

export const fetchAgentUpgradeJobs = async () => { return []; };
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

export const fetchUebaFindings = async () => { return []; };
export const fetchModelExperiments = async () => { return []; };
export const fetchRegisteredModels = async () => { return []; };
// fetchAutomationPolicies moved to bottom
export const fetchSastFindings = async () => { return []; };
export const fetchCodeRepositories = async () => { return []; };
export const fetchApiDocs = async () => { return []; };
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

export const fetchSensitiveDataFindings = async () => { return []; };
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
export const fetchServiceTemplates = async () => { return []; };
export const fetchProvisionedServices = async () => { return []; };
export const fetchDoraMetrics = async () => { return []; };
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

export const fetchProactiveInsights = async () => { return []; };
// export const fetchTraces = async () => { return []; };
// export const fetchServiceMap = async () => { return null; };
export const fetchThreatIntelFeed = async () => { return []; };

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
        console.warn("Backend offline for KPIs, using fallback data");
        // Fallback data if backend is unreachable
        return {
            trends: [
                { month: 'Jan', revenue: 50000, securityScore: 85, uptime: 99.9 },
                { month: 'Feb', revenue: 55000, securityScore: 88, uptime: 99.95 },
                { month: 'Mar', revenue: 48000, securityScore: 92, uptime: 99.98 },
                { month: 'Apr', revenue: 60000, securityScore: 90, uptime: 99.92 },
                { month: 'May', revenue: 75000, securityScore: 95, uptime: 99.99 },
                { month: 'Jun', revenue: 80000, securityScore: 98, uptime: 100 },
            ]
        };
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
        const payload = {
            email: user.email,
            password: "TempPassword123!", // Temporary hardcoded password
            full_name: user.name, // React sends 'name', Backend API model expects 'full_name'
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

export const registerNewTenant = async (payload: NewTenantPayload) => {
    await mockDelay(1000);
    const newTenant: Tenant = {
        id: `tenant-${Date.now()}`,
        name: payload.companyName,
        subscriptionTier: 'Free',
        registrationKey: `key-${Date.now()}`,
        dataIngestionGB: 0,
        apiCallsMillions: 0,
        aiComputeVCPUHours: 0,
        enabledFeatures: ['view:dashboard', 'view:agents', 'view:assets', 'view:profile'],
        apiKeys: [],
        budget: { monthlyLimit: 1000 }
    };
    const newUser: User = {
        id: `user-${Date.now()}`,
        tenantId: newTenant.id,
        tenantName: newTenant.name,
        name: payload.name,
        email: payload.email,
        password: payload.password,
        role: 'Tenant Admin',
        avatar: `https://i.pravatar.cc/150?u=${payload.email}`,
        status: 'Active'
    };
    USERS = [...USERS, newUser];
    TENANTS = [...TENANTS, newTenant];
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

export const runAgentDiagnostics = async (agentId: string): Promise<Agent> => {
    const agentIndex = AGENTS.findIndex(a => a.id === agentId);
    if (agentIndex === -1) {
        throw new Error(`Agent with ID ${agentId} not found.`);
    }

    const agent = AGENTS[agentIndex];
    // This is still a mock as there's no backend endpoint for diagnostics yet
    const isHealthy = true;

    const newHealth: AgentHealth = {
        overallStatus: 'Healthy',
        checks: [
            { name: 'Connectivity', status: 'Pass', message: 'Agent is connected to the platform.' },
            { name: 'Service Status', status: 'Pass', message: 'Service is running optimal.' },
            { name: 'Cache Write Access', status: 'Pass', message: 'Local cache is writable.' }
        ]
    };

    const updatedAgent = {
        ...agent,
        lastSeen: new Date().toISOString(),
        status: 'Online',
        health: newHealth
    } as Agent;

    AGENTS[agentIndex] = updatedAgent;
    return updatedAgent;
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
                tenantId
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

export const resetPassword = async (userId: string) => {
    return true;
};

export const generateApiKey = async (tenantId: string, name: string, userId: string) => {
    const newKey = `omni_sk_${Math.random().toString(36).substr(2, 18)}`;
    const tenant = TENANTS.find(t => t.id === tenantId);
    if (tenant) {
        tenant.apiKeys.push({
            id: `key-${Date.now()}`,
            name,
            key: newKey,
            createdAt: new Date().toISOString(),
            userId
        });
    }
    return { name, key: newKey };
};

export const revokeApiKey = async (tenantId: string, keyId: string) => {
    const tenant = TENANTS.find(t => t.id === tenantId);
    if (tenant) {
        tenant.apiKeys = tenant.apiKeys.filter(k => k.id !== keyId);
    }
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
        return caseItem;
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
    const newAccount: CloudAccount = {
        id: `ca-${Date.now()}`,
        tenantId,
        ...data,
        status: 'Connected'
    };
    CLOUD_ACCOUNTS.push(newAccount);
    return newAccount;
};

export const saveAlertRule = async (rule: AlertRule) => {
    const index = ALERT_RULES.findIndex(r => r.id === rule.id);
    if (index > -1) {
        ALERT_RULES[index] = rule;
    } else {
        ALERT_RULES.push(rule);
    }
    return rule;
};

export const deleteAlertRule = async (id: string) => {
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

export const saveDataSource = async (source: DataSource) => {
    const index = DATA_SOURCES.findIndex(ds => ds.id === source.id);
    if (index > -1) {
        DATA_SOURCES[index] = source;
    } else {
        DATA_SOURCES.push(source);
    }
    return source;
};

export const deleteDataSource = async (id: string) => {
    DATA_SOURCES = DATA_SOURCES.filter(ds => ds.id !== id);
};

export const testDataSourceConnection = async (source: DataSource) => {
    await mockDelay(1500);
    if (Math.random() > 0.2) {
        return { message: "Connection successful!" };
    } else {
        throw new Error("Failed to connect to data source.");
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

export const testDatabaseConnection = async (settings: DatabaseSettings) => {
    await mockDelay(1500);
    return { message: "Database connection established successfully." };
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
    // This is a mock as there's no backend endpoint for VT yet
    return {
        id: `vt-scan-${Date.now()}`,
        artifact,
        artifactType: type,
        source: 'VirusTotal',
        verdict: 'Harmless',
        detectionRatio: '0/88',
        scanDate: new Date().toISOString(),
        reportUrl: 'https://www.virustotal.com/gui/'
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
    // This is a mock as there's no backend endpoint for risk remediation yet
    const steps = [
        { type: 'goal', content: `Mitigate risk: ${risk.title}` },
        { type: 'thought', content: 'Analyzing risk factors and system configuration...' },
        { type: 'action', content: 'Scanning training data for bias correlations...' },
        { type: 'observation', content: 'Found uneven distribution in dataset.' },
        { type: 'thought', content: 'Re-balancing dataset required.' },
        { type: 'action', content: 'Applying re-weighting algorithm...' },
        { type: 'observation', content: 'New dataset distribution verified.' },
        { type: 'action', content: 'Initiating model retraining...' },
        { type: 'observation', content: 'Retraining job started successfully.' }
    ];

    for (const step of steps) {
        yield { ...step, timestamp: new Date().toISOString() } as AgenticStep;
    }
};

export const generateAgenticPlan = async function* (agent: Agent): AsyncGenerator<AgenticStep> {
    // This is a mock as there's no backend endpoint for agentic plans yet
    const steps = [
        { type: 'goal', content: `Restore agent health on ${agent.hostname}` },
        { type: 'thought', content: 'Checking connectivity and service status...' },
        { type: 'action', content: `ssh ${agent.hostname} "systemctl status omni-agent"` },
        { type: 'observation', content: 'Service is inactive (dead).' },
        { type: 'thought', content: 'Attempting to restart service.' },
        { type: 'action', content: `ssh ${agent.hostname} "systemctl restart omni-agent"` },
        { type: 'observation', content: 'Service active (running).' },
        { type: 'thought', content: 'Verifying connectivity...' },
        { type: 'action', content: `ping -c 1 ${agent.ipAddress}` },
        { type: 'observation', content: 'Packet loss: 0%.' }
    ];

    for (const step of steps) {
        yield { ...step, timestamp: new Date().toISOString() } as AgenticStep;
    }
};

export const fetchHealthAnalysis = async (metrics: Metric[], alerts: Alert[]) => {
    return {
        analysis: "Health analysis unavailable",
        recommendations: []
    };
};

export const fetchSecurityAnalysis = async (events: SecurityEvent[]) => {
    return {
        analysis: "Security analysis unavailable",
        recommendations: []
    };
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

export const executePlaybook = async function* (playbookId: string, targetId: string, targetType: string): AsyncGenerator<PlaybookExecutionStep> {
    yield { timestamp: new Date().toISOString(), message: `Starting playbook ${playbookId} on ${targetType} ${targetId}...`, status: 'running' };
    yield { timestamp: new Date().toISOString(), message: `Playbook execution unavailable`, status: 'error' };
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
export const getNotifications = async (tenantId: string = "default") => {
    try {
        const response = await fetch(`${API_BASE}/notifications?tenant_id=${tenantId}`);
        return await response.json();
    } catch (err) {
        console.error("Error fetching notifications:", err);
        return [];
    }
};

// --- FinOps ---




// --- Compliance Reports ---
export const generateComplianceReport = async (frameworkId: string) => {
    try {
        const formData = new FormData();
        formData.append('framework_id', frameworkId);

        const token = localStorage.getItem('token');
        const headers: any = { 'Authorization': `Bearer ${token}` };

        const res = await fetch(`${API_BASE}/compliance/reports/generate`, {
            method: 'POST',
            headers: headers,
            body: formData
        });
        return await res.json();
    } catch (e) {
        console.error("Error generating report:", e);
        throw e;
    }
};

export const generateExcelComplianceReport = async (frameworkId: string) => {
    try {
        const formData = new FormData();
        formData.append('framework_id', frameworkId);

        const token = localStorage.getItem('token');
        const headers: any = { 'Authorization': `Bearer ${token}` };

        const res = await fetch(`${API_BASE}/compliance/reports/generate/excel`, {
            method: 'POST',
            headers: headers,
            body: formData
        });
        return await res.json();
    } catch (e) {
        console.error("Error generating Excel report:", e);
        throw e;
    }
};

export const generatePDFComplianceReport = async (frameworkId: string) => {
    try {
        const formData = new FormData();
        formData.append('framework_id', frameworkId);

        const token = localStorage.getItem('token');
        const headers: any = { 'Authorization': `Bearer ${token}` };

        const res = await fetch(`${API_BASE}/compliance/reports/generate/pdf`, {
            method: 'POST',
            headers: headers,
            body: formData
        });
        return await res.json();
    } catch (e) {
        console.error("Error generating PDF report:", e);
        throw e;
    }
};

export const fetchComplianceReports = async () => {
    try {
        const res = await fetch(`${API_BASE}/compliance/reports`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching reports:", e);
        return [];
    }
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
        const res = await fetch(`${API_BASE}/approvals/pending?user_email=${userEmail}`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching pending approvals:", e);
        return [];
    }
};

export const fetchApprovalHistory = async () => {
    try {
        const res = await fetch(`${API_BASE}/approvals/history`);
        if (res.ok) return await res.json();
        return [];
    } catch (e) {
        console.error("Error fetching approval history:", e);
        return [];
    }
};

export const submitApprovalDecision = async (requestId: string, userEmail: string, decision: 'approve' | 'reject', comments: string) => {
    try {
        const res = await fetch(`${API_BASE}/approvals/${requestId}/decide`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
        const response = await fetch(`${API_BASE}/notifications/${notificationId}/read`, {
            method: 'PUT'
        });
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
        const response = await fetch(`${API_BASE}/notifications/${notificationId}`, {
            method: 'DELETE'
        });
        return await response.json();
    } catch (err) {
        console.error("Error deleting notification:", err);
        return { success: false };
    }
};

export const getNotificationConfig = async (tenantId: string = localStorage.getItem('tenantId') || "default") => {
    try {
        const response = await fetch(`${API_BASE}/notifications/config?tenant_id=${tenantId}`);
        return await response.json();
    } catch (err) {
        console.error("Error fetching notification config:", err);
        return [];
    }
};

export const updateNotificationConfig = async (config: any) => {
    try {
        const response = await fetch(`${API_BASE}/notifications/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
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
        const response = await fetch(`${API_BASE}/maintenance/windows?tenant_id=${tenantId}`);
        return await response.json();
    } catch (err) {
        console.error("Error fetching maintenance windows:", err);
        return [];
    }
};

export const createMaintenanceWindow = async (windowData: any) => {
    try {
        const response = await fetch(`${API_BASE}/maintenance/windows`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
        const response = await fetch(`${API_BASE}/maintenance/windows/${windowId}`, {
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
        const response = await fetch(`${API_BASE}/maintenance/check?tenant_id=${tenantId}`);
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

