import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { fetchResponseSettings, saveResponseSettings } from '../services/autonomousOpsApi';
import type { AutonomousOpsApiError, ResponseSettings, ResponseSettingsChanges } from '../services/autonomousOpsApi';
import { showToast } from '../utils/toast';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HEALTH_SKELETON, HealthNotice } from './AutonomousOpsHealthChips';
import { ACCENT_BUTTON, TurnOffRuleDialog, plain, plural } from './AutonomousOpsResponseSettingsDialogs';
import { ChevronRightIcon, PlusIcon, SettingsIcon, XIcon } from './icons';

// ── shared values (the platform form reads these too) ───────────────────────

export type BlockUnit = 'hours' | 'days';
export const MAX_SERVICES = 50;
/** The agent's own rule for a service name (R12); the server stays authoritative. */
export const SERVICE_NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
export const BLOCK_LENGTH_ERROR = 'Enter a block length between 1 hour and 7 days.';
export const LOAD_ERROR = "Couldn't load response settings. Check your connection and try again.";

export const RULE_LABEL = 'Require two sources before blocking or quarantining';
export const RULE_HELP =
    "On: an IP address is blocked or a file is quarantined on its own only when two different sources agree, for example the agent's verdict and a public threat feed. One source becomes a suggestion. Off: one source is enough. Every other limit still applies.";
export const BLOCK_HELP =
    "How long a blocked IP address stays blocked. The agent removes the block itself when the time is up, even if it can't reach the platform. Between 1 hour and 7 days. New blocks use this length; blocks already in place keep theirs.";
export const HELPER = 'break-words text-xs text-gray-500 dark:text-gray-400';
export const FIELD =
    'min-h-10 rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100';

/** A stored length shows in days when it is a whole number of days above one day, else in hours: 24 stays "24 hours", 48 reads "2 days". */
export function splitHours(hours: number): { value: string; unit: BlockUnit } {
    return hours > 24 && hours % 24 === 0 ? { value: String(hours / 24), unit: 'days' } : { value: String(hours), unit: 'hours' };
}

/** The staged length in hours, or null when it is not a whole number from 1 hour to 7 days. */
export function toHours(value: string, unit: BlockUnit): number | null {
    const text = value.trim();
    if (!/^\d+$/.test(text)) return null;
    const hours = Number(text) * (unit === 'days' ? 24 : 1);
    return hours >= 1 && hours <= 168 ? hours : null;
}

/** Changing the unit keeps the same length where it can: 48 hours becomes 2 days, 2 days becomes 48 hours. */
export function convertUnit(value: string, from: BlockUnit, to: BlockUnit): string {
    if (from === to || !/^\d+$/.test(value.trim())) return value;
    const n = Number(value.trim());
    if (to === 'hours') return String(n * 24);
    return n % 24 === 0 ? String(n / 24) : value;
}

export function durationText(hours: number): string {
    return hours > 24 && hours % 24 === 0 ? plural(hours / 24, 'day', 'days') : plural(hours, 'hour', 'hours');
}

export function serviceProblem(name: string, list: string[]): string | null {
    if (!name) return 'Enter a service name.';
    if (list.length >= MAX_SERVICES) return 'You can watch up to 50 services.';
    if (!SERVICE_NAME.test(name)) return 'Use only letters, numbers, dots, hyphens and underscores, starting with a letter or number.';
    if (list.some(s => s.toLowerCase() === name.toLowerCase())) return `${name} is already on the list.`;
    return null;
}

const isSettings = (v: unknown): v is ResponseSettings => {
    const s = v as Partial<ResponseSettings> | null;
    return !!s && typeof s.twoSignal === 'boolean' && typeof s.blockHours === 'number' && Array.isArray(s.watchedServices);
};

/** The On/Off switch with its visible word; Space and Enter toggle because it is a real button. */
export const OnOffSwitch: React.FC<{
    checked: boolean; labelledBy: string; onChange: (next: boolean) => void; disabled?: boolean; stateText?: string;
}> = ({ checked, labelledBy, onChange, disabled, stateText }) => (
    <div className="flex items-center gap-2">
        <button
            type="button" role="switch" aria-checked={checked} aria-labelledby={labelledBy} disabled={disabled}
            onClick={() => onChange(!checked)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full disabled:opacity-60 ${checked ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-600'}`}
        >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
        <span className="text-sm font-semibold text-gray-900 dark:text-white">{stateText ?? (checked ? 'On' : 'Off')}</span>
    </div>
);

/** The number and unit pair of the block length. */
export const BlockLengthControl: React.FC<{
    value: string; unit: BlockUnit; invalid: boolean; errorId: string; disabled?: boolean;
    onValue: (value: string) => void; onUnit: (unit: BlockUnit) => void;
}> = ({ value, unit, invalid, errorId, disabled, onValue, onUnit }) => (
    <div className="flex items-center gap-2">
        <input
            type="number" inputMode="numeric" min={1} aria-label="Block length" value={value} disabled={disabled}
            aria-invalid={invalid} aria-describedby={invalid ? errorId : undefined}
            onChange={e => onValue(e.target.value)} className={`${FIELD} w-24 tabular-nums`}
        />
        <select aria-label="Block length unit" value={unit} disabled={disabled} onChange={e => onUnit(e.target.value as BlockUnit)} className={FIELD}>
            <option value="hours">hours</option>
            <option value="days">days</option>
        </select>
    </div>
);

/** One setting: label and helper on the left, the control on the right, stacked below lg. */
export const Group: React.FC<{
    labelId: string; label: string; helper: React.ReactNode; control: React.ReactNode; notice?: React.ReactNode; wide?: boolean;
}> = ({ labelId, label, helper, control, notice, wide }) => (
    <div className="flex flex-col gap-4 py-6 first:pt-0 last:pb-0">
        {notice}
        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
            <div className="flex min-w-0 flex-col gap-1">
                <p id={labelId} className="break-words text-sm font-semibold text-gray-900 dark:text-white">{label}</p>
                {helper}
            </div>
            <div className={`min-w-0 ${wide ? 'lg:w-96' : ''}`}>{control}</div>
        </div>
    </div>
);

const InlineError: React.FC<{ id: string; children: React.ReactNode }> = ({ id, children }) => (
    <p id={id} role="alert" className="mt-1 break-words text-xs text-red-600 dark:text-red-400">{children}</p>
);

// ── the tenant panel ────────────────────────────────────────────────────────

interface Draft { twoSignal: boolean; value: string; unit: BlockUnit; services: string[] }

const draftFrom = (s: ResponseSettings): Draft => ({ twoSignal: s.twoSignal, services: [...s.watchedServices], ...splitHours(s.blockHours) });

const summaryOf = (s: ResponseSettings): string => {
    const base = `Two-source rule ${s.twoSignal ? 'on' : 'off'} · Blocks last ${durationText(s.blockHours)} · ${plural(s.watchedServices.length, 'service', 'services')} watched`;
    return s.watchedServices.length === 0 ? `${base} · Nothing restarts until you add a service` : base;
};

/** What the staged form would change, and whether the staged length is usable. */
function compare(saved: ResponseSettings, draft: Draft) {
    const hours = toHours(draft.value, draft.unit);
    const changes: ResponseSettingsChanges = {};
    if (draft.twoSignal !== saved.twoSignal) changes.twoSignal = draft.twoSignal;
    if (hours !== null && hours !== saved.blockHours) changes.blockHours = hours;
    const same = draft.services.length === saved.watchedServices.length && draft.services.every((s, i) => s === saved.watchedServices[i]);
    if (!same) changes.watchedServices = draft.services;
    const valid = hours !== null;
    return { changes, valid, dirty: !valid || Object.keys(changes).length > 0 };
}

/** This person's adds and removes, applied to the list read just before saving, so another administrator's edits survive (WR-28). */
const mergeServices = (base: string[], draft: string[], fresh: string[]): string[] => {
    const removed = new Set(base.filter(s => !draft.includes(s)));
    return [...fresh.filter(s => !removed.has(s)), ...draft.filter(s => !base.includes(s) && !fresh.includes(s))];
};

interface PanelProps {
    /** The organization the platform administrator entered, else null (the viewer's own organization). */
    tenantId: string | null;
    tenantName: string;
}

/**
 * The collapsed Response settings card (83-UI-SPEC section 6, D-22): the two-source switch, the block length and the
 * watched services as one staged form with one Save. Rendered by the screen for holders of manage:autonomous_ops only.
 */
export const AutonomousOpsResponseSettings: React.FC<PanelProps> = ({ tenantId, tenantName }) => {
    const uid = useId();
    const bodyId = `${uid}-body`;
    const switchLabelId = `${uid}-rule`;
    const blockLabelId = `${uid}-block`;
    const blockErrorId = `${uid}-block-error`;
    const servicesLabelId = `${uid}-services`;
    const serviceErrorId = `${uid}-service-error`;

    const [expanded, setExpanded] = useState(false);
    const [data, setData] = useState<ResponseSettings | null>(null);
    const [loadFailed, setLoadFailed] = useState(false);
    const [draft, setDraft] = useState<Draft | null>(null);
    const [svcInput, setSvcInput] = useState('');
    const [svcError, setSvcError] = useState<string | null>(null);
    const [pending, setPending] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const alive = useRef(true);
    const inFlight = useRef(false);

    const load = useCallback(async () => {
        try {
            const next = await fetchResponseSettings(tenantId);
            if (!alive.current) return;
            if (!isSettings(next)) throw new Error('unreadable response settings');
            setData(next);
            setLoadFailed(false);
        } catch {
            if (alive.current) setLoadFailed(true);
        }
    }, [tenantId]);

    useEffect(() => {
        alive.current = true;
        void load();
        return () => { alive.current = false; };
    }, [load]);

    // The staged form starts from, and returns to, whatever the server last said.
    useEffect(() => { if (data) setDraft(draftFrom(data)); }, [data]);

    const reload = () => { setLoadFailed(false); setData(null); void load(); };
    const stage = (change: Partial<Draft>) => { setDraft(d => (d ? { ...d, ...change } : d)); setSaveError(null); };
    const discard = () => { if (data) setDraft(draftFrom(data)); setSvcInput(''); setSvcError(null); setSaveError(null); };

    const tryAdd = () => {
        if (!draft) return;
        const name = svcInput.trim();
        const problem = serviceProblem(name, draft.services);
        if (problem) { setSvcError(problem); return; }
        stage({ services: [...draft.services, name] });
        setSvcInput('');
        setSvcError(null);
    };

    const { changes, valid, dirty } = data && draft ? compare(data, draft) : { changes: {} as ResponseSettingsChanges, valid: true, dirty: false };
    const ruleOff = changes.twoSignal === false;

    const doSave = async () => {
        if (inFlight.current || !dirty || !valid) return;
        inFlight.current = true;
        setPending(true);
        setSaveError(null);
        try {
            const body = { ...changes };
            if (body.watchedServices && data && draft) {
                const fresh = await fetchResponseSettings(tenantId).catch(() => null);
                if (isSettings(fresh)) body.watchedServices = mergeServices(data.watchedServices, draft.services, fresh.watchedServices);
            }
            const saved = await saveResponseSettings(body, tenantId);
            showToast(ruleOff ? 'Response settings saved. The two-source rule is off.' : 'Response settings saved.', 'success');
            setDialogOpen(false);
            // The PUT answers with what was saved; a second read would reset the form again a moment later (WR-28).
            if (isSettings(saved)) setData(saved); else void load();
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            if (err.status === 403) {
                showToast("You don't have permission to change these settings.", 'error');
                setDialogOpen(false);
                setExpanded(false);
                void load();
            } else {
                const message = err.detail ? plain(err.detail) : '';
                setSaveError(message
                    ? `Couldn't save response settings: ${message}. Try again.`
                    : "Couldn't save response settings. Check your connection and try again.");
            }
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    // Loosening the rule asks first; every other change saves straight away.
    const onSave = () => { if (ruleOff) { setSaveError(null); setDialogOpen(true); } else void doSave(); };

    const blockInvalid = draft !== null && !valid;
    const loading = data === null && !loadFailed;

    return (
        <section className="card p-6" aria-labelledby={`${uid}-title`}>
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0">
                    <h2 id={`${uid}-title`} className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">
                        <button
                            type="button" aria-expanded={expanded} aria-controls={bodyId} onClick={() => setExpanded(v => !v)}
                            className="inline-flex items-center gap-2 text-left"
                        >
                            <SettingsIcon size={20} aria-hidden="true" />
                            <span>Response settings</span>
                            <ChevronRightIcon size={16} aria-hidden="true" className={expanded ? 'rotate-90' : ''} />
                        </button>
                    </h2>
                    {loading && <div className={`mt-2 h-4 w-64 ${HEALTH_SKELETON}`} />}
                    {data && <p className="mt-2 break-words text-sm text-gray-600 dark:text-gray-400">{summaryOf(data)}</p>}
                </div>
            </div>

            {loadFailed && data === null && (
                <div className="mt-4">
                    <HealthNotice tone="red" role="alert">
                        <p>{LOAD_ERROR}</p>
                        <p>
                            <button type="button" onClick={reload} className="text-sm font-semibold underline underline-offset-2">Try again</button>
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
                            <p>This organization's response settings couldn't be read, so the safe defaults apply: two sources required, 24-hour blocks, no services watched.</p>
                        </HealthNotice>
                    )}
                    <div className="divide-y divide-gray-200 dark:divide-white/10">
                        <Group
                            labelId={switchLabelId}
                            label={RULE_LABEL}
                            helper={(
                                <>
                                    <p className={HELPER}>{RULE_HELP}</p>
                                    <p className={HELPER}>Restarting a failed service doesn't need two sources.</p>
                                </>
                            )}
                            control={<OnOffSwitch checked={draft.twoSignal} labelledBy={switchLabelId} disabled={pending} onChange={v => stage({ twoSignal: v })} />}
                        />
                        <Group
                            labelId={blockLabelId}
                            label="Block length"
                            helper={<p className={HELPER}>{BLOCK_HELP}</p>}
                            control={(
                                <div>
                                    <BlockLengthControl
                                        value={draft.value} unit={draft.unit} invalid={blockInvalid} errorId={blockErrorId} disabled={pending}
                                        onValue={value => stage({ value })}
                                        onUnit={unit => stage({ unit, value: convertUnit(draft.value, draft.unit, unit) })}
                                    />
                                    {blockInvalid && <InlineError id={blockErrorId}>{BLOCK_LENGTH_ERROR}</InlineError>}
                                </div>
                            )}
                        />
                        <Group
                            wide
                            labelId={servicesLabelId}
                            label="Services to restart"
                            notice={!data.restartAvailable && (
                                <HealthNotice tone="blue">
                                    <p>Restarting services needs remediation to be switched on for this organization. Ask a platform administrator. You can still build the list now.</p>
                                </HealthNotice>
                            )}
                            helper={(
                                <>
                                    <p className={HELPER}>Autonomous Ops restarts these services on a computer if they fail, up to 3 times an hour per service per computer, then asks for your approval. A service you stop on purpose isn't counted as failed. Nothing restarts until you add a service.</p>
                                    <p className={HELPER}>Works on Windows and Linux computers running the current agent. Other computers are skipped.</p>
                                </>
                            )}
                            control={(
                                <div className="flex flex-col gap-2">
                                    <div className="flex items-start gap-2">
                                        <input
                                            type="text" aria-label="Service name" placeholder="Service name, for example nginx or Spooler"
                                            value={svcInput} disabled={pending} aria-invalid={svcError !== null} aria-describedby={svcError ? serviceErrorId : undefined}
                                            onChange={e => { setSvcInput(e.target.value); setSvcError(null); }}
                                            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); tryAdd(); } }}
                                            className={`${FIELD} w-full max-w-sm`}
                                        />
                                        <button type="button" className={SECONDARY_BUTTON} disabled={pending} onClick={tryAdd}>
                                            <PlusIcon size={16} aria-hidden="true" />
                                            Add
                                        </button>
                                    </div>
                                    {svcError && <InlineError id={serviceErrorId}>{svcError}</InlineError>}
                                    {draft.services.length === 0 ? (
                                        <p className={HELPER}>No services are watched yet, so nothing restarts on its own.</p>
                                    ) : (
                                        <ul className="flex flex-wrap gap-2" aria-label="Watched services">
                                            {draft.services.map(name => (
                                                <li key={name} className="inline-flex items-center gap-1 rounded-full border border-gray-300 pl-3 pr-1 text-xs dark:border-gray-600">
                                                    <span className="break-all font-mono font-normal text-gray-900 dark:text-gray-100">{name}</span>
                                                    <button
                                                        type="button" aria-label={`Remove ${name}`} disabled={pending}
                                                        onClick={() => stage({ services: draft.services.filter(s => s !== name) })}
                                                        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
                                                    >
                                                        <XIcon size={16} aria-hidden="true" />
                                                    </button>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    <p className={`tabular-nums ${HELPER}`}>{`${draft.services.length}/${MAX_SERVICES} services`}</p>
                                </div>
                            )}
                        />
                    </div>

                    {saveError && !dialogOpen && (
                        <HealthNotice tone="red" role="alert">
                            <p>{saveError}</p>
                        </HealthNotice>
                    )}
                    <div className="flex flex-wrap items-center gap-4 border-t border-gray-200 pt-6 dark:border-white/10">
                        <button
                            type="button" onClick={onSave} disabled={!dirty || !valid || pending}
                            className={dirty && valid ? ACCENT_BUTTON : SECONDARY_BUTTON}
                        >
                            {pending ? 'Saving...' : 'Save settings'}
                        </button>
                        {dirty && (
                            <button
                                type="button" onClick={discard} disabled={pending}
                                className="min-h-10 text-sm font-semibold text-gray-700 underline underline-offset-2 disabled:opacity-60 dark:text-gray-200"
                            >
                                Discard changes
                            </button>
                        )}
                    </div>
                </div>
            )}

            <TurnOffRuleDialog
                open={dialogOpen}
                tenantName={tenantName}
                alsoBlockHours={changes.blockHours ?? null}
                alsoServices={changes.watchedServices ? changes.watchedServices.length : null}
                pending={pending}
                error={dialogOpen ? saveError : null}
                onCancel={() => { setDialogOpen(false); setSaveError(null); }}
                onConfirm={() => { void doSave(); }}
            />
        </section>
    );
};

export default AutonomousOpsResponseSettings;
