import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { fetchIncidents } from '../services/autonomousOpsIncidentsApi';
import type { IncidentCard, IncidentPage } from '../services/autonomousOpsIncidentsApi';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HealthNotice } from './AutonomousOpsHealthChips';
import { AutonomousOpsIncidentCard } from './AutonomousOpsIncidentCard';
import type { LinePatch, StopScope } from './AutonomousOpsIncidentCard';
import { plural } from './AutonomousOpsResponseSettingsDialogs';
import { PauseCircleIcon } from './icons';

/**
 * The Needs your decision section (ACTV-02, 83-19, UI-SPEC section 2). One fetch on mount, then every 30 seconds
 * while the tab is visible, on focus, on the page Refresh and straight after any decision. The first load shows
 * nothing, a background read never shows a skeleton and a failed one keeps the last cards. A card whose last
 * waiting line was just decided stays in place showing its settled lines until the next background read.
 */

export const DECISIONS_POLL_MS = 30_000;
const PAGE = 10;
const MAX_PAGE = 50;
const LOAD_ERROR = "Couldn't load approvals. Check your connection and try again.";
const STOP_TENANT = 'Approving is paused while automatic actions are stopped. You can still deny. Requests keep their 24-hour clock.';
const STOP_PLATFORM =
    'Approving is paused while automatic actions are stopped for the whole platform. You can still deny. Requests keep their 24-hour clock.';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

interface Loaded { items: IncidentCard[]; total: number; stopped: IncidentPage['stopped'] }
interface Held { card: IncidentCard; index: number }

const readable = (page: IncidentPage | null | undefined): page is IncidentPage => Array.isArray(page?.items);

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
    const { status } = useAutonomousOpsStatus();
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
    const idsKey = useRef('');
    const callbacks = useRef({ onDecisionIds, onDecided: onDecidedProp });
    current.current = state;
    callbacks.current = { onDecisionIds, onDecided: onDecidedProp };

    const load = useCallback(async (kind: 'poll' | 'decision') => {
        const mine = ++seq.current;
        const limit = Math.min(MAX_PAGE, Math.max(PAGE, current.current?.items.length ?? 0));
        try {
            const next = await fetchIncidents({ offset: 0, limit, tenantId });
            if (!alive.current || mine !== seq.current) return;
            if (!readable(next)) throw new Error('unreadable incidents');
            if (previousTotal.current !== null && next.total > previousTotal.current) {
                setAnnouncement(`${plural(next.total, 'incident needs', 'incidents need')} your decision`);
            }
            previousTotal.current = next.total;
            setState({ items: next.items, total: next.total, stopped: next.stopped ?? null });
            setFailed(false);
            setNow(Date.now());
            if (kind === 'poll') { setPatches({}); setHeld([]); }
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
            const next = await fetchIncidents({ offset: at.items.length, limit: PAGE, tenantId });
            if (!alive.current) return;
            if (!readable(next)) throw new Error('unreadable incidents');
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
        void load('poll');
        // One timer for the whole section: it re-reads the cards and recomputes every countdown from the server's deadline.
        const timer = setInterval(() => {
            setNow(Date.now());
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

    const onDecided = useCallback((card: IncidentCard, actionId: string, patch: LinePatch) => {
        setPatches(prev => ({ ...prev, [actionId]: { ...prev[actionId], ...patch } }));
        setHeld(prev => (prev.some(h => h.card.id === card.id)
            ? prev
            : [...prev, { card, index: Math.max(0, current.current?.items.findIndex(c => c.id === card.id) ?? 0) }]));
        callbacks.current.onDecided?.();
        void load('decision');
    }, [load]);

    const cards = useMemo(() => {
        const list = state ? state.items.slice() : [];
        for (const { card, index } of [...held].sort((a, b) => a.index - b.index)) {
            if (!list.some(c => c.id === card.id)) list.splice(Math.min(index, list.length), 0, card);
        }
        return list;
    }, [state, held]);

    useEffect(() => {
        const key = cards.map(c => c.id).join('|');
        if (key === idsKey.current) return;
        idsKey.current = key;
        callbacks.current.onDecisionIds?.(new Set(cards.map(c => c.id)));
    }, [cards]);
    useEffect(() => () => { callbacks.current.onDecisionIds?.(new Set()); }, []);

    const fromStatus = status?.stop?.platform ? 'platform' : status?.stop?.tenant ? 'tenant' : null;
    const fromCards = state?.stopped?.scope ?? null;
    const stop: StopScope = fromStatus === 'platform' || fromCards === 'platform' ? 'platform' : fromStatus ?? fromCards;
    const shadow = status?.shadow?.effective === true;

    // First load: nothing at all. Nothing to decide: nothing at all.
    if (state === null && !failed) return null;
    if (state !== null && cards.length === 0) return null;

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

    return (
        <section id="decisions" aria-labelledby="decisions-title" className="space-y-6">
            <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    {heading}
                    <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400">{plural(Math.max(state.total, cards.length), 'incident', 'incidents')}</span>
                </div>
                <p className="break-words text-sm text-gray-600 dark:text-gray-400">
                    Approvals expire after 24 hours and then count as denied. An isolated computer returns to the network after 4 hours unless you confirm it.
                </p>
            </div>
            {stop !== null && (
                <HealthNotice tone="amber" icon={PauseCircleIcon} role="status">
                    <p>{stop === 'platform' ? STOP_PLATFORM : STOP_TENANT}</p>
                </HealthNotice>
            )}
            {cards.map(card => (
                <AutonomousOpsIncidentCard
                    key={card.id}
                    card={card}
                    now={now}
                    stop={stop}
                    shadow={shadow}
                    tenantId={tenantId}
                    patches={patches}
                    onDecided={onDecided}
                />
            ))}
            {state.items.length < state.total && (
                <div className="flex flex-col items-start gap-2">
                    <button type="button" className={SECONDARY_BUTTON} disabled={loadingMore} onClick={() => void loadMore()}>
                        {loadingMore ? 'Loading...' : 'Show more incidents'}
                    </button>
                    {moreFailed && <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{LOAD_ERROR}</p>}
                </div>
            )}
            <div data-live="decisions" role="status" className="sr-only">{announcement}</div>
        </section>
    );
};

export default AutonomousOpsDecisions;
