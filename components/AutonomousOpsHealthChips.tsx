import React from 'react';

export type HealthChipKind =
    | 'healthy' | 'checking' | 'restarting' | 'down' | 'gave_up' | 'expected_off' | 'unknown'
    | 'running' | 'silent' | 'not_installed' | 'ok' | 'notice' | 'warning' | 'critical' | 'pinned'
    | 'working' | 'not_working' | 'not_set_up' | 'not_tested' | 'counting_only' | 'deleting_nightly'
    | 'waiting' | 'running_now' | 'paged' | 'skipped';

/** Skeleton for the RED commit: renders nothing until the chips are implemented. */
export const HealthChip: React.FC<{ kind: HealthChipKind }> = () => null;

export function ladderChip(_rung: number | null | undefined): HealthChipKind {
    return 'unknown';
}
