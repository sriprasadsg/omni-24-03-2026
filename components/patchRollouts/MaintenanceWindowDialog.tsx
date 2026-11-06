import React, { useId, useMemo, useState } from 'react';
import { Modal } from '../Modal';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { AlertTriangleIcon } from '../icons';
import { showToast } from '../../utils/toast';
import type { MaintenanceWindow } from '../../services/patchRollouts/types';
import {
    WindowApiError, browserTimeZone, createWindow, deleteWindow, isKnownTimeZone, listTimeZones, updateWindow,
} from '../../services/patchRollouts/windows';
import type { WindowRequest } from '../../services/patchRollouts/windows';

/**
 * Add, edit and delete a maintenance window (UI-SPEC section 8). The dialogs make their own call so the Settings
 * panel only reloads. Every sentence is server or UI-SPEC text and is rendered as React text.
 */

type Recurrence = 'none' | 'daily' | 'weekly';

const INPUT =
    'min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm ' +
    'text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500';
const LABEL = 'block text-sm font-semibold text-gray-900 dark:text-white mb-1';
const HELPER = 'break-words text-xs text-gray-500 dark:text-gray-400';
const ERROR_TEXT = 'break-words text-xs text-red-700 dark:text-red-300';
const ERROR_BLOCK =
    'break-words rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800 ' +
    'dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-200';
const AMBER_BLOCK =
    'flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800 ' +
    'dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200';
const ACCENT_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white ' +
    'hover:bg-primary-700 disabled:opacity-60';
const DANGER_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white ' +
    'hover:bg-red-700 disabled:opacity-60';

/** ISO weekdays, Monday 1 to Sunday 7: the numbers the server stores. */
export const DAYS: Array<{ iso: number; short: string; full: string }> = [
    { iso: 1, short: 'Mon', full: 'Monday' }, { iso: 2, short: 'Tue', full: 'Tuesday' },
    { iso: 3, short: 'Wed', full: 'Wednesday' }, { iso: 4, short: 'Thu', full: 'Thursday' },
    { iso: 5, short: 'Fri', full: 'Friday' }, { iso: 6, short: 'Sat', full: 'Saturday' },
    { iso: 7, short: 'Sun', full: 'Sunday' },
];

const MAX_MINUTES = 24 * 60;

interface Form {
    name: string;
    recurrence: Recurrence;
    startTime: string;
    endTime: string;
    days: number[];
    startsAt: string;
    endsAt: string;
    zone: string;
}

function initialForm(win: MaintenanceWindow | null): Form {
    return {
        name: win?.name ?? '',
        recurrence: win?.recurrence ?? 'daily',
        startTime: win?.startTime ?? '',
        endTime: win?.endTime ?? '',
        days: win?.daysOfWeek ? [...win.daysOfWeek] : [],
        startsAt: win?.startsAt ?? '',
        endsAt: win?.endsAt ?? '',
        zone: '',
    };
}

const toMinutes = (hhmm: string): number | null => {
    const m = /^(\d{2}):(\d{2})$/.exec(hhmm);
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
};

const stampMinutes = (value: string): number | null => {
    const ms = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) ? Date.parse(`${value.slice(0, 16)}:00Z`) : NaN;
    return Number.isNaN(ms) ? null : ms / 60000;
};

interface Checked {
    nameMissing: boolean;
    daysError: string | null;
    timeError: string | null;
    zoneError: string | null;
    zoneMissing: boolean;
    minutes: number | null;
    ready: boolean;
}

/** The window rules, in the order the person meets them (UI-SPEC section 8 validation). */
function check(form: Form, needZone: boolean): Checked {
    const nameMissing = form.name.trim().length === 0;
    let daysError: string | null = null;
    let timeError: string | null = null;
    let minutes: number | null = null;
    if (form.recurrence === 'weekly' && form.days.length === 0) daysError = 'Choose at least one day.';
    if (form.recurrence === 'none') {
        const start = stampMinutes(form.startsAt);
        const end = stampMinutes(form.endsAt);
        if (start !== null && end !== null) {
            if (end <= start) timeError = 'The end must be after the start.';
            else if (end - start > MAX_MINUTES) timeError = 'A window can be up to 24 hours long.';
            else minutes = end - start;
        }
    } else {
        const start = toMinutes(form.startTime);
        const end = toMinutes(form.endTime);
        if (start !== null && end !== null) {
            if (start === end) timeError = "The window can't start and end at the same time.";
            else minutes = (end - start + MAX_MINUTES) % MAX_MINUTES;
        }
    }
    const zoneMissing = needZone && form.zone.trim().length === 0;
    const zoneError = needZone && !zoneMissing && !isKnownTimeZone(form.zone)
        ? 'Choose a time zone from the list, for example Asia/Kolkata.' : null;
    return {
        nameMissing, daysError, timeError, zoneError, zoneMissing, minutes,
        ready: !nameMissing && !daysError && !timeError && minutes !== null && !zoneMissing && !zoneError,
    };
}

const runsText = (minutes: number, zone: string) =>
    `Runs ${Math.floor(minutes / 60)} h ${minutes % 60} min${zone ? ` in ${zone}` : ''}.`;

const withoutStop = (text: string) => text.replace(/[.\s]+$/, '');

function requestBody(form: Form, storedZone: string | null): WindowRequest {
    const body: WindowRequest = { name: form.name.trim(), recurrence: form.recurrence };
    if (form.recurrence === 'none') {
        body.startsAt = form.startsAt;
        body.endsAt = form.endsAt;
    } else {
        body.startTime = form.startTime;
        body.endTime = form.endTime;
        if (form.recurrence === 'weekly') body.daysOfWeek = [...form.days].sort((a, b) => a - b);
    }
    if (!storedZone) body.timeZone = form.zone.trim();
    return body;
}

export interface WindowDialogProps {
    isOpen: boolean;
    /** The window being edited; null adds a new one. */
    window: MaintenanceWindow | null;
    /** The organization's stored zone, or null when it has none (the dialog then asks for one). */
    timeZone: string | null;
    onClose: () => void;
    onSaved: (saved: MaintenanceWindow) => void;
}

const WindowForm: React.FC<WindowDialogProps> = ({ window: editing, timeZone, onClose, onSaved }) => {
    const ids = useId();
    const [form, setForm] = useState<Form>(() => initialForm(editing));
    const [touched, setTouched] = useState(false);
    const [saving, setSaving] = useState(false);
    const [failed, setFailed] = useState<string | null>(null);
    const zones = useMemo(() => listTimeZones(), []);
    const needZone = !timeZone;
    const result = check(form, needZone);
    const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm(prev => ({ ...prev, [key]: value }));
    const toggleDay = (iso: number) =>
        set('days', form.days.includes(iso) ? form.days.filter(d => d !== iso) : [...form.days, iso]);
    const shownZone = timeZone ?? (result.zoneError || result.zoneMissing ? '' : form.zone.trim());
    const close = () => { if (!saving) onClose(); };

    const save = async () => {
        if (!result.ready || saving) return;
        setSaving(true);
        setFailed(null);
        try {
            const body = requestBody(form, timeZone);
            const saved = editing ? await updateWindow(editing.id, body) : await createWindow(body);
            showToast(`Window "${form.name.trim()}" saved.`, 'success');
            onSaved(saved);
        } catch (err) {
            const detail = err instanceof WindowApiError ? err.detail : '';
            setFailed(detail
                ? `Couldn't save the window: ${withoutStop(detail)}. Try again.`
                : "Couldn't save the window. Check your connection and try again.");
        } finally {
            setSaving(false);
        }
    };

    const timeField = (key: 'startTime' | 'endTime' | 'startsAt' | 'endsAt', label: string, type: string, wide = false) => (
        <div>
            <label htmlFor={`${ids}-${key}`} className={LABEL}>{label}</label>
            <input
                id={`${ids}-${key}`} type={type} value={form[key]} disabled={saving}
                onChange={e => set(key, e.target.value)}
                className={`${INPUT} ${wide ? 'w-full' : 'w-32'}`}
            />
        </div>
    );

    return (
        <Modal
            isOpen
            onClose={close}
            title={editing ? 'Edit maintenance window' : 'Add maintenance window'}
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!saving}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={close} disabled={saving}>
                        Close without saving
                    </button>
                    <button type="button" className={ACCENT_BUTTON} onClick={save} disabled={!result.ready || saving}>
                        {saving ? 'Saving...' : 'Save window'}
                    </button>
                </>
            )}
        >
            <div className="space-y-4">
                {needZone && (
                    <div>
                        <label htmlFor={`${ids}-zone`} className={LABEL}>Time zone</label>
                        <input
                            id={`${ids}-zone`} type="text" list={`${ids}-zones`} value={form.zone} disabled={saving}
                            placeholder={browserTimeZone()} autoComplete="off" spellCheck={false}
                            onChange={e => set('zone', e.target.value)}
                            className={`${INPUT} w-full max-w-sm font-mono`}
                        />
                        <datalist id={`${ids}-zones`}>
                            {zones.map(z => <option key={z} value={z} />)}
                        </datalist>
                        <p className={`${HELPER} mt-1`}>
                            All of this organization's windows use this time zone. Daylight-saving changes are handled.
                        </p>
                        {result.zoneError && <p role="alert" className={`${ERROR_TEXT} mt-1`}>{result.zoneError}</p>}
                    </div>
                )}
                <div>
                    <label htmlFor={`${ids}-name`} className={LABEL}>Window name</label>
                    <input
                        id={`${ids}-name`} type="text" value={form.name} maxLength={60} disabled={saving}
                        placeholder="Weekly patching" onChange={e => set('name', e.target.value)}
                        onBlur={() => setTouched(true)}
                        className={`${INPUT} w-full max-w-sm break-words`}
                    />
                    {touched && result.nameMissing && <p role="alert" className={`${ERROR_TEXT} mt-1`}>Enter a window name.</p>}
                </div>
                <div>
                    <label htmlFor={`${ids}-repeats`} className={LABEL}>Repeats</label>
                    <select
                        id={`${ids}-repeats`} value={form.recurrence} disabled={saving}
                        onChange={e => set('recurrence', e.target.value as Recurrence)}
                        className={`${INPUT} w-full max-w-sm`}
                    >
                        <option value="none">One-time</option>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                    </select>
                </div>
                {form.recurrence === 'none' ? (
                    <div className="grid gap-4 sm:grid-cols-2">
                        {timeField('startsAt', 'Starts', 'datetime-local', true)}
                        {timeField('endsAt', 'Ends', 'datetime-local', true)}
                    </div>
                ) : (
                    <div className="flex flex-wrap gap-4">
                        {timeField('startTime', 'Starts at', 'time')}
                        {timeField('endTime', 'Ends at', 'time')}
                    </div>
                )}
                {form.recurrence === 'weekly' && (
                    <div>
                        <span className={LABEL} id={`${ids}-days`}>Days</span>
                        <div role="group" aria-labelledby={`${ids}-days`} className="flex flex-wrap gap-2">
                            {DAYS.map(day => {
                                const on = form.days.includes(day.iso);
                                return (
                                    <button
                                        key={day.iso} type="button" aria-pressed={on} aria-label={day.full} disabled={saving}
                                        onClick={() => toggleDay(day.iso)}
                                        className={`min-h-10 w-10 rounded-lg border text-xs font-semibold disabled:opacity-60 ${on
                                            ? 'border-gray-700 bg-gray-800 text-white dark:border-gray-300 dark:bg-gray-200 dark:text-gray-900'
                                            : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700'}`}
                                    >
                                        {day.short}
                                    </button>
                                );
                            })}
                        </div>
                        <p className={`${HELPER} mt-1`}>The window starts on these days.</p>
                        {result.daysError && <p role="alert" className={`${ERROR_TEXT} mt-1`}>{result.daysError}</p>}
                    </div>
                )}
                <div aria-live="polite" className={`${HELPER} space-y-1`}>
                    {result.minutes !== null && <p>{runsText(result.minutes, shownZone)}</p>}
                    {result.minutes !== null && form.recurrence !== 'none'
                        && (toMinutes(form.endTime) ?? 0) < (toMinutes(form.startTime) ?? 0)
                        && <p>{`Ends the next day at ${form.endTime}.`}</p>}
                </div>
                {result.timeError && <p role="alert" className={ERROR_TEXT}>{result.timeError}</p>}
                {failed && <div role="alert" className={ERROR_BLOCK}>{failed}</div>}
            </div>
        </Modal>
    );
};

/** Add (window null) or edit one window. Closed, it renders nothing and keeps no state. */
export const WindowDialog: React.FC<WindowDialogProps> = props =>
    props.isOpen ? <WindowForm {...props} /> : null;

export interface DeleteWindowDialogProps {
    isOpen: boolean;
    window: MaintenanceWindow | null;
    /** True when this is the only window: an amber block says nobody can start a rollout afterwards. */
    isLast: boolean;
    onClose: () => void;
    onDeleted: () => void;
}

const DeleteForm: React.FC<DeleteWindowDialogProps & { window: MaintenanceWindow }> = ({
    window: target, isLast, onClose, onDeleted,
}) => {
    const [deleting, setDeleting] = useState(false);
    const [failed, setFailed] = useState<string | null>(null);
    const close = () => { if (!deleting) onClose(); };

    const remove = async () => {
        if (deleting) return;
        setDeleting(true);
        setFailed(null);
        try {
            await deleteWindow(target.id);
            showToast(`Window "${target.name}" deleted.`, 'success');
            onDeleted();
        } catch (err) {
            const detail = err instanceof WindowApiError ? err.detail : '';
            setFailed(detail
                ? `Couldn't delete the window: ${withoutStop(detail)}. Try again.`
                : "Couldn't delete the window. Check your connection and try again.");
        } finally {
            setDeleting(false);
        }
    };

    return (
        <Modal
            isOpen
            onClose={close}
            title="Delete this window?"
            size="md"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!deleting}
            footer={(
                <>
                    <button type="button" className={SECONDARY_BUTTON} onClick={close} disabled={deleting} autoFocus>
                        Keep window
                    </button>
                    <button type="button" className={DANGER_BUTTON} onClick={remove} disabled={deleting}>
                        {deleting ? 'Deleting...' : 'Delete window'}
                    </button>
                </>
            )}
        >
            <div className="space-y-4">
                <p className="break-words text-sm text-gray-700 dark:text-gray-200">
                    {`"${target.name}" will be removed. Rollouts and approved restarts that were waiting for it wait for the next window.`}
                </p>
                {isLast && (
                    <div role="status" className={AMBER_BLOCK}>
                        <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 flex-shrink-0" />
                        <p>This is the last window. Nobody can start a rollout until you add another.</p>
                    </div>
                )}
                {failed && <div role="alert" className={ERROR_BLOCK}>{failed}</div>}
            </div>
        </Modal>
    );
};

export const DeleteWindowDialog: React.FC<DeleteWindowDialogProps> = props =>
    props.isOpen && props.window ? <DeleteForm {...props} window={props.window} /> : null;
