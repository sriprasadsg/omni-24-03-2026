import React from 'react';
import type { StatsWindow } from '../../services/autonomousOpsReporting';

interface StatsCardProps {
    tenantId: string | null;
    days: StatsWindow;
    onDaysChange: (days: StatsWindow) => void;
    refreshSignal: number;
}

// Skeleton for the failing-test commit (Phase 86, plan 86-01). Replaced by the real card.
export const StatsCard: React.FC<StatsCardProps> = () => null;

export default StatsCard;
