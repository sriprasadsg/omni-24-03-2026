import React, { useEffect, useRef } from 'react';
import type { AppView, Permission, User } from '../types';
import { InfoIcon, ShieldLockIcon } from './icons';
import { SkeletonDashboard } from './ui/skeleton';
import { catalogueFor } from '../utils/catalogueAccess';
import { roleLabel } from '../utils/permissions';
import { evaluateViewAccess, permissionsKnown } from '../utils/viewAccess';

interface NoAccessPanelProps {
  screenLabel: string;
  reason: 'role' | 'switched_off' | 'unmapped';
  permission?: Permission;
  roleName?: string;
  landingLabel?: string;
  onGoToLanding?: () => void;
  accessChanged?: boolean;
}

function reasonCopy(reason: NoAccessPanelProps['reason'], screenLabel: string, roleName?: string): string {
  if (reason === 'switched_off') {
    return `${screenLabel} is switched off for your organization. Ask your administrator to turn it on.`;
  }
  if (reason === 'unmapped') return "This screen isn't open to your role.";
  return `Your role (${roleName ?? 'unknown'}) doesn't include the permission this screen needs. If you need access, ask your administrator.`;
}

/**
 * D-05: the in-place panel shown inside <main> instead of a screen the role cannot see. It names
 * only the screen label, the reason and (role variant) the required permission; nothing of the
 * denied screen mounts or fetches.
 */
export const NoAccessPanel: React.FC<NoAccessPanelProps> = ({
  screenLabel, reason, permission, roleName, landingLabel, onGoToLanding, accessChanged,
}) => {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { headingRef.current?.focus(); }, []);

  return (
    <div className="flex justify-center pt-12">
      <div className="w-full max-w-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-md p-8 flex flex-col gap-4">
        <div className="h-12 w-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center text-gray-500 dark:text-gray-400">
          <ShieldLockIcon size={24} aria-hidden="true" />
        </div>
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="text-lg font-semibold text-gray-900 dark:text-white break-words focus:outline-none"
        >
          {`You don't have access to ${screenLabel}`}
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 break-words">{reasonCopy(reason, screenLabel, roleName)}</p>
        {reason === 'role' && permission && (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-gray-500 dark:text-gray-400">Required permission</span>
            <span className="self-start font-mono text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 break-all">
              {permission}
            </span>
          </div>
        )}
        {accessChanged && (
          <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/50 dark:text-blue-300 p-3 text-sm">
            <InfoIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <span>Your access was updated by an administrator.</span>
          </div>
        )}
        {onGoToLanding && landingLabel && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onGoToLanding}
              className="px-4 py-2 text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
            >
              {`Go to ${landingLabel}`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

interface ViewGateProps {
  view: AppView;
  user: User | null;
  hasPermission: (permission: Permission) => boolean;
  landing: AppView | null;
  onGoToLanding: () => void;
  accessChanged?: boolean;
  render: () => React.ReactNode;
}

/**
 * Render-time gate around renderView(): skeleton while permissions are unknown (C09), the panel
 * when the view is denied, the real screen only when allowed. Derived state, no fetch of its own.
 */
export const ViewGate: React.FC<ViewGateProps> = ({
  view, user, hasPermission, landing, onGoToLanding, accessChanged, render,
}) => {
  if (!permissionsKnown(user)) return <SkeletonDashboard />;
  const access = evaluateViewAccess(view, user, hasPermission);
  if (access.allowed) return <>{render()}</>;
  return (
    <NoAccessPanel
      screenLabel={access.label}
      reason={access.reason}
      permission={access.permission}
      roleName={user ? roleLabel(user.role) : undefined}
      landingLabel={landing ? catalogueFor(landing)?.label : undefined}
      onGoToLanding={onGoToLanding}
      accessChanged={accessChanged}
    />
  );
};
