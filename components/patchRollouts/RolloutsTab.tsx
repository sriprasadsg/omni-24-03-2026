import React from 'react';
import type { AppView } from '../../types';
import type { RingView, RolloutCard } from '../../services/patchRollouts/types';
import { ASSURANCE_LINE } from './rolloutCopy';
import { InfoIcon } from '../icons';

/**
 * The Rollouts tab on the Patching screen (84-14, UI-SPEC section 2). The optional props are the extension points
 * later plans fill: the Start dialog and the rings card (84-17), the ring detail and the Resume and Cancel actions
 * (84-18). With none given the tab shows rollouts read-only.
 */

export interface RolloutsTabProps {
    /** The organization platform staff entered from Tenants, else null (a tenant role never sends one). */
    tenantId?: string | null;
    /** Where Review in Needs your decision and Open maintenance windows navigate. */
    onOpenView?: (view: AppView) => void;
    /** False while another Patching tab is showing: polling pauses. */
    active?: boolean;
    /** A counter the parent bumps after an action so the list reads again straight away. */
    refreshSignal?: number;
    /** Reports the number of rollouts that need a person after every read, so the tab badge follows the list. */
    onAttentionCount?: (count: number) => void;
    /** Start rollout was pressed. Without it the button is not rendered. */
    onStartRequested?: () => void;
    renderStartDialog?: () => React.ReactNode;
    renderRingsCard?: () => React.ReactNode;
    renderRingDetail?: (ring: RingView, card: RolloutCard) => React.ReactNode;
    renderActions?: (card: RolloutCard, refresh: () => void) => React.ReactNode;
}

export const RolloutsTab: React.FC<RolloutsTabProps> = () => (
    <section className="space-y-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Rollouts</h2>
        <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <InfoIcon size={12} aria-hidden="true" />
            {ASSURANCE_LINE}
        </p>
    </section>
);

export default RolloutsTab;
