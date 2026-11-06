import React from 'react';
import type { AppView } from '../../types';
import type { RingView, RolloutCard as RolloutCardData } from '../../services/patchRollouts/types';

/** One rollout card (84-14, UI-SPEC section 4). Task 3 builds the header, ring strip and halt block. */

export interface RolloutCardProps {
    card: RolloutCardData;
    onOpenView?: (view: AppView) => void;
    renderRingDetail?: (ring: RingView, card: RolloutCardData) => React.ReactNode;
    actions?: React.ReactNode;
}

export const RolloutCard: React.FC<RolloutCardProps> = ({ card }) => (
    <article id={`rollout-${card.id}`} tabIndex={-1} aria-labelledby={`rollout-${card.id}-title`} className="card overflow-hidden">
        <h3 id={`rollout-${card.id}-title`} className="px-6 py-4 text-sm font-semibold text-gray-900 dark:text-white">{card.name}</h3>
    </article>
);

export default RolloutCard;
