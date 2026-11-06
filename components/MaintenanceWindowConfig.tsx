import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    CalendarIcon, CheckCircleIcon, ClockIcon, InfoIcon, PencilIcon, PlusIcon, RefreshCwIcon, TrashIcon,
} from './icons';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { EmptyStateCard } from './AutonomousOpsActivityList';
import { DAYS, DeleteWindowDialog, WindowDialog } from './patchRollouts/MaintenanceWindowDialog';
import { showToast } from '../utils/toast';
import type { MaintenanceWindow, WindowStatus } from '../services/patchRollouts/types';
import {
    WindowApiError, browserTimeZone, fetchTimeZone, fetchWindows, fetchWindowStatus, isKnownTimeZone, listTimeZones,
    saveTimeZone,
} from '../services/patchRollouts/windows';

/**
 * Settings > Maintenance (UI-SPEC section 8): the organization's time zone, whether a window is open, and the
 * windows themselves. Rollouts and approved restarts run only inside these windows. Every text from the server is
 * rendered as React text; the server decides what is allowed, the buttons only ask.
 */

const ACCENT_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white ' +
    'hover:bg-primary-700 disabled:opacity-60';
const ICON_BUTTON =
    'inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900 ' +
    'dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white disabled:opacity-60';
const INPUT =
    'min-h-10 w-full max-w-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 ' +
    'font-mono text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500';
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const GREEN_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-green-200 bg-green-50 px-2 py-1 text-xs font-semibold text-green-800 ' +
    'dark:border-green-400/25 dark:bg-green-400/10 dark:text-green-200';
const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs font-semibold ' +
    'text-gray-700 dark:text-gray-200';
const NEUTRAL_CHIP =
    'inline-flex items-center rounded-full bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-700 dark:bg-white/10 dark:text-gray-200';
const DAY_CHIP =
    'inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gray-200 text-xs font-semibold text-gray-900 ' +
    'dark:bg-white/15 dark:text-gray-100';
const BLUE_BLOCK =
    'flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-800 ' +
    'dark:border-blue-400/25 dark:bg-blue-400/10 dark:text-blue-200';
const AMBER_LINE =
    'flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 ' +
    'dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200';
const ERROR_BLOCK =
    'flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 ' +
    'dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-200';
const SKELETON = 'h-32 animate-pulse rounded-lg bg-gray-200 dark:bg-white/10';

const ZONE_SENTENCE = 'Choose a time zone from the list, for example Asia/Kolkata.';
const RECURRENCE_LABEL: Record<MaintenanceWindow['recurrence'], string> = {
    none: 'One-time', daily: 'Daily', weekly: 'Weekly',
};

type Dialog = { kind: 'edit'; window: MaintenanceWindow | null } | { kind: 'delete'; window: MaintenanceWindow } | null;

const MaintenanceWindowConfig: React.FC = () => {
    const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
    const [zone, setZone] = useState<string | null>(null);
    const [status, setStatus] = useState<WindowStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [loadFailed, setLoadFailed] = useState(false);
    const [zoneInput, setZoneInput] = useState('');
    const [zoneSaving, setZoneSaving] = useState(false);
    const [zoneFailed, setZoneFailed] = useState<string | null>(null);
    const [dialog, setDialog] = useState<Dialog>(null);
    const alive = useRef(true);
    const zones = useMemo(() => listTimeZones(), []);

    useEffect(() => () => { alive.current = false; }, []);

    /** `first` shows the skeletons and fills the zone field; later reads keep what the person typed. */
    const load = useCallback(async (first: boolean) => {
        if (first) setLoading(true); else setRefreshing(true);
        setLoadFailed(false);
        try {
            const [rows, storedZone, state] = await Promise.all([fetchWindows(), fetchTimeZone(), fetchWindowStatus()]);
            if (!alive.current) return;
            setWindows(rows);
            setZone(storedZone);
            setStatus(state);
            if (first) setZoneInput(storedZone ?? '');
        } catch {
            if (alive.current) setLoadFailed(true);
        } finally {
            if (alive.current) { setLoading(false); setRefreshing(false); }
        }
    }, []);

    useEffect(() => { void load(true); }, [load]);

    const dirty = zoneInput !== (zone ?? '');
    const zoneValid = isKnownTimeZone(zoneInput);
    const zoneError = dirty && zoneInput !== '' && !zoneValid ? ZONE_SENTENCE : null;

    const saveZone = async () => {
        if (!dirty || !zoneValid || zoneSaving) return;
        setZoneSaving(true);
        setZoneFailed(null);
        try {
            const saved = await saveTimeZone(zoneInput);
            showToast(`Time zone saved. Window times now use ${saved ?? zoneInput}.`, 'success');
            setZone(saved);
            setZoneInput(saved ?? '');
            void load(false);
        } catch (err) {
            const detail = err instanceof WindowApiError ? err.detail.replace(/[.\s]+$/, '') : '';
            setZoneFailed(detail
                ? `Couldn't save the time zone: ${detail}. Try again.`
                : "Couldn't save the time zone. Check your connection and try again.");
        } finally {
            if (alive.current) setZoneSaving(false);
        }
    };

    const reload = () => { setDialog(null); void load(false); };
    const ready = !loading && !loadFailed;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                    <h2 className="flex items-center gap-2 text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                        <CalendarIcon size={20} aria-hidden="true" className="text-gray-500 dark:text-gray-400" />
                        Maintenance windows
                    </h2>
                    <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                        Rollouts and approved restarts run only inside these windows.
                    </p>
                </div>
                <button type="button" className={SECONDARY_BUTTON} disabled={!ready} onClick={() => setDialog({ kind: 'edit', window: null })}>
                    <PlusIcon size={16} aria-hidden="true" />
                    Add window
                </button>
            </div>

            {loading && (
                <div aria-busy="true" className="grid gap-6 md:grid-cols-2">
                    <div className={SKELETON} />
                    <div className={SKELETON} />
                </div>
            )}

            {loadFailed && !loading && (
                <div role="alert" className={ERROR_BLOCK}>
                    <p>Couldn't load maintenance windows. Check your connection and try again.</p>
                    <button type="button" className={SECONDARY_BUTTON} onClick={() => void load(true)}>Try again</button>
                </div>
            )}

            {ready && (
                <>
                    <section className="card space-y-3 p-6">
                        <label htmlFor="maintenance-time-zone" className="block text-sm font-semibold text-gray-900 dark:text-white">
                            Time zone
                        </label>
                        <div className="flex flex-wrap items-center gap-3">
                            <input
                                id="maintenance-time-zone" type="text" list="maintenance-time-zones" value={zoneInput}
                                placeholder={browserTimeZone()} autoComplete="off" spellCheck={false} disabled={zoneSaving}
                                onChange={e => { setZoneInput(e.target.value); setZoneFailed(null); }}
                                aria-describedby="maintenance-time-zone-help"
                                className={INPUT}
                            />
                            <datalist id="maintenance-time-zones">
                                {zones.map(z => <option key={z} value={z} />)}
                            </datalist>
                            <button
                                type="button" onClick={saveZone} disabled={!dirty || !zoneValid || zoneSaving}
                                className={dirty ? ACCENT_BUTTON : SECONDARY_BUTTON}
                            >
                                {zoneSaving ? 'Saving...' : 'Save time zone'}
                            </button>
                        </div>
                        <p id="maintenance-time-zone-help" className={MUTED}>
                            All of this organization's windows use this time zone. Daylight-saving changes are handled.
                        </p>
                        {zone === null && (
                            <div role="status" className={BLUE_BLOCK}>
                                <InfoIcon size={16} aria-hidden="true" className="mt-0.5 flex-shrink-0" />
                                <p>No time zone is set yet. Windows use UTC until you choose one.</p>
                            </div>
                        )}
                        {zoneError && <p role="alert" className="break-words text-xs text-red-700 dark:text-red-300">{zoneError}</p>}
                        {dirty && zoneValid && windows.length > 0 && (
                            <div role="status" className={AMBER_LINE}>
                                <p>{`Existing windows keep their clock times but now run in ${zoneInput}.`}</p>
                            </div>
                        )}
                        {zoneFailed && <p role="alert" className="break-words text-sm text-red-700 dark:text-red-300">{zoneFailed}</p>}
                    </section>

                    {status && status.state !== 'none' && (
                        <div className="card flex items-center justify-between gap-4 p-4">
                            <div className="flex min-w-0 flex-wrap items-center gap-3">
                                {status.state === 'open'
                                    ? <span className={GREEN_CHIP}><CheckCircleIcon size={12} aria-hidden="true" />Window open</span>
                                    : <span className={OUTLINE_CHIP}><ClockIcon size={12} aria-hidden="true" />Window closed</span>}
                                <p className="break-words text-sm text-gray-700 dark:text-gray-200">{status.text}</p>
                            </div>
                            <button type="button" aria-label="Refresh" className={ICON_BUTTON} onClick={() => void load(false)} disabled={refreshing}>
                                <RefreshCwIcon size={16} aria-hidden="true" className={refreshing ? 'animate-spin' : ''} />
                            </button>
                        </div>
                    )}

                    {windows.length === 0 ? (
                        <div className="card">
                            <EmptyStateCard icon={CalendarIcon} heading="No maintenance windows yet">
                                <p className="max-w-prose text-sm text-gray-600 dark:text-gray-400">
                                    Add a window. Rollouts and approved restarts run only inside your windows.
                                </p>
                                <button type="button" className={SECONDARY_BUTTON} onClick={() => setDialog({ kind: 'edit', window: null })}>
                                    <PlusIcon size={16} aria-hidden="true" />
                                    Add window
                                </button>
                            </EmptyStateCard>
                        </div>
                    ) : (
                        <ul className="grid gap-6 md:grid-cols-2">
                            {windows.map(w => (
                                <li key={w.id} className="card space-y-3 p-6">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0 space-y-2">
                                            <h3 className="break-words text-sm font-semibold text-gray-900 dark:text-white">{w.name}</h3>
                                            <span className={NEUTRAL_CHIP}>{RECURRENCE_LABEL[w.recurrence] ?? w.recurrence}</span>
                                        </div>
                                        <div className="flex flex-shrink-0 gap-1">
                                            <button
                                                type="button" className={ICON_BUTTON} aria-label={`Edit window ${w.name}`}
                                                onClick={() => setDialog({ kind: 'edit', window: w })}
                                            >
                                                <PencilIcon size={16} aria-hidden="true" />
                                            </button>
                                            <button
                                                type="button" className={ICON_BUTTON} aria-label={`Delete window ${w.name}`}
                                                onClick={() => setDialog({ kind: 'delete', window: w })}
                                            >
                                                <TrashIcon size={16} aria-hidden="true" />
                                            </button>
                                        </div>
                                    </div>
                                    <p className="break-words text-sm text-gray-700 dark:text-gray-200">{w.scheduleText}</p>
                                    {w.recurrence === 'weekly' && (
                                        <div className="flex flex-wrap gap-1">
                                            {DAYS.filter(d => w.daysOfWeek?.includes(d.iso)).map(d => (
                                                <span key={d.iso} role="img" aria-label={d.full} className={DAY_CHIP}>{d.short}</span>
                                            ))}
                                        </div>
                                    )}
                                    <p className={`${MUTED} font-mono`}>{zone ?? 'UTC'}</p>
                                    <p className={MUTED}>{w.nextText}</p>
                                </li>
                            ))}
                        </ul>
                    )}
                </>
            )}

            <WindowDialog
                isOpen={dialog?.kind === 'edit'}
                window={dialog?.kind === 'edit' ? dialog.window : null}
                timeZone={zone}
                onClose={() => setDialog(null)}
                onSaved={reload}
            />
            <DeleteWindowDialog
                isOpen={dialog?.kind === 'delete'}
                window={dialog?.kind === 'delete' ? dialog.window : null}
                isLast={windows.length === 1}
                onClose={() => setDialog(null)}
                onDeleted={reload}
            />
        </div>
    );
};

export default MaintenanceWindowConfig;
