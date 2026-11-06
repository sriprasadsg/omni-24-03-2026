import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchDraft, postPreflight, startRollout } from '../../services/patchRollouts/start';
import type { Preflight } from '../../services/patchRollouts/types';
import { showToast } from '../../utils/toast';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { HELPER, FIELD } from '../AutonomousOpsResponseSettings';
import { ACCENT_BUTTON, plain } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon, InfoIcon, RocketIcon } from '../icons';
import { Modal } from '../Modal';
import { NOTHING_PENDING, StartPatchPicker } from './StartPatchPicker';
import { StartPreflight, WhatWillHappen, checkingId, detailId } from './StartPreflight';
import type { PreflightLinks } from './StartPreflight';
import { plural } from './rolloutCopy';

/**
 * The Start a rollout dialog (84-17, UI-SPEC section 3, D-03, D-09..D-13). Name, the patches to install, the server
 * preflight and the What will happen block. Nothing is stored until Start rollout is pressed: the picker and the
 * check only read, a draft from a vulnerability suggestion only fills the form. Every check shown is the server's
 * preflight (debounced 300 ms after the selection changes, the previous result kept while the next one is read), and
 * the server runs it again at Start. Start is disabled with a visible reason that aria-describedby points at.
 */

export const PREFLIGHT_DEBOUNCE_MS = 300;
const NAME_MAX = 60;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const STOPPED = 'Paused while automatic actions are stopped.';
const NAME_ERROR = 'Enter a name for this rollout.';
const PICK_PATCH = 'Pick at least one patch to install.';
const CHECK_AGAIN = 'Try the check again first.';
const START_FALLBACK = "Couldn't start the rollout. Check your connection and try again.";

export interface StartDialogProps {
    open: boolean;
    /** Close without starting (also called after a successful Start). */
    onClose: () => void;
    /** A rollout was started; the parent reads the list again and moves focus to the new card. */
    onStarted: (rolloutId: string) => void;
    /** A vulnerability suggestion to fill the form from (D-11); nothing starts until Start is pressed. */
    draftSuggestionId?: string | null;
    /** Automatic actions are stopped: Start is disabled with the paused reason. */
    stopped?: boolean;
    /** The organization platform staff entered from Tenants, else null. */
    tenantId?: string | null;
    onOpenMaintenance?: () => void;
    onOpenRings?: () => void;
    onOpenAgentGroups?: () => void;
}

const defaultName = () => {
    const now = new Date();
    return `Rollout ${now.getDate()} ${MONTHS[now.getMonth()]}`;
};

interface Reason {
    /** The element Start's aria-describedby points at. */
    id: string;
    /** Set when no visible text carries the reason yet, so one line is shown under the button. */
    text?: string;
}

const StartDialogInner: React.FC<StartDialogProps> = ({
    onClose, onStarted, draftSuggestionId = null, stopped = false, tenantId = null,
    onOpenMaintenance, onOpenRings, onOpenAgentGroups,
}) => {
    const uid = useId();
    const [name, setName] = useState(defaultName);
    const [nameTouched, setNameTouched] = useState(false);
    const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
    const [empty, setEmpty] = useState(false);
    const [preflight, setPreflight] = useState<Preflight | null>(null);
    const [checking, setChecking] = useState(true);
    const [checkFailed, setCheckFailed] = useState(false);
    const [recheck, setRecheck] = useState(0);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [draft, setDraft] = useState<{ host: string; removed: number } | null>(null);
    const alive = useRef(true);
    const seq = useRef(0);
    const immediate = useRef(false);
    const selectedRef = useRef(selected);
    const nameTouchedRef = useRef(nameTouched);
    selectedRef.current = selected;
    nameTouchedRef.current = nameTouched;

    useEffect(() => {
        alive.current = true;
        return () => { alive.current = false; };
    }, []);

    // A draft only fills the form: the name (unless the person already typed one) and the ticks.
    useEffect(() => {
        if (!draftSuggestionId) return;
        fetchDraft(draftSuggestionId, tenantId)
            .then(found => {
                if (!alive.current) return;
                const ids = Array.isArray(found?.patchIds) ? found.patchIds : [];
                setSelected(prev => new Set([...prev, ...ids]));
                if (!nameTouchedRef.current && found?.name) setName(String(found.name).slice(0, NAME_MAX));
                setDraft({ host: String(found?.host ?? ''), removed: Number(found?.removedCount) || 0 });
            })
            .catch(() => { /* an unreadable draft opens the dialog as an ordinary Start */ });
    }, [draftSuggestionId, tenantId]);

    // The server preflight, read again whenever the ticks change. The last result stays on screen meanwhile.
    const key = Array.from(selected).join('\n');
    useEffect(() => {
        const mine = ++seq.current;
        const delay = immediate.current ? 0 : PREFLIGHT_DEBOUNCE_MS;
        immediate.current = false;
        setChecking(true);
        const timer = setTimeout(() => {
            postPreflight(Array.from(selectedRef.current), tenantId)
                .then(result => {
                    if (!alive.current || mine !== seq.current) return;
                    setPreflight(result);
                    setCheckFailed(false);
                })
                .catch(() => { if (alive.current && mine === seq.current) setCheckFailed(true); })
                .finally(() => { if (alive.current && mine === seq.current) setChecking(false); });
        }, delay);
        return () => clearTimeout(timer);
    }, [key, tenantId, recheck]);

    const readAgainNow = useCallback(() => {
        immediate.current = true;
        setRecheck(n => n + 1);
    }, []);

    const toggle = useCallback((patchId: string) => setSelected(prev => {
        const next = new Set(prev);
        if (!next.delete(patchId)) next.add(patchId);
        return next;
    }), []);

    const trimmed = name.trim();
    const nameErrorId = `${uid}-name-error`;
    const emptyId = `${uid}-empty`;
    const rows = preflight?.rows ?? [];
    const blockerIndex = rows.findIndex(r => r.blocker);

    let reason: Reason | null = null;
    if (stopped) reason = { id: `${uid}-reason`, text: STOPPED };
    else if (!trimmed) reason = { id: nameErrorId };
    else if (empty) reason = { id: emptyId };
    else if (selected.size === 0) reason = { id: `${uid}-reason`, text: PICK_PATCH };
    else if (checkFailed && checking === false) reason = { id: `${uid}-reason`, text: CHECK_AGAIN };
    else if (checking || preflight === null) reason = { id: checkingId(uid) };
    else if (blockerIndex >= 0) reason = { id: detailId(uid, blockerIndex) };
    else if (!preflight.canStart) reason = { id: `${uid}-reason`, text: preflight.firstBlocker ?? CHECK_AGAIN };

    const disabled = submitting || reason !== null;

    const submit = async () => {
        if (disabled) return;
        setSubmitting(true);
        setError(null);
        try {
            const result = await startRollout({ name: trimmed, patchIds: Array.from(selected) }, tenantId);
            if (!alive.current) return;
            const shown = result?.name || trimmed;
            showToast(result?.simulation
                ? `Rollout "${shown}" started as a simulation. Nothing will be installed.`
                : `Rollout "${shown}" started. The canary ring goes first.`, 'success');
            onStarted(result.id);
            onClose();
        } catch (failure) {
            if (!alive.current) return;
            const status = (failure as { status?: number })?.status;
            const code = (failure as { code?: string | null })?.code;
            const detail = String((failure as { detail?: string })?.detail ?? '');
            if (code === 'already_in_rollout' || status === 422) readAgainNow();
            setError(detail ? `Couldn't start the rollout: ${plain(detail)}. Try again.` : START_FALLBACK);
        } finally {
            if (alive.current) setSubmitting(false);
        }
    };

    const links: PreflightLinks = { onOpenMaintenance, onOpenRings, onOpenAgentGroups };

    return (
        <Modal
            isOpen
            onClose={onClose}
            title="Start a rollout"
            size="2xl"
            showClose={false}
            closeOnBackdrop={false}
            closeOnEsc={!submitting}
            footer={(
                <div className="flex w-full flex-col gap-3">
                    {error && <HealthNotice tone="red" icon={AlertTriangleIcon} role="alert"><p>{error}</p></HealthNotice>}
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <button type="button" className={SECONDARY_BUTTON} disabled={submitting} onClick={onClose}>Close without starting</button>
                        <div className="flex min-w-0 flex-col items-end gap-1">
                            <button
                                type="button" className={ACCENT_BUTTON} disabled={disabled}
                                aria-describedby={reason ? reason.id : undefined} onClick={() => void submit()}
                            >
                                <RocketIcon size={16} aria-hidden="true" />
                                {submitting ? 'Starting...' : 'Start rollout'}
                            </button>
                            {reason?.text && <p id={reason.id} className={`${HELPER} text-right`}>{reason.text}</p>}
                        </div>
                    </div>
                </div>
            )}
        >
            <div className="flex flex-col gap-6">
                {draft && (
                    <HealthNotice tone="blue" icon={InfoIcon} role="status">
                        <p>{`Filled in from the vulnerabilities reported by ${draft.host}. Nothing starts until you press Start rollout.`}</p>
                        {draft.removed > 0 && (
                            <p>{draft.removed === 1
                                ? '1 patch is no longer needed and was removed.'
                                : `${draft.removed} patches are no longer needed and were removed.`}</p>
                        )}
                    </HealthNotice>
                )}
                <div className="space-y-1">
                    <label htmlFor={`${uid}-name`} className="block text-sm font-semibold text-gray-900 dark:text-white">Rollout name</label>
                    <input
                        id={`${uid}-name`} type="text" autoFocus value={name} maxLength={NAME_MAX}
                        className={`${FIELD} w-full max-w-sm`} onChange={e => { setName(e.target.value); setNameTouched(true); }}
                        aria-invalid={!trimmed && nameTouched}
                    />
                    <p className={HELPER}>Shown in the list and when a computer is left out of another rollout.</p>
                    {!trimmed && nameTouched && <p id={nameErrorId} role="alert" className="break-words text-xs text-red-600 dark:text-red-400">{NAME_ERROR}</p>}
                </div>
                <StartPatchPicker tenantId={tenantId} selected={selected} onToggle={toggle} onEmptyChange={setEmpty} emptyId={emptyId} />
                <StartPreflight
                    preflight={preflight} checking={checking} failed={checkFailed} links={links} idBase={uid}
                    onRetry={readAgainNow}
                />
                <WhatWillHappen />
            </div>
        </Modal>
    );
};

export const StartDialog: React.FC<StartDialogProps> = props => (props.open ? <StartDialogInner {...props} /> : null);

export { NOTHING_PENDING };
export default StartDialog;
