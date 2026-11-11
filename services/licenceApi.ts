import { API_BASE, authFetch } from './apiService';

// Plan-driven licence view (88-01, 88-06): GET/PATCH /api/tenants/{id}/license.
export interface LicenceSubLimit {
    key: string;
    max: number;
}

export interface LicenceTrial {
    startedAt: string | null;
    endsAt: string;
    consumed: boolean;
    ended: boolean;
    daysLeft: number;
}

export interface LicenceNetwork {
    cidr: string;
    source: 'learned' | 'approved' | 'migrated' | string;
    addedAt?: string;
}

export interface LicenceView {
    tenantId: string;
    maxAgents: number | null;   // null when the organization is exempt
    seatsUsed: number;
    seatsAvailable: number;
    overBy: number;
    inactiveReclaimDays: number;
    allowlistMode: 'off' | 'enforce';
    subLimits: LicenceSubLimit[];
    expiresAt: string | null;
    plan: string;
    planSeats: number | null;
    seatOverride: number | null;
    partnerManaged: boolean;
    exempt: boolean;
    trial: LicenceTrial | null;
    allowedNetworks: LicenceNetwork[];
}

export interface LicenceChanges {
    maxAgents?: number;
    inactiveReclaimDays?: number;
    allowlistMode?: 'off' | 'enforce';
    subLimits?: LicenceSubLimit[];
    expiresAt?: string | null;
    clearSeatOverride?: boolean;
    trialExtendDays?: number;
}

const failure = async (res: Response, fallback: string): Promise<never> => {
    let message: unknown = null;
    try {
        const body = await res.json();
        message = body?.error || body?.detail;
    } catch { /* non-JSON error body */ }
    throw new Error(typeof message === 'string' && message ? message : `${fallback} (HTTP ${res.status})`);
};

export const fetchLicenceView = async (tenantId: string): Promise<LicenceView> => {
    const res = await authFetch(`${API_BASE}/tenants/${tenantId}/license`);
    if (!res.ok) return failure(res, 'Failed to load the licence');
    return res.json();
};

export const updateLicence = async (tenantId: string, changes: LicenceChanges): Promise<LicenceView> => {
    const res = await authFetch(`${API_BASE}/tenants/${tenantId}/license`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
    });
    if (!res.ok) return failure(res, 'Failed to update the licence');
    return res.json();
};

/** A network as people write it: a single-address /32 (or /128) drops its suffix. */
export const networkLabel = (cidr: string): string => cidr.replace(/\/(32|128)$/, '');
