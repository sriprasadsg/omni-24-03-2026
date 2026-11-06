import React from 'react';
import type { ApprovalCard } from '../../services/patchRollouts/types';

/** Skeleton for the RED commit of 84-15 task 1: the props are fixed, nothing renders yet. */
export interface RolloutApprovalCardProps {
    card: ApprovalCard;
    now?: number;
    stopped: boolean;
    shadow: boolean;
    tenantId?: string | null;
    onDecided: (card: ApprovalCard) => void;
    onStale?: () => void;
}

export const RolloutApprovalCard: React.FC<RolloutApprovalCardProps> = () => null;

export default RolloutApprovalCard;
