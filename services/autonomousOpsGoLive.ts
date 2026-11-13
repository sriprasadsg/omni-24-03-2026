import { API_BASE, authFetch } from './apiService';
import { failure, getJson } from './autonomousOpsApi';

/** The five live checks a platform administrator records before any organization leaves shadow mode (86-07). */
export type GoLiveCheckId = 'firewall_round_trip' | 'reboot_gate' | 'watchdog_stop_start' | 'alert_delivery' | 'live_stop_drill';

export interface GoLiveCheck {
    id: GoLiveCheckId;
    recorded: boolean;
    recordedBy: { username: string; display: string } | null;
    recordedAt: string | null;
    note: string | null;
}

/** One reason a lift is refused. The server decides; the card only turns the code into a sentence. */
export interface GoLiveReason {
    code: 'checks_missing' | 'no_shadow_records' | 'days_short' | 'unreadable';
    recorded?: number;
    days?: number;
}

export interface GoLiveOrganization {
    id: string;
    name: string;
    /** True while the organization's own shadow flag is on. */
    shadow: boolean;
    /** Whole days since its first shadow record; null when there is none or it could not be read. */
    daysObserved: number | null;
    /** Simulation count: shadow records that would have been carried out. Never a real count. */
    wouldHaveDone: number;
    canLift: boolean;
    reasons: GoLiveReason[];
}

export interface GoLiveOverview {
    checks: GoLiveCheck[];
    recordedCount: number;
    organizations: GoLiveOrganization[];
    /** The deployment-wide shadow switch, set on the server. */
    masterShadow: boolean;
}

/** GET /api/platform/autonomous-ops/golive (Super Admin, interactive session) */
export function fetchGoLive(): Promise<GoLiveOverview> {
    return getJson(`${API_BASE}/platform/autonomous-ops/golive`);
}

/** POST /api/platform/autonomous-ops/golive/checks/{id}: adds one record; earlier records stay. 201 on success. */
export async function recordGoLiveCheck(id: GoLiveCheckId, note: string): Promise<unknown> {
    const res = await authFetch(`${API_BASE}/platform/autonomous-ops/golive/checks/${id}`, {
        method: 'POST', body: JSON.stringify({ note }),
    });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/**
 * PUT /api/platform/autonomous-ops/tenants/{id}/shadow. false lifts shadow mode, true turns it back on. A refused lift
 * answers 409 with the unmet reasons in `detail`; the thrown AutonomousOpsApiError keeps the status. The server is the gate.
 */
export async function setOrganizationShadow(tenantId: string, shadow: boolean): Promise<unknown> {
    const res = await authFetch(`${API_BASE}/platform/autonomous-ops/tenants/${encodeURIComponent(tenantId)}/shadow`, {
        method: 'PUT', body: JSON.stringify({ shadow }),
    });
    if (!res.ok) throw await failure(res);
    return res.json();
}
