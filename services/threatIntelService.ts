import { API_BASE, authFetch } from './apiService';

// --- Threat Intelligence API (P0-1: Real-Time Integration) ---

export interface ThreatIntelScan {
    id: string;
    tenant_id: string;
    artifact: string;
    artifact_type: 'ip' | 'domain' | 'url' | 'hash';
    verdict: string;
    detection_ratio: string;
    malicious?: number;
    suspicious?: number;
    harmless?: number;
    undetected?: number;
    scan_date: string;
    reputation?: number;
    created_at: string;
    created_by: string;
}

export interface ThreatIntelStats {
    total_scans: number;
    verdict_breakdown: Record<string, number>;
    malicious_count: number;
    suspicious_count: number;
    harmless_count: number;
    unknown_count: number;
}

export const scanArtifact = async (
    artifact: string,
    artifactType: 'ip' | 'domain' | 'url' | 'hash',
    tenantId: string
): Promise<ThreatIntelScan> => {
    const res = await authFetch(`${API_BASE}/threat-intel/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            artifact,
            artifact_type: artifactType,
            tenant_id: tenantId
        })
    });

    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to scan artifact');
    }

    return await res.json();
};

export const fetchThreatIntelFeed = async (
    tenantId?: string,
    limit: number = 50
): Promise<ThreatIntelScan[]> => {
    try {
        const params = new URLSearchParams();
        if (tenantId) params.append('tenant_id', tenantId);
        params.append('limit', limit.toString());

        const res = await authFetch(`${API_BASE}/threat-intel/feed?${params}`);
        if (!res.ok) throw new Error('Failed to fetch threat feed');
        return await res.json();
    } catch (error) {
        console.error('Error fetching threat feed:', error);
        return [];
    }
};

export const fetchArtifactHistory = async (artifact: string): Promise<ThreatIntelScan[]> => {
    try {
        const res = await authFetch(`${API_BASE}/threat-intel/history/${encodeURIComponent(artifact)}`);
        if (!res.ok) throw new Error('Failed to fetch artifact history');
        return await res.json();
    } catch (error) {
        console.error('Error fetching artifact history:', error);
        return [];
    }
};

export const enrichSecurityEvent = async (eventId: string): Promise<any> => {
    const res = await authFetch(`${API_BASE}/threat-intel/enrich-security-event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: eventId })
    });

    if (!res.ok) {
        throw new Error('Failed to enrich security event');
    }

    return await res.json();
};

export const fetchThreatIntelStats = async (tenantId?: string): Promise<ThreatIntelStats> => {
    try {
        const params = tenantId ? `?tenant_id=${tenantId}` : '';
        const res = await authFetch(`${API_BASE}/threat-intel/stats${params}`);
        if (!res.ok) throw new Error('Failed to fetch threat intel stats');
        return await res.json();
    } catch (error) {
        console.error('Error fetching threat intel stats:', error);
        return {
            total_scans: 0,
            verdict_breakdown: {},
            malicious_count: 0,
            suspicious_count: 0,
            harmless_count: 0,
            unknown_count: 0
        };
    }
};
