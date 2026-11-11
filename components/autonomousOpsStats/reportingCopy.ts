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
