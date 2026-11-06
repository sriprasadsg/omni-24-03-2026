import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchPendingPatches } from '../../services/patchRollouts/start';
import type { PendingPatch } from '../../services/patchRollouts/types';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { FIELD, HELPER } from '../AutonomousOpsResponseSettings';
import { LinuxIcon, SearchIcon, WindowsIcon } from '../icons';
import { chipClasses } from './RolloutChip';
import { LINK_LABELS, plural } from './rolloutCopy';

/**
 * The Patches to install section of the Start dialog (84-17, UI-SPEC section 3): the patches the organization's
 * computers are waiting for, 50 at a time with a search, one checkbox row each. The ticks belong to the dialog, so
 * they survive a new search and a page change. The picker only reads; nothing is stored here.
 */

export const PATCH_SEARCH_DEBOUNCE_MS = 300;
const PAGE = 50;
const LOAD_ERROR = "Couldn't load the patches. Check your connection and try again.";

export const NOTHING_PENDING = 'Nothing is waiting to be installed.';

interface Props {
    tenantId?: string | null;
    selected: ReadonlySet<string>;
    onToggle: (patchId: string) => void;
    /** True once the server says nothing at all is pending (no search applied). */
    onEmptyChange: (empty: boolean) => void;
    /** The id the dialog points Start's aria-describedby at when nothing is pending. */
    emptyId: string;
}

const OsChip: React.FC<{ os: PendingPatch['os'] }> = ({ os }) => {
    const Icon = os === 'windows' ? WindowsIcon : LinuxIcon;
    return (
        <span className={chipClasses('outline')}>
            <Icon size={12} aria-hidden="true" />
            {os === 'windows' ? 'Windows' : 'Linux'}
        </span>
    );
};

export const StartPatchPicker: React.FC<Props> = ({ tenantId = null, selected, onToggle, onEmptyChange, emptyId }) => {
    const labelId = useId();
    const [items, setItems] = useState<PendingPatch[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState('');
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [failed, setFailed] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const alive = useRef(true);
    const seq = useRef(0);
    const emptyCb = useRef(onEmptyChange);
    emptyCb.current = onEmptyChange;

    useEffect(() => {
        alive.current = true;
        return () => { alive.current = false; };
    }, []);

    useEffect(() => {
        if (search === query) return undefined;
        const timer = setTimeout(() => setQuery(search.trim()), PATCH_SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(timer);
    }, [search, query]);

    useEffect(() => {
        const mine = ++seq.current;
        setLoading(true);
        setFailed(false);
        fetchPendingPatches({ offset: 0, limit: PAGE, search: query, tenantId })
            .then(page => {
                if (!alive.current || mine !== seq.current) return;
                const list = Array.isArray(page?.items) ? page.items : [];
                setItems(list);
                setTotal(Number.isFinite(page?.total) ? page.total : list.length);
                if (!query) emptyCb.current(list.length === 0 && !(page?.total > 0));
            })
            .catch(() => { if (alive.current && mine === seq.current) setFailed(true); })
            .finally(() => { if (alive.current && mine === seq.current) setLoading(false); });
    }, [query, tenantId, attempt]);

    const showMore = useCallback(async () => {
        const mine = seq.current;
        setLoadingMore(true);
        try {
            const page = await fetchPendingPatches({ offset: items.length, limit: PAGE, search: query, tenantId });
            if (!alive.current || mine !== seq.current) return;
            const known = new Set(items.map(p => p.patchId));
            setItems(prev => [...prev, ...(Array.isArray(page?.items) ? page.items : []).filter(p => !known.has(p.patchId))]);
            setTotal(Number.isFinite(page?.total) ? page.total : total);
        } catch {
            if (alive.current) setFailed(true);
        } finally {
            if (alive.current) setLoadingMore(false);
        }
    }, [items, query, tenantId, total]);

    const nothingPending = !loading && !failed && items.length === 0 && !query;

    return (
        <div className="space-y-2">
            <p id={labelId} className="text-sm font-semibold text-gray-900 dark:text-white">Patches to install</p>
            <p className={HELPER}>These are the updates your computers are waiting for.</p>
            {nothingPending ? (
                <p id={emptyId} className="break-words text-sm text-gray-600 dark:text-gray-400">{NOTHING_PENDING}</p>
            ) : (
                <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="relative w-full max-w-sm">
                            <SearchIcon size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                            <input
                                type="search" value={search} aria-label="Search patches" placeholder="Search patches"
                                className={`${FIELD} w-full pl-9`} onChange={e => setSearch(e.target.value)}
                            />
                        </div>
                        <p className="text-xs tabular-nums text-gray-500 dark:text-gray-400">{`${selected.size} selected`}</p>
                    </div>
                    {failed ? (
                        <div className="space-y-2">
                            <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{LOAD_ERROR}</p>
                            <button type="button" className={SECONDARY_BUTTON} onClick={() => setAttempt(n => n + 1)}>{LINK_LABELS.tryAgain}</button>
                        </div>
                    ) : loading ? (
                        <div aria-busy="true" className="h-16 animate-pulse rounded-lg bg-gray-200 dark:bg-white/10" />
                    ) : items.length === 0 ? (
                        <p className="break-words text-sm text-gray-600 dark:text-gray-400">No patches match your search.</p>
                    ) : (
                        <div className="max-h-72 overflow-y-auto rounded-lg border border-gray-200 dark:border-white/10">
                            <ul aria-labelledby={labelId} className="divide-y divide-gray-200 dark:divide-white/10">
                                {items.map(p => (
                                    <li key={p.patchId}>
                                        <label className="flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm text-gray-900 dark:text-white">
                                            <input
                                                type="checkbox" className="h-4 w-4 shrink-0" checked={selected.has(p.patchId)}
                                                onChange={() => onToggle(p.patchId)}
                                            />
                                            <span className="break-all font-mono text-xs">{p.patchId}</span>
                                            <span className="min-w-0 flex-1 break-words">{p.title}</span>
                                            <OsChip os={p.os} />
                                            <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400">{plural(p.computers, 'computer', 'computers')}</span>
                                        </label>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {!failed && !loading && items.length < total && (
                        <button type="button" className={SECONDARY_BUTTON} disabled={loadingMore} onClick={() => void showMore()}>
                            {loadingMore ? 'Loading...' : 'Show more patches'}
                        </button>
                    )}
                </>
            )}
        </div>
    );
};
