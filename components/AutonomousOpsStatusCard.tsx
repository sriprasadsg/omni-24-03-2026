import React, { useState } from 'react';
import { useUser } from '../contexts/UserContext';
import { resolveAutonomousOpsScope, useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { platformTier } from '../utils/permissions';
import type { AutonomousOpsLevel, AutonomousOpsStatus, PlatformAutonomousOpsStatus, StopView } from '../services/autonomousOpsApi';
import { AutonomousOpsStopDialog, StopDialogKind, StopDialogScope } from './AutonomousOpsStopDialog';
import { stoppedBy, stopReasonLine } from './AutonomousOpsStopBanner';
import {
    AlertOctagonIcon, AlertTriangleIcon, CheckCircleIcon, FlaskConicalIcon, InfoIcon, PauseCircleIcon, PlayCircleIcon,
} from './icons';

const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs font-semibold text-gray-700 dark:text-gray-200 break-words';
const AMBER_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200';
const SIMULATION_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-dashed border-gray-400 dark:border-gray-500 px-2 py-1 text-xs font-semibold text-gray-800 dark:text-gray-100';
const STOP_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';
const RESUME_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60';
const TEXT_BUTTON = 'text-sm font-semibold underline underline-offset-2';
const DIVIDER = 'border-t border-gray-200 pt-6 dark:border-white/10';
const SKELETON = 'animate-pulse rounded-lg bg-gray-200 dark:bg-white/10';

const LEVEL_LABEL: Record<string, string> = {
    off: 'Off', suggest: 'Suggest only', undoable_auto: 'Automatic within limits',
};
const LEVEL_HELP: Record<string, string> = {
    off: 'Nothing is decided or recorded.',
    suggest: 'Autonomous Ops suggests actions. Every action needs your approval.',
    undoable_auto: 'Low-risk actions run on their own and can be undone. Riskier actions need your approval.',
};
const levelLabel = (level: string | null | undefined) => (level && LEVEL_LABEL[level]) || level || 'Off';

interface DialogState { kind: StopDialogKind; scope: StopDialogScope }

// ── small pieces ────────────────────────────────────────────────────────────

const Cell: React.FC<{ label: string; value: React.ReactNode; help?: React.ReactNode }> = ({ label, value, help }) => (
    <div className="min-w-0">
        <dt className="text-xs text-gray-500 dark:text-gray-400">{label}</dt>
        <dd className="mt-1 break-words text-sm font-semibold text-gray-900 dark:text-white">{value}</dd>
        {help && <p className="mt-1 break-words text-xs text-gray-500 dark:text-gray-400">{help}</p>}
    </div>
);

const Notice: React.FC<{ tone: 'amber' | 'blue'; children: React.ReactNode }> = ({ tone, children }) => {
    const Icon = tone === 'amber' ? AlertTriangleIcon : InfoIcon;
    const cls = tone === 'amber'
        ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200'
        : 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-400/25 dark:bg-blue-400/10 dark:text-blue-200';
    return (
        <div className={`flex items-start gap-2 break-words rounded-lg border p-4 text-sm ${cls}`}>
            <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p className="min-w-0">{children}</p>
        </div>
    );
};

const StopChip: React.FC<{ stop: StopView | null }> = ({ stop }) => (stop
    ? <span className={AMBER_CHIP}><PauseCircleIcon size={12} aria-hidden="true" />Stopped</span>
    : <span className={OUTLINE_CHIP}><CheckCircleIcon size={12} aria-hidden="true" />Not stopped</span>);

const stopHelp = (stop: StopView | null) => (stop ? `${stoppedBy(stop)} ${stopReasonLine(stop)}` : undefined);

const StopButton: React.FC<{ label: string; onClick: () => void; describedBy?: string }> = ({ label, onClick, describedBy }) => (
    <button type="button" className={STOP_BUTTON} onClick={onClick} aria-describedby={describedBy}>
        <AlertOctagonIcon size={16} aria-hidden="true" />
        {label}
    </button>
);

const ResumeButton: React.FC<{ label: string; onClick?: () => void; disabled?: boolean }> = ({ label, onClick, disabled }) => (
    <button type="button" className={RESUME_BUTTON} onClick={onClick} disabled={disabled}>
        <PlayCircleIcon size={16} aria-hidden="true" />
        {label}
    </button>
);

const Muted: React.FC<{ id?: string; children: React.ReactNode }> = ({ id, children }) => (
    <span id={id} className="break-words text-xs text-gray-500 dark:text-gray-400">{children}</span>
);

// ── the card ────────────────────────────────────────────────────────────────

interface CardProps {
    /** viewingTenantId: the organization platform staff entered from Tenants, else null. */
    tenantId?: string | null;
}

/**
 * The Autonomous Ops status card (D-22): what Autonomous Ops will do for this organization, and the
 * brake. Level, maximum and shadow mode are display-only. Who may resume comes from the server's
 * canResume / canResumePlatform flags and the name shown for a stop is the server's `by` value; the
 * permission checks here only decide which controls to draw (D-25, T-81-42).
 */
export const AutonomousOpsStatusCard: React.FC<CardProps> = ({ tenantId = null }) => {
    const { currentUser, hasPermission } = useUser();
    const { status, platformStatus, loading, error, refresh } = useAutonomousOpsStatus();
    const [dialog, setDialog] = useState<DialogState | null>(null);

    const scope = resolveAutonomousOpsScope(currentUser?.role, tenantId);
    if (scope.kind === 'none') return null;

    const isSupport = platformTier(currentUser?.role) === 'support';
    const holdsStop = hasPermission('control:autonomous_ops') && !isSupport;
    const holdsManage = hasPermission('manage:autonomous_ops') && !isSupport;
    const holdsPlatform = hasPermission('control:platform_autonomous_ops') && !isSupport;
    const inPlatformScope = scope.kind === 'platform';
    const data = inPlatformScope ? platformStatus : status;

    if (!data && !loading && !error) return null;

    const openDialog = (kind: StopDialogKind, dialogScope: StopDialogScope) => setDialog({ kind, scope: dialogScope });

    if (!data && loading) {
        return (
            <div className="card p-6 flex flex-col gap-6" aria-busy="true">
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                    {[0, 1, 2, 3].map(i => <div key={i} className={`h-16 ${SKELETON}`} />)}
                </div>
                <div className={`h-10 w-56 ${SKELETON}`} />
            </div>
        );
    }

    let platformStop: StopView | null = null;
    let canStopPlatform = false;
    let canResumePlatform = false;
    if (inPlatformScope && platformStatus) {
        platformStop = platformStatus.stop.platform;
        canStopPlatform = platformStatus.canStopPlatform;
        canResumePlatform = platformStatus.canResumePlatform;
    } else if (status) {
        platformStop = status.stop.platform;
        canStopPlatform = status.canStopPlatform;
        canResumePlatform = status.canResumePlatform;
    }
    const showPlatformRow = holdsPlatform && (data ? canStopPlatform : inPlatformScope);

    // ── status could not be loaded: Stop stays available, Resume waits for a status ──
    if (!data) {
        const canBrake = inPlatformScope ? holdsPlatform : holdsStop;
        return (
            <div className="card p-6 flex flex-col gap-6">
                <div role="alert" className="flex flex-wrap items-center gap-2 break-words rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
                    <AlertTriangleIcon size={16} aria-hidden="true" className="shrink-0" />
                    <span className="min-w-0">{`Couldn't load the current status.${canBrake ? ' Stop is still available.' : ''}`}</span>
                    <button type="button" className={`${TEXT_BUTTON} ml-auto`} onClick={() => { void refresh(); }}>Try again</button>
                </div>
                {canBrake && (
                    <div className={`flex flex-wrap items-center gap-4 ${DIVIDER}`}>
                        <StopButton
                            label={inPlatformScope ? 'Stop all organizations' : 'Stop automatic actions'}
                            onClick={() => openDialog('stop', inPlatformScope ? 'platform' : 'tenant')}
                        />
                        {(inPlatformScope ? holdsPlatform : holdsManage) && (
                            <ResumeButton label={inPlatformScope ? 'Resume all organizations' : 'Resume automatic actions'} disabled />
                        )}
                    </div>
                )}
                {renderDialog(null)}
            </div>
        );
    }

    // ── tenant controls ──
    const tenantStatus: AutonomousOpsStatus | null = inPlatformScope ? null : status;
    let tenantControls: React.ReactNode = null;
    if (tenantStatus && !tenantStatus.platformTenant && !isSupport) {
        const tenantStop = tenantStatus.stop.tenant;
        const anyStop = tenantStop ?? tenantStatus.stop.platform;
        if (anyStop) {
            if (tenantStatus.canResume) {
                tenantControls = <ResumeButton label="Resume automatic actions" onClick={() => openDialog('resume', 'tenant')} />;
            } else if (holdsStop || holdsManage) {
                const needsManage = !!tenantStop && !holdsManage;
                tenantControls = (
                    <p className="break-words text-sm text-gray-600 dark:text-gray-400">
                        {needsManage
                            ? 'Only an administrator with manage access can resume this.'
                            : 'Only a platform administrator can resume this.'}
                    </p>
                );
            }
        } else if (holdsStop && tenantStatus.canStop) {
            tenantControls = (
                <>
                    <StopButton label="Stop automatic actions" onClick={() => openDialog('stop', 'tenant')} describedBy="autonomous-ops-stop-help" />
                    <Muted id="autonomous-ops-stop-help">Takes effect right away. Undo still works.</Muted>
                </>
            );
        }
    }

    // ── platform-wide row (Super Admin) ──
    let platformRow: React.ReactNode = null;
    if (showPlatformRow) {
        platformRow = (
            <div className={`flex flex-col gap-4 ${DIVIDER}`}>
                <div className="flex flex-col gap-1">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Platform-wide stop</h3>
                    <Muted>Halts or resumes automatic actions for every organization at once. Only a platform administrator can resume it.</Muted>
                </div>
                <div className="flex flex-wrap items-center gap-4">
                    {platformStop
                        ? (canResumePlatform && <ResumeButton label="Resume all organizations" onClick={() => openDialog('resume', 'platform')} />)
                        : <StopButton label="Stop all organizations" onClick={() => openDialog('stop', 'platform')} />}
                </div>
            </div>
        );
    }

    function renderDialog(current: StopView | null) {
        if (!dialog) return null;
        return (
            <AutonomousOpsStopDialog
                kind={dialog.kind}
                scope={dialog.scope}
                tenantName={status?.tenantName || 'this organization'}
                tenantId={tenantId}
                current={current}
                shadow={!!status?.shadow.effective}
                onClose={() => setDialog(null)}
                onDone={() => { void refresh(); }}
            />
        );
    }
    const dialogCurrent = dialog?.kind === 'resume'
        ? (dialog.scope === 'platform' ? platformStop : tenantStatus?.stop.tenant ?? null)
        : null;

    return (
        <div className="card p-6 flex flex-col gap-6">
            {inPlatformScope && platformStatus
                ? <PlatformReadout status={platformStatus} />
                : tenantStatus && <TenantReadout status={tenantStatus} />}
            {tenantControls && <div className={`flex flex-wrap items-center gap-4 ${DIVIDER}`}>{tenantControls}</div>}
            {platformRow}
            {renderDialog(dialogCurrent)}
        </div>
    );
};

// ── readouts ────────────────────────────────────────────────────────────────

const PlatformReadout: React.FC<{ status: PlatformAutonomousOpsStatus }> = ({ status }) => {
    const n = status.tenantStopsCount;
    return (
        <dl className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <Cell label="Platform-wide stop" value={<StopChip stop={status.stop.platform} />} help={stopHelp(status.stop.platform)} />
            <Cell
                label="Tenant stops"
                value={`${n} ${n === 1 ? 'organization' : 'organizations'} stopped`}
                help="Each organization can also be stopped on its own."
            />
        </dl>
    );
};

const TenantReadout: React.FC<{ status: AutonomousOpsStatus }> = ({ status }) => {
    const shown = status.stop.tenant ?? status.stop.platform;
    const shadowOn = status.shadow.effective;
    const shadowSource = status.shadow.source === 'deployment'
        ? ' Set for the whole deployment.'
        : status.shadow.source === 'tenant' ? ' Set for this organization.' : '';
    const level = (value: AutonomousOpsLevel) => <span className={OUTLINE_CHIP}>{levelLabel(value)}</span>;
    return (
        <>
            <dl className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                <Cell label="Current level" value={level(status.level)} help={LEVEL_HELP[status.level]} />
                <Cell label="Highest level allowed" value={level(status.maxLevel)} help="Set by a platform administrator." />
                <Cell
                    label="Shadow mode"
                    value={shadowOn
                        ? <span className={SIMULATION_CHIP}><FlaskConicalIcon size={12} aria-hidden="true" />On: simulation only</span>
                        : <span className={OUTLINE_CHIP}>Off: actions are live</span>}
                    help={shadowOn
                        ? `Autonomous Ops records what it would have done. Nothing is carried out.${shadowSource}`
                        : 'Actions allowed by the level above are carried out.'}
                />
                <Cell label="Stop" value={<StopChip stop={shown} />} help={stopHelp(shown)} />
            </dl>
            {status.previousLevel && (
                <Notice tone="amber">
                    {`Lowered from ${levelLabel(status.previousLevel)} after several automatic actions in a row were undone or failed. A person with manage access can restore it.`}
                </Notice>
            )}
            {!status.levelReadable && (
                <Notice tone="blue">
                    This organization's setting couldn't be read, so it is treated as Suggest only. Every action needs approval.
                </Notice>
            )}
            {status.platformTenant && (
                <Notice tone="blue">Autonomous Ops is not available for the platform organization.</Notice>
            )}
            {!status.eligible && !status.platformTenant && (
                <Notice tone="blue">
                    This screen isn't switched on for this organization, so nothing is decided or recorded for it.
                </Notice>
            )}
        </>
    );
};

export default AutonomousOpsStatusCard;
