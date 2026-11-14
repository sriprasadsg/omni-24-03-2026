import React, { useEffect, useId, useState } from 'react';
import type { GoLiveOrganization, GoLiveTestOrganization } from '../../services/autonomousOpsGoLive';
import { EmptyStateCard } from '../AutonomousOpsEmptyStateCard';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { HealthChip, HealthNotice } from '../AutonomousOpsHealthChips';
import { ClockIcon, FlaskConicalIcon, ShieldCheckIcon } from '../icons';
import { LiftShadowDialog, RestoreShadowDialog } from './ShadowDialogs';
import { ClearTestOrgDialog, MarkTestOrgDialog } from './TestOrgDialogs';
import {
    COL_ACTION, COL_DAYS, COL_ORGANIZATION, COL_SHADOW, COL_SIMULATION, CHIP_SHADOW_LIFTED, CHIP_SHADOW_ON, LIFT_BUTTON, MASTER_NOTICE,
    ORG_CAPTION, ORG_EMPTY_BODY, ORG_EMPTY_HEADING, ORG_HEADING, ORG_HELPER, RESTORE_BUTTON, TEST_ORG_CLEAR, TEST_ORG_CLEAR_REASON,
    TEST_ORG_LABEL, TEST_ORG_USE, daysLabel, reasonSentence,
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
 * The organization name, the one place it is drawn. Server text, React text only, wraps instead of overflowing. The
 * "Test organization" label (D-23) sits beside it as text, never colour alone.
 */
const OrganizationName: React.FC<{ org: GoLiveOrganization; isTest: boolean }> = ({ org, isTest }) => (
    <span className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="min-w-0 break-words text-sm font-semibold text-gray-900 dark:text-white">{org.name}</span>
        {isTest && <HealthChip kind="notice" label={TEST_ORG_LABEL} />}
    </span>
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
    /** This row is the marked go-live test organization (the server's flag). */
    isTest: boolean;
    /** Some organization is marked, so no other row offers marking. */
    anyMarked: boolean;
    onLift: (org: GoLiveOrganization) => void;
    onRestore: (org: GoLiveOrganization) => void;
    onMark: (org: GoLiveOrganization) => void;
    onClear: (org: GoLiveOrganization) => void;
}
type RowHandlers = Pick<ActionProps, 'onLift' | 'onRestore' | 'onMark' | 'onClear'>;
type RowMarks = { testId: string | null; anyMarked: boolean };

/**
 * The Action cell: Lift shadow mode while shadow is on (disabled exactly when the server says canLift is false, with every
 * unmet reason beneath it), or Turn shadow mode back on, which is never gated. The decision comes from the server.
 */
const ShadowAction: React.FC<Pick<ActionProps, 'org' | 'idPrefix' | 'onLift' | 'onRestore'>> = ({ org, idPrefix, onLift, onRestore }) => {
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

/**
 * The go-live test organization controls (D-23): Use as test organization while nothing is marked, and on the marked row
 * Clear test mark, disabled with its reason while the organization's own shadow mode is off. Which row is marked and
 * whether the mark can be cleared is the server's; a refusal is shown by the dialog.
 */
const TestOrgAction: React.FC<ActionProps> = ({ org, idPrefix, isTest, anyMarked, onMark, onClear }) => {
    if (isTest) {
        const reasonId = `${idPrefix}-clear-reason`;
        return (
            <div className="flex flex-col items-start gap-2">
                <button
                    type="button" className={SECONDARY_BUTTON} disabled={!org.shadow} onClick={() => onClear(org)}
                    aria-describedby={org.shadow ? undefined : reasonId}
                >
                    {TEST_ORG_CLEAR}
                </button>
                {!org.shadow && (
                    <p id={reasonId} role="status" className="flex items-start gap-1 break-words text-xs text-amber-800 dark:text-amber-200">
                        <ClockIcon size={12} aria-hidden="true" className="mt-0.5 shrink-0" />
                        <span className="min-w-0">{TEST_ORG_CLEAR_REASON}</span>
                    </p>
                )}
            </div>
        );
    }
    if (anyMarked) return null;
    return <button type="button" className={SECONDARY_BUTTON} onClick={() => onMark(org)}>{TEST_ORG_USE}</button>;
};

const OrganizationAction: React.FC<ActionProps> = props => (
    <div className="flex flex-col items-start gap-3">
        <ShadowAction org={props.org} idPrefix={props.idPrefix} onLift={props.onLift} onRestore={props.onRestore} />
        <TestOrgAction {...props} />
    </div>
);

/** A row is the test organization when the server flags it or names it at the top level. */
const isTestRow = (org: GoLiveOrganization, testId: string | null): boolean => org.testOrganization === true || org.id === testId;

const OrganizationTable: React.FC<{ rows: GoLiveOrganization[]; uid: string } & RowHandlers & RowMarks> = ({ rows, uid, testId, anyMarked, ...handlers }) => (
    <div role="region" aria-label={ORG_CAPTION} tabIndex={0} className="min-w-0 overflow-x-auto">
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
                        <th scope="row" className="min-w-[240px] px-4 py-2 text-left align-top font-normal"><OrganizationName org={org} isTest={isTestRow(org, testId)} /></th>
                        <td className="px-4 py-2 align-top"><ShadowChip org={org} /></td>
                        <td className="px-4 py-2 text-right align-top tabular-nums text-gray-900 dark:text-white">{daysLabel(org.daysObserved)}</td>
                        <td className={`px-4 py-2 text-right align-top tabular-nums ${MUTED} ${SIM_RULE}`}>{org.wouldHaveDone}</td>
                        <td className="px-4 py-2 align-top">
                            <OrganizationAction org={org} idPrefix={`${uid}-t-${org.id}`} isTest={isTestRow(org, testId)} anyMarked={anyMarked} {...handlers} />
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const OrganizationCards: React.FC<{ rows: GoLiveOrganization[]; uid: string } & RowHandlers & RowMarks> = ({ rows, uid, testId, anyMarked, ...handlers }) => (
    <ul aria-label={ORG_CAPTION} className="divide-y divide-gray-200 dark:divide-white/10">
        {rows.map(org => (
            <li key={org.id} className="flex flex-col gap-4 p-4">
                <OrganizationName org={org} isTest={isTestRow(org, testId)} />
                <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <div className="min-w-0">
                        <dt className={`text-xs ${MUTED}`}>{COL_SHADOW}</dt>
                        <dd className="mt-1"><ShadowChip org={org} /></dd>
                    </div>
                    <div className="min-w-0">
                        <dt className={`text-xs ${MUTED}`}>{COL_DAYS}</dt>
                        <dd className="mt-1 text-sm tabular-nums text-gray-900 dark:text-white">{daysLabel(org.daysObserved)}</dd>
                    </div>
                    <div className="col-span-full min-w-0 border-t border-dashed border-gray-400 pt-2 dark:border-gray-500">
                        <dt className={`text-xs ${MUTED}`}>{COL_SIMULATION}</dt>
                        <dd className={`mt-1 text-sm tabular-nums ${MUTED}`}>{org.wouldHaveDone}</dd>
                    </div>
                </dl>
                <OrganizationAction org={org} idPrefix={`${uid}-c-${org.id}`} isTest={isTestRow(org, testId)} anyMarked={anyMarked} {...handlers} />
            </li>
        ))}
    </ul>
);

interface GoLiveOrganizationsProps {
    organizations: GoLiveOrganization[];
    /** The deployment-wide shadow switch, reported by the server. */
    masterShadow: boolean;
    /** The marked go-live test organization as the server reports it (D-23), or null. */
    testOrganization?: GoLiveTestOrganization | null;
    /** Called after any write or refused lift; the card refetches. */
    onChanged: () => void | Promise<void>;
}

/**
 * Organizations (86-UI-SPEC section 6c, D-15, D-16): every organization with Autonomous Ops switched on, its shadow state,
 * days observed, the separate simulation count and the action. A real table at lg and wider, stacked cards below; when the card is narrower than the table (about 884 px) the
 * table scrolls sideways inside the card (G-86-5). Whether a
 * lift is allowed is read from the server's answer, never recomputed here; the dialog still handles a refusal.
 */
export const GoLiveOrganizations: React.FC<GoLiveOrganizationsProps> = ({ organizations, masterShadow, testOrganization, onChanged }) => {
    const uid = useId();
    const wide = useWideLayout();
    const [lifting, setLifting] = useState<GoLiveOrganization | null>(null);
    const [restoring, setRestoring] = useState<GoLiveOrganization | null>(null);
    const [marking, setMarking] = useState<GoLiveOrganization | null>(null);
    const [clearing, setClearing] = useState<GoLiveOrganization | null>(null);
    const rows = [...organizations].sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
    const done = () => { void onChanged(); };
    const testId = testOrganization?.id ?? null;
    const anyMarked = testId !== null || rows.some(r => r.testOrganization === true);
    const rowProps = { rows, uid, testId, anyMarked, onLift: setLifting, onRestore: setRestoring, onMark: setMarking, onClear: setClearing };

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
                    {wide ? <OrganizationTable {...rowProps} /> : <OrganizationCards {...rowProps} />}
                </div>
            )}
            {lifting && <LiftShadowDialog org={lifting} onClose={() => setLifting(null)} onDone={done} />}
            {restoring && <RestoreShadowDialog org={restoring} onClose={() => setRestoring(null)} onDone={done} />}
            {marking && <MarkTestOrgDialog org={marking} onClose={() => setMarking(null)} onDone={done} />}
            {clearing && <ClearTestOrgDialog org={clearing} onClose={() => setClearing(null)} onDone={done} />}
        </section>
    );
};

export default GoLiveOrganizations;
