import { authFetch } from './apiService';

/** Client for /api/dashboards (backend tenant_dashboards_endpoints.py). */

export interface Placement {
  i: string;
  widget: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title?: string | null;
}

export interface Sharing {
  everyone: boolean;
  roles: string[];
}

export interface DashboardDraft {
  name: string;
  description: string;
  widgets: Placement[];
  sharing: Sharing;
}

export interface DashboardSummary {
  id: string;
  name: string;
  description: string;
  widgetCount: number;
  status: 'draft' | 'published';
  publishedAt?: string | null;
  updatedAt?: string | null;
  version?: number;
  sharing?: Sharing;
  hasUnpublishedChanges?: boolean;
}

export interface DashboardDetail extends DashboardSummary {
  widgets: Placement[];
  withheld: number;
  hidden: string[];
  mode: 'published' | 'draft';
  unavailable?: Placement[];
}

export interface CatalogueWidget {
  id: string;
  title: string;
  view: string;
  kind: 'kpi' | 'bar' | 'table' | 'list';
  size: { w: number; h: number; minW: number; minH: number; maxH: number };
  available: boolean;
}

export interface WidgetCatalogue {
  grid: { columns: number; maxRows: number; maxWidgets: number };
  widgets: CatalogueWidget[];
}

/** The server's message for a refused request, so the screen can say what went wrong. */
export class DashboardApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(`/api/dashboards${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch { /* keep the generic message */ }
    throw new DashboardApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const listDashboards = () =>
  call<{ dashboards: DashboardSummary[]; canDesign: boolean }>('');

export const getDashboard = (id: string, mode: 'published' | 'draft' = 'published') =>
  call<DashboardDetail>(`/${encodeURIComponent(id)}?mode=${mode}`);

export const getWidgetCatalogue = () => call<WidgetCatalogue>('/widgets');

export const createDashboard = (draft: DashboardDraft) =>
  call<DashboardSummary>('', { method: 'POST', body: JSON.stringify(draft) });

export const saveDashboard = (id: string, draft: DashboardDraft, version: number) =>
  call<DashboardSummary>(`/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ draft, version }) });

export const publishDashboard = (id: string, version: number) =>
  call<DashboardSummary>(`/${encodeURIComponent(id)}/publish`, { method: 'POST', body: JSON.stringify({ version }) });

export const unpublishDashboard = (id: string) =>
  call<DashboardSummary>(`/${encodeURIComponent(id)}/unpublish`, { method: 'POST' });

export const deleteDashboard = (id: string) =>
  call<{ deleted: string }>(`/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const setHiddenWidgets = (id: string, hidden: string[]) =>
  call<{ hidden: string[] }>(`/${encodeURIComponent(id)}/hidden`, { method: 'PUT', body: JSON.stringify({ hidden }) });
