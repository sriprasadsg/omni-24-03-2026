import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { AutonomousOpsApiError } from '../../services/autonomousOpsApi';
import {
    DESK_SETTINGS_CHANGED, fetchDeskSettings, restoreDeskPosting, saveDeskSettings,
} from '../../services/serviceDesk/settingsApi';
import type { DeskMode, DeskSettingsChanges, DeskSettingsView } from '../../services/serviceDesk/types';
import { showToast } from '../../utils/toast';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HEALTH_SKELETON, HealthChip, HealthNotice } from '../AutonomousOpsHealthChips';
import { ACCENT_BUTTON, plain } from '../AutonomousOpsResponseSettingsDialogs';
import { ChevronRightIcon, PauseCircleIcon, TicketIcon } from '../icons';
import { PostAnswersDialog, RestorePostingDialog } from './DeskDialogs';
import { DeskModeGroup, DeskReadiness, blockerText } from './DeskModeGroup';
import { DeskWords } from './DeskWords';
import { ERRORS, MODES, OFFLINE_STATUS, SETTINGS, TOASTS, fill } from './serviceDeskCopy';

const HELPER = 'break-words text-xs text-gray-500 dark:text-gray-400';
const POLL_MS = 60_000;

interface Draft { mode: DeskMode; words: string[] }

const draftFrom = (view: DeskSettingsView): Draft => ({ mode: view.mode, words: [...view.words] });

/** The server's view, or something that cannot be shown: a malformed answer reads as a load failure. */
const isView = (v: unknown): v is DeskSettingsView => {
    const s = v as Partial<DeskSettingsView> | null;
    return !!s && typeof s.mode === 'string' && Array.isArray(s.words) && !!s.posting && Array.isArray(s.posting.blockers)
        && !!s.model && !!s.timing;
};

/** 100 seconds reads "1 min 40 s", 120 reads "2 min", 40 reads "40 s". */
export function formatTypical(seconds: number): string {
    const total = Math.max(0, Math.round(seconds));
    const m = Math.floor(total / 60);
    const s = total % 60;
    if (m === 0) return `${s} s`;
    return s === 0 ? `${m} min` : `${m} min ${s} s`;
}

const measured = (v: DeskSettingsView): boolean => v.timing.measured && typeof v.timing.medianSeconds === 'number';

function modeSummary(v: DeskSettingsView): string {
    if (v.effectiveMode === 'off' && !v.screensOn) return SETTINGS.summaryOffScreens;
    if (v.mode === 'off') return SETTINGS.summaryOff;
    if (v.mode === 'drafts') return v.breaker ? SETTINGS.summaryRestoreNeeded : SETTINGS.summaryDraftsOnly;
    return v.posting.posting ? SETTINGS.summaryPosting : SETTINGS.summaryPostingDrafts;
}

/** Mode, model, typical answer time and word count on one line, joined by middle dots (UI-SPEC 2). */
export function summaryOf(v: DeskSettingsView): string {
    const model = v.model.state === 'online' ? SETTINGS.modelOnline
        : v.model.state === 'offline' ? SETTINGS.modelOffline : SETTINGS.modelNotChecked;
    const time = measured(v) ? fill(SETTINGS.timeTypical, { time: formatTypical(v.timing.medianSeconds as number) }) : SETTINGS.timeNotMeasured;
    const parts = [modeSummary(v), model, time];
    if (v.words.length === 1) parts.push(SETTINGS.extraWord);
    else if (v.words.length > 1) parts.push(fill(SETTINGS.extraWords, { n: v.words.length }));
    return parts.join(' · ');
}

const StatusLine: React.FC<{ view: DeskSettingsView }> = ({ view }) => {
    const { model, timing } = view;
    return (
        <div role="status" className="flex flex-col gap-2">
            <div className="flex flex-wrap items-start gap-2">
                {model.state === 'online' && <HealthChip kind="healthy" label={SETTINGS.chipOnline} />}
                {model.state === 'offline' && <HealthChip kind="down" label={SETTINGS.chipOffline} />}
                {model.state === 'not_checked' && <HealthChip kind="unknown" label={SETTINGS.chipNotChecked} />}
                <div className="min-w-0 flex-1">
                    {model.state === 'offline' ? (
                        <>
                            <p className="break-words text-sm text-gray-900 dark:text-white">{OFFLINE_STATUS}</p>
                            <p className={HELPER}>{SETTINGS.offlineDetail}</p>
                        </>
                    ) : (
                        <p className="break-words text-sm text-gray-900 dark:text-white">
                            {model.state === 'online' ? SETTINGS.onlineText : SETTINGS.modelNotChecked}
                            {model.state === 'online' && model.tag && (
                                <span className="ml-2 break-all font-mono text-xs text-gray-500 dark:text-gray-400">{model.tag}</span>
                            )}
                        </p>
                    )}
                </div>
            </div>
            {measured(view) ? (
                <div>
                    <p className="break-words text-sm text-gray-900 dark:text-white">
                        {fill(SETTINGS.typicalTime, { time: formatTypical(timing.medianSeconds as number) })}
                    </p>
                    <p className={HELPER}>{fill(SETTINGS.medianOf, { n: timing.samples })}</p>
                </div>
            ) : (
                <div>
                    <p className="break-words text-sm text-gray-900 dark:text-white">{SETTINGS.timeNotMeasuredYet}</p>
                    <p className={HELPER}>{SETTINGS.timeSafeDefaults}</p>
                </div>
            )}
            <p className={HELPER}>{SETTINGS.queueLimit}</p>
        </div>
    );
};

interface CardProps {
    /** The organization platform staff entered, else null (the viewer's own organization). */
    tenantId: string | null;
}

/**
 * The collapsed Service desk card under Response settings (85-UI-SPEC section 2, R4): the three-way switch, why answers
 * are or are not posted, the tenant's own hand-off words, the local model and the typical answer time, as one staged form
 * with one Save. Rendered by the screen for holders of manage:autonomous_ops in an organization; every control follows
 * the flags the server sends.
 */
export const DeskSettingsCard: React.FC<CardProps> = ({ tenantId }) => {
    const uid = useId();
    const bodyId = `${uid}-body`;
    const modeLabelId = `${uid}-mode`;
    const reasonId = `${uid}-reason`;
    const readyLabelId = `${uid}-ready`;

    const [expanded, setExpanded] = useState(false);
    const [data, setData] = useState<DeskSettingsView | null>(null);
    const [loadFailed, setLoadFailed] = useState(false);
    const [draft, setDraft] = useState<Draft | null>(null);
    const [pending, setPending] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [postOpen, setPostOpen] = useState(false);
    const [restoreOpen, setRestoreOpen] = useState(false);
    const alive = useRef(true);
    const inFlight = useRef(false);
    const seq = useRef(0);
    const dirtyRef = useRef(false);

    const load = useCallback(async () => {
        const mine = ++seq.current;
        try {
            const next = await fetchDeskSettings(tenantId);
            if (!alive.current || mine !== seq.current) return;
            if (!isView(next)) throw new Error('unreadable service desk settings');
            setData(next);
            setLoadFailed(false);
            // A refresh in the background never throws away what the person has staged.
            setDraft(d => (d === null || !dirtyRef.current ? draftFrom(next) : d));
        } catch {
            if (alive.current && mine === seq.current) setLoadFailed(true);
        }
    }, [tenantId]);

    useEffect(() => {
        alive.current = true;
        void load();
        const onChanged = () => { void load(); };
        window.addEventListener(DESK_SETTINGS_CHANGED, onChanged);
        return () => { alive.current = false; window.removeEventListener(DESK_SETTINGS_CHANGED, onChanged); };
    }, [load]);

    // Expanding reads the settings again, then every minute while it stays open; nothing runs while collapsed.
    useEffect(() => {
        if (!expanded) return undefined;
        void load();
        const timer = setInterval(() => { void load(); }, POLL_MS);
        return () => clearInterval(timer);
    }, [expanded, load]);

    const reload = () => { setLoadFailed(false); setData(null); setDraft(null); void load(); };
    const stage = (change: Partial<Draft>) => { setDraft(d => (d ? { ...d, ...change } : d)); setSaveError(null); };
    const discard = () => { if (data) setDraft(draftFrom(data)); setSaveError(null); };

    const changes: DeskSettingsChanges = {};
    if (data && draft) {
        if (draft.mode !== data.mode) changes.mode = draft.mode;
        const same = draft.words.length === data.words.length && draft.words.every((w, i) => w === data.words[i]);
        if (!same) changes.words = draft.words;
    }
    const dirty = Object.keys(changes).length > 0;
    dirtyRef.current = dirty;

    const accept = (view: unknown) => {
        if (isView(view)) { setData(view); setDraft(draftFrom(view)); } else void load();
    };

    const fail = (e: unknown) => {
        const err = e as Partial<AutonomousOpsApiError>;
        if (err.status === 403) {
            showToast(TOASTS.noPermission, 'error');
            setPostOpen(false);
            setRestoreOpen(false);
            setExpanded(false);
            void load();
            return;
        }
        const message = err.detail ? plain(err.detail) : '';
        setSaveError(message ? fill(ERRORS.settingsSave, { message }) : ERRORS.settingsSaveFallback);
    };

    const doSave = async () => {
        if (inFlight.current || !dirty) return;
        inFlight.current = true;
        seq.current += 1; // an answer still on its way from an older read must not overwrite this save
        setPending(true);
        setSaveError(null);
        try {
            const saved = await saveDeskSettings(changes, tenantId);
            showToast(changes.mode ? fill(TOASTS.modeSet, { mode: MODES[changes.mode].title }) : TOASTS.settingsSaved, 'success');
            setPostOpen(false);
            accept(saved);
        } catch (e) {
            fail(e);
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    const doRestore = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        seq.current += 1;
        setPending(true);
        setSaveError(null);
        try {
            const restored = await restoreDeskPosting(tenantId);
            showToast(TOASTS.restored, 'success');
            setRestoreOpen(false);
            accept(restored);
        } catch (e) {
            fail(e);
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    // Turning Post answers on asks first; every other change saves straight away.
    const newlyPost = changes.mode === 'post';
    const onSave = () => { if (newlyPost) { setSaveError(null); setPostOpen(true); } else void doSave(); };

    const loading = data === null && !loadFailed;
    const canManage = data?.canManage === true;
    const firstBlocker = data && data.posting.blockers.length > 0 ? blockerText(data.posting.blockers[0]) : null;
    const dialogOpen = postOpen || restoreOpen;

    return (
        <section className="card p-6" aria-labelledby={`${uid}-title`}>
            <div className="min-w-0">
                <h2 id={`${uid}-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                    <button
                        type="button" aria-expanded={expanded} aria-controls={bodyId} onClick={() => setExpanded(v => !v)}
                        className="inline-flex items-center gap-2 text-left"
                    >
                        <TicketIcon size={20} aria-hidden="true" />
                        <span>{SETTINGS.title}</span>
                        <ChevronRightIcon size={16} aria-hidden="true" className={expanded ? 'rotate-90' : ''} />
                    </button>
                </h2>
                {loading && !expanded && <div className={`mt-2 h-4 w-64 ${HEALTH_SKELETON}`}><span className="sr-only">{SETTINGS.loadingHint}</span></div>}
                {data && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{summaryOf(data)}</p>}
            </div>

            {loadFailed && data === null && (
                <div className="mt-4">
                    <HealthNotice tone="red" role="alert">
                        <p>{ERRORS.settingsLoad}</p>
                        <p>
                            <button type="button" onClick={reload} className="text-sm font-semibold underline underline-offset-2">{SETTINGS.tryAgain}</button>
                        </p>
                    </HealthNotice>
                </div>
            )}

            {expanded && loading && (
                <div id={bodyId} aria-busy="true" className="mt-6 flex flex-col gap-4 border-t border-gray-200 pt-6 dark:border-white/10">
                    {[0, 1, 2].map(i => <div key={i} className={`h-16 ${HEALTH_SKELETON}`} />)}
                </div>
            )}

            {expanded && data && draft && (
                <div id={bodyId} className="mt-6 flex flex-col gap-6 border-t border-gray-200 pt-6 dark:border-white/10">
                    {!data.readable && (
                        <HealthNotice tone="blue">
                            <p>{ERRORS.settingsUnreadable}</p>
                        </HealthNotice>
                    )}
                    {data.breaker && (
                        <HealthNotice tone="amber" icon={PauseCircleIcon} role="status">
                            <p>{SETTINGS.breakerTitle}</p>
                            <p className={HELPER}>{SETTINGS.breakerNote}</p>
                            {data.canRestore && (
                                <p>
                                    <button
                                        type="button" className={SECONDARY_BUTTON} disabled={pending}
                                        onClick={() => { setSaveError(null); setRestoreOpen(true); }}
                                    >
                                        {SETTINGS.restoreButton}
                                    </button>
                                </p>
                            )}
                        </HealthNotice>
                    )}
                    <StatusLine view={data} />
                    {!data.screensOn && (
                        <HealthNotice tone="blue">
                            <p>{SETTINGS.screensOff}</p>
                        </HealthNotice>
                    )}
                    <DeskModeGroup
                        value={draft.mode} onChange={mode => stage({ mode })} disabled={pending || !canManage}
                        postLocked={data.breaker !== null} labelId={modeLabelId} reasonId={reasonId}
                    />
                    {data.mode === 'post' && (
                        <DeskReadiness blockers={data.posting.blockers} posting={data.posting.posting} labelId={readyLabelId} />
                    )}
                    <DeskWords
                        words={draft.words} max={data.maxWords} disabled={pending || !canManage}
                        onChange={words => stage({ words })}
                    />

                    {saveError && !dialogOpen && (
                        <HealthNotice tone="red" role="alert">
                            <p>{saveError}</p>
                        </HealthNotice>
                    )}
                    {canManage && (
                        <div className="flex flex-wrap items-center gap-4 border-t border-gray-200 pt-6 dark:border-white/10">
                            <button
                                type="button" onClick={onSave} disabled={!dirty || pending}
                                className={dirty ? ACCENT_BUTTON : SECONDARY_BUTTON}
                            >
                                {pending && !dialogOpen ? SETTINGS.saving : SETTINGS.save}
                            </button>
                            {dirty && (
                                <button
                                    type="button" onClick={discard} disabled={pending}
                                    className="min-h-10 text-sm font-semibold text-gray-700 underline underline-offset-2 disabled:opacity-60 dark:text-gray-200"
                                >
                                    {SETTINGS.discard}
                                </button>
                            )}
                        </div>
                    )}
                </div>
            )}

            <PostAnswersDialog
                open={postOpen} pending={pending} error={postOpen ? saveError : null} firstBlocker={firstBlocker}
                onCancel={() => { setPostOpen(false); setSaveError(null); }} onConfirm={() => { void doSave(); }}
            />
            <RestorePostingDialog
                open={restoreOpen} pending={pending} error={restoreOpen ? saveError : null}
                onCancel={() => { setRestoreOpen(false); setSaveError(null); }} onConfirm={() => { void doRestore(); }}
            />
        </section>
    );
};

export default DeskSettingsCard;
