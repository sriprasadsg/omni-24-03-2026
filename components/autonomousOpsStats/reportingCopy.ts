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

// ── By rule (86-UI-SPEC section 2e) ─────────────────────────────────────────────────────────────────────

export const RULES_HEADING = 'By rule';
export const rulesCaption = (days: number): string => `Decisions by rule, last ${days} days`;
export const RULE_HEADER = 'Rule';
/** The seven real count columns, in table order. Simulation is never one of them. */
export const RULE_COUNT_COLUMNS = [
    { key: 'fired', label: 'Fired' },
    { key: 'done', label: 'Done' },
    { key: 'approved', label: 'Approved' },
    { key: 'denied', label: 'Denied' },
    { key: 'undone', label: 'Undone' },
    { key: 'failed', label: 'Failed' },
    { key: 'refused', label: 'Refused' },
] as const;
export const SIMULATION_HEADER = 'Would have done (simulation)';
export const simulationCard = (n: string | number): string => `${SIMULATION_HEADER}: ${n}`;
export const ALL_RULES = 'All rules';
export const MISSING_COUNT = '—';
export const RULES_VISIBLE = 15;
export const showAllRules = (n: number): string => `Show all ${n} rules`;
export const SHOW_FEWER_RULES = 'Show fewer rules';
export const GLOSSARY_SHOW = 'What the columns mean';
export const GLOSSARY_HIDE = 'Hide what the columns mean';
/** Refused is widened from the UI-SPEC wording (flagged assumption A-86-A2): it also covers expired and stopped approvals. */
export const GLOSSARY: ReadonlyArray<{ term: string; meaning: string }> = [
    { term: 'Fired', meaning: 'times the rule made a decision' },
    { term: 'Done', meaning: 'carried out and still in place' },
    { term: 'Approved', meaning: 'a person approved it' },
    { term: 'Denied', meaning: 'a person said no' },
    { term: 'Undone', meaning: 'carried out, then undone' },
    { term: 'Failed', meaning: "tried, and it didn't work" },
    { term: 'Refused', meaning: 'blocked by a limit, a never-touch entry or a stop, or nobody answered the approval in time' },
    { term: 'Would have done', meaning: 'simulation only; shadow mode was on and nothing was carried out' },
];

// ── Export activity dialog (86-UI-SPEC section 3, D-09, D-10, D-12) ───────────────────────────────────

export const EXPORT_OPEN = 'Export activity';
export const EXPORT_TITLE = 'Export activity';
export const EXPORT_ROW_LIMIT = 5000;
export const EXPORT_LIMIT_TEXT = '5,000';
export const FORMAT_LEGEND = 'Format';
export const PERIOD_LEGEND = 'Period';
export const FORMAT_OPTIONS = [
    { value: 'csv', label: 'CSV', helper: 'One row per decision. Opens in a spreadsheet.' },
    { value: 'pdf', label: 'PDF', helper: 'A summary page with the per-rule table and the time-saved estimate, then the rows.' },
] as const;
export const PERIOD_OPTIONS = [
    { value: '7', label: 'Last 7 days' },
    { value: '30', label: 'Last 30 days' },
    { value: '90', label: 'Last 90 days' },
    { value: 'all', label: 'All time' },
] as const;
/** The state names of the list's filter pills, in the words the pills use. */
export const BUCKET_LABELS: Record<string, string> = {
    all: 'All', pending: 'Pending', done: 'Done', undone: 'Undone', failed: 'Failed', refused: 'Refused',
    suggested: 'Suggested', simulation: 'Simulation', platform_health: 'Platform health',
};
export const periodOptionLabel = (days: string): string => PERIOD_OPTIONS.find(o => o.value === days)?.label ?? 'Last 30 days';
export const includedLine = (bucket: string, days: string): string =>
    `Activity: ${BUCKET_LABELS[bucket] ?? 'All'}. Period: ${periodOptionLabel(days)}. Newest first, up to ${EXPORT_LIMIT_TEXT} rows.`;
export const EXPORT_AUDIT_SENTENCE = 'Each export is recorded in the audit log with who exported, the filter, the number of rows and the format.';
export const EXPORT_CLOSE = 'Close';
export const exportButton = (format: string): string => `Download ${format.toUpperCase()}`;
export const EXPORT_PREPARING = 'Preparing...';
export const EXPORT_ERROR = "Couldn't create the export. Check your connection and try again.";
export const EXPORT_FORBIDDEN = "You don't have permission to export this. It needs the right to export reports and to view Autonomous Ops.";
export const EXPORT_EMPTY = 'There are no rows for this filter, so nothing was downloaded.';
const rowsWord = (n: number): string => `${n.toLocaleString('en-US')} ${n === 1 ? 'row' : 'rows'}`;
export const exportToast = (rows: number): string => `Export downloaded. ${rowsWord(rows)}.`;
/** The cap note (D-10): the true total comes from X-Export-Total; the same sentence is written into the file. */
export const capNote = (fileName: string, total: number): string =>
    `Downloaded ${fileName}: the newest ${EXPORT_LIMIT_TEXT} of ${total.toLocaleString('en-US')} rows. Rows older than that were left out. Pick a shorter period or a single state to get the rest.`;

// ── Reporting screen card (86-UI-SPEC section 4, D-09) ──────────────────────────────────────────────────

export const REPORT_CARD_TITLE = 'Autonomous Ops Activity';
export const REPORT_CARD_NOTE = `All states, last 30 days, newest ${EXPORT_LIMIT_TEXT} rows.`;
export const REPORT_NEEDS_EXPORT = 'Needs permission to export reports.';
export const REPORT_NEEDS_VIEW = 'Needs permission to view Autonomous Ops.';
export const REPORT_PLATFORM_STAFF = 'Open an organization in Tenants, then export from its Autonomous Ops screen.';
export const REPORT_TRUNCATED_TOAST = `Export downloaded. Only the newest ${EXPORT_LIMIT_TEXT} rows are included.`;
export const REPORT_FAILED_TOAST = `Failed to export ${REPORT_CARD_TITLE}.`;
