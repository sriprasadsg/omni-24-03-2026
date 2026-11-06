import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircleIcon, ClockIcon } from '../icons';
import { fetchChangeWindows } from '../../services/patchRollouts/windows';
import type { ChangeWindowRow } from '../../services/patchRollouts/types';

/**
 * The maintenance windows rollouts obey, read-only, above the changes list (UI-SPEC section 9, PTCH-05). Nothing
 * here creates, edits or deletes a window: Manage in Settings is a button only when the viewer can open Settings
 * (the parent passes `onOpenSettings`), plain text otherwise. All texts are server texts rendered as React text.
 */

const SHOWN_FIRST = 5;

const CARD = 'mb-6 rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800';
const TEXT_BUTTON = 'text-sm font-semibold text-gray-900 underline underline-offset-2 dark:text-white';
const GREEN_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-green-200 bg-green-50 px-2 py-1 text-xs font-semibold text-green-800 ' +
    'dark:border-green-400/25 dark:bg-green-400/10 dark:text-green-200';
const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 px-2 py-1 text-xs font-semibold text-gray-700 ' +
    'dark:border-gray-600 dark:text-gray-200';

export interface ChangeManagementWindowsProps {
    /** Given only when the viewer can open Settings; without it Manage in Settings is plain text. */
    onOpenSettings?: () => void;
}

export const ChangeManagementWindows: React.FC<ChangeManagementWindowsProps> = ({ onOpenSettings }) => {
    const [rows, setRows] = useState<ChangeWindowRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [failed, setFailed] = useState(false);
    const [showAll, setShowAll] = useState(false);
    const alive = useRef(true);

    useEffect(() => () => { alive.current = false; }, []);

    const load = useCallback(async () => {
        setLoading(true);
        setFailed(false);
        try {
            const found = await fetchChangeWindows();
            if (alive.current) setRows(found);
        } catch {
            if (alive.current) setFailed(true);
        } finally {
            if (alive.current) setLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    const manage = onOpenSettings
        ? <button type="button" className={TEXT_BUTTON} onClick={onOpenSettings}>Manage in Settings</button>
        : <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">Manage in Settings</span>;
    const visible = showAll ? rows : rows.slice(0, SHOWN_FIRST);
    const hidden = rows.length - visible.length;

    return (
        <section className={CARD}>
            <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-4">
                <div className="min-w-0">
                    <h2 className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">Maintenance windows</h2>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        Rollouts install and restart computers only in these windows.
                    </p>
                </div>
                {manage}
            </div>

            {loading && (
                <div aria-busy="true" className="px-4 pb-4">
                    <div className="h-16 animate-pulse rounded-lg bg-gray-200 dark:bg-white/10" />
                </div>
            )}

            {!loading && failed && (
                <div role="alert" className="flex flex-wrap items-center gap-3 px-4 pb-4">
                    <p className="text-sm text-red-700 dark:text-red-300">Couldn't load maintenance windows.</p>
                    <button type="button" className={TEXT_BUTTON} onClick={() => void load()}>Try again</button>
                </div>
            )}

            {!loading && !failed && rows.length === 0 && (
                <p className="px-4 pb-4 text-sm text-gray-600 dark:text-gray-400">
                    No maintenance windows. Rollouts can't start until one is added.
                </p>
            )}

            {!loading && !failed && rows.length > 0 && (
                <>
                    <ul className="divide-y divide-gray-200 border-t border-gray-200 dark:divide-gray-700 dark:border-gray-700">
                        {visible.map(w => (
                            <li key={w.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                                <div className="min-w-0 flex-1">
                                    <p className="break-words text-sm font-semibold text-gray-900 dark:text-white">{w.name}</p>
                                    <p className="break-words text-xs text-gray-500 dark:text-gray-400">{w.scheduleText}</p>
                                </div>
                                {w.openNow
                                    ? <span className={GREEN_CHIP}><CheckCircleIcon size={12} aria-hidden="true" />Open now</span>
                                    : <span className={OUTLINE_CHIP}><ClockIcon size={12} aria-hidden="true" />{w.nextText}</span>}
                            </li>
                        ))}
                    </ul>
                    {hidden > 0 && (
                        <div className="border-t border-gray-200 px-4 py-3 dark:border-gray-700">
                            <button type="button" className={TEXT_BUTTON} onClick={() => setShowAll(true)}>{`Show ${hidden} more`}</button>
                        </div>
                    )}
                </>
            )}
        </section>
    );
};

export default ChangeManagementWindows;
