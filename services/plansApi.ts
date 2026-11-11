/**
 * Phase 88 (LIC-07): the Super Admin's plan table. A plan is a ceiling (D-27): the plan's screen list
 * limits what Manage Tenant may tick, it never ticks anything. The server enforces every rule here;
 * these helpers only shape the UI.
 */
import { API_BASE, authFetch } from './apiService';

export type PlanKey = 'Free' | 'Pro' | 'Enterprise' | 'Custom';
export const PLAN_KEYS: PlanKey[] = ['Free', 'Pro', 'Enterprise', 'Custom'];

export interface Plan {
  key: PlanKey;
  seats: number | null;
  trialDays?: number | null;
  /** Screen keys the plan may sell ("view:x" / "screen:x"), or "all". */
  screens: string[] | 'all';
  tenantCount: number;
  updatedAt?: string | null;
  updatedBy?: string | null;
}

export interface PlanChanges {
  seats?: number;
  trialDays?: number;
  screens?: string[];
}

async function readError(res: Response): Promise<Error> {
  const body = await res.json().catch(() => ({}));
  const text = [body?.error, body?.detail].find(v => typeof v === 'string' && v.trim()) as string | undefined;
  return new Error(text ?? `HTTP ${res.status}`);
}

export async function fetchPlans(): Promise<Plan[]> {
  const res = await authFetch(`${API_BASE}/platform/plans`);
  if (!res.ok) throw await readError(res);
  const data = await res.json();
  return Array.isArray(data?.plans) ? data.plans : [];
}

export async function savePlan(key: PlanKey, changes: PlanChanges): Promise<{ plan: Plan; tenantsUpdated: number }> {
  const res = await authFetch(`${API_BASE}/platform/plans/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw await readError(res);
  return res.json();
}

/** The screens a plan allows: "all" for Custom (per-tenant contract) or a plan that lists everything. */
export function allowedScreens(plan: Plan | undefined): Set<string> | 'all' {
  if (!plan || plan.key === 'Custom' || plan.screens === 'all' || !Array.isArray(plan.screens)) return 'all';
  return new Set(plan.screens);
}
