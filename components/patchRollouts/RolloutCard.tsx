import React, { useId, useState } from 'react';
import type { AppView } from '../../types';
import type { ChipSpec } from './rolloutCopy';
import type { RingView, RolloutCard as RolloutCardData } from '../../services/patchRollouts/types';
import { formatWhen } from '../AutonomousOpsActivityList';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { AlertOctagonIcon, ChevronRightIcon, ExternalLinkIcon, LayersIcon } from '../icons';
import { RolloutChip } from './RolloutChip';
import { HaltActions, RunningCancel, hasHaltActions } from './RolloutDialogs';
import { LINK_LABELS, RING_STATE_CHIP, ROLLOUT_STATUS_CHIP, SIMULATION_CHIP, plural } from './rolloutCopy';

/**
 * One rollout card (84-14, UI-SPEC section 4): a header with the name, the meta line and the status chips; the ring
 * strip, one block per ring with its chip and the server's detail line; the halt block; and the completed lines. Every
 * sentence is the server's (detail lines, halt reason, revert summary, closed text) and is rendered as React text. The
 * only controls are the ones the server's flags earned: Review in Needs your decision (the ring says the viewer can
 * open it and the parent gave a handler), Show details (only when a ring detail renderer is given) and the actions the
 * parent supplies for a halted rollout; with `onChanged` the halt block offers Resume rollout and Cancel rollout itself
 * (84-18), each behind its own dialog, from the server's canResume and canCancel flags.
 */

const HALT_SECOND_LINE = 'A rollout halts on failure; reverts where supported. Rings that already passed keep the patches. Nothing further installs.';
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';
const NOT_REACHED_CHIP: ChipSpec = { label: 'not reached', tone: 'outline', icon: 'ClockIcon' };
const UNKNOWN_RING_CHIP: ChipSpec = { label: 'Unknown', tone: 'neutral', icon: 'InfoIcon' };

export interface RolloutCardProps {
    card: RolloutCardData;
    /** Where Review in Needs your decision navigates; without it the link is never rendered. */
    onOpenView?: (view: AppView) => void;
    /** The ring detail disclosure content (84-18). Without it no Show details control is rendered. */
    renderRingDetail?: (ring: RingView, card: RolloutCardData) => React.ReactNode;
    /** Rendered in the halt block instead of the built-in Resume rollout and Cancel rollout. */
    actions?: React.ReactNode;
    /** Reads the card again after Resume or Cancel succeeds. Without it (and without `actions`) the halt block has no buttons. */
    onChanged?: () => void;
    /** The organization platform staff entered from Tenants, sent with Resume and Cancel; a tenant role passes null. */
    tenantId?: string | null;
    /** The clock the "Started" text reads against; tests pass a fixed one. */
    now?: number;
}

const RingBlock: React.FC<{
    ring: RingView;
    current: boolean;
    detailId: string;
    open: boolean;
    onOpenView?: (view: AppView) => void;
    onToggle?: () => void;
}> = ({ ring, current, detailId, open, onOpenView, onToggle }) => {
    const chip = RING_STATE_CHIP[ring.state] ?? UNKNOWN_RING_CHIP;
    const waiting = ring.state === 'waiting_for_approval';
    return (
        <li
            aria-current={current ? 'step' : undefined}
            className="flex min-w-[200px] flex-1 flex-col gap-2 rounded-lg border border-gray-200 p-4 dark:border-white/10"
        >
            <p className="break-words text-sm font-semibold text-gray-900 dark:text-white">{ring.name}</p>
            <div><RolloutChip spec={chip} /></div>
            <p className={MUTED}>{ring.detail}</p>
            {waiting && ring.decisionsLink && onOpenView && (
                <div>
                    <button type="button" className={TEXT_BUTTON} onClick={() => onOpenView('autonomousOps')}>
                        {LINK_LABELS.reviewDecisions}
                        <ExternalLinkIcon size={12} aria-hidden="true" />
                    </button>
                </div>
            )}
            {waiting && !ring.decisionsLink && ring.waitingText && <p className={MUTED}>{ring.waitingText}</p>}
            {ring.groups.length > 0 && (
                <div className="flex flex-wrap gap-x-2 gap-y-1">
                    {ring.groups.map(group => (
                        <span key={group} className="break-all font-mono text-xs text-gray-500 dark:text-gray-400">{group}</span>
                    ))}
                </div>
            )}
            {onToggle && (
                <div>
                    <button type="button" className={TEXT_BUTTON} aria-expanded={open} aria-controls={open ? detailId : undefined} onClick={onToggle}>
                        <ChevronRightIcon size={12} aria-hidden="true" className={open ? 'rotate-90' : ''} />
                        {open ? LINK_LABELS.hideDetails : LINK_LABELS.showDetails}
                        <span className="sr-only"> for {ring.name}</span>
                    </button>
                </div>
            )}
        </li>
    );
};

export const RolloutCard: React.FC<RolloutCardProps> = ({ card, onOpenView, renderRingDetail, actions, onChanged, tenantId = null, now }) => {
    const ids = useId();
    const titleId = `rollout-${card.id}-title`;
    const detailId = `${ids}-ring-detail`;
    const [openRing, setOpenRing] = useState<number | null>(null);
    const started = card.startedAt ? formatWhen(card.startedAt, now) : null;
    const open = openRing === null ? undefined : card.rings.find(r => r.index === openRing);
    const status = ROLLOUT_STATUS_CHIP[card.status] ?? UNKNOWN_RING_CHIP;
    const notReached = card.status === 'completed' && card.notReachedCount > 0;
    const haltActions = actions ?? (onChanged && hasHaltActions(card)
        ? <HaltActions card={card} tenantId={tenantId} onChanged={onChanged} />
        : null);

    return (
        <article id={`rollout-${card.id}`} tabIndex={-1} aria-labelledby={titleId} className="card overflow-hidden focus:outline-none">
            <header className="flex flex-wrap items-start justify-between gap-4 border-b border-gray-200 px-6 py-4 dark:border-white/10">
                <div className="flex min-w-0 items-start gap-2">
                    <LayersIcon size={20} aria-hidden="true" className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />
                    <div className="flex min-w-0 flex-col gap-1">
                        <h3 id={titleId} className="break-words text-sm font-semibold text-gray-900 dark:text-white">{card.name}</h3>
                        <p className={MUTED}>
                            {`${plural(card.patchCount, 'patch', 'patches')} · ${plural(card.computerCount, 'computer', 'computers')}`}
                            {started && <> · Started <time dateTime={card.startedAt ?? undefined} title={started.title}>{started.text === 'Just now' ? 'just now' : started.text}</time></>}
                            {started && card.startedBy ? ` by ${card.startedBy}` : ''}
                        </p>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <RolloutChip spec={status} />
                    {card.simulation && <RolloutChip spec={SIMULATION_CHIP} />}
                    {notReached && <RolloutChip spec={NOT_REACHED_CHIP} label={`${card.notReachedCount} not reached`} />}
                </div>
            </header>
            <ol aria-label="Rings" className="flex flex-wrap gap-4 px-6 py-4">
                {card.rings.map(ring => (
                    <RingBlock
                        key={ring.index}
                        ring={ring}
                        current={card.currentRing === ring.index}
                        detailId={detailId}
                        open={openRing === ring.index}
                        onOpenView={onOpenView}
                        onToggle={renderRingDetail ? () => setOpenRing(prev => (prev === ring.index ? null : ring.index)) : undefined}
                    />
                ))}
            </ol>
            {card.halt && (
                <div className="px-6 pb-4">
                    <HealthNotice tone="red" icon={AlertOctagonIcon} role="alert">
                        <p className="break-words font-semibold">{`Halted at ${card.halt.ringName}: ${card.halt.reason}`}</p>
                        <p className="break-words text-xs">{HALT_SECOND_LINE}</p>
                        {card.halt.reverts.length > 0 && (
                            <ul className="list-disc space-y-1 pl-4">
                                {card.halt.reverts.map((line, i) => <li key={i} className="break-words">{line}</li>)}
                            </ul>
                        )}
                        {haltActions && <div className="flex flex-wrap items-start gap-2">{haltActions}</div>}
                    </HealthNotice>
                </div>
            )}
            {!card.halt && card.status === 'running' && card.canCancel && onChanged && (
                <div className="flex px-6 pb-4"><RunningCancel card={card} tenantId={tenantId} onChanged={onChanged} /></div>
            )}
            {open && renderRingDetail && <div id={detailId} className="px-6 pb-4">{renderRingDetail(open, card)}</div>}
            {card.closedText && (
                <p className="break-words px-6 pb-4 text-sm text-gray-600 dark:text-gray-400">{card.closedText}</p>
            )}
        </article>
    );
};

export default RolloutCard;
