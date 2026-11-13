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
