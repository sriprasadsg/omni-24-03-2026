import React, { useEffect, useId, useState } from 'react';
import type { GoLiveOrganization } from '../../services/autonomousOpsGoLive';
import { EmptyStateCard } from '../AutonomousOpsEmptyStateCard';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthChip, HealthNotice } from '../AutonomousOpsHealthChips';
import { ClockIcon, FlaskConicalIcon, ShieldCheckIcon } from '../icons';
import { LiftShadowDialog, RestoreShadowDialog } from './ShadowDialogs';
import {
    COL_ACTION, COL_DAYS, COL_ORGANIZATION, COL_SHADOW, COL_SIMULATION, CHIP_SHADOW_LIFTED, CHIP_SHADOW_ON, LIFT_BUTTON, MASTER_NOTICE,
    ORG_CAPTION, ORG_EMPTY_BODY, ORG_EMPTY_HEADING, ORG_HEADING, ORG_HELPER, RESTORE_BUTTON, daysLabel, reasonSentence,
} from './goLiveCopy';

const WIDE_QUERY = '(min-width: 1024px)';
const MUTED = 'text-gray-500 dark:text-gray-400';
const HEAD = `px-4 py-2 text-left text-xs font-semibold ${MUTED}`;
const SIM_RULE = 'border-l-2 border-dashed border-gray-400 dark:border-gray-500';
/** The Phase 81 Simulation chip anatomy (dashed outline, FlaskConicalIcon) under this card's own label. */
const SHADOW_CHIP =
    'inline-flex items-center gap-1 rounded-full border border-dashed border-gray-400 bg-transparent px-2 py-1 text-xs font-semibold text-gray-800 dark:border-gray-500 dark:text-gray-100';

/** lg and wider shows the table; below it the cards. With no matchMedia (tests, old engines) the wide layout is used. */
function useWideLayout(): boolean {
    const read = () => (typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(WIDE_QUERY).matches : true);
    const [wide, setWide] = useState(read);
    useEffect(() => {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
        const list = window.matchMedia(WIDE_QUERY);
        const onChange = () => setWide(list.matches);
        list.addEventListener?.('change', onChange);
        return () => list.removeEventListener?.('change', onChange);
    }, []);
    return wide;
}

/**
 * The organization name, the one place it is drawn. Server text, React text only, wraps instead of overflowing. A later
 * label such as "Test organization" belongs next to the name here.
 */
const OrganizationName: React.FC<{ org: GoLiveOrganization }> = ({ org }) => (
    <span className="min-w-0 break-words text-sm font-semibold text-gray-900 dark:text-white">{org.name}</span>
);

const ShadowChip: React.FC<{ org: GoLiveOrganization }> = ({ org }) => (
    org.shadow
        ? <span className={SHADOW_CHIP}><FlaskConicalIcon size={12} aria-hidden="true" />{CHIP_SHADOW_ON}</span>
        : <HealthChip kind="ok" label={CHIP_SHADOW_LIFTED} />
);

interface ActionProps {
    org: GoLiveOrganization;
    /** Prefix that keeps the reason ids unique when the table and the cards could both be drawn. */
    idPrefix: string;
    onLift: (org: GoLiveOrganization) => void;
    onRestore: (org: GoLiveOrganization) => void;
}

/**
 * The Action cell: Lift shadow mode while shadow is on (disabled exactly when the server says canLift is false, with every
 * unmet reason beneath it), or Turn shadow mode back on, which is never gated. The decision comes from the server.
 */
const OrganizationAction: React.FC<ActionProps> = ({ org, idPrefix, onLift, onRestore }) => {
    if (!org.shadow) {
        return <button type="button" className={SECONDARY_BUTTON} onClick={() => onRestore(org)}>{RESTORE_BUTTON}</button>;
    }
    const ids = org.canLift ? [] : org.reasons.map((_, i) => `${idPrefix}-${i}`);
    return (
        <div className="flex flex-col items-start gap-2">
            <button
                type="button" className={SECONDARY_BUTTON} disabled={!org.canLift} onClick={() => onLift(org)}
                aria-describedby={ids.length > 0 ? ids.join(' ') : undefined}
            >
                {LIFT_BUTTON}
            </button>
            {!org.canLift && org.reasons.map((reason, i) => (
                <p key={ids[i]} id={ids[i]} role="status" className="flex items-start gap-1 break-words text-xs text-amber-800 dark:text-amber-200">
                    <ClockIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
                    <span className="min-w-0">{reasonSentence(reason)}</span>
                </p>
            ))}
        </div>
    );
};

const OrganizationTable: React.FC<{ rows: GoLiveOrganization[]; uid: string } & Pick<ActionProps, 'onLift' | 'onRestore'>> = ({ rows, uid, onLift, onRestore }) => (
    <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{ORG_CAPTION}</caption>
        <thead>
            <tr>
                <th scope="col" className={`${HEAD} min-w-[240px]`}>{COL_ORGANIZATION}</th>
                <th scope="col" className={`${HEAD} min-w-[160px]`}>{COL_SHADOW}</th>
                <th scope="col" className={`${HEAD} min-w-[120px] text-right`}>{COL_DAYS}</th>
                <th scope="col" className={`${HEAD} min-w-[144px] text-right ${SIM_RULE}`}>{COL_SIMULATION}</th>
                <th scope="col" className={`${HEAD} min-w-[220px]`}>{COL_ACTION}</th>
            </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-white/10">
            {rows.map(org => (
                <tr key={org.id}>
                    <th scope="row" className="min-w-[240px] px-4 py-2 text-left align-top font-normal"><OrganizationName org={org} /></th>
                    <td className="px-4 py-2 align-top"><ShadowChip org={org} /></td>
                    <td className="px-4 py-2 text-right align-top tabular-nums text-gray-900 dark:text-white">{daysLabel(org.daysObserved)}</td>
                    <td className={`px-4 py-2 text-right align-top tabular-nums ${MUTED} ${SIM_RULE}`}>{org.wouldHaveDone}</td>
                    <td className="px-4 py-2 align-top">
                        <OrganizationAction org={org} idPrefix={`${uid}-t-${org.id}`} onLift={onLift} onRestore={onRestore} />
                    </td>
                </tr>
            ))}
        </tbody>
    </table>
);

const OrganizationCards: React.FC<{ rows: GoLiveOrganization[]; uid: string } & Pick<ActionProps, 'onLift' | 'onRestore'>> = ({ rows, uid, onLift, onRestore }) => (
    <ul aria-label={ORG_CAPTION} className="divide-y divide-gray-200 dark:divide-white/10">
        {rows.map(org => (
            <li key={org.id} className="flex flex-col gap-4 p-4">
                <OrganizationName org={org} />
                <dl className="grid grid-cols-2 gap-2">
                    <div className="min-w-0">
                        <dt className={`text-xs ${MUTED}`}>{COL_SHADOW}</dt>
                        <dd className="mt-1"><ShadowChip org={org} /></dd>
                    </div>
                    <div className="min-w-0">
                        <dt className={`text-xs ${MUTED}`}>{COL_DAYS}</dt>
                        <dd className="mt-1 text-sm tabular-nums text-gray-900 dark:text-white">{daysLabel(org.daysObserved)}</dd>
                    </div>
                    <div className="col-span-2 min-w-0 border-t border-dashed border-gray-400 pt-2 dark:border-gray-500">
                        <dt className={`text-xs ${MUTED}`}>{COL_SIMULATION}</dt>
                        <dd className={`mt-1 text-sm tabular-nums ${MUTED}`}>{org.wouldHaveDone}</dd>
                    </div>
                </dl>
                <OrganizationAction org={org} idPrefix={`${uid}-c-${org.id}`} onLift={onLift} onRestore={onRestore} />
            </li>
        ))}
    </ul>
);

interface GoLiveOrganizationsProps {
    organizations: GoLiveOrganization[];
    /** The deployment-wide shadow switch, reported by the server. */
    masterShadow: boolean;
    /** Called after any write or refused lift; the card refetches. */
    onChanged: () => void | Promise<void>;
}

/**
 * Organizations (86-UI-SPEC section 6c, D-15, D-16): every organization with Autonomous Ops switched on, its shadow state,
 * days observed, the separate simulation count and the action. A real table at lg and wider, stacked cards below. Whether a
 * lift is allowed is read from the server's answer, never recomputed here; the dialog still handles a refusal.
 */
export const GoLiveOrganizations: React.FC<GoLiveOrganizationsProps> = ({ organizations, masterShadow, onChanged }) => {
    const uid = useId();
    const wide = useWideLayout();
    const [lifting, setLifting] = useState<GoLiveOrganization | null>(null);
    const [restoring, setRestoring] = useState<GoLiveOrganization | null>(null);
    const rows = [...organizations].sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
    const done = () => { void onChanged(); };

    return (
        <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{ORG_HEADING}</h3>
            <p className={`break-words text-xs ${MUTED}`}>{ORG_HELPER}</p>
            {masterShadow && (
                <HealthNotice tone="blue"><p>{MASTER_NOTICE}</p></HealthNotice>
            )}
            {rows.length === 0 ? (
                <div className="card overflow-hidden">
                    <EmptyStateCard icon={ShieldCheckIcon} heading={ORG_EMPTY_HEADING}>
                        <p className="max-w-prose break-words text-sm text-gray-600 dark:text-gray-400">{ORG_EMPTY_BODY}</p>
                    </EmptyStateCard>
                </div>
            ) : (
                <div className="min-w-0">
                    {wide
                        ? <OrganizationTable rows={rows} uid={uid} onLift={setLifting} onRestore={setRestoring} />
                        : <OrganizationCards rows={rows} uid={uid} onLift={setLifting} onRestore={setRestoring} />}
                </div>
            )}
            {lifting && <LiftShadowDialog org={lifting} onClose={() => setLifting(null)} onDone={done} />}
            {restoring && <RestoreShadowDialog org={restoring} onClose={() => setRestoring(null)} onDone={done} />}
        </section>
    );
};

export default GoLiveOrganizations;
