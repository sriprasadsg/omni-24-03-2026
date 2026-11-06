import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchRings, saveRings } from '../../services/patchRollouts/rings';
import type { RingsSettings as RingsData } from '../../services/patchRollouts/types';
import { showToast } from '../../utils/toast';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HEALTH_SKELETON, HealthNotice } from '../AutonomousOpsHealthChips';
import { FIELD, HELPER } from '../AutonomousOpsResponseSettings';
import { ACCENT_BUTTON, plain } from '../AutonomousOpsResponseSettingsDialogs';
import { AlertTriangleIcon, ArrowDownIcon, ArrowUpIcon, ChevronRightIcon, LayersIcon, PlusIcon, XIcon } from '../icons';
import {
    CANARY_NAME, MAX_RINGS, MIN_RINGS, NAME_MAX, hasProblems, isDirty, newRing, ringsSummary, ringsToDraft, toInput,
    validateRings,
} from './ringsForm';
import type { DraftRing, ProblemCode, RingProblems } from './ringsForm';
import { LINK_LABELS, plural } from './rolloutCopy';

/**
 * The collapsible Rollout rings card on the Rollouts tab (84-17, UI-SPEC section 5, PTCH-01, D-09, D-10). Collapsed it
 * is one button and the saved rings in a line; expanded it is the form: one block per ring (2 to 4) built from the
 * organization's agent groups, each with its soak and, after the Canary ring, its failure limit. Every limit is
 * checked on screen with the contract's sentences, and the server checks them again on Save. A group sits in one ring
 * only; the Canary ring keeps its name, its place and its first spot. The card works while rollouts are stopped
 * (changing settings is not an action). It renders only with the server's `canManageRings`.
 */

const LOAD_ERROR = "Couldn't load rollout rings. Check your connection and try again.";
const UNREADABLE = "Your rollout rings couldn't be read, so no rollout can start until they load.";
const NO_GROUPS = 'You have no agent groups yet. Create one in Agent Groups, then pick it here.';
const INTRO =
    'A rollout installs on one ring at a time. Rings are made of your agent groups and are used by every rollout. Changes apply to rollouts you start afterwards; a running rollout keeps the rings it started with.';
const TWO_RINGS = 'A computer in groups from two rings joins the earlier ring.';
const SAVE_FALLBACK = "Couldn't save rollout rings. Check your connection and try again.";
const NO_PERMISSION = "You don't have permission to change rollout rings.";
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';
const ICON_BUTTON =
    'inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-40 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700';

export interface RingsSettingsProps {
    /** The organization platform staff entered from Tenants, else null. */
    tenantId?: string | null;
    /** The server's flag; without it the card is not rendered at all. */
    canManageRings: boolean;
    /** Where Open agent groups leads; without it the link is plain text. */
    onOpenAgentGroups?: () => void;
    /** Controlled expansion, so the Start dialog's Open rollout rings link can open the card. */
    expanded?: boolean;
    onExpandedChange?: (expanded: boolean) => void;
    /** Called after a save, so the list reads its empty-state text again. */
    onSaved?: () => void;
}

/** The inline sentences, word for word as the contract gives them (the last is the server's own for a middle ring). */
const PROBLEM_TEXT: Record<ProblemCode, string> = {
    canaryGroup: 'Pick at least one group for the Canary ring.',
    middleGroup: 'Pick at least one group for every ring except the last.',
    name: 'Enter a ring name.',
    unique: 'Ring names must be different.',
    soak: 'Enter hours between 1 and 168.',
    failPct: 'Enter a percentage between 1 and 50.',
    minSample: 'Enter a number between 1 and 100.',
};

const Problem: React.FC<{ children?: ProblemCode }> = ({ children }) =>
    children ? <p role="alert" className="mt-1 break-words text-xs text-red-600 dark:text-red-400">{PROBLEM_TEXT[children]}</p> : null;

interface BlockProps {
    ring: DraftRing;
    index: number;
    count: number;
    groups: RingsData['groups'];
    rings: DraftRing[];
    problems: RingProblems;
    onChange: (patch: Partial<DraftRing>) => void;
    onMove: (by: -1 | 1) => void;
    onRemove: () => void;
}

const RingBlock: React.FC<BlockProps> = ({ ring, index, count, groups, rings, problems, onChange, onMove, onRemove }) => {
    const uid = useId();
    const canary = index === 0;
    const label = ring.name.trim() || `ring ${index + 1}`;
    const otherRing = (groupId: string) => rings.find((r, i) => i !== index && r.groupIds.includes(groupId));
    const toggle = (groupId: string) => onChange({
        groupIds: ring.groupIds.includes(groupId) ? ring.groupIds.filter(g => g !== groupId) : [...ring.groupIds, groupId],
    });
    return (
        <div role="group" aria-label={`Ring ${index + 1}: ${label}`} className="space-y-4 rounded-lg border border-gray-200 p-4 dark:border-white/10">
            <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                    {canary
                        ? <p className="break-words text-sm font-semibold text-gray-900 dark:text-white">{CANARY_NAME}</p>
                        : <input
                            type="text" value={ring.name} maxLength={NAME_MAX} aria-label={`Name of ring ${index + 1}`}
                            className={`${FIELD} w-full max-w-sm`} onChange={e => onChange({ name: e.target.value })}
                        />}
                    <Problem>{problems.name}</Problem>
                </div>
                {!canary && (
                    <div className="flex gap-2">
                        <button type="button" className={ICON_BUTTON} aria-label={`Move ${label} earlier`} disabled={index === 1} onClick={() => onMove(-1)}>
                            <ArrowUpIcon size={16} aria-hidden="true" />
                        </button>
                        <button type="button" className={ICON_BUTTON} aria-label={`Move ${label} later`} disabled={index === count - 1} onClick={() => onMove(1)}>
                            <ArrowDownIcon size={16} aria-hidden="true" />
                        </button>
                        <button type="button" className={ICON_BUTTON} aria-label={`Remove ring ${label}`} disabled={count <= MIN_RINGS} onClick={onRemove}>
                            <XIcon size={16} aria-hidden="true" />
                        </button>
                    </div>
                )}
            </div>
            <div className="space-y-2">
                <p className="text-sm font-semibold text-gray-900 dark:text-white">Agent groups in this ring</p>
                {groups.map(g => {
                    const elsewhere = otherRing(g.id);
                    return (
                        <label key={g.id} className="flex min-h-10 items-center gap-2 text-sm text-gray-900 dark:text-white">
                            <input
                                type="checkbox" className="h-4 w-4 shrink-0" checked={ring.groupIds.includes(g.id)}
                                disabled={!!elsewhere} onChange={() => toggle(g.id)}
                            />
                            <span className="min-w-0 break-words">
                                <span className="break-all font-mono">{g.name}</span>{' '}
                                {elsewhere ? `(in ${elsewhere.name.trim() || 'another ring'})` : `(${plural(g.computers, 'computer', 'computers')})`}
                            </span>
                        </label>
                    );
                })}
                <Problem>{problems.groups}</Problem>
                <p className={HELPER}>{TWO_RINGS}</p>
            </div>
            <div className="space-y-1">
                <label htmlFor={`${uid}-soak`} className="block text-sm font-semibold text-gray-900 dark:text-white">Soak after the last install or restart</label>
                <div className="flex items-center gap-2">
                    <input
                        id={`${uid}-soak`} type="number" inputMode="decimal" className={`${FIELD} w-24`} value={ring.soak}
                        onChange={e => onChange({ soak: e.target.value })}
                    />
                    <span className="text-sm text-gray-600 dark:text-gray-400">hours</span>
                </div>
                <Problem>{problems.soak}</Problem>
            </div>
            {canary ? (
                <p className="text-sm text-gray-900 dark:text-white">Any failure halts the rollout.</p>
            ) : (
                <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm text-gray-900 dark:text-white">
                        <span>Halt when more than</span>
                        <input
                            type="number" inputMode="numeric" className={`${FIELD} w-24`} value={ring.failPct}
                            aria-label={`Failure limit percentage for ${label}`} onChange={e => onChange({ failPct: e.target.value })}
                        />
                        <span>% of computers fail, once at least</span>
                        <input
                            type="number" inputMode="numeric" className={`${FIELD} w-24`} value={ring.minSample}
                            aria-label={`Computers that must have reported for ${label}`} onChange={e => onChange({ minSample: e.target.value })}
                        />
                        <span>computers have reported</span>
                    </div>
                    <Problem>{problems.failPct}</Problem>
                    <Problem>{problems.minSample}</Problem>
                    <p className={HELPER}>Below that many computers, any failure halts.</p>
                </div>
            )}
        </div>
    );
};

const RingsCard: React.FC<Omit<RingsSettingsProps, 'canManageRings'>> = ({
    tenantId = null, onOpenAgentGroups, expanded, onExpandedChange, onSaved,
}) => {
    const bodyId = useId();
    const [data, setData] = useState<RingsData | null>(null);
    const [failed, setFailed] = useState(false);
    const [draft, setDraft] = useState<DraftRing[]>(() => ringsToDraft(null));
    const [localOpen, setLocalOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const alive = useRef(true);
    const seq = useRef(0);

    const open = expanded ?? localOpen;
    const setOpen = (next: boolean) => {
        onExpandedChange?.(next);
        if (expanded === undefined) setLocalOpen(next);
    };

    const load = useCallback(async () => {
        const mine = ++seq.current;
        try {
            const next = await fetchRings(tenantId);
            if (!alive.current || mine !== seq.current) return;
            if (!Array.isArray(next?.rings) || !Array.isArray(next?.groups)) throw new Error('unreadable rings');
            setData(next);
            setDraft(ringsToDraft(next));
            setFailed(false);
        } catch {
            if (alive.current && mine === seq.current) setFailed(true);
        }
    }, [tenantId]);

    useEffect(() => {
        alive.current = true;
        void load();
        return () => { alive.current = false; };
    }, [load]);

    const baseline = ringsToDraft(data);
    const problems = validateRings(draft);
    const dirty = isDirty(draft, baseline);
    const canSave = dirty && !hasProblems(problems) && !saving && !!data;

    const edit = (index: number, patch: Partial<DraftRing>) =>
        setDraft(prev => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
    const move = (index: number, by: -1 | 1) => setDraft(prev => {
        const to = index + by;
        if (to < 1 || to >= prev.length) return prev;
        const next = [...prev];
        [next[index], next[to]] = [next[to], next[index]];
        return next;
    });

    const save = async () => {
        if (!canSave) return;
        setSaving(true);
        setSaveError(null);
        try {
            const saved = await saveRings(toInput(draft), tenantId);
            if (!alive.current) return;
            if (Array.isArray(saved?.rings) && Array.isArray(saved?.groups)) {
                setData(saved);
                setDraft(ringsToDraft(saved));
            } else {
                await load();
            }
            showToast('Rollout rings saved.', 'success');
            onSaved?.();
        } catch (error) {
            if (!alive.current) return;
            const status = (error as { status?: number })?.status;
            const detail = String((error as { detail?: string })?.detail ?? '');
            if (status === 403) {
                setOpen(false);
                showToast(NO_PERMISSION, 'error');
            } else {
                setSaveError(detail ? `Couldn't save rollout rings: ${plain(detail)}. Try again.` : SAVE_FALLBACK);
            }
        } finally {
            if (alive.current) setSaving(false);
        }
    };

    const agentGroupsLink = onOpenAgentGroups
        ? <button type="button" className={TEXT_BUTTON} onClick={onOpenAgentGroups}>{LINK_LABELS.agentGroups}</button>
        : <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">{LINK_LABELS.agentGroups}</span>;

    return (
        <section className="card space-y-6 p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0 flex-1 space-y-1">
                    <h2 className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                        <button
                            type="button" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen(!open)}
                            className="inline-flex items-center gap-2 text-left"
                        >
                            <LayersIcon size={20} aria-hidden="true" className="shrink-0 text-gray-500 dark:text-gray-400" />
                            Rollout rings
                            <ChevronRightIcon size={16} aria-hidden="true" className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} />
                        </button>
                    </h2>
                    {data === null && !failed && <div className={`${HEALTH_SKELETON} h-4 w-64`} />}
                    {data !== null && data.readable && <p className="break-words text-sm text-gray-600 dark:text-gray-400">{ringsSummary(data)}</p>}
                </div>
            </div>
            {failed && data === null && (
                <HealthNotice tone="red" icon={AlertTriangleIcon} role="alert">
                    <p>{LOAD_ERROR}</p>
                    <div><button type="button" className={TEXT_BUTTON} onClick={() => { setFailed(false); void load(); }}>{LINK_LABELS.tryAgain}</button></div>
                </HealthNotice>
            )}
            {data !== null && !data.readable && (
                <HealthNotice tone="blue" role="status"><p>{UNREADABLE}</p></HealthNotice>
            )}
            {open && (
                <div id={bodyId} role="region" aria-label="Rollout rings" aria-busy={data === null && !failed} className="space-y-6 border-t border-gray-200 pt-6 dark:border-white/10">
                    {data === null ? (
                        !failed && <div className="space-y-4">{[0, 1, 2].map(i => <div key={i} className={`${HEALTH_SKELETON} h-16`} />)}</div>
                    ) : (
                        <>
                            <p className={HELPER}>{INTRO}</p>
                            {data.groups.length === 0 && (
                                <HealthNotice tone="blue" role="status">
                                    <p>{NO_GROUPS}</p>
                                    <div>{agentGroupsLink}</div>
                                </HealthNotice>
                            )}
                            <div className="space-y-4">
                                {draft.map((ring, index) => (
                                    <RingBlock
                                        key={ring.key || `new-${index}`} ring={ring} index={index} count={draft.length}
                                        groups={data.groups} rings={draft} problems={problems[index] ?? {}}
                                        onChange={patch => edit(index, patch)} onMove={by => move(index, by)}
                                        onRemove={() => setDraft(prev => prev.filter((_, i) => i !== index))}
                                    />
                                ))}
                            </div>
                            {draft.length < MAX_RINGS && (
                                <button type="button" className={SECONDARY_BUTTON} onClick={() => setDraft(prev => [...prev, newRing(prev)])}>
                                    <PlusIcon size={16} aria-hidden="true" />
                                    Add ring
                                </button>
                            )}
                            {saveError && (
                                <HealthNotice tone="red" icon={AlertTriangleIcon} role="alert"><p>{saveError}</p></HealthNotice>
                            )}
                            <div className="flex flex-wrap items-center gap-4">
                                <button type="button" className={dirty ? ACCENT_BUTTON : SECONDARY_BUTTON} disabled={!canSave} onClick={() => void save()}>
                                    {saving ? 'Saving...' : 'Save rings'}
                                </button>
                                {dirty && !saving && (
                                    <button type="button" className={TEXT_BUTTON} onClick={() => { setDraft(baseline); setSaveError(null); }}>
                                        Discard changes
                                    </button>
                                )}
                            </div>
                        </>
                    )}
                </div>
            )}
        </section>
    );
};

export const RingsSettings: React.FC<RingsSettingsProps> = ({ canManageRings, ...rest }) =>
    canManageRings ? <RingsCard {...rest} /> : null;

export default RingsSettings;
