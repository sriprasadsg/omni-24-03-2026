import type { AutonomousOpsStatistics } from '../../services/autonomousOpsReporting';

export const STATS_TITLE = 'Statistics';
export const STATS_LOAD_FAILED_SUMMARY = "Statistics couldn't be loaded";
export const STATS_LOAD_ERROR = "Couldn't load statistics. Check your connection and try again.";

export const periodLabel = (days: number): string => `Last ${days} days`;

/**
 * The time format of 86-UI-SPEC R16: "0 min", "About 45 min", "About 5 h 40 min", "About 2 h".
 * From one hour up it rounds to the nearest 5 minutes. Matches stats.format_minutes on the server.
 */
export function formatMinutes(minutes: number): string {
    const m = Math.floor(Number.isFinite(minutes) ? minutes : 0);
    if (m <= 0) return '0 min';
    if (m < 60) return `About ${m} min`;
    const rounded = 5 * Math.floor((m + 2) / 5);
    const hours = Math.floor(rounded / 60);
    const rest = rounded % 60;
    return rest === 0 ? `About ${hours} h` : `About ${hours} h ${rest} min`;
}

/** The line under the card title (86-UI-SPEC section 2): the headline, always with the word estimate when minutes show. */
export function summaryLine(stats: AutonomousOpsStatistics): string {
    const label = periodLabel(stats.days);
    const { totals, timeSaved } = stats;
    if (totals.fired === 0 && totals.wouldHaveDone > 0) {
        return `${label} · Simulation only: ${totals.wouldHaveDone} would have been done · Nothing was carried out`;
    }
    if (totals.fired === 0) return `${label} · No decisions yet`;
    return `${label} · ${totals.done} done · ${totals.undone} undone · ${formatMinutes(timeSaved.minutes)} saved (estimate)`;
}

// ── Expanded card (86-UI-SPEC sections 2a to 2d) ────────────────────────────────────────────────────────

export const STATS_PERIOD_LABEL = 'Period';
export const STATS_PERIOD_GROUP = 'Statistics period';
export const periodPillLabel = (days: number): string => `${days} days`;
export const updatedLine = (clock: string): string => `Updated ${clock}`;

export const READOUT_DECISIONS = 'Decisions';
export const READOUT_DONE = 'Done';
export const READOUT_UNDONE = 'Undone';
export const READOUT_TIME_SAVED = 'Time saved';
export const ESTIMATE_CHIP = 'Estimate';
export const TRY_AGAIN = 'Try again';

/** Section c: the dashed simulation line. Simulation is never part of the real counts above it. */
export function simulationLine(wouldHaveDone: number): string {
    return wouldHaveDone > 0
        ? `Simulation: ${wouldHaveDone} would have been done in this period. Nothing was carried out, and none of it is counted above.`
        : 'Simulation: nothing would have been done in this period.';
}

export const emptyHeading = (days: number): string => `No decisions in the last ${days} days`;
export const EMPTY_BODY = "Autonomous Ops hasn't made a decision in this period. Pick a longer period, or see Activity below for older entries.";

/** Section d: the method, always visible next to the figure (D-08). */
export const TIME_SAVED_METHOD = "This is an estimate, not a measurement. Each action that really ran and was not undone counts a fixed number of minutes for its kind, for example 15 minutes to isolate a host or 8 minutes to answer a ticket. Simulated and undone actions are not counted. These minutes are fixed in the product and can't be changed.";
export const TIME_SAVED_SHADOW_SENTENCE = 'Shadow mode is on, so nothing has been carried out and no time is counted.';
export const SHOW_MINUTES = 'Show minutes per kind of action';
export const HIDE_MINUTES = 'Hide minutes per kind of action';
export const MINUTES_TABLE_CAPTION = 'Minutes per kind of action';
export const MINUTES_HEADERS = { kind: 'Kind of action', counted: 'Counted', each: 'Minutes each', subtotal: 'Subtotal' } as const;
export const MINUTES_TOTAL = 'Total';
/** A plain minutes figure for the table cells; the estimate wording ("About ...") belongs to the headline only. */
export const plainMinutes = (minutes: number): string => `${Number.isFinite(minutes) ? minutes : 0} min`;
