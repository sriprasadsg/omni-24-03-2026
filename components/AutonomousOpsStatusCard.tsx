import React, { useState } from 'react';
import { useUser } from '../contexts/UserContext';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { platformTier } from '../utils/permissions';
import { AutonomousOpsStopDialog } from './AutonomousOpsStopDialog';
import { stoppedBy, stopReasonLine } from './AutonomousOpsStopBanner';
import { AlertOctagonIcon, CheckCircleIcon, PauseCircleIcon } from './icons';

const OUTLINE_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs font-semibold text-gray-700 dark:text-gray-200 break-words';
const AMBER_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200';
const STOP_BUTTON =
    'inline-flex items-center justify-center gap-2 min-h-10 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60';

interface CardProps {
    /** viewingTenantId: the organization platform staff entered from Tenants, else null. */
    tenantId?: string | null;
}

/** The Autonomous Ops status card (D-22): what it will do for this organization, and the brake. */
export const AutonomousOpsStatusCard: React.FC<CardProps> = ({ tenantId = null }) => {
    const { currentUser, hasPermission } = useUser();
    const { status, refresh } = useAutonomousOpsStatus();
    const [dialog, setDialog] = useState<'stop' | null>(null);

    if (!status) return null;

    const isSupport = platformTier(currentUser?.role) === 'support';
    const canStop = hasPermission('control:autonomous_ops') && !isSupport && status.canStop;
    const stop = status.stop.tenant ?? status.stop.platform;

    return (
        <div className="card p-6 flex flex-col gap-6">
            <dl className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                <div className="min-w-0">
                    <dt className="text-xs text-gray-500 dark:text-gray-400">Stop</dt>
                    <dd className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
                        {stop ? (
                            <span className={AMBER_CHIP}><PauseCircleIcon size={12} aria-hidden="true" />Stopped</span>
                        ) : (
                            <span className={OUTLINE_CHIP}><CheckCircleIcon size={12} aria-hidden="true" />Not stopped</span>
                        )}
                    </dd>
                    {stop && (
                        <p className="mt-1 break-words text-xs text-gray-500 dark:text-gray-400">
                            {stoppedBy(stop)} {stopReasonLine(stop)}
                        </p>
                    )}
                </div>
            </dl>
            {canStop && !stop && (
                <div className="flex flex-wrap items-center gap-4 border-t border-gray-200 pt-6 dark:border-white/10">
                    <button type="button" className={STOP_BUTTON} aria-describedby="autonomous-ops-stop-help" onClick={() => setDialog('stop')}>
                        <AlertOctagonIcon size={16} aria-hidden="true" />
                        Stop automatic actions
                    </button>
                    <span id="autonomous-ops-stop-help" className="break-words text-xs text-gray-500 dark:text-gray-400">
                        Takes effect right away. Undo still works.
                    </span>
                </div>
            )}
            {dialog === 'stop' && (
                <AutonomousOpsStopDialog
                    tenantName={status.tenantName}
                    tenantId={tenantId}
                    onClose={() => setDialog(null)}
                    onDone={() => { void refresh(); }}
                />
            )}
        </div>
    );
};

export default AutonomousOpsStatusCard;
