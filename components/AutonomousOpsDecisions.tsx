import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { fetchIncidents } from '../services/autonomousOpsIncidentsApi';
import type { IncidentCard, IncidentPage } from '../services/autonomousOpsIncidentsApi';
import { fetchRolloutCards } from '../services/patchRollouts/approvals';
import type { RolloutCardPage } from '../services/patchRollouts/approvals';
import type { ApprovalCard } from '../services/patchRollouts/types';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HealthNotice } from './AutonomousOpsHealthChips';
import { AutonomousOpsIncidentCard } from './AutonomousOpsIncidentCard';
import type { LinePatch, StopScope } from './AutonomousOpsIncidentCard';
import { plural } from './AutonomousOpsResponseSettingsDialogs';
import { PauseCircleIcon } from './icons';
import { RolloutApprovalCard } from './patchRollouts/RolloutApprovalCard';

/**
 * The Needs your decision section (ACTV-02, 83-19, UI-SPEC section 2). One fetch on mount, then every 30 seconds
 * while the tab is visible, on focus, on the page Refresh and straight after any decision. The first load shows
 * nothing, a background read never shows a skeleton and a failed one keeps the last cards. A card whose last
 * waiting line was just decided stays in place showing its settled lines until the next background read.
 *
 * Phase 84 (84-15, UI-SPEC section 6): rollout approval cards are read beside the incident cards on the same cadence
 * and merged into the one list, soonest deadline first (each source keeps its own order). A failed read of one kind
 * never hides the cards of the other: it keeps that kind's last cards and shows the "couldn't refresh" notice.
 */

export const DECISIONS_POLL_MS = 30_000;
const PAGE = 10;
const MAX_PAGE = 50;
const LOAD_ERROR = "Couldn't load approvals. Check your connection and try again.";
const STALE_ERROR = "Couldn't refresh approvals. Showing the last result.";
const STOP_TENANT = 'Approving is paused while automatic actions are stopped. You can still deny. Requests keep their 24-hour clock.';
const STOP_PLATFORM =
    'Approving is paused while automatic actions are stopped for the whole platform. You can still deny. Requests keep their 24-hour clock.';
const EXPIRY_SENTENCE = 'Approvals expire after 24 hours and then count as denied.';
const ISOLATION_SENTENCE = 'An isolated computer returns to the network after 4 hours unless you confirm it.';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

type Stopped = IncidentPage['stopped'];
interface Loaded {
    items: IncidentCard[]; total: number; rollouts: ApprovalCard[]; rolloutTotal: number; stopped: Stopped;
}
/** One card of the merged list: an incident or a patch rollout ring. */
type Entry = { key: string; kind: 'incident'; card: IncidentCard } | { key: string; kind: 'rollout'; card: ApprovalCard };
interface Held { entry: Entry; index: number }

const readable = (page: { items?: unknown } | null | undefined): boolean => Array.isArray(page?.items);
const incidentEntry = (card: IncidentCard): Entry => ({ key: `i:${card.id}`, kind: 'incident', card });
const rolloutEntry = (card: ApprovalCard): Entry => ({ key: `r:${card.anchorId}`, kind: 'rollout', card });
const deadlineOf = (e: Entry): number => {
    const at = Date.parse((e.kind === 'incident' ? e.card.deadlineAt : e.card.expiresAt) ?? '');
    return Number.isFinite(at) ? at : Infinity;
};

/** Two lists that are each already in order, merged by the soonest deadline; an incident wins a tie (it carries a start time). */
function mergeByDeadline(incidents: IncidentCard[], rollouts: ApprovalCard[]): Entry[] {
    const out: Entry[] = [];
    let i = 0;
    let r = 0;
    while (i < incidents.length || r < rollouts.length) {
        const a = i < incidents.length ? incidentEntry(incidents[i]) : null;
        const b = r < rollouts.length ? rolloutEntry(rollouts[r]) : null;
        if (a && (!b || deadlineOf(a) <= deadlineOf(b))) { out.push(a); i += 1; } else if (b) { out.push(b); r += 1; }
    }
    return out;
}

/** The wider stop of the two reads: platform beats tenant; none when neither read reports one. */
const stopFrom = (...stops: Array<Stopped | undefined>): Stopped =>
    stops.some(x => x?.scope === 'platform') ? { scope: 'platform' } : stops.some(x => x) ? { scope: 'tenant' } : null;

interface Props {
    /** viewingTenantId: the organization platform staff entered from Tenants, else null (a tenant role never sends one). */
    tenantId: string | null;
    /** The page Refresh counter. */
    refreshSignal?: number;
    /** The incident ids whose card is on screen, so the Activity list can link to them. */
    onDecisionIds?: (ids: ReadonlySet<string>) => void;
    /** A decision was made: the Activity list reloads its rows. */
    onDecided?: () => void;
}

export const AutonomousOpsDecisions: React.FC<Props> = ({ tenantId, refreshSignal = 0, onDecisionIds, onDecided: onDecidedProp }) => {
    const { status, refresh } = useAutonomousOpsStatus();
    const [state, setState] = useState<Loaded | null>(null);
    const [failed, setFailed] = useState(false);
    const [patches, setPatches] = useState<Record<string, LinePatch>>({});
    const [held, setHeld] = useState<Held[]>([]);
    const [now, setNow] = useState(() => Date.now());
    const [announcement, setAnnouncement] = useState('');
    const [loadingMore, setLoadingMore] = useState(false);
    const [moreFailed, setMoreFailed] = useState(false);
    const alive = useRef(true);
    const seq = useRef(0);
    const current = useRef<Loaded | null>(null);
    const previousTotal = useRef<number | null>(null);
    const moreBusy = useRef(false);
    const lastSignal = useRef(refreshSignal);
    /** Server clock minus browser clock, from the newest read that carried `serverNow` (WR-27). */
    const skew = useRef(0);
    const idsKey = useRef('');
    const callbacks = useRef({ onDecisionIds, onDecided: onDecidedProp });
    current.current = state;
    callbacks.current = { onDecisionIds, onDecided: onDecidedProp };

    const load = useCallback(async (kind: 'poll' | 'decision') => {
        const mine = ++seq.current;
        const at = current.current;
        const size = (n: number | undefined) => Math.min(MAX_PAGE, Math.max(PAGE, n ?? 0));
        const [inc, rol] = await Promise.allSettled([
            fetchIncidents({ offset: 0, limit: size(at?.items.length), tenantId }),
            fetchRolloutCards({ offset: 0, limit: size(at?.rollouts.length), tenantId }),
        ]);
        if (!alive.current || mine !== seq.current) return;
        const incidents: IncidentPage | null = inc.status === 'fulfilled' && readable(inc.value) ? inc.value : null;
        const rollouts: RolloutCardPage | null = rol.status === 'fulfilled' && readable(rol.value) ? rol.value : null;
        // Nothing readable at all: the old behaviour (the load error on a first load, the notice after).
        if (!incidents && !rollouts) { setFailed(true); return; }
        // A first load where one kind failed and the other has nothing to show is a failed load, not an empty section.
        if (!at && (!incidents || !rollouts) && (incidents?.items.length ?? 0) + (rollouts?.items.length ?? 0) === 0) {
            setFailed(true);
            return;
        }
        // One kind unreadable: it keeps its last cards, so a decision waiting there is never hidden by the other kind's read.
        const next: Loaded = {
            items: incidents ? incidents.items : at?.items ?? [],
            total: incidents ? incidents.total : at?.total ?? 0,
            rollouts: rollouts ? rollouts.items : at?.rollouts ?? [],
            rolloutTotal: rollouts ? rollouts.total : at?.rolloutTotal ?? 0,
            stopped: stopFrom(incidents ? incidents.stopped : at?.stopped, rollouts?.stopped),
        };
        const combined = next.total + next.rolloutTotal;
        if (previousTotal.current !== null && combined > previousTotal.current) {
            setAnnouncement(next.rolloutTotal > 0
                ? `${plural(combined, 'decision needs', 'decisions need')} your decision`
                : `${plural(next.total, 'incident needs', 'incidents need')} your decision`);
        }
        previousTotal.current = combined;
        const serverAt = Date.parse(incidents?.serverNow ?? rollouts?.serverNow ?? '');
        if (Number.isFinite(serverAt)) skew.current = serverAt - Date.now();
        setState(next);
        setFailed(!incidents || !rollouts);
        setNow(Date.now() + skew.current);
        if (kind === 'poll') { setPatches({}); setHeld([]); }
        // A held card still on the server follows its newest version, so lines resolved elsewhere settle (WR-30).
        else {
            const fresh = [...next.items.map(incidentEntry), ...next.rollouts.map(rolloutEntry)];
            setHeld(prev => prev.map(h => ({ ...h, entry: fresh.find(e => e.key === h.entry.key) ?? h.entry })));
        }
    }, [tenantId]);

    const loadMore = useCallback(async () => {
        const at = current.current;
        if (moreBusy.current || !at) return;
        moreBusy.current = true;
        setLoadingMore(true);
        setMoreFailed(false);
        try {
            const [inc, rol] = await Promise.all([
                at.items.length < at.total ? fetchIncidents({ offset: at.items.length, limit: PAGE, tenantId }) : null,
                at.rollouts.length < at.rolloutTotal ? fetchRolloutCards({ offset: at.rollouts.length, limit: PAGE, tenantId }) : null,
            ]);
            if (!alive.current) return;
            if ((inc && !readable(inc)) || (rol && !readable(rol))) throw new Error('unreadable approvals');
            setState(prev => {
                if (!prev) return prev;
                const known = new Set(prev.items.map(c => c.id));
                const knownRollouts = new Set(prev.rollouts.map(c => c.anchorId));
                return {
                    ...prev,
                    items: inc ? [...prev.items, ...inc.items.filter(c => !known.has(c.id))] : prev.items,
                    total: inc ? inc.total : prev.total,
                    rollouts: rol ? [...prev.rollouts, ...rol.items.filter(c => !knownRollouts.has(c.anchorId))] : prev.rollouts,
                    rolloutTotal: rol ? rol.total : prev.rolloutTotal,
                };
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
        void load('poll');
        // One timer for the whole section: it re-reads the cards and recomputes every countdown from the server's deadline.
        const timer = setInterval(() => {
            setNow(Date.now() + skew.current);
            if (document.visibilityState !== 'hidden') void load('poll');
        }, DECISIONS_POLL_MS);
        const onFocus = () => { void load('poll'); };
        window.addEventListener('focus', onFocus);
        return () => { alive.current = false; clearInterval(timer); window.removeEventListener('focus', onFocus); };
    }, [load]);

    useEffect(() => {
        if (refreshSignal === lastSignal.current) return;
        lastSignal.current = refreshSignal;
        void load('poll');
    }, [refreshSignal, load]);

    /** Keeps a card whose last waiting line was just decided in place until the next background read. */
    const hold = useCallback((entry: Entry) => {
        const at = current.current;
        const position = at ? mergeByDeadline(at.items, at.rollouts).findIndex(e => e.key === entry.key) : 0;
        setHeld(prev => (prev.some(h => h.entry.key === entry.key)
            ? prev.map(h => (h.entry.key === entry.key ? { ...h, entry } : h))
            : [...prev, { entry, index: Math.max(0, position) }]));
    }, []);

    const onDecided = useCallback((card: IncidentCard, actionId: string, patch: LinePatch) => {
        setPatches(prev => ({ ...prev, [actionId]: { ...prev[actionId], ...patch } }));
        hold(incidentEntry(card));
        callbacks.current.onDecided?.();
        void load('decision');
    }, [load, hold]);

    const onRolloutDecided = useCallback((card: ApprovalCard) => {
        hold(rolloutEntry(card));
        callbacks.current.onDecided?.();
        void load('decision');
    }, [load, hold]);

    /** A decision the server refused for a lasting reason: re-read the cards and the stop state (WR-26). */
    const onStale = useCallback(() => { void load('decision'); void refresh(); }, [load, refresh]);

    const entries = useMemo(() => {
        const list = state ? mergeByDeadline(state.items, state.rollouts) : [];
        for (const { entry, index } of [...held].sort((a, b) => a.index - b.index)) {
            if (!list.some(e => e.key === entry.key)) list.splice(Math.min(index, list.length), 0, entry);
        }
        return list;
    }, [state, held]);

    const incidentCards = useMemo(
        () => entries.flatMap(e => (e.kind === 'incident' ? [e.card] : [])),
        [entries],
    );
    const rolloutCount = entries.length - incidentCards.length;

    useEffect(() => {
        const key = incidentCards.map(c => c.id).join('|');
        if (key === idsKey.current) return;
        idsKey.current = key;
        callbacks.current.onDecisionIds?.(new Set(incidentCards.map(c => c.id)));
    }, [incidentCards]);
    useEffect(() => () => { callbacks.current.onDecisionIds?.(new Set()); }, []);

    const fromStatus = status?.stop?.platform ? 'platform' : status?.stop?.tenant ? 'tenant' : null;
    const fromCards = state?.stopped?.scope ?? null;
    const stop: StopScope = fromStatus === 'platform' || fromCards === 'platform' ? 'platform' : fromStatus ?? fromCards;
    const shadow = status?.shadow?.effective === true;

    // First load: nothing at all. Nothing to decide: nothing at all.
    if (state === null && !failed) return null;
    if (state !== null && entries.length === 0) return null;

    const heading = (
        <h2 id="decisions-title" tabIndex={-1} className="text-lg font-semibold leading-tight text-gray-900 focus:outline-none dark:text-white">
            Needs your decision
        </h2>
    );

    if (state === null) {
        return (
            <section id="decisions" aria-labelledby="decisions-title" className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-4">{heading}</div>
                <HealthNotice tone="red" role="alert">
                    <p>{LOAD_ERROR}</p>
                    <div>
                        <button type="button" className={TEXT_BUTTON} onClick={() => { setFailed(false); void load('poll'); }}>Try again</button>
                    </div>
                </HealthNotice>
            </section>
        );
    }

    const incidentTotal = Math.max(state.total, incidentCards.length);
    const rolloutTotal = Math.max(state.rolloutTotal, rolloutCount);
    const counts = [
        incidentTotal > 0 ? plural(incidentTotal, 'incident', 'incidents') : '',
        rolloutTotal > 0 ? plural(rolloutTotal, 'rollout ring', 'rollout rings') : '',
    ].filter(Boolean).join(' · ');
    const hasMore = state.items.length < state.total || state.rollouts.length < state.rolloutTotal;

    return (
        <section id="decisions" aria-labelledby="decisions-title" className="space-y-6">
            <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    {heading}
                    <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400">{counts}</span>
                </div>
                <p className="break-words text-sm text-gray-600 dark:text-gray-400">
                    {incidentCards.length > 0 ? `${EXPIRY_SENTENCE} ${ISOLATION_SENTENCE}` : EXPIRY_SENTENCE}
                </p>
            </div>
            {failed && (
                <HealthNotice tone="amber" role="status">
                    <p>{STALE_ERROR}</p>
                    <div>
                        <button type="button" className={TEXT_BUTTON} onClick={() => void load('poll')}>Try again</button>
                    </div>
                </HealthNotice>
            )}
            {stop !== null && (
                <HealthNotice tone="amber" icon={PauseCircleIcon} role="status">
                    <p>{stop === 'platform' ? STOP_PLATFORM : STOP_TENANT}</p>
                </HealthNotice>
            )}
            {entries.map(entry => (entry.kind === 'incident' ? (
                <AutonomousOpsIncidentCard
                    key={entry.key}
                    card={entry.card}
                    now={now}
                    stop={stop}
                    shadow={shadow}
                    tenantId={tenantId}
                    patches={patches}
                    onDecided={onDecided}
                    onStale={onStale}
                />
            ) : (
                <RolloutApprovalCard
                    key={entry.key}
                    card={entry.card}
                    now={now}
                    stopped={stop !== null}
                    shadow={shadow}
                    tenantId={tenantId}
                    onDecided={onRolloutDecided}
                    onStale={onStale}
                />
            )))}
            {hasMore && (
                <div className="flex flex-col items-start gap-2">
                    <button type="button" className={SECONDARY_BUTTON} disabled={loadingMore} onClick={() => void loadMore()}>
                        {loadingMore ? 'Loading...' : rolloutTotal > 0 ? 'Show more' : 'Show more incidents'}
                    </button>
                    {moreFailed && <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{LOAD_ERROR}</p>}
                </div>
            )}
            <div data-live="decisions" role="status" className="sr-only">{announcement}</div>
        </section>
    );
};

export default AutonomousOpsDecisions;
