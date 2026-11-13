import type { GoLiveCheckId } from '../../services/autonomousOpsGoLive';

/**
 * Every fixed string of the Going live card (86-UI-SPEC section 6 and the Copywriting Contract), so the screen,
 * the tests and the copy gate share one source. Naming rule (ACTV-08): undo, simulation; never the banned terms.
 */

export const GOLIVE_TITLE = 'Going live';
export const GOLIVE_DOC = 'docs/autonomous-ops-go-live.md';
export const CHECK_TOTAL = 5;
export const TRY_AGAIN = 'Try again';

export const GOLIVE_LOAD_ERROR = "Couldn't load the go-live checks. Check your connection and try again.";
export const GOLIVE_LOAD_FAILED_SUMMARY = "Go-live checks couldn't be loaded";

export const GOLIVE_INTRO =
    `Before any organization leaves shadow mode, a platform administrator walks five checks on the live server and records each one here. Every record is stored with your name and the time and is written to the audit log. How to walk each check is in ${GOLIVE_DOC}.`;

/** The collapsed summary line (D-14). */
export function goLiveSummary(recorded: number, outOfShadow: number): string {
    if (recorded >= CHECK_TOTAL) return `All ${CHECK_TOTAL} checks recorded`;
    const left = `${recorded} of ${CHECK_TOTAL} checks recorded`;
    const right = outOfShadow === 0
        ? 'No organization is out of shadow mode'
        : `${outOfShadow} ${outOfShadow === 1 ? 'organization' : 'organizations'} out of shadow mode`;
    return `${left} · ${right}`;
}

// ── The five checks. Descriptions are the "Summary:" lines of docs/autonomous-ops-go-live.md, word for word. ──

export const CHECKS_LIST_LABEL = 'Go-live checks';

export const CHECK_COPY: Record<GoLiveCheckId, { title: string; description: string }> = {
    firewall_round_trip: {
        title: 'Firewall round-trip',
        description: 'Block a test address with Autonomous Ops, confirm the firewall refuses it, then undo the block and confirm the address works again.',
    },
    reboot_gate: {
        title: 'Reboot gate',
        description: 'Confirm a patch that needs a reboot waits for approval on its card, and the machine does not restart on its own.',
    },
    watchdog_stop_start: {
        title: 'Watchdog stop and start',
        description: 'Stop the watchdog timer on the server, confirm Platform health shows Silent, start it again and confirm it shows Running.',
    },
    alert_delivery: {
        title: 'Alert delivery',
        description: 'Send a test alert from Platform health and confirm it reaches the on-call channel.',
    },
    live_stop_drill: {
        title: 'Live stop drill',
        description: 'Use Stop all organizations and confirm new decisions halt, queued instructions are held back, approvals and rollouts freeze and AI ticket replies pause. Then resume.',
    },
};

export const CHIP_RECORDED = 'Recorded';
export const CHIP_NOT_RECORDED = 'Not recorded';
export const RECORD_THIS = 'Record this check';
export const RECORD_AGAIN = 'Record again';
export const EARLIER_RECORDS = 'Earlier records stay in the audit log.';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Recorded by Pat on 12 Nov 2026 at 14:02", on the viewer's own clock. An unreadable time reads "an unknown time". */
export function recordedLine(by: string, iso: string | null): string {
    const at = iso ? new Date(iso) : null;
    if (!at || Number.isNaN(at.getTime())) return `Recorded by ${by} at an unknown time`;
    const pad = (n: number) => String(n).padStart(2, '0');
    return `Recorded by ${by} on ${pad(at.getDate())} ${MONTHS[at.getMonth()]} ${at.getFullYear()} at ${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

// ── The inline note form (E9) ────────────────────────────────────────────────────────────────────────

export const NOTE_MIN = 10;
export const NOTE_MAX = 500;
export const NOTE_LABEL = 'Note (required)';
/** The UI-SPEC example reworded (research Pitfall 9): no address from a documentation range. */
export const NOTE_HELPER = 'Say what you did and what you saw, for example: Blocked our test address, the firewall refused it at 14:02, undone at 14:05.';
export const NOTE_TOO_SHORT = `Add a note of at least ${NOTE_MIN} characters.`;
export const noteCounter = (n: number): string => `${n}/${NOTE_MAX}`;
export const RECORD_CHECK = 'Record check';
export const RECORDING = 'Recording...';
export const CLOSE_FORM = 'Close form';
export const DISCARD_ASK = 'Discard this note?';
export const DISCARD_NOTE = 'Discard note';
export const KEEP_EDITING = 'Keep editing';
export const RECORD_FORBIDDEN = 'Only a platform administrator can record these checks.';
export const RECORD_FALLBACK = "Couldn't record the check. Check your connection and try again.";
export const recordFailed = (message: string): string => `Couldn't record the check: ${message}. Try again.`;
export const recordedToast = (title: string): string => `Check recorded: ${title}.`;

// ── Organizations (86-UI-SPEC section 6c, E10) ─────────────────────────────────────────────────────

export const SHADOW_DAYS = 7;
export const ORG_HEADING = 'Organizations';
export const ORG_HELPER = 'Only organizations with Autonomous Ops switched on are listed. Turning shadow mode back on is always allowed.';
export const MASTER_NOTICE =
    "The deployment-wide shadow switch is also on. It forces shadow mode on for every organization until it is removed on the server. Lifting an organization's own setting here takes effect once that switch is removed.";
export const ORG_CAPTION = 'Shadow mode by organization';
export const COL_ORGANIZATION = 'Organization';
export const COL_SHADOW = 'Shadow mode';
export const COL_DAYS = 'Days observed';
export const COL_SIMULATION = 'Would have done (simulation)';
export const COL_ACTION = 'Action';
export const CHIP_SHADOW_ON = 'Shadow mode on';
export const CHIP_SHADOW_LIFTED = 'Shadow mode lifted';
export const NO_VALUE = '—';
export const ORG_EMPTY_HEADING = 'No organization has Autonomous Ops switched on';
export const ORG_EMPTY_BODY = 'Switch it on for an organization in Tenants. It starts in shadow mode and appears here.';
export const LIFT_BUTTON = 'Lift shadow mode';
export const RESTORE_BUTTON = 'Turn shadow mode back on';

export const daysLabel = (days: number | null): string => (days === null ? NO_VALUE : `${days} of ${SHADOW_DAYS} days`);

/** One unmet lift condition as a sentence. The wording matches the server's own sentences (golive.blocker_sentence). */
export function reasonSentence(reason: { code: string; recorded?: number; days?: number }): string {
    switch (reason.code) {
        case 'checks_missing':
            return `Record all ${CHECK_TOTAL} go-live checks first (${reason.recorded ?? 0} of ${CHECK_TOTAL} recorded).`;
        case 'no_shadow_records':
            return `No shadow records yet. Needs ${SHADOW_DAYS} days.`;
        case 'days_short': {
            const days = reason.days ?? 0;
            return `Needs ${SHADOW_DAYS} days of shadow records. ${days} ${days === 1 ? 'day' : 'days'} so far.`;
        }
        case 'unreadable':
            return "Shadow records couldn't be read, so lifting is blocked.";
        default:
            return 'Not ready to lift yet.';
    }
}

// ── The two dialogs (86-UI-SPEC section 6d, E11 and E12) ──────────────────────────────────────────

const count = (n: number, one: string, many: string): string => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

export const liftTitle = (name: string): string => `Lift shadow mode for ${name}?`;
export const liftBody = (name: string): string =>
    `From now on, automatic actions in ${name} are carried out for real, within the level and limits already set. Until now they were simulations. Anything that needs approval still waits for a person.`;
export const liftEvidence = (days: number, wouldHaveDone: number): string =>
    `${count(days, 'day', 'days')} of shadow records. ${count(wouldHaveDone, 'action', 'actions')} would have been done. All ${CHECK_TOTAL} go-live checks are recorded.`;
export const LIFT_REASSURANCE = 'You can turn shadow mode back on at any time. Actions already done stay done, and each can be undone where undo is supported.';
export const TYPE_NAME_LABEL = 'Type the organization name to confirm';
export const typeNameHelper = (name: string): string => `Type ${name} exactly as shown.`;
export const TYPE_NAME_REASON = 'Type the name to continue.';
export const KEEP_SHADOW_ON = 'Keep shadow mode on';
export const LIFTING = 'Lifting...';
export const LIFT_FORBIDDEN = 'Only a platform administrator can lift shadow mode.';
export const LIFT_FALLBACK = "Couldn't lift shadow mode. Check your connection and try again.";
export const liftRefused = (message: string): string => (message ? `Shadow mode can't be lifted yet: ${message}.` : "Shadow mode can't be lifted yet.");
export const liftedToast = (name: string): string => `Shadow mode lifted for ${name}.`;

export const restoreTitle = (name: string): string => `Turn shadow mode back on for ${name}?`;
export const restoreBody = (name: string): string =>
    `Automatic actions in ${name} become simulations again and nothing new is carried out. Actions already done stay done, and each can be undone where undo is supported.`;
export const KEEP_LIFTED = 'Keep it lifted';
export const TURN_ON = 'Turn shadow mode on';
export const SAVING = 'Saving...';
export const RESTORE_FORBIDDEN = 'Only a platform administrator can change shadow mode.';
export const RESTORE_FALLBACK = "Couldn't turn shadow mode back on. Check your connection and try again.";
export const restoreFailed = (message: string): string => `Couldn't turn shadow mode back on: ${message}. Try again.`;
export const restoredToast = (name: string): string => `Shadow mode is on again for ${name}.`;

// ── The go-live test organization (D-23, plan 86-15) ───────────────────────────────────────────────

export const TEST_ORG_LABEL = 'Test organization';
export const TEST_ORG_USE = 'Use as test organization';
export const TEST_ORG_CLEAR = 'Clear test mark';
export const TEST_ORG_CLEAR_REASON = 'Turn shadow mode back on first.';
export const TEST_ORG_CANCEL = 'Cancel';
export const TEST_ORG_KEEP = 'Keep test mark';
export const TEST_ORG_MARKING = 'Marking...';
export const TEST_ORG_CLEARING = 'Clearing...';

export const markTitle = (name: string): string => `Use ${name} as the go-live test organization?`;
export const MARK_BODY =
    "This organization can leave shadow mode before the five checks are recorded and without the seven days of shadow records, so you can walk checks 1, 2 and 5. Use a dedicated test organization, never a customer's. Only one organization can be marked. This is recorded in the platform audit log.";
export const markTypeLabel = (name: string): string => `Type ${name} to confirm`;
export const markedToast = (name: string): string => `${name} is now the test organization.`;
export const MARK_FORBIDDEN = 'Only a platform administrator can mark the test organization.';
export const MARK_FALLBACK = "Couldn't mark the test organization. Check your connection and try again.";

export const clearTitle = (name: string): string => `Clear the test mark on ${name}?`;
export const CLEAR_BODY = 'Customer rules apply to it again: it needs the five checks and seven days before it can leave shadow mode.';
export const clearedToast = (name: string): string => `The test mark on ${name} is cleared.`;
export const CLEAR_FORBIDDEN = 'Only a platform administrator can clear the test mark.';
export const CLEAR_FALLBACK = "Couldn't clear the test mark. Check your connection and try again.";
