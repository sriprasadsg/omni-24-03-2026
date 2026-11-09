import { API_BASE, authFetch } from '../apiService';
import { failure, getJson, withTenant } from '../autonomousOpsApi';
import type { DeskSettingsChanges, DeskSettingsView } from './types';

/** Dispatched on `window` when something outside the Service desk card changed what it shows (an Undo that dropped the desk to Drafts only); the card reads the settings again. */
export const DESK_SETTINGS_CHANGED = 'service-desk-settings-changed';

/**
 * The service desk settings routes (85-11). The server decides who may use them (manage:autonomous_ops in a
 * signed-in session); the card renders from the flags in the view and never works that out itself.
 * Platform staff name an organization with `tenantId`; a tenant's own people leave it out.
 */

/** GET /api/autonomous-ops/service-desk[?tenantId=] (manage:autonomous_ops): the saved mode, the words, why answers are or are not posted, the model state and the typical answer time. */
export function fetchDeskSettings(tenantId?: string | null): Promise<DeskSettingsView> {
    return getJson(withTenant(`${API_BASE}/autonomous-ops/service-desk`, tenantId));
}

/** PUT /api/autonomous-ops/service-desk[?tenantId=] (manage:autonomous_ops): either key may be sent; 409 {detail} while the desk breaker is stored, 422 {detail} for a refused value. Returns the same view as GET. */
export async function saveDeskSettings(changes: DeskSettingsChanges, tenantId?: string | null): Promise<DeskSettingsView> {
    const url = withTenant(`${API_BASE}/autonomous-ops/service-desk`, tenantId);
    const res = await authFetch(url, { method: 'PUT', body: JSON.stringify(changes) });
    if (!res.ok) throw await failure(res);
    return res.json();
}

/** POST /api/autonomous-ops/service-desk/restore[?tenantId=] (manage:autonomous_ops): clears the drop to Drafts only and sets Post answers; 409 {detail} when nothing needs restoring. Returns the same view as GET. */
export async function restoreDeskPosting(tenantId?: string | null): Promise<DeskSettingsView> {
    const url = withTenant(`${API_BASE}/autonomous-ops/service-desk/restore`, tenantId);
    const res = await authFetch(url, { method: 'POST', body: JSON.stringify({}) });
    if (!res.ok) throw await failure(res);
    return res.json();
}
