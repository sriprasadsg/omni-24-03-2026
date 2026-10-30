import React from 'react';
import { useAutonomousOpsStatus } from '../contexts/AutonomousOpsStatusContext';
import { useUser } from '../contexts/UserContext';
import type { PlatformHealthSummary } from '../services/autonomousOpsApi';
import { AlertOctagonIcon, AlertTriangleIcon } from './icons';

/** "14:02": a clock time on the viewer's own 24-hour clock (the same format family as formatStopDate). */
export function formatClock(iso: string | null | undefined): string {
    const at = iso ? new Date(iso) : null;
    if (!at || Number.isNaN(at.getTime())) return 'an unknown time';
    return at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
}

let focusRequested = false;

/** A banner's View details asks the Platform health section to take focus when it appears (read once, on mount). */
export function requestPlatformHealthFocus(): void {
    focusRequested = true;
}

/** True once after requestPlatformHealthFocus; the section calls it on mount and moves focus to its heading. */
export function consumePlatformHealthFocus(): boolean {
    const was = focusRequested;
    focusRequested = false;
    return was;
}

interface HealthBannersProps {
    /** The current AppView. */
    currentView: string;
    /** True when no organization is selected (the Platform health section is on the Autonomous Ops screen). */
    inPlatformScope: boolean;
    onViewPlatformHealth: () => void;
}

interface BannerShellProps extends HealthBannersProps {
    role: 'alert' | 'status';
    title: string;
    detail: string;
    classes: string;
    linkClasses: string;
    Icon: React.FC<any>;
}

const RED = 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300';
const RED_LINK = 'text-red-800 dark:text-red-200';
const AMBER = 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200';
const AMBER_LINK = 'text-amber-900 dark:text-amber-100';

const BannerShell: React.FC<BannerShellProps> = ({
    role, title, detail, classes, linkClasses, Icon, currentView, inPlatformScope, onViewPlatformHealth,
}) => (
    <div role={role} className={`flex flex-wrap items-start gap-4 rounded-2xl border p-4 ${classes}`}>
        <Icon size={20} aria-hidden="true" className="shrink-0" />
        <div className="flex min-w-0 flex-1 basis-64 flex-col gap-1">
            <p className="break-words text-sm font-semibold">{title}</p>
            <p className="line-clamp-2 break-words text-sm" title={detail}>{detail}</p>
        </div>
        {!(currentView === 'autonomousOps' && inPlatformScope) && (
            <button
                type="button"
                onClick={() => { requestPlatformHealthFocus(); onViewPlatformHealth(); }}
                className={`basis-full text-left text-sm font-semibold underline underline-offset-2 sm:basis-auto ${linkClasses}`}
            >
                View details
            </button>
        )}
    </div>
);

function SilentBanner(props: HealthBannersProps & { health: PlatformHealthSummary }) {
    const detail = `Last seen ${formatClock(props.health.lastSeenAt)}. Services are not being checked or restarted, and no on-call pages can be sent, until it reports again.`;
    return (
        <BannerShell
            {...props}
            role="alert"
            title="The watchdog has gone silent."
            detail={detail}
            classes={RED}
            linkClasses={RED_LINK}
            Icon={AlertOctagonIcon}
        />
    );
}

export type HealthBannerKind = 'silent' | 'channel_none' | 'channel_failing';

function ChannelBanner(props: HealthBannersProps & { health: PlatformHealthSummary; failing: boolean }) {
    const { health, failing, ...shell } = props;
    const detail = failing
        ? `The last alert couldn't be delivered: ${health.channelError || 'no reason was given'}. Nobody will be paged until a test alert succeeds.`
        : 'Nobody will be paged if a service fails. Set up a channel on the server, then send a test alert.';
    return (
        <BannerShell
            {...shell}
            role="status"
            title="No working on-call channel."
            detail={detail}
            classes={AMBER}
            linkClasses={AMBER_LINK}
            Icon={AlertTriangleIcon}
        />
    );
}

/**
 * Which health banner the viewer sees, if any. Gated on control:platform_autonomous_ops and on the first
 * successful poll (D-22); no banner while the watchdog has never reported or health is unknown (D-24).
 */
export function useHealthBannerKind(): { kind: HealthBannerKind | null; health: PlatformHealthSummary | null } {
    const { hasPermission } = useUser();
    const { platformStatus } = useAutonomousOpsStatus();
    const health = platformStatus?.health ?? null;
    if (!hasPermission('control:platform_autonomous_ops') || !health) return { kind: null, health: null };
    if (health.watchdog === 'silent') return { kind: 'silent', health };
    if (health.watchdog !== 'running') return { kind: null, health }; // not installed: nothing is armed yet (D-24)
    if (health.channel === 'none') return { kind: 'channel_none', health };
    if (health.channel === 'failing') return { kind: 'channel_failing', health };
    return { kind: null, health };
}

/**
 * The app-wide platform health banner (D-05, D-22, D-24): at most one, for a holder of
 * control:platform_autonomous_ops only. Fed by the shared status poller, so nothing renders before the
 * first successful poll, a failed poll keeps the last state, and the banner never shows its own error.
 * It has no dismiss control: it describes a standing condition.
 */
export const AutonomousOpsHealthBanners: React.FC<HealthBannersProps> = (props) => {
    const { kind, health } = useHealthBannerKind();
    if (!health) return null;
    if (kind === 'silent') return <SilentBanner {...props} health={health} />;
    if (kind === 'channel_none') return <ChannelBanner {...props} health={health} failing={false} />;
    if (kind === 'channel_failing') return <ChannelBanner {...props} health={health} failing />;
    return null;
};

export default AutonomousOpsHealthBanners;
