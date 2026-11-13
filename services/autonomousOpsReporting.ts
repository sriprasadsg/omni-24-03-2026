import { API_BASE, authFetch } from './apiService';
import { failure, getJson } from './autonomousOpsApi';
import type { AutonomousOpsBucket } from './autonomousOpsApi';

/** The statistics periods the server accepts (D-06). */
export type StatsWindow = 7 | 30 | 90;

export interface AutonomousOpsStatsTotals {
    fired: number; done: number; approved: number; denied: number; undone: number; failed: number; refused: number;
    /** Simulation only: shadow mode was on and nothing was carried out. Never part of the real counts. */
    wouldHaveDone: number;
}

export interface AutonomousOpsRuleStats extends AutonomousOpsStatsTotals {
    id: string;
    name: string;
}

export interface AutonomousOpsTimeSavedKind {
    kind: string;
    label: string;
    counted: number;
    minutesEach: number;
    subtotal: number;
}

export interface AutonomousOpsTimeSaved {
    minutes: number;
    /** Always true: the figure is an estimate (D-08). */
    estimate: true;
    perKind: AutonomousOpsTimeSavedKind[];
}

export interface AutonomousOpsStatistics {
    tenantId: string;
    days: number;
    generatedAt: string;
    shadowOnly: boolean;
    canExport: boolean;
    rules: AutonomousOpsRuleStats[];
    totals: AutonomousOpsStatsTotals;
    timeSaved: AutonomousOpsTimeSaved;
}

/** GET /api/autonomous-ops/statistics?days=[&tenantId=] */
export function fetchAutonomousOpsStatistics(days: StatsWindow, tenantId?: string | null): Promise<AutonomousOpsStatistics> {
    const params = new URLSearchParams();
    params.set('days', String(days));
    if (tenantId) params.set('tenantId', tenantId);
    return getJson(`${API_BASE}/autonomous-ops/statistics?${params.toString()}`);
}

// ── Export (86-11: ACTV-06, D-09, D-10) ─────────────────────────────────────────────────────────────────

export type ExportFormat = 'csv' | 'pdf';
/** The periods the export route accepts; 'all' is every row up to the 5,000 cap. */
export type ExportDays = '7' | '30' | '90' | 'all';

export type ExportOutcome =
    | { status: 'downloaded'; fileName: string; rows: number; total: number; truncated: boolean }
    | { status: 'empty' };

/** The file name from a Content-Disposition header, parsed as exportReport does; the fallback when there is none. */
export function fileNameFrom(disposition: string | null | undefined, fallback: string): string {
    if (disposition && disposition.indexOf('attachment') !== -1) {
        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
        const name = matches?.[1]?.replace(/['"]/g, '').trim();
        if (name) return name;
    }
    return fallback;
}

/** A header read as a whole number; anything else falls back. The numbers are shown as text, never trusted further. */
const wholeNumber = (value: string | null, fallback: number): number => {
    const n = Number.parseInt(value ?? '', 10);
    return Number.isFinite(n) && n >= 0 ? n : fallback;
};

function saveBlob(blob: Blob, fileName: string): void {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

async function saveExport(res: Response, fallbackName: string): Promise<{ fileName: string; rows: number; total: number; truncated: boolean }> {
    const blob = await res.blob();
    const fileName = fileNameFrom(res.headers.get('Content-Disposition'), fallbackName);
    saveBlob(blob, fileName);
    const rows = wholeNumber(res.headers.get('X-Export-Rows'), 0);
    return {
        fileName,
        rows,
        total: wholeNumber(res.headers.get('X-Export-Total'), rows),
        truncated: res.headers.get('X-Export-Truncated') === 'true',
    };
}

/**
 * GET /api/autonomous-ops/export. 204 means nothing matched and no file exists; a failure throws an
 * AutonomousOpsApiError that keeps the status (403 has its own sentence). X-Export-Total is the true count.
 */
export async function downloadAutonomousOpsExport(
    q: { format: ExportFormat; bucket: AutonomousOpsBucket; days: ExportDays; tenantId?: string | null },
): Promise<ExportOutcome> {
    const params = new URLSearchParams();
    params.set('format', q.format);
    params.set('bucket', q.bucket);
    params.set('days', q.days);
    if (q.tenantId) params.set('tenantId', q.tenantId);
    const res = await authFetch(`${API_BASE}/autonomous-ops/export?${params.toString()}`);
    if (res.status === 204) return { status: 'empty' };
    if (!res.ok) throw await failure(res);
    return { status: 'downloaded', ...(await saveExport(res, `autonomous_ops_activity.${q.format}`)) };
}

/** The registry type string the Reporting screen's export route knows (86-08). It always means all states, the last 30 days. */
const REGISTRY_TYPE = 'Autonomous Ops Activity';

/** GET /api/reports/export?type=Autonomous Ops Activity&format= for the Reporting screen card (D-09). A zero-row file still downloads. */
export async function downloadAutonomousOpsReport(format: ExportFormat): Promise<{ fileName: string; rows: number; truncated: boolean }> {
    const res = await authFetch(`${API_BASE}/reports/export?type=${encodeURIComponent(REGISTRY_TYPE)}&format=${format}`);
    if (!res.ok) throw await failure(res);
    const { fileName, rows, truncated } = await saveExport(res, `autonomous_ops_activity_report.${format}`);
    return { fileName, rows, truncated };
}
