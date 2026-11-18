// The ITAM Costs tab's data (Phase 80, COST-08): GET /api/itam/costs/summary and /assets (backend/itam_cost_endpoints.py,
// itam_cost_service + itam_license_cost). Money is integer cents; a figure that cannot be computed is null, never 0.
// A Platform Owner's selected tenant travels as X-Tenant-ID, like the KPI panel.
import { API_BASE, authFetch } from '../../services/apiService';

export interface CentsTotal { cents: number | null; hasData: boolean }
export interface LicenseBucket {
    spendCents: number | null; allocatedCents: number | null; unattributedCents: number | null; idleCents: number | null;
    allocatedToExcludedCents: number | null; licenses: number; hasData: boolean;
}
export interface CostSummary {
    tenantId: string; computedAt: string; includeDisposed: boolean;
    purchaseTotal: CentsTotal; bookValueTotal: CentsTotal;
    coverage: { total: number; priced: number; valued: number; excludedByLifecycle: number; reasons: Record<string, number> };
    licenses?: { coverage: { total: number; priced: number; notTracked: number }; recurringAnnual: LicenseBucket; oneTime: LicenseBucket };
}
export interface CostRow {
    assetId: string; assetTag?: string | null; name?: string | null; lifecycleStatus: string;
    purchaseCostCents: number | null; bookValueCents: number | null; reason: string | null;
    agent?: { hostname?: string | null } | null;
    license?: { recurringAnnualCents: number | null; oneTimeCents: number | null; pricedSeats: number; untrackedSeats: number };
}
export interface CostPage { items: CostRow[]; total: number; page: number; page_size?: number; pageSize?: number; hasNext?: boolean; totalPages?: number }

export const COSTS_REPORT_KEY = 'endpoint_costs';
export const PAGE_SIZE = 50;

/** Why an asset has no book value, in words (the reason codes of itam_cost_service). */
export const REASON_TEXT: Record<string, string> = {
    disposed: 'Disposed', retired: 'Retired', no_purchase_record: 'No purchase record',
    no_depreciation_policy_assigned: 'No depreciation policy on its model', salvage_exceeds_cost: 'Salvage above purchase cost',
    unreadable_purchase_cost: 'Purchase cost unreadable', unreadable_purchase_date: 'Purchase date unreadable',
};

const get = async <T,>(path: string, tenantId?: string | null): Promise<T> => {
    const res = await authFetch(`${API_BASE}${path}`, { tenantId: tenantId || undefined });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`);
    return body as T;
};

export const fetchCostSummary = (tenantId?: string | null) => get<CostSummary>('/itam/costs/summary', tenantId);
export const fetchCostAssets = (page: number, tenantId?: string | null) =>
    get<CostPage>(`/itam/costs/assets?page=${page}&page_size=${PAGE_SIZE}`, tenantId);
