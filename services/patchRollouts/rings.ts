import { API_BASE, authFetch } from '../apiService';
import { rolloutFailure } from './rollouts';
import type { RingSettingView, RingsSettings } from './types';

/**
 * The Rollout rings calls (84-09 routes GET and PUT /api/patch-rollouts/rings). The server checks every value again
 * and answers 422 with the sentence the card shows; a non-2xx answer becomes a RolloutApiError whose `detail` is that
 * sentence (empty when the body had none). `tenantId` is the organization platform staff entered from Tenants.
 */

const withTenant = (url: string, tenantId?: string | null) =>
    tenantId ? `${url}?tenantId=${encodeURIComponent(tenantId)}` : url;

/** What the card sends for one ring: `key` is left out for a ring that has not been saved yet. */
export type RingInput = Omit<RingSettingView, 'key'> & { key?: string };

/** GET /api/patch-rollouts/rings: the saved rings and the organization's groups with the ring each one is in. */
export async function fetchRings(tenantId?: string | null): Promise<RingsSettings> {
    const res = await authFetch(withTenant(`${API_BASE}/patch-rollouts/rings`, tenantId));
    if (!res.ok) throw await rolloutFailure(res);
    return res.json();
}

/** PUT /api/patch-rollouts/rings: saves 2 to 4 rings and answers with the settings as they read back. */
export async function saveRings(rings: RingInput[], tenantId?: string | null): Promise<RingsSettings> {
    const res = await authFetch(withTenant(`${API_BASE}/patch-rollouts/rings`, tenantId), {
        method: 'PUT',
        body: JSON.stringify({ rings }),
    });
    if (!res.ok) throw await rolloutFailure(res);
    return res.json();
}
