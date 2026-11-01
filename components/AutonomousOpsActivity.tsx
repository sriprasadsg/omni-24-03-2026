import React, { useCallback, useMemo, useState } from 'react';
import type { AppView } from '../types';
import { useUser } from '../contexts/UserContext';
import { resolveAutonomousOpsScope, useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { platformTier } from '../utils/permissions';
import { AutonomousOpsActivityList, EmptyStateCard } from './AutonomousOpsActivityList';
import type { OpenViewHandlers } from './AutonomousOpsRowActions';
import { AutonomousOpsPlatformHealth } from './AutonomousOpsPlatformHealth';
import { AutonomousOpsResponseSettings } from './AutonomousOpsResponseSettings';
import { PlatformResponseSettings } from './AutonomousOpsResponseSettingsPlatform';
import { AutonomousOpsStatusCard } from './AutonomousOpsStatusCard';
import { EyeIcon, RefreshCwIcon, ShieldLockIcon } from './icons';

interface AutonomousOpsActivityProps {
    /** viewingTenantId: the organization platform staff entered from Tenants, else null. */
    tenantId?: string | null;
    onGoToTenants?: () => void;
    /** Moves the app to another screen. A suggestion row may open Patching or File Integrity through it. */
    onOpenView?: (view: AppView) => void;
}

const SECONDARY_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs font-semibold text-gray-700 dark:text-gray-200 break-words';

/** Autonomous Ops (ACTV-01, ACTV-03): the read-only record of every decision. Phase 83 adds Undo and links to Patching and File Integrity. */
export const AutonomousOpsActivity: React.FC<AutonomousOpsActivityProps> = ({ tenantId = null, onGoToTenants, onOpenView }) => {
    const { currentUser, hasPermission } = useUser();
    const { status, refresh } = useAutonomousOpsStatus();
    const [refreshing, setRefreshing] = useState(false);
    const [refreshSignal, setRefreshSignal] = useState(0);

    const scope = resolveAutonomousOpsScope(currentUser?.role, tenantId);
    const readOnly = platformTier(currentUser?.role) === 'support';

    const onRefresh = useCallback(async () => {
        setRefreshing(true);
        setRefreshSignal(n => n + 1);
        try { await refresh(); } finally { setRefreshing(false); }
    }, [refresh]);

    // A link out exists for a target only when the viewer may open that screen; otherwise it reads as plain text.
    const canPatch = hasPermission('view:patching');
    const canFim = hasPermission('view:fim');
    const openers = useMemo<OpenViewHandlers | undefined>(() => {
        if (!onOpenView) return undefined;
        const out: OpenViewHandlers = {};
        if (canPatch) out.patchManagement = () => onOpenView('patchManagement');
        if (canFim) out.fimMonitoring = () => onOpenView('fimMonitoring');
        return out;
    }, [onOpenView, canPatch, canFim]);

    // Response settings (D-22): holders of manage in an organization that is not the platform one; never Platform Support.
    const showResponseSettings = scope.kind === 'tenant' && !readOnly && !!status && !status.platformTenant
        && hasPermission('manage:autonomous_ops');

    const scopeLabel = scope.kind === 'platform'
        ? 'Platform'
        : status?.tenantName ? `Viewing ${status.tenantName}` : null;

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                    <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.03em] text-gray-900 dark:text-white">Autonomous Ops</h1>
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                        Automatic actions within limits you set. Riskier actions wait for your approval, and every decision is listed below.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {scopeLabel && <span className={OUTLINE_CHIP}>{scopeLabel}</span>}
                    {readOnly && (
                        <span className={OUTLINE_CHIP}>
                            <EyeIcon size={12} aria-hidden="true" />
                            Read-only
                        </span>
                    )}
                    {scope.kind !== 'none' && (
                        <button type="button" className={SECONDARY_BUTTON} onClick={onRefresh} disabled={refreshing}>
                            <RefreshCwIcon size={16} aria-hidden="true" className={refreshing ? 'animate-spin' : ''} />
                            {refreshing ? 'Refreshing...' : 'Refresh'}
                        </button>
                    )}
                </div>
            </div>

            {scope.kind === 'none' ? (
                <div className="card overflow-hidden">
                    <EmptyStateCard icon={ShieldLockIcon} heading="Select an organization" headingLevel="h2">
                        <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">
                            Choose an organization in Tenants to see its Autonomous Ops activity. This view is read-only.
                        </p>
                        {onGoToTenants && (
                            <button type="button" className={SECONDARY_BUTTON} onClick={onGoToTenants}>Go to Tenants</button>
                        )}
                    </EmptyStateCard>
                </div>
            ) : (
                <>
                    <div data-slot="autonomous-ops-status">
                        <AutonomousOpsStatusCard tenantId={tenantId} />
                    </div>
                    {scope.kind === 'platform' && hasPermission('control:platform_autonomous_ops') && (
                        <AutonomousOpsPlatformHealth refreshSignal={refreshSignal} />
                    )}
                    {scope.kind === 'platform' && hasPermission('control:platform_autonomous_ops') && <PlatformResponseSettings />}
                    {showResponseSettings && (
                        <AutonomousOpsResponseSettings
                            key={scope.kind === 'tenant' ? scope.tenantId ?? 'own' : 'own'}
                            tenantId={scope.kind === 'tenant' ? scope.tenantId : null}
                            tenantName={status?.tenantName || 'this organization'}
                        />
                    )}
                    <section className="space-y-4" aria-labelledby="autonomous-ops-activity-title">
                        <div className="flex flex-wrap items-center justify-between gap-4">
                            <h2 id="autonomous-ops-activity-title" className="text-lg font-semibold leading-tight text-gray-900 dark:text-white">Activity</h2>
                            <span className="text-xs text-gray-500 dark:text-gray-400">Newest first</span>
                        </div>
                        <AutonomousOpsActivityList scope={scope} refreshSignal={refreshSignal} onOpenView={openers} />
                    </section>
                </>
            )}
        </div>
    );
};

export default AutonomousOpsActivity;
