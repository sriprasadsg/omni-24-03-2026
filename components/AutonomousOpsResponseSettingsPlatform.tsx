import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { applyResponseSettingsToAll, fetchResponseSettingsDistribution } from '../services/autonomousOpsApi';
import type { ApplyToAllBody, AutonomousOpsApiError, ResponseSettingsDistribution } from '../services/autonomousOpsApi';
import { showToast } from '../utils/toast';
import { HEALTH_SKELETON, HealthNotice } from './AutonomousOpsHealthChips';
import { ACCENT_BUTTON, ApplyAllDialog, plain, plural } from './AutonomousOpsResponseSettingsDialogs';
import {
    BLOCK_HELP, BLOCK_LENGTH_ERROR, BlockLengthControl, Group, HELPER, LOAD_ERROR, OnOffSwitch, RULE_HELP, RULE_LABEL,
    convertUnit, durationText, toHours,
} from './AutonomousOpsResponseSettings';
import type { BlockUnit } from './AutonomousOpsResponseSettings';
import { ChevronRightIcon, SettingsIcon } from './icons';

const isDistribution = (v: unknown): v is ResponseSettingsDistribution => {
    const d = v as Partial<ResponseSettingsDistribution> | null;
    return !!d && typeof d.organizations === 'number' && !!d.twoSignal && typeof d.twoSignal.on === 'number'
        && typeof d.twoSignal.off === 'number' && !!d.blockHours && typeof d.blockHours === 'object';
};

/** "Two-source rule on in 3 organizations, off in 1 · Block length differs across organizations". */
function summaryOf(d: ResponseSettingsDistribution): string {
    const rule = `Two-source rule on in ${plural(d.twoSignal.on, 'organization', 'organizations')}, off in ${d.twoSignal.off}`;
    const lengths = Object.keys(d.blockHours);
    if (lengths.length === 0) return rule;
    return lengths.length === 1
        ? `${rule} · Blocks last ${durationText(Number(lengths[0]))} in every organization`
        : `${rule} · Block length differs across organizations`;
}

const CheckRow: React.FC<{ checked: boolean; describedBy: string; onChange: (next: boolean) => void }> = ({ checked, describedBy, onChange }) => (
    <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
        <input type="checkbox" checked={checked} aria-describedby={describedBy} onChange={e => onChange(e.target.checked)} className="h-4 w-4 shrink-0" />
        <span className="min-w-0 break-words">Change this setting for every organization</span>
    </label>
);

/**
 * Response settings for every organization (83-UI-SPEC section 6, R10): the Super Admin's platform-scope card. Two groups,
 * each behind its own box, written to each organization on its own through a confirmation. Watched services are not offered.
 */
export const PlatformResponseSettings: React.FC = () => {
    const uid = useId();
    const bodyId = `${uid}-body`;
    const ruleLabelId = `${uid}-rule`;
    const blockLabelId = `${uid}-block`;
    const blockErrorId = `${uid}-block-error`;

    const [expanded, setExpanded] = useState(false);
    const [dist, setDist] = useState<ResponseSettingsDistribution | null>(null);
    const [loadFailed, setLoadFailed] = useState(false);
    const [ruleTicked, setRuleTicked] = useState(false);
    const [ruleOn, setRuleOn] = useState(true);
    const [blockTicked, setBlockTicked] = useState(false);
    const [value, setValue] = useState('24');
    const [unit, setUnit] = useState<BlockUnit>('hours');
    const [dialogOpen, setDialogOpen] = useState(false);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // A partial failure: the organizations still to retry, and how many were already changed.
    const [failedIds, setFailedIds] = useState<string[]>([]);
    const [changedBefore, setChangedBefore] = useState(0);
    const alive = useRef(true);
    const inFlight = useRef(false);

    const load = useCallback(async () => {
        try {
            const next = await fetchResponseSettingsDistribution();
            if (!alive.current) return;
            if (!isDistribution(next)) throw new Error('unreadable distribution');
            setDist(next);
            setLoadFailed(false);
        } catch {
            if (alive.current) setLoadFailed(true);
        }
    }, []);

    useEffect(() => {
        alive.current = true;
        void load();
        return () => { alive.current = false; };
    }, [load]);

    const hours = toHours(value, unit);
    const blockInvalid = blockTicked && hours === null;
    const valid = (ruleTicked || blockTicked) && !blockInvalid;
    const loosening = ruleTicked && !ruleOn;

    const lines: string[] = [];
    if (ruleTicked) lines.push(`Two-source rule: ${ruleOn ? 'on' : 'off'}`);
    if (blockTicked && hours !== null) lines.push(`Block length: ${plural(hours, 'hour', 'hours')}`);

    const resetRetry = () => { setFailedIds([]); setChangedBefore(0); setError(null); };
    const closeDialog = () => {
        setDialogOpen(false);
        if (changedBefore > 0) void load(); // some organizations were written before the person gave up
        resetRetry();
    };

    const apply = async () => {
        if (inFlight.current || !valid) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        const body: ApplyToAllBody = {};
        if (ruleTicked) body.twoSignal = ruleOn;
        if (blockTicked && hours !== null) body.blockHours = hours;
        if (failedIds.length > 0) body.onlyTenants = failedIds;
        try {
            const result = await applyResponseSettingsToAll(body);
            const total = changedBefore + result.changed.length;
            if (result.failures.length === 0) {
                showToast(`Settings applied to ${plural(total, 'organization', 'organizations')}.`, 'success');
                setDialogOpen(false);
                resetRetry();
                setRuleTicked(false);
                setBlockTicked(false);
                void load();
            } else {
                const k = result.failures.length;
                const n = k + result.changed.length;
                const reasons = Array.from(new Set(result.failures.map(f => plain(f.detail)))).join('; ');
                const counts = `Couldn't change ${k} of ${plural(n, 'organization', 'organizations')}: ${reasons}.`;
                setFailedIds(result.failures.map(f => f.tenantId));
                setChangedBefore(total);
                setError(result.changed.length > 0
                    ? `${counts} The others were changed. Try again to retry the rest.`
                    : `${counts} Try again.`);
            }
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (err.status === 403) {
                showToast("You don't have permission to change these settings.", 'error');
                setDialogOpen(false);
                setExpanded(false);
                resetRetry();
                void load();
            } else {
                const message = err.detail ? plain(err.detail) : '';
                setError(message
                    ? `Couldn't save response settings: ${message}. Try again.`
                    : "Couldn't save response settings. Check your connection and try again.");
            }
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    const loading = dist === null && !loadFailed;
    const organizations = failedIds.length > 0 ? failedIds.length : dist?.organizations ?? 0;

    return (
        <section className="card p-6" aria-labelledby={`${uid}-title`}>
            <div className="min-w-0">
                <h2 id={`${uid}-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                    <button
                        type="button" aria-expanded={expanded} aria-controls={bodyId} onClick={() => setExpanded(v => !v)}
                        className="inline-flex items-center gap-2 text-left"
                    >
                        <SettingsIcon size={20} aria-hidden="true" />
                        <span>Response settings for every organization</span>
                        <ChevronRightIcon size={16} aria-hidden="true" className={expanded ? 'rotate-90' : ''} />
                    </button>
                </h2>
                {loading && <div className={`mt-2 h-4 w-64 ${HEALTH_SKELETON}`} />}
                {dist && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{summaryOf(dist)}</p>}
            </div>

            {loadFailed && dist === null && (
                <div className="mt-4">
                    <HealthNotice tone="red" role="alert">
                        <p>{LOAD_ERROR}</p>
                        <p>
                            <button
                                type="button" className="text-sm font-semibold underline underline-offset-2"
                                onClick={() => { setLoadFailed(false); void load(); }}
                            >
                                Try again
                            </button>
                        </p>
                    </HealthNotice>
                </div>
            )}

            {expanded && loading && (
                <div id={bodyId} aria-busy="true" className="mt-6 flex flex-col gap-4 border-t border-gray-200 pt-6 dark:border-white/10">
                    {[0, 1].map(i => <div key={i} className={`h-16 ${HEALTH_SKELETON}`} />)}
                </div>
            )}

            {expanded && dist && (
                <div id={bodyId} className="mt-6 flex flex-col gap-6 border-t border-gray-200 pt-6 dark:border-white/10">
                    <p className={HELPER}>Watched services are set for each organization on its own screen.</p>
                    <div className="divide-y divide-gray-200 dark:divide-white/10">
                        <Group
                            labelId={ruleLabelId}
                            label={RULE_LABEL}
                            notice={<CheckRow checked={ruleTicked} describedBy={ruleLabelId} onChange={setRuleTicked} />}
                            helper={<p className={HELPER}>{RULE_HELP}</p>}
                            control={(
                                <OnOffSwitch
                                    checked={ruleOn} labelledBy={ruleLabelId} onChange={setRuleOn}
                                    disabled={!ruleTicked} stateText={ruleTicked ? undefined : 'No change'}
                                />
                            )}
                        />
                        <Group
                            labelId={blockLabelId}
                            label="Block length"
                            notice={<CheckRow checked={blockTicked} describedBy={blockLabelId} onChange={setBlockTicked} />}
                            helper={<p className={HELPER}>{BLOCK_HELP}</p>}
                            control={(
                                <div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <BlockLengthControl
                                            value={value} unit={unit} invalid={blockInvalid} errorId={blockErrorId} disabled={!blockTicked}
                                            onValue={setValue} onUnit={next => { setValue(convertUnit(value, unit, next)); setUnit(next); }}
                                        />
                                        {!blockTicked && <span className="text-sm font-semibold text-gray-900 dark:text-white">No change</span>}
                                    </div>
                                    {blockInvalid && (
                                        <p id={blockErrorId} role="alert" className="mt-1 break-words text-xs text-red-600 dark:text-red-400">{BLOCK_LENGTH_ERROR}</p>
                                    )}
                                </div>
                            )}
                        />
                    </div>
                    <div className="flex flex-wrap items-center gap-4 border-t border-gray-200 pt-6 dark:border-white/10">
                        <button type="button" className={ACCENT_BUTTON} disabled={!valid} onClick={() => { resetRetry(); setDialogOpen(true); }}>
                            Apply to every organization
                        </button>
                    </div>
                </div>
            )}

            <ApplyAllDialog
                open={dialogOpen}
                lines={lines}
                organizations={organizations}
                loosening={loosening}
                pending={pending}
                error={error}
                onCancel={closeDialog}
                onConfirm={() => { void apply(); }}
            />
        </section>
    );
};

export default PlatformResponseSettings;
