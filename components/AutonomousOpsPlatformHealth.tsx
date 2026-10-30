import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetchPlatformHealth } from '../services/autonomousOpsApi';
import type { PlatformHealthDocument, PlatformHealthService, PlatformHealthTestAlert, ServiceState } from '../services/autonomousOpsApi';
import { formatWhen } from './AutonomousOpsActivityList';
import { CertificatesCard, DiskCard, OnCallCard, useTestAlertNoAnswer } from './AutonomousOpsHealthCards';
import { consumePlatformHealthFocus, formatClock } from './AutonomousOpsHealthBanners';
import {
    clockOrDash, HEALTH_SKELETON, HealthChip, HealthNotice, InstallChecklistLink,
} from './AutonomousOpsHealthChips';
import type { HealthChipKind } from './AutonomousOpsHealthChips';
import { PauseCircleIcon } from './icons';

export const HEALTH_POLL_MS = 30_000;
/** While a test alert waits for the watchdog the section polls faster (D-21). */
export const TEST_ALERT_POLL_MS = 5_000;
const RESTART_BUDGET = 3;
const DIVIDER = 'border-t border-gray-200 pt-6 dark:border-white/10';
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';

interface PlatformHealthProps {
    /** The page Refresh button's counter (AutonomousOpsActivity); a change refetches the section. */
    refreshSignal?: number;
}

// The fixed order of the services grid: MongoDB first because it is restarted first (D-09).
const SERVICE_ORDER: Array<{ id: string; name: string }> = [
    { id: 'mongod', name: 'MongoDB' },
    { id: 'omni-backend', name: 'Backend' },
    { id: 'nginx', name: 'nginx' },
    { id: 'ollama', name: 'Ollama' },
];

const SERVICE_CHIP: Record<ServiceState, HealthChipKind> = {
    healthy: 'healthy', checking: 'checking', down: 'down', restarting: 'restarting', gave_up: 'gave_up',
    expected_off: 'expected_off', unexpected_running: 'notice',
};
const SERVICE_LABEL: Record<ServiceState, string> = {
    healthy: 'Healthy', checking: 'Checking', down: 'Down', restarting: 'Restarting', gave_up: 'Gave up',
    expected_off: 'Expected off', unexpected_running: 'Running',
};

const STOP_NOTICE = 'Restarts are paused because automatic actions are stopped for the whole platform. Checks, warnings and pages continue.';
const stopNotice = (source: PlatformHealthDocument['stop']['source']) => {
    if (source === 'file') return 'Restarts are paused by a STOP file on the server. Checks, warnings and pages continue.';
    if (source === 'cache') return `${STOP_NOTICE} The database can't be reached, so the watchdog is using the last stop state it saw.`;
    return STOP_NOTICE;
};

// ── data ────────────────────────────────────────────────────────────────────

/**
 * One fetch on mount, then every 30 s while the tab is visible, on window focus and when the page Refresh
 * counter changes. A background poll never shows a skeleton or spinner; a failure keeps the last document.
 */
function usePlatformHealth(refreshSignal: number) {
    const [doc, setDoc] = useState<PlatformHealthDocument | null>(null);
    const [fetchedAt, setFetchedAt] = useState<number | null>(null);
    const [failed, setFailed] = useState(false);
    const alive = useRef(true);
    const lastSignal = useRef(refreshSignal);
    const generation = useRef(0);

    const load = useCallback(async () => {
        const mine = generation.current;
        try {
            const next = await fetchPlatformHealth();
            if (!alive.current || mine !== generation.current) return; // a newer test alert answer outranks this read
            setDoc(next);
            setFetchedAt(Date.now());
            setFailed(false);
        } catch {
            if (alive.current) setFailed(true);
        }
    }, []);

    useEffect(() => {
        alive.current = true;
        void load();
        const visible = () => document.visibilityState !== 'hidden';
        const timer = setInterval(() => { if (visible()) void load(); }, HEALTH_POLL_MS);
        const onVisibility = () => { if (visible()) void load(); };
        const onFocus = () => { void load(); };
        document.addEventListener('visibilitychange', onVisibility);
        window.addEventListener('focus', onFocus);
        return () => {
            alive.current = false;
            clearInterval(timer);
            document.removeEventListener('visibilitychange', onVisibility);
            window.removeEventListener('focus', onFocus);
        };
    }, [load]);

    useEffect(() => {
        if (refreshSignal === lastSignal.current) return;
        lastSignal.current = refreshSignal;
        void load();
    }, [refreshSignal, load]);

    const reload = useCallback(() => { setFailed(false); void load(); }, [load]);
    const applyTestAlert = useCallback((testAlert: PlatformHealthTestAlert) => {
        generation.current += 1;
        setDoc(current => (current ? { ...current, testAlert } : current));
    }, []);
    return { doc, fetchedAt, load, reload, applyTestAlert, loading: doc === null && !failed, loadFailed: doc === null && failed };
}

// ── services ────────────────────────────────────────────────────────────────

/** Whole minutes until `iso`, or null when it is missing, unreadable or already past. */
function minutesUntil(iso: string | null | undefined): number | null {
    const at = iso ? Date.parse(iso) : NaN;
    if (Number.isNaN(at)) return null;
    const minutes = Math.ceil((at - Date.now()) / 60_000);
    return minutes > 0 ? minutes : null;
}

function budgetLine(service: PlatformHealthService): string | null {
    const parts: string[] = [];
    if (typeof service.restartsInWindow === 'number' && service.restartsInWindow > 0) {
        parts.push(`Restarts used: ${service.restartsInWindow} of ${RESTART_BUDGET} in the last 30 minutes.`);
    }
    const back = minutesUntil(service.budgetReturnsAt);
    if (back !== null) parts.push(`Restart budget back in ${back} min.`);
    return parts.length ? parts.join(' ') : null;
}

interface CellView { chip: HealthChipKind; chipLabel?: string; line1: string; line2: string | null }

/** The state table of 82-UI-SPEC section 3: chip and the two helper lines for one service. */
function cellView(service: PlatformHealthService | undefined, doc: PlatformHealthDocument): CellView {
    const state = service?.state ?? null;
    if (!service || !state || service.stale || doc.watchdog.state !== 'running') {
        const known = service && state && doc.watchdog.state !== 'not_installed';
        return {
            chip: 'unknown',
            line1: known ? `Last known: ${SERVICE_LABEL[state]} at ${clockOrDash(doc.updatedAt)}.` : 'No reading yet.',
            line2: null,
        };
    }
    const chip = SERVICE_CHIP[state];
    const budget = budgetLine(service);
    const restartNumber = Math.min(RESTART_BUDGET, (service.restartsInWindow ?? 0) + 1);
    switch (state) {
        case 'healthy':
            return { chip, line1: `Checked ${doc.updatedAt ? formatWhen(doc.updatedAt).text : '—'}.`, line2: budget };
        case 'checking':
            return { chip, line1: '1 failed check. Counted as down after 2 in a row.', line2: budget };
        case 'down': {
            let line1: string;
            if (doc.stop.effective) {
                line1 = 'Restarts paused: automatic actions are stopped.';
            } else if (service.waitingOn === 'mongod') {
                line1 = 'Waiting for MongoDB to be healthy first.';
            } else {
                const wait = minutesUntil(service.nextRestartAt);
                const next = service.nextRestartAt
                    ? ` Restart ${restartNumber} of ${RESTART_BUDGET} ${wait !== null ? `waiting ${wait} min` : `at ${clockOrDash(service.nextRestartAt)}`}.`
                    : '';
                line1 = `Down since ${clockOrDash(service.since)}.${next}`;
            }
            return { chip, line1, line2: budget };
        }
        case 'restarting': {
            const number = Math.max(1, Math.min(RESTART_BUDGET, service.restartsInWindow ?? 1));
            return { chip, line1: `Restart ${number} of ${RESTART_BUDGET} started ${clockOrDash(service.since)}.`, line2: budget };
        }
        case 'gave_up':
            return {
                chip,
                line1: `Restarted ${RESTART_BUDGET} times in 30 minutes. Not restarting again. On-call was paged at ${clockOrDash(service.pagedAt)}.`,
                line2: 'Restart budget returns after 1 hour healthy.',
            };
        case 'expected_off':
            return { chip, line1: 'Not installed on this server. The watchdog never starts it.', line2: null };
        default:
            return { chip, chipLabel: 'Running', line1: 'Running, but not expected on this server. Not managed.', line2: null };
    }
}

const ServiceCell: React.FC<{ order: { id: string; name: string }; service: PlatformHealthService | undefined; doc: PlatformHealthDocument }> = ({ order, service, doc }) => {
    const view = cellView(service, doc);
    return (
        <div className="min-w-0">
            <dt>
                <span className="block break-words text-sm font-semibold text-gray-900 dark:text-white">{order.name}</span>
                <span className="block break-words font-mono text-xs text-gray-500 dark:text-gray-400">{service?.unit ?? order.id}</span>
            </dt>
            <dd className="mt-2 flex flex-col gap-2">
                <span><HealthChip kind={view.chip} label={view.chipLabel} /></span>
                <p className={MUTED}>{view.line1}</p>
                {view.line2 && <p className={MUTED}>{view.line2}</p>}
            </dd>
        </div>
    );
};

// ── watchdog ────────────────────────────────────────────────────────────────

const WatchdogRow: React.FC<{ doc: PlatformHealthDocument }> = ({ doc }) => {
    const { state, lastSeenAt } = doc.watchdog;
    const seen = lastSeenAt ? formatWhen(lastSeenAt) : null;
    return (
        <>
            <div className="flex flex-wrap items-center justify-between gap-4">
                <dl>
                    <dt className="text-xs text-gray-500 dark:text-gray-400">Watchdog</dt>
                    <dd className="mt-1">
                        <HealthChip kind={state === 'running' ? 'running' : state === 'silent' ? 'silent' : 'not_installed'} />
                    </dd>
                </dl>
                <p className={MUTED}>
                    {state === 'not_installed' && <span>The watchdog has never reported on this server.</span>}
                    {state !== 'not_installed' && (
                        <span title={seen?.title}>{`Last seen ${seen ? seen.text : '—'}.`}</span>
                    )}
                    {state === 'running' && <span>{' '}Checks run every minute.</span>}
                </p>
            </div>
            {state === 'silent' && (
                <HealthNotice tone="red" role="alert">
                    <p>
                        {`The watchdog has not reported since ${clockOrDash(lastSeenAt)}. Services are not being checked or restarted, and no on-call pages can be sent. Check the timer on the server:`}
                    </p>
                    <p><code className="font-mono text-xs">omni-watchdog.timer</code></p>
                    <p><InstallChecklistLink checklist={doc.installChecklist} /></p>
                </HealthNotice>
            )}
            {state === 'not_installed' && (
                <HealthNotice tone="blue">
                    <p>Watchdog not installed. Service, certificate, disk and alert-channel status appear here once it is installed and reports. Installing it is a step on the server.</p>
                    <p><InstallChecklistLink checklist={doc.installChecklist} /></p>
                </HealthNotice>
            )}
        </>
    );
};

const WatchdogAndServices: React.FC<{ doc: PlatformHealthDocument }> = ({ doc }) => (
    <div className="card flex flex-col gap-6 p-6">
        <WatchdogRow doc={doc} />
        <div className={`flex flex-col gap-4 ${DIVIDER}`}>
            {doc.stop.effective && (
                <HealthNotice tone="amber" icon={PauseCircleIcon}>
                    <p>{stopNotice(doc.stop.source)}</p>
                </HealthNotice>
            )}
            <dl className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {SERVICE_ORDER.map(order => (
                    <ServiceCell key={order.id} order={order} service={doc.services.find(s => s.id === order.id)} doc={doc} />
                ))}
            </dl>
        </div>
    </div>
);

// ── section ─────────────────────────────────────────────────────────────────

const SkeletonCards: React.FC = () => (
    <>
        {[0, 1, 2, 3].map(i => (
            <div key={i} className="card p-6">
                <div className={`h-16 ${HEALTH_SKELETON}`} />
            </div>
        ))}
    </>
);

/**
 * The Platform health section of the Autonomous Ops screen (D-20): the watchdog and its four services first
 * (the focal block), then the cards that follow. Rendered only for a holder of control:platform_autonomous_ops
 * in platform scope (AutonomousOpsActivity), so it never fetches for anyone else.
 */
export const AutonomousOpsPlatformHealth: React.FC<PlatformHealthProps> = ({ refreshSignal = 0 }) => {
    const { doc, fetchedAt, load, loading, loadFailed, reload, applyTestAlert } = usePlatformHealth(refreshSignal);
    const headingRef = useRef<HTMLHeadingElement>(null);
    const testAlert = doc?.testAlert ?? null;
    const noAnswer = useTestAlertNoAnswer(testAlert);
    const fastPoll = testAlert?.state === 'pending' && !noAnswer;

    useEffect(() => {
        if (consumePlatformHealthFocus()) headingRef.current?.focus();
    }, []);

    useEffect(() => {
        if (!fastPoll) return;
        const timer = setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, TEST_ALERT_POLL_MS);
        return () => clearInterval(timer);
    }, [fastPoll, load]);

    const updatedIso = fetchedAt ? new Date(fetchedAt).toISOString() : null;
    const stale = doc ? doc.watchdog.state !== 'running' : true;
    return (
        <section id="platform-health" aria-labelledby="platform-health-title" aria-busy={loading} className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0">
                    <h2 ref={headingRef} id="platform-health-title" tabIndex={-1} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                        Platform health
                    </h2>
                    <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                        Services, certificates, disk and alerting for the platform server, checked every minute by the watchdog.
                    </p>
                </div>
                {updatedIso && (
                    <time dateTime={updatedIso} title={new Date(updatedIso).toLocaleString()} className="text-xs text-gray-500 dark:text-gray-400">
                        {`Updated ${formatClock(updatedIso)}`}
                    </time>
                )}
            </div>
            {loading && <SkeletonCards />}
            {loadFailed && (
                <div className="card p-6">
                    <HealthNotice tone="red" role="alert">
                        <p>Couldn't load platform health. Check your connection and try again.</p>
                        <p>
                            <button type="button" onClick={reload} className="text-sm font-semibold underline underline-offset-2">
                                Reload platform health
                            </button>
                        </p>
                    </HealthNotice>
                </div>
            )}
            {doc && (
                <>
                    <WatchdogAndServices doc={doc} />
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <CertificatesCard certs={doc.certs} stale={stale} updatedAt={doc.updatedAt} />
                        <DiskCard disks={doc.disks} stale={stale} updatedAt={doc.updatedAt} />
                    </div>
                    <OnCallCard
                        oncall={doc.oncall}
                        testAlert={testAlert}
                        watchdogState={doc.watchdog.state}
                        installChecklist={doc.installChecklist}
                        noAnswer={noAnswer}
                        onTestRequested={applyTestAlert}
                    />
                </>
            )}
        </section>
    );
};

export default AutonomousOpsPlatformHealth;
