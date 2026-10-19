import React, { useEffect, useRef, useState } from 'react';
import { BotIcon, LogOutIcon, RefreshCwIcon } from './icons';
import type { RefreshResult } from '../utils/permissionRefresh';

interface ZeroAccessScreenProps {
  email: string;
  roleName: string;
  tenantName: string;
  companyName?: string;
  onRetry: () => Promise<RefreshResult>;
  onSignOut: () => void;
}

type RetryStatus = { kind: 'idle' } | { kind: 'pending' } | { kind: 'same'; at: string } | { kind: 'error' };

const IdentityRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-baseline justify-between gap-4 min-w-0">
    <dt className="text-xs text-gray-500 dark:text-gray-400 shrink-0">{label}</dt>
    <dd className="text-sm font-semibold text-gray-900 dark:text-white truncate min-w-0" title={value}>{value}</dd>
  </div>
);

/**
 * D-07: the full-page screen for a signed-in user whose delivered permissions allow no screen.
 * It replaces the whole shell (no sidebar, header or floating widgets). Sign out is never gated by
 * Retry, so a hung permission check cannot trap the user.
 */
export const ZeroAccessScreen: React.FC<ZeroAccessScreenProps> = ({
  email, roleName, tenantName, companyName, onRetry, onSignOut,
}) => {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const [status, setStatus] = useState<RetryStatus>({ kind: 'idle' });

  useEffect(() => {
    headingRef.current?.focus();
    return () => { mounted.current = false; };
  }, []);

  const handleRetry = async () => {
    if (inFlight.current) return; // repeated clicks are ignored while a check is running
    inFlight.current = true;
    setStatus({ kind: 'pending' });
    let result: RefreshResult;
    try {
      result = await onRetry();
    } catch {
      result = 'error';
    }
    inFlight.current = false;
    if (!mounted.current) return;
    if (result === 'error') setStatus({ kind: 'error' });
    else if (result === 'same') setStatus({ kind: 'same', at: new Date().toLocaleTimeString() });
    else setStatus({ kind: 'idle' }); // 'changed': App lands on the first allowed screen, no toast
  };

  const pending = status.kind === 'pending';

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-[#0b1220] p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-md p-8 flex flex-col gap-6">
        <div className="flex items-center gap-3 min-w-0">
          <div className="bg-gradient-to-tr from-primary-500 to-primary-700 p-2 rounded-lg shadow-lg shadow-primary-500/20 shrink-0">
            <BotIcon className="text-white" size={24} aria-hidden="true" />
          </div>
          <span className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">{companyName || 'Omni-Agent'}</span>
        </div>
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-2xl font-semibold leading-tight text-gray-900 dark:text-white break-words focus:outline-none"
        >
          Your role has no screens yet
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Ask your administrator to give your role access to at least one screen, then select Retry.
        </p>
        <dl className="rounded-lg bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 p-4 flex flex-col gap-2">
          <IdentityRow label="Signed in as" value={email} />
          <IdentityRow label="Role" value={roleName} />
          <IdentityRow label="Tenant" value={tenantName} />
        </dl>
        <div className="min-h-[20px] text-sm" aria-live="polite">
          {status.kind === 'same' && (
            <span className="text-gray-600 dark:text-gray-400">{`Still no screens for your role. Last checked ${status.at}.`}</span>
          )}
          {status.kind === 'error' && (
            <span role="alert" className="text-red-600 dark:text-red-400">
              Couldn't check your permissions. Check your connection and try again.
            </span>
          )}
        </div>
        <div className="flex flex-col min-[400px]:flex-row gap-2">
          <button
            type="button"
            aria-label="Retry permission check"
            disabled={pending}
            onClick={handleRetry}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            <RefreshCwIcon size={16} aria-hidden="true" className={pending ? 'motion-safe:animate-spin' : ''} />
            {pending ? 'Checking...' : 'Retry'}
          </button>
          <button
            type="button"
            onClick={onSignOut}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
          >
            <LogOutIcon size={16} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
};
