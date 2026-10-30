import React, { useEffect, useRef, useState } from 'react';
import { AutonomousOpsApiError, requestTestAlert } from '../services/autonomousOpsApi';
import type {
    PlatformHealthCert, PlatformHealthDisk, PlatformHealthOnCall, PlatformHealthTestAlert, WatchdogState,
} from '../services/autonomousOpsApi';
import {
    clockOrDash, HealthCell, HealthChip, InstallChecklistLink, ladderChip,
} from './AutonomousOpsHealthChips';
import type { HealthChipKind } from './AutonomousOpsHealthChips';
import { AlertTriangleIcon, CheckCircleIcon, InfoIcon, RefreshCwIcon, SendIcon, XCircleIcon } from './icons';

/** How long a test alert may wait for the watchdog before the screen says it was not picked up (H10). */
export const TEST_ALERT_WAIT_MS = 90_000;

const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const DIVIDER = 'border-t border-gray-200 pt-6 dark:border-white/10';
const NO_REASON = 'no reason was given';
export const SECONDARY_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const CERT_NOTE =
    'Agents pin the nginx certificate. Replacing it needs an agent update first, so plan the swap before it expires. The platform never renews certificates.';
const DISK_NOTE = 'Nothing is deleted automatically to free space. Free space yourself.';

interface FreshnessProps {
    /** True while the watchdog is silent or has never reported: every entry reads Unknown. */
    stale: boolean;
    /** The watchdog's last report, for "Last known" lines. */
    updatedAt?: string | null;
}

const CardHeader: React.FC<{ title: string; chip: HealthChipKind | null }> = ({ title, chip }) => (
    <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{title}</h3>
        {chip && <HealthChip kind={chip} />}
    </div>
);

const validDate = (iso: string | null | undefined) => (iso && !Number.isNaN(new Date(iso).getTime()) ? new Date(iso) : null);

// ── certificates ────────────────────────────────────────────────────────────

const certDate = (iso: string | null) => {
    const date = validDate(iso);
    return date ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
};

function daysText(daysLeft: number): string {
    const days = Math.floor(daysLeft);
    if (days > 1) return `in ${days} days`;
    if (days === 1) return 'expires tomorrow';
    if (days === 0) return 'expires today';
    return `expired ${-days} ${days === -1 ? 'day' : 'days'} ago`;
}

const unreadable = (cert: PlatformHealthCert) => Boolean(cert.error) || (cert.notAfter === null && cert.daysLeft === null);
const certRung = (cert: PlatformHealthCert) => (unreadable(cert) ? 2 : cert.rung ?? 0);

/** Soonest expiry first; an entry with no expiry sorts first, as on the server. */
function byExpiry(a: PlatformHealthCert, b: PlatformHealthCert): number {
    if ((a.daysLeft === null) !== (b.daysLeft === null)) return a.daysLeft === null ? -1 : 1;
    return (a.daysLeft ?? 0) - (b.daysLeft ?? 0) || (a.path ?? '').localeCompare(b.path ?? '');
}

const CertEntry: React.FC<{ cert: PlatformHealthCert; stale: boolean }> = ({ cert, stale }) => {
    let body: React.ReactNode;
    if (stale || cert.stale) {
        body = (
            <>
                <HealthChip kind="unknown" />
                <span className={MUTED}>{validDate(cert.notAfter) ? `Last known expiry ${certDate(cert.notAfter)}.` : 'No reading yet.'}</span>
            </>
        );
    } else if (unreadable(cert)) {
        body = (
            <>
                <HealthChip kind="warning" />
                <span className="break-words text-sm text-gray-700 dark:text-gray-200">Can't read this file.</span>
            </>
        );
    } else {
        body = (
            <>
                <span className="text-sm font-semibold text-gray-900 dark:text-white">{certDate(cert.notAfter)}</span>
                {cert.daysLeft !== null && <span className="text-sm text-gray-700 dark:text-gray-200">{daysText(cert.daysLeft)}</span>}
                <HealthChip kind={ladderChip(cert.rung)} />
            </>
        );
    }
    return (
        <li className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0">
            <p className="break-all font-mono text-xs text-gray-700 dark:text-gray-200">{cert.path ?? '—'}</p>
            <div className="flex flex-wrap items-center gap-2">
                {body}
                {cert.pinned && <HealthChip kind="pinned" />}
            </div>
        </li>
    );
};

/** The certificate card (HEAL-03, D-13): every watched file, soonest expiry first, and the pinned-certificate note. */
export const CertificatesCard: React.FC<FreshnessProps & { certs: PlatformHealthCert[] }> = ({ certs, stale }) => {
    const sorted = [...certs].sort(byExpiry);
    const worst: HealthChipKind | null = stale ? 'unknown' : sorted.length ? ladderChip(Math.max(...sorted.map(certRung))) : null;
    return (
        <div className="card flex flex-col gap-4 p-6">
            <CardHeader title="Certificates" chip={worst} />
            {sorted.length === 0 ? (
                <p className="text-sm text-gray-700 dark:text-gray-200">No certificates are being watched.</p>
            ) : (
                <ul className="divide-y divide-gray-200 dark:divide-white/10">
                    {sorted.map((cert, i) => <CertEntry key={`${cert.path ?? 'unknown'}-${i}`} cert={cert} stale={stale} />)}
                </ul>
            )}
            <p className={MUTED}>{CERT_NOTE}</p>
        </div>
    );
};

// ── disk ────────────────────────────────────────────────────────────────────

const FILL = ['bg-green-600', 'bg-blue-600', 'bg-amber-500', 'bg-red-600'];
const gbText = (bytes: number | null) => (typeof bytes === 'number' ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : '—');

const NO_READING: PlatformHealthDisk = {
    mount: '/', paths: [], usedPct: null, freeBytes: null, totalBytes: null, rung: null, forecast: null, stale: true,
};

const Forecast: React.FC<{ forecast: PlatformHealthDisk['forecast'] }> = ({ forecast }) => {
    let content: React.ReactNode;
    if (forecast?.state === 'ok' && typeof forecast.days === 'number') {
        const days = Math.max(1, Math.round(forecast.days));
        content = (
            <>
                <span>{`Forecast: full in about ${days} ${days === 1 ? 'day' : 'days'} at the last 7 days of growth.`}</span>
                <HealthChip kind={ladderChip(forecast.rung)} />
            </>
        );
    } else if (forecast?.state === 'flat') {
        content = <span>Usage is not growing. No forecast.</span>;
    } else {
        content = <span>Not enough readings for a forecast yet.</span>;
    }
    return <div data-slot="disk-forecast" className="flex flex-wrap items-center gap-2 break-words text-sm text-gray-700 dark:text-gray-200">{content}</div>;
};

const Meter: React.FC<{ pct: number; rung: number | null }> = ({ pct, rung }) => (
    <div
        role="meter" aria-label="Disk used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        className="relative h-2 w-full rounded-full bg-gray-200 dark:bg-white/10"
    >
        <div data-fill className={`h-2 rounded-full ${FILL[Math.min(3, Math.max(0, rung ?? 0))]}`} style={{ width: `${pct}%` }} />
        {[80, 90, 95].map(tick => (
            <span key={tick} aria-hidden="true" className="absolute top-0 h-2 w-px bg-gray-500 dark:bg-gray-300" style={{ left: `${tick}%` }} />
        ))}
    </div>
);

const DiskEntry: React.FC<{ disk: PlatformHealthDisk; stale: boolean; updatedAt?: string | null }> = ({ disk, stale, updatedAt }) => {
    const pct = typeof disk.usedPct === 'number' ? Math.min(100, Math.max(0, Math.round(disk.usedPct))) : null;
    const others = disk.paths.filter(path => path !== disk.mount);
    const known = stale || disk.stale ? null : pct;
    return (
        <li className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0">
            <div className="min-w-0">
                <p className="break-all font-mono text-xs text-gray-700 dark:text-gray-200">{disk.mount}</p>
                {others.length > 0 && (
                    <p className={`mt-1 ${MUTED}`}>
                        {'Also holds '}
                        {others.map((path, i) => (
                            <React.Fragment key={path}>{i > 0 && ', '}<span className="break-all font-mono">{path}</span></React.Fragment>
                        ))}
                    </p>
                )}
            </div>
            {known === null ? (
                <div className="flex flex-wrap items-center gap-2">
                    <HealthChip kind="unknown" />
                    <span className={MUTED}>{pct !== null ? `Last known: ${pct}% used at ${clockOrDash(updatedAt)}.` : 'No reading yet.'}</span>
                </div>
            ) : (
                <>
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold tabular-nums text-gray-900 dark:text-white">{`${known}% used`}</span>
                        <HealthChip kind={ladderChip(disk.rung)} />
                    </div>
                    <p className={`${MUTED} tabular-nums`}>{`${gbText(disk.freeBytes)} free of ${gbText(disk.totalBytes)}`}</p>
                    <Meter pct={known} rung={disk.rung} />
                    <Forecast forecast={disk.forecast} />
                </>
            )}
        </li>
    );
};

/** The disk card (HEAL-02, D-14): fullness with a meter and the 7-day fill forecast, one entry per filesystem. */
export const DiskCard: React.FC<FreshnessProps & { disks: PlatformHealthDisk[] }> = ({ disks, stale, updatedAt }) => {
    const rows = disks.length ? disks : [NO_READING];
    const unknown = stale || disks.length === 0;
    const worst: HealthChipKind = unknown
        ? 'unknown'
        : ladderChip(Math.max(...rows.map(d => Math.max(d.rung ?? 0, d.forecast?.rung ?? 0))));
    return (
        <div className="card flex flex-col gap-4 p-6">
            <CardHeader title="Disk" chip={worst} />
            <ul className="divide-y divide-gray-200 dark:divide-white/10">
                {rows.map((disk, i) => <DiskEntry key={`${disk.mount}-${i}`} disk={disk} stale={stale} updatedAt={updatedAt} />)}
            </ul>
            <p className={MUTED}>{DISK_NOTE}</p>
        </div>
    );
};

// ── on-call and Send test alert ─────────────────────────────────────────────

/**
 * True once a pending test alert has gone 90 s without an answer from the watchdog (H10). The clock starts
 * at the server's requestedAt, or when this browser first saw the test if that time is missing or ahead.
 */
export function useTestAlertNoAnswer(testAlert: PlatformHealthTestAlert | null): boolean {
    const [, wake] = useState(0);
    const seen = useRef<{ id: string; at: number } | null>(null);
    const pending = testAlert?.state === 'pending' ? testAlert : null;
    if (pending && seen.current?.id !== pending.id) seen.current = { id: pending.id, at: Date.now() };
    const requested = pending?.requestedAt ? Date.parse(pending.requestedAt) : NaN;
    const started = pending && seen.current ? Math.min(Number.isNaN(requested) ? Infinity : requested, seen.current.at) : null;
    const expired = started !== null && Date.now() - started >= TEST_ALERT_WAIT_MS;

    useEffect(() => {
        if (started === null || expired) return;
        const timer = setTimeout(() => wake(n => n + 1), Math.max(0, started + TEST_ALERT_WAIT_MS - Date.now()));
        return () => clearTimeout(timer);
    }, [started, expired]);
    return expired;
}

const RESULT_TONES = {
    muted: 'text-gray-700 dark:text-gray-200',
    green: 'text-green-800 dark:text-green-200',
    amber: 'text-amber-800 dark:text-amber-200',
    blue: 'text-blue-800 dark:text-blue-200',
    red: 'text-red-700 dark:text-red-300',
};

const ResultLine: React.FC<{ tone: keyof typeof RESULT_TONES; icon: React.FC<any>; role?: 'alert'; children: string }> = ({ tone, icon: Icon, role, children }) => (
    <p role={role} className={`flex items-start gap-2 break-words text-sm ${RESULT_TONES[tone]}`}>
        <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
        <span className="min-w-0">{children}</span>
    </p>
);

function requestErrorText(error: unknown): string {
    if (error instanceof AutonomousOpsApiError && error.detail) {
        return `Couldn't request a test alert: ${error.detail.replace(/\.+$/, '')}. Try again.`;
    }
    return "Couldn't request a test alert. Check your connection and try again.";
}

const CHANNEL_NAME: Record<string, string> = { pagerduty: 'PagerDuty', webhook: 'Webhook' };

interface OnCallProps {
    oncall: PlatformHealthOnCall;
    testAlert: PlatformHealthTestAlert | null;
    watchdogState: WatchdogState;
    installChecklist: { path: string; url: string | null } | null | undefined;
    /** From useTestAlertNoAnswer: the watchdog has not picked the pending test up in 90 s. */
    noAnswer: boolean;
    onTestRequested: (testAlert: PlatformHealthTestAlert) => void;
}

/**
 * The on-call card (HEAL-04, D-01..D-05): the channel type and booleans only, never a key or a url, and
 * Send test alert with its state machine (D-21). The test state comes from the server so it survives a reload.
 */
export const OnCallCard: React.FC<OnCallProps> = ({ oncall, testAlert, watchdogState, installChecklist, noAnswer, onTestRequested }) => {
    const [requesting, setRequesting] = useState(false);
    const [requestError, setRequestError] = useState<string | null>(null);
    const inFlight = useRef(false);

    const channel = oncall.type ? CHANNEL_NAME[oncall.type] : undefined;
    const waiting = testAlert?.state === 'pending' && !noAnswer;
    const disabled = requesting || waiting || watchdogState !== 'running';

    const send = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setRequesting(true);
        setRequestError(null);
        try {
            onTestRequested((await requestTestAlert()).testAlert);
        } catch (error) {
            setRequestError(requestErrorText(error));
        } finally {
            inFlight.current = false;
            setRequesting(false);
        }
    };

    let status: React.ReactNode = <HealthChip kind="not_tested" />;
    let statusHelp: string | null = null;
    if (oncall.status === 'working') {
        status = <HealthChip kind="working" />;
        statusHelp = `Last delivered ${clockOrDash(oncall.last?.at)}.`;
    } else if (oncall.status === 'not_working') {
        status = <HealthChip kind="not_working" />;
        statusHelp = `Last attempt ${clockOrDash(oncall.last?.at)}: ${oncall.last?.error || NO_REASON}`;
    } else if (oncall.status === 'not_tested') {
        statusHelp = 'No alert has been sent yet. Send a test alert.';
    }

    const quiet = requesting || requestError !== null;
    const sentAt = clockOrDash(testAlert?.sentAt);
    return (
        <div className="card flex flex-col gap-4 p-6">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">On-call alerting</h3>
            <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <HealthCell
                    label="Channel"
                    value={channel ?? <HealthChip kind="not_set_up" />}
                    help={channel
                        ? 'Held on the server. The platform never sees the key.'
                        : <>Set up a channel in the on-call file on the server, then send a test alert. <InstallChecklistLink checklist={installChecklist} /></>}
                />
                <HealthCell label="Status" value={status} help={statusHelp} />
                <HealthCell
                    label="External heartbeat"
                    value={oncall.heartbeatConfigured ? 'Configured' : 'Not configured'}
                    help={oncall.heartbeatConfigured
                        ? null
                        : 'Without it, nobody is paged if the watchdog or the whole server goes down. The install checklist recommends setting it up.'}
                />
            </dl>
            <div className={`flex flex-col gap-2 ${DIVIDER}`}>
                <div>
                    <button type="button" className={SECONDARY_BUTTON} onClick={send} disabled={disabled} aria-describedby="test-alert-help">
                        {waiting
                            ? <RefreshCwIcon size={16} aria-hidden="true" className="animate-spin" />
                            : <SendIcon size={16} aria-hidden="true" />}
                        {requesting ? 'Requesting...' : waiting ? 'Waiting for the watchdog...' : 'Send test alert'}
                    </button>
                </div>
                <p id="test-alert-help" className={MUTED}>
                    {watchdogState === 'not_installed'
                        ? <>Install the watchdog first. <InstallChecklistLink checklist={installChecklist} /></>
                        : 'The watchdog sends it within about a minute.'}
                </p>
                <div role="status" className="flex flex-col gap-2">
                    {watchdogState === 'silent' && (
                        <ResultLine tone="blue" icon={InfoIcon}>The watchdog is silent, so a test can't be sent until it reports again.</ResultLine>
                    )}
                    {!quiet && waiting && (
                        <ResultLine tone="muted" icon={RefreshCwIcon}>
                            {`Test requested at ${clockOrDash(testAlert?.requestedAt)}. The watchdog sends it within about a minute.`}
                        </ResultLine>
                    )}
                    {!quiet && testAlert?.state === 'pending' && noAnswer && (
                        <ResultLine tone="amber" icon={AlertTriangleIcon}>The watchdog hasn't picked up the test request yet. Check that it is running.</ResultLine>
                    )}
                    {!quiet && testAlert?.state === 'delivered' && (
                        <ResultLine tone="green" icon={CheckCircleIcon}>{`Sent at ${sentAt}, delivered.`}</ResultLine>
                    )}
                </div>
                {!quiet && testAlert?.state === 'failed' && (
                    <ResultLine tone="red" icon={XCircleIcon} role="alert">{`Sent at ${sentAt}, not delivered: ${testAlert.error || NO_REASON}`}</ResultLine>
                )}
                {requestError && <ResultLine tone="red" icon={XCircleIcon} role="alert">{requestError}</ResultLine>}
            </div>
        </div>
    );
};
