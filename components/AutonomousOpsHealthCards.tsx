import React from 'react';
import type { PlatformHealthCert, PlatformHealthDisk, PlatformHealthOnCall, PlatformHealthTestAlert, WatchdogState } from '../services/autonomousOpsApi';

interface FreshnessProps {
    /** True while the watchdog is silent or has never reported: every entry reads Unknown. */
    stale: boolean;
    /** The watchdog's last report, for "Last known" lines. */
    updatedAt?: string | null;
}

export const CertificatesCard: React.FC<FreshnessProps & { certs: PlatformHealthCert[] }> = () => null;
export const DiskCard: React.FC<FreshnessProps & { disks: PlatformHealthDisk[] }> = () => null;

interface OnCallProps {
    oncall: PlatformHealthOnCall;
    testAlert: PlatformHealthTestAlert | null;
    watchdogState: WatchdogState;
    installChecklist: { path: string; url: string | null } | null | undefined;
    noAnswer: boolean;
    onTestRequested: (testAlert: PlatformHealthTestAlert) => void;
}
export const OnCallCard: React.FC<OnCallProps> = () => null;

/** True once a pending test alert has gone 90 s without an answer from the watchdog (H10). */
export function useTestAlertNoAnswer(_testAlert: PlatformHealthTestAlert | null): boolean {
    return false;
}
