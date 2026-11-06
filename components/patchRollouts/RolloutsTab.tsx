import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { AppView } from '../../types';
import { useUser } from '../../contexts/UserContext';
import { fetchRollouts } from '../../services/patchRollouts/rollouts';
import type { RingView, RolloutCard as RolloutCardData, RolloutPage, WindowStrip } from '../../services/patchRollouts/types';
import { isSuperAdminRoleName } from '../../utils/permissions';
import { EmptyStateCard } from '../AutonomousOpsActivityList';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { ACCENT_BUTTON } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon, ClockIcon, FlaskConicalIcon, InfoIcon, LayersIcon, PauseCircleIcon, RefreshCwIcon, RocketIcon } from '../icons';
import { RolloutCard } from './RolloutCard';
import { chipClasses } from './RolloutChip';
import { ASSURANCE_LINE, LINK_LABELS, plural } from './rolloutCopy';

/**
 * The Rollouts tab on the Patching screen (84-14, UI-SPEC sections 1 and 2): header, assurance line, window strip,
 * the rollout list and its states. One read on open, then every 30 seconds while the document is visible and the tab
 * is active, on focus, on Refresh and straight after an action. The first load shows skeleton cards; a background read
 * never shows a skeleton or a spinner and a failed one keeps the last cards. Every control comes from the server's
 * flags and every string is React text. The optional props are the extension points later plans fill (84-17 the Start
 * dialog and the rings card, 84-18 the ring detail and the Resume and Cancel actions).
 */

export const ROLLOUTS_POLL_MS = 30_000;
const PAGE = 10;
const MAX_PAGE = 50;

const LOAD_ERROR = "Couldn't load rollouts. Check your connection and try again.";
const INTRO =
    'Install patches in rings: a small canary group first, then larger groups. Each ring waits and is health-checked before the next one starts.';
const NO_START = 'Ask someone with patching access to start a rollout.';
const STOP_BLOCKED = 'Paused while automatic actions are stopped.';
const NO_WINDOW = 'Add a maintenance window first.';
const STOP_TENANT =
    'Rollouts are paused while automatic actions are stopped. Nothing new installs or restarts. A revert that is already under way still runs.';
const STOP_PLATFORM =
    'Rollouts are paused while automatic actions are stopped for the whole platform. Nothing new installs or restarts. A revert that is already under way still runs.';
const SHADOW =
    'Shadow mode is on for this organization. A rollout runs as a simulation: it records what it would have done and installs and restarts nothing.';
const EMPTY_RINGS_NOT_SET = 'Set up your rings, then start a rollout from the patches your computers are waiting for.';
const EMPTY_RINGS_SET = 'Pick the patches your computers are waiting for and roll them out ring by ring.';
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

export interface RolloutsTabProps {
    /** The organization platform staff entered from Tenants, else null (a tenant role never sends one). */
    tenantId?: string | null;
    /** Where Review in Needs your decision and Open maintenance windows navigate. */
    onOpenView?: (view: AppView) => void;
    /** False while another Patching tab is showing: polling pauses. */
    active?: boolean;
    /** A counter the parent bumps after an action so the list reads again straight away. */
    refreshSignal?: number;
    /** Reports the number of rollouts that need a person after every read, so the tab badge follows the list. */
    onAttentionCount?: (count: number) => void;
    /** Start rollout was pressed. Without it the button is not rendered. */
    onStartRequested?: () => void;
    renderStartDialog?: () => React.ReactNode;
    renderRingsCard?: () => React.ReactNode;
    renderRingDetail?: (ring: RingView, card: RolloutCardData) => React.ReactNode;
    renderActions?: (card: RolloutCardData, refresh: () => void) => React.ReactNode;
}

const readable = (page: RolloutPage | null | undefined): page is RolloutPage => Array.isArray(page?.items);

// ---------------------------------------------------------------- the window strip (PTCH-05)

const SettingsLink: React.FC<{ onOpen?: () => void }> = ({ onOpen }) => (
    onOpen
        ? <button type="button" className={TEXT_BUTTON} onClick={onOpen}>{LINK_LABELS.maintenance}</button>
        : <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">{LINK_LABELS.maintenance}</span>
);

const WindowStripCard: React.FC<{ strip: WindowStrip; onOpenSettings?: () => void }> = ({ strip, onOpenSettings }) => (
    <div className="card flex flex-wrap items-center gap-4 p-4">
        {strip.state === 'none' ? (
            <div className="min-w-0 flex-1">
                <HealthNotice tone="amber" icon={AlertTriangleIcon} role="status">
                    <p className="font-semibold">{NO_WINDOW}</p>
                    <div><SettingsLink onOpen={onOpenSettings} /></div>
                </HealthNotice>
            </div>
        ) : (
            <>
                {strip.state === 'open'
                    ? <span className={chipClasses('green')}><ClockIcon size={12} aria-hidden="true" />Window open</span>
                    : <span className={chipClasses('outline')}><ClockIcon size={12} aria-hidden="true" />Window closed</span>}
                <p className="min-w-0 break-words text-sm text-gray-900 dark:text-white">{strip.text}</p>
            </>
        )}
        <p className={`${MUTED} ml-auto`}>
            {strip.timeZone
                ? <>Time zone: <span className="break-all font-mono">{strip.timeZone}</span></>
                : 'No time zone set. Windows use UTC.'}
        </p>
    </div>
);

// ---------------------------------------------------------------- the tab

export const RolloutsTab: React.FC<RolloutsTabProps> = ({
    tenantId = null, onOpenView, active = true, refreshSignal = 0, onAttentionCount, onStartRequested,
    renderStartDialog, renderRingsCard, renderRingDetail, renderActions,
}) => {
    const { currentUser, hasPermission } = useUser();
    const [state, setState] = useState<RolloutPage | null>(null);
    const [failed, setFailed] = useState(false);
    const [announcement, setAnnouncement] = useState('');
    const [loadingMore, setLoadingMore] = useState(false);
    const [moreFailed, setMoreFailed] = useState(false);
    const alive = useRef(true);
    const seq = useRef(0);
    const current = useRef<RolloutPage | null>(null);
    const previousAttention = useRef<number | null>(null);
    const moreBusy = useRef(false);
    const lastSignal = useRef(refreshSignal);
    const callbacks = useRef({ onAttentionCount });
    current.current = state;
    callbacks.current = { onAttentionCount };

    const load = useCallback(async () => {
        const mine = ++seq.current;
        const limit = Math.min(MAX_PAGE, Math.max(PAGE, current.current?.items.length ?? 0));
        try {
            const next = await fetchRollouts({ offset: 0, limit, tenantId });
            if (!alive.current || mine !== seq.current) return;
            if (!readable(next)) throw new Error('unreadable rollouts');
            const attention = Number.isFinite(next.attentionCount) ? next.attentionCount : 0;
            if (previousAttention.current !== null && attention > previousAttention.current) {
                setAnnouncement(`${plural(attention, 'rollout needs', 'rollouts need')} your attention`);
            }
            previousAttention.current = attention;
            setState(next);
            setFailed(false);
            callbacks.current.onAttentionCount?.(attention);
        } catch {
            if (alive.current && mine === seq.current) setFailed(true);
        }
    }, [tenantId]);

    const loadMore = useCallback(async () => {
        const at = current.current;
        if (moreBusy.current || !at) return;
        moreBusy.current = true;
        setLoadingMore(true);
        setMoreFailed(false);
        try {
            const next = await fetchRollouts({ offset: at.items.length, limit: PAGE, tenantId });
            if (!alive.current) return;
            if (!readable(next)) throw new Error('unreadable rollouts');
            setState(prev => {
                if (!prev) return prev;
                const known = new Set(prev.items.map(c => c.id));
                return { ...prev, items: [...prev.items, ...next.items.filter(c => !known.has(c.id))], total: next.total };
            });
        } catch {
            if (alive.current) setMoreFailed(true);
        } finally {
            moreBusy.current = false;
            if (alive.current) setLoadingMore(false);
        }
    }, [tenantId]);

    useEffect(() => {
        alive.current = true;
        return () => { alive.current = false; };
    }, []);

    useEffect(() => {
        if (!active) return undefined;
        void load();
        const timer = setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, ROLLOUTS_POLL_MS);
        const onFocus = () => { void load(); };
        window.addEventListener('focus', onFocus);
        return () => { clearInterval(timer); window.removeEventListener('focus', onFocus); };
    }, [load, active]);

    useEffect(() => {
        if (refreshSignal === lastSignal.current) return;
        lastSignal.current = refreshSignal;
        if (active) void load();
    }, [refreshSignal, active, load]);

    const refresh = useCallback(() => { void load(); }, [load]);

    const canOpenSettings = !!onOpenView && (isSuperAdminRoleName(currentUser?.role) || hasPermission('manage:settings'));

    const intro = (
        <div className="space-y-2">
            <h2 className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">Rollouts</h2>
            <p className="break-words text-sm text-gray-600 dark:text-gray-400">{INTRO}</p>
        </div>
    );
    const assurance = (
        <p className={`${MUTED} flex items-start gap-2`}>
            <InfoIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
            {ASSURANCE_LINE}
        </p>
    );
    const refreshButton = (
        <button type="button" className={SECONDARY_BUTTON} onClick={refresh}>
            <RefreshCwIcon size={16} aria-hidden="true" />
            Refresh
        </button>
    );

    // ---- first load, and a first load that failed: nothing but the header, the assurance line and the state

    if (state === null) {
        return (
            <section aria-labelledby="rollouts-list-title" aria-busy={!failed} className="space-y-6">
                <div className="flex flex-wrap items-start justify-between gap-4">{intro}{refreshButton}</div>
                {assurance}
                <h3 id="rollouts-list-title" className="sr-only">All rollouts</h3>
                {failed ? (
                    <HealthNotice tone="red" icon={AlertTriangleIcon} role="alert">
                        <p>{LOAD_ERROR}</p>
                        <div>
                            <button type="button" className={TEXT_BUTTON} onClick={() => { setFailed(false); void load(); }}>{LINK_LABELS.tryAgain}</button>
                        </div>
                    </HealthNotice>
                ) : (
                    <div className="space-y-6">
                        {[0, 1, 2].map(i => <div key={i} className="card h-24 animate-pulse" />)}
                    </div>
                )}
            </section>
        );
    }

    const { flags, window: strip } = state;

    // ---- the platform organization has no rollouts

    if (flags.platformTenant) {
        return (
            <section className="card">
                <EmptyStateCard icon={LayersIcon} heading="Rollouts aren't available for the platform organization" headingLevel="h2">
                    <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">
                        Patches are never rolled out to the platform's own server. Open a customer organization to start a rollout.
                    </p>
                </EmptyStateCard>
            </section>
        );
    }

    // ---- what Start rollout does: the server's flag shows it, the stop and a missing window only disable it

    const blocked = flags.stopped ? STOP_BLOCKED : strip.state === 'none' ? NO_WINDOW : null;
    const canStart = flags.canStart && !!onStartRequested;
    const startButton = (id: string) => (
        <div className="flex flex-col items-start gap-1">
            <button
                type="button"
                className={ACCENT_BUTTON}
                disabled={blocked !== null}
                aria-describedby={blocked ? id : undefined}
                onClick={() => onStartRequested?.()}
            >
                <RocketIcon size={16} aria-hidden="true" />
                {LINK_LABELS.startRollout}
            </button>
            {blocked && <p id={id} className={MUTED}>{blocked}</p>}
        </div>
    );

    const cards = state.items;
    const empty = cards.length === 0 && state.total === 0;

    return (
        <section aria-labelledby="rollouts-list-title" aria-busy="false" className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                {intro}
                <div className="flex flex-wrap items-start gap-2">
                    {refreshButton}
                    {canStart && startButton('rollouts-start-reason')}
                </div>
            </div>
            {!flags.canStart && <p className={MUTED}>{NO_START}</p>}
            {assurance}
            <WindowStripCard strip={strip} onOpenSettings={canOpenSettings ? () => onOpenView?.('settings') : undefined} />
            {flags.stopped && (
                <HealthNotice tone="amber" icon={PauseCircleIcon} role="status">
                    <p>{flags.stopScope === 'platform' ? STOP_PLATFORM : STOP_TENANT}</p>
                </HealthNotice>
            )}
            {flags.shadow && (
                <HealthNotice tone="blue" icon={FlaskConicalIcon} role="status">
                    <p>{SHADOW}</p>
                </HealthNotice>
            )}
            <h3 id="rollouts-list-title" className="sr-only">All rollouts</h3>
            {empty ? (
                <div className="card">
                    <EmptyStateCard icon={LayersIcon} heading="No rollouts yet">
                        <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">
                            {state.ringsSet ? EMPTY_RINGS_SET : EMPTY_RINGS_NOT_SET}
                        </p>
                        {canStart && startButton('rollouts-empty-start-reason')}
                    </EmptyStateCard>
                </div>
            ) : (
                <div className="space-y-6">
                    {cards.map(card => (
                        <RolloutCard
                            key={card.id}
                            card={card}
                            onOpenView={onOpenView}
                            renderRingDetail={renderRingDetail}
                            actions={renderActions?.(card, refresh)}
                        />
                    ))}
                </div>
            )}
            {cards.length < state.total && (
                <div className="flex flex-col items-start gap-2">
                    <button type="button" className={SECONDARY_BUTTON} disabled={loadingMore} onClick={() => void loadMore()}>
                        {loadingMore ? 'Loading...' : 'Show more rollouts'}
                    </button>
                    {moreFailed && <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{LOAD_ERROR}</p>}
                </div>
            )}
            {renderRingsCard?.()}
            {renderStartDialog?.()}
            <div data-live="rollouts" role="status" className="sr-only">{announcement}</div>
        </section>
    );
};

export default RolloutsTab;
