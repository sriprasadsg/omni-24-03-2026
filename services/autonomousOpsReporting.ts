import { API_BASE } from './apiService';
import { getJson } from './autonomousOpsApi';

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
