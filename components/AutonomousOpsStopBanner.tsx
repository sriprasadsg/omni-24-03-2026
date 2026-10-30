import React from 'react';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import type { StopView } from '../services/autonomousOpsApi';
import { AlertOctagonIcon } from './icons';
import { AutonomousOpsHealthBanners, useHealthBannerKind } from './AutonomousOpsHealthBanners';

/** "Oct 25, 2026, 14:32": the one date format used for a stop in the banner, card and dialogs. */
export function formatStopDate(iso: string): string {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return 'an unknown date';
    return at.toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    });
}

/** "Stopped by {name} on {date}." (the first sentence of every stop description). */
export function stoppedBy(stop: StopView): string {
    return `Stopped by ${stop.by} on ${formatStopDate(stop.at)}.`;
}

/** The second sentence: the typed reason, or "No reason was given.". */
export function stopReasonLine(stop: StopView): string {
    const reason = (stop.reason ?? '').trim();
    return reason ? `Reason: ${reason}` : 'No reason was given.';
}

interface BannerProps {
    /** The current AppView; the View details button is hidden on the Autonomous Ops screen itself. */
    currentView: string;
    onViewDetails: () => void;
}

interface StopBannerProps extends BannerProps {
    /** True when no organization is selected. Phase 82: lets the health banner decide where View details goes. */
    inPlatformScope?: boolean;
    /** Opens the Autonomous Ops screen in platform scope (the shell clears the selected organization). */
    onViewPlatformHealth?: () => void;
}

interface OneBannerProps extends BannerProps {
    title: string;
    stop: StopView;
}

const OneBanner: React.FC<OneBannerProps> = ({ title, stop, currentView, onViewDetails }) => {
    const detail = `${stoppedBy(stop)} ${stopReasonLine(stop)}`;
    return (
        <div
            role="status"
            className="flex flex-wrap items-start gap-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200"
        >
            <AlertOctagonIcon size={20} aria-hidden="true" className="shrink-0" />
            <div className="flex min-w-0 flex-1 basis-64 flex-col gap-1">
                <p className="break-words text-sm font-semibold">{title}</p>
                <p className="line-clamp-2 break-words text-sm" title={detail}>{detail}</p>
            </div>
            {currentView !== 'autonomousOps' && (
                <button
                    type="button"
                    onClick={onViewDetails}
                    className="basis-full text-left text-sm font-semibold text-amber-900 underline underline-offset-2 dark:text-amber-100 sm:basis-auto"
                >
                    View details
                </button>
            )}
        </div>
    );
};

/**
 * The app-wide stop banner (D-15, GATE-06). Fed by the shared status poller, so a viewer without
 * view:autonomous_ops (provider disabled) and a viewer before the first successful poll see
 * nothing. It has no dismiss control: a stop never clears itself, so hiding it would misstate the
 * system (PROH-81-14). A failed poll keeps the last state; the banner never shows its own error.
 */
export const AutonomousOpsStopBanner: React.FC<StopBannerProps> = ({
    currentView, onViewDetails, inPlatformScope = false, onViewPlatformHealth = onViewDetails,
}) => {
    const { status, platformStatus } = useAutonomousOpsStatus();
    const platformStop = status?.stop.platform ?? platformStatus?.stop.platform ?? null;
    const tenantStop = status?.stop.tenant ?? null;
    const { kind: healthKind } = useHealthBannerKind();
    if (!platformStop && !tenantStop && !healthKind) return null;

    return (
        <div className="flex shrink-0 flex-col gap-2">
            {platformStop && (
                <OneBanner
                    title="Automatic actions are stopped for the whole platform."
                    stop={platformStop}
                    currentView={currentView}
                    onViewDetails={onViewDetails}
                />
            )}
            {tenantStop && (
                <OneBanner
                    title={`Automatic actions are stopped for ${status?.tenantName || 'this organization'}.`}
                    stop={tenantStop}
                    currentView={currentView}
                    onViewDetails={onViewDetails}
                />
            )}
            <AutonomousOpsHealthBanners
                currentView={currentView}
                inPlatformScope={inPlatformScope}
                onViewPlatformHealth={onViewPlatformHealth}
            />
        </div>
    );
};

export default AutonomousOpsStopBanner;
