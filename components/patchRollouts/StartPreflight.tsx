import React, { useState } from 'react';
import type { Preflight, PreflightLink, PreflightRow } from '../../services/patchRollouts/types';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { AlertTriangleIcon, CheckCircleIcon, InfoIcon } from '../icons';
import { ASSURANCE_LINE, LINK_LABELS } from './rolloutCopy';

/**
 * The Check before starting section and the What will happen block of the Start dialog (84-17, UI-SPEC section 3).
 * Every row is the server's preflight: the browser adds no check of its own. A blocker row (amber) stops Start; a
 * Left out or Offline now row is information. Left out lists 3 lines then "and {k} more"; Show hosts lists the
 * names the server sent (at most 10) and says how many there are in all.
 */

export const LEFT_OUT_SHOWN = 3;
const CHECK_ERROR = "Couldn't check this rollout. Check your connection and try again.";
const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const TEXT_BUTTON = 'inline-flex items-center gap-1 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2';

export interface PreflightLinks {
    onOpenMaintenance?: () => void;
    onOpenRings?: () => void;
    onOpenAgentGroups?: () => void;
}

const LINKS: Record<PreflightLink, { label: string; handler: keyof PreflightLinks }> = {
    maintenance: { label: LINK_LABELS.maintenance, handler: 'onOpenMaintenance' },
    rings: { label: LINK_LABELS.rings, handler: 'onOpenRings' },
    agentGroups: { label: LINK_LABELS.agentGroups, handler: 'onOpenAgentGroups' },
};

/** The id of a row's detail text, which Start's aria-describedby points at when that row is the first blocker. */
export const detailId = (base: string, index: number) => `${base}-detail-${index}`;

const RowLink: React.FC<{ link: PreflightLink; links: PreflightLinks }> = ({ link, links }) => {
    const spec = LINKS[link];
    const handler = links[spec.handler];
    return handler
        ? <button type="button" className={TEXT_BUTTON} onClick={handler}>{spec.label}</button>
        : <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">{spec.label}</span>;
};

const RowIcon: React.FC<{ row: PreflightRow }> = ({ row }) => {
    if (row.blocker) return <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />;
    if (row.check === 'left_out' || row.check === 'offline') {
        return <InfoIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />;
    }
    return <CheckCircleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-green-600 dark:text-green-400" />;
};

const Row: React.FC<{ row: PreflightRow; id: string; links: PreflightLinks }> = ({ row, id, links }) => {
    const [showing, setShowing] = useState(false);
    const hosts = Array.isArray(row.hosts) ? row.hosts : [];
    return (
        <li className="flex items-start gap-2">
            <RowIcon row={row} />
            <div className="min-w-0 flex-1 space-y-1">
                <p className="break-words text-sm font-semibold text-gray-900 dark:text-white">{row.title}</p>
                <p id={id} className={MUTED}>{row.detail}</p>
                {row.link && <div><RowLink link={row.link} links={links} /></div>}
                {hosts.length > 0 && (
                    <div className="space-y-1">
                        <button type="button" className={TEXT_BUTTON} aria-expanded={showing} onClick={() => setShowing(v => !v)}>
                            {LINK_LABELS.showHosts}
                        </button>
                        {showing && (
                            <>
                                <ul className="flex flex-wrap gap-x-4 gap-y-1">
                                    {hosts.map(name => <li key={name} className="break-all font-mono text-xs text-gray-700 dark:text-gray-200">{name}</li>)}
                                </ul>
                                {row.hostTotal > hosts.length && <p className={MUTED}>{`Showing ${hosts.length} of ${row.hostTotal}.`}</p>}
                            </>
                        )}
                    </div>
                )}
            </div>
        </li>
    );
};

interface Props {
    preflight: Preflight | null;
    checking: boolean;
    failed: boolean;
    onRetry: () => void;
    links: PreflightLinks;
    /** Prefix for the ids of the rows' detail text and of the Checking... line. */
    idBase: string;
}

export const checkingId = (base: string) => `${base}-checking`;

export const StartPreflight: React.FC<Props> = ({ preflight, checking, failed, onRetry, links, idBase }) => {
    const rows = preflight?.rows ?? [];
    const leftOut = rows.map((r, i) => ({ r, i })).filter(x => x.r.check === 'left_out');
    const hidden = new Set(leftOut.slice(LEFT_OUT_SHOWN).map(x => x.i));
    const more = hidden.size;
    const lastShownLeftOut = leftOut.length > LEFT_OUT_SHOWN ? leftOut[LEFT_OUT_SHOWN - 1].i : -1;
    return (
        <section role="status" aria-live="polite" aria-label="Check before starting" className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Check before starting</h3>
            {checking && <p id={checkingId(idBase)} className={MUTED}>Checking...</p>}
            {failed && (
                <div className="space-y-2">
                    <p role="alert" className="break-words text-sm text-red-600 dark:text-red-400">{CHECK_ERROR}</p>
                    <button type="button" className={TEXT_BUTTON} onClick={onRetry}>{LINK_LABELS.tryAgain}</button>
                </div>
            )}
            {rows.length > 0 && (
                <ul className="space-y-4">
                    {rows.map((row, i) => (hidden.has(i) ? null : (
                        <React.Fragment key={`${row.check}-${i}`}>
                            <Row row={row} id={detailId(idBase, i)} links={links} />
                            {i === lastShownLeftOut && <li className={`${MUTED} pl-6`}>{`and ${more} more`}</li>}
                        </React.Fragment>
                    )))}
                </ul>
            )}
        </section>
    );
};

const HAPPENS = [
    'Installs and restarts run only inside your maintenance window.',
    'Only the canary ring installs on its own, and only patches that can be reversed on that computer. That is checked just before each install.',
    'Every other install and every restart waits for your approval, one ring at a time.',
    ASSURANCE_LINE,
];

/** What will happen: four lines and the platform note. It closes the form. */
export const WhatWillHappen: React.FC = () => (
    <div className="space-y-2">
        <HealthNotice tone="blue" icon={InfoIcon}>
            <ul className="list-disc space-y-1 pl-4 font-normal">
                {HAPPENS.map(line => <li key={line}>{line}</li>)}
            </ul>
        </HealthNotice>
        <p className={MUTED}>The platform's own server is never patched by a rollout.</p>
    </div>
);
