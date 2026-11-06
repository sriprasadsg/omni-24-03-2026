import { API_BASE, authFetch } from '../apiService';
import type {
    ChangeWindowRow, MaintenanceWindow, WindowBody, WindowStatus,
} from './types';

/**
 * Maintenance window calls (84-05 routes). A window is stored in the organization's one time zone; the first
 * window can carry that zone. A non-2xx answer becomes a WindowApiError whose `detail` is the server's sentence
 * (empty when the body had none), so a screen shows the sentence or its own fallback.
 */

export class WindowApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
        super(detail || `Request failed (${status})`);
        this.name = 'WindowApiError';
        this.status = status;
        this.detail = detail;
    }
}

/**
 * What a create or edit sends: the window fields (daysOfWeek are ISO weekday numbers, Monday 1 to Sunday 7) plus,
 * for the organization's first window, its time zone.
 */
export type WindowRequest = WindowBody & { timeZone?: string | null };

async function failure(res: Response): Promise<WindowApiError> {
    let detail = '';
    try {
        const body = await res.json();
        detail = typeof body?.detail === 'string' ? body.detail : '';
    } catch { /* non-JSON error body */ }
    return new WindowApiError(res.status, detail);
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
    const res = await authFetch(url, init);
    if (!res.ok) throw await failure(res);
    return res.json();
}

const send = (method: string, body?: unknown): RequestInit =>
    ({ method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

/** GET /api/maintenance/windows */
export async function fetchWindows(): Promise<MaintenanceWindow[]> {
    const rows = await call<MaintenanceWindow[]>(`${API_BASE}/maintenance/windows`);
    return Array.isArray(rows) ? rows : [];
}

/** POST /api/maintenance/windows: 422 carries the screen sentence. */
export async function createWindow(body: WindowRequest): Promise<MaintenanceWindow> {
    const out = await call<{ window: MaintenanceWindow }>(`${API_BASE}/maintenance/windows`, send('POST', body));
    return out.window;
}

/** PUT /api/maintenance/windows/{id} */
export async function updateWindow(id: string, body: WindowRequest): Promise<MaintenanceWindow> {
    const out = await call<{ window: MaintenanceWindow }>(
        `${API_BASE}/maintenance/windows/${encodeURIComponent(id)}`, send('PUT', body));
    return out.window;
}

/** DELETE /api/maintenance/windows/{id} */
export async function deleteWindow(id: string): Promise<void> {
    await call<unknown>(`${API_BASE}/maintenance/windows/${encodeURIComponent(id)}`, send('DELETE'));
}

/** GET /api/maintenance/time-zone: null while the organization has none. */
export async function fetchTimeZone(): Promise<string | null> {
    const out = await call<{ timeZone: string | null }>(`${API_BASE}/maintenance/time-zone`);
    return out.timeZone ?? null;
}

/** PUT /api/maintenance/time-zone */
export async function saveTimeZone(timeZone: string): Promise<string | null> {
    const out = await call<{ timeZone: string | null }>(`${API_BASE}/maintenance/time-zone`, send('PUT', { timeZone }));
    return out.timeZone ?? null;
}

/** GET /api/maintenance/status: open, closed or none, with the sentence to show. */
export function fetchWindowStatus(): Promise<WindowStatus> {
    return call<WindowStatus>(`${API_BASE}/maintenance/status`);
}

/** GET /api/changes/maintenance-windows: the read-only list shown in Change Management. */
export async function fetchChangeWindows(): Promise<ChangeWindowRow[]> {
    const rows = await call<ChangeWindowRow[]>(`${API_BASE}/changes/maintenance-windows`);
    return Array.isArray(rows) ? rows : [];
}

// ---------------------------------------------------------------- time zone names

const EXTRA_ZONES = ['UTC'];

/** IANA names for the datalist: what the browser supports, plus UTC. */
export function listTimeZones(): string[] {
    let names: string[] = [];
    try {
        const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
        names = intl.supportedValuesOf ? intl.supportedValuesOf('timeZone') : [];
    } catch { /* an older browser: the field still accepts a typed name */ }
    return [...new Set([...names, ...EXTRA_ZONES])];
}

/** True when the browser accepts the name as written (the server has the final say). */
export function isKnownTimeZone(name: string): boolean {
    const value = name.trim();
    if (!value || value !== name || value.length > 64) return false;
    try {
        new Intl.DateTimeFormat('en', { timeZone: value });
        return true;
    } catch {
        return false;
    }
}

/** The browser's own zone, shown as a placeholder only. */
export function browserTimeZone(): string {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch {
        return '';
    }
}
