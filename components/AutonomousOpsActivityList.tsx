import React, { useEffect, useRef, useState } from 'react';
import {
    AutonomousOpsRow, AutonomousOpsBucket, AutonomousOpsActionsPage,
    fetchAutonomousOpsActions, fetchPlatformAutonomousOpsActions,
} from '../services/autonomousOpsApi';
import {
    CheckCircleIcon, ClockIcon, FlaskConicalIcon, InfoIcon, PauseCircleIcon, PlayCircleIcon,
    RefreshCcwIcon, ShieldLockIcon, XCircleIcon,
} from './icons';

export const PAGE_SIZE = 25;

type ChipKey = 'pending' | 'done' | 'undone' | 'failed' | 'refused' | 'suggested' | 'simulation' | 'stop' | 'resume';

const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold border';
const AMBER = 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:border-amber-400/25';
const NEUTRAL = 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-white/[0.06] dark:text-gray-200 dark:border-white/10';

const CHIPS: Record<ChipKey, { label: string; Icon: React.FC<any>; classes: string }> = {
    pending: { label: 'Pending', Icon: ClockIcon, classes: AMBER },
    done: { label: 'Done', Icon: CheckCircleIcon, classes: 'bg-green-50 text-green-800 border-green-200 dark:bg-green-400/10 dark:text-green-200 dark:border-green-400/25' },
    undone: { label: 'Undone', Icon: RefreshCcwIcon, classes: NEUTRAL },
    failed: { label: 'Failed', Icon: XCircleIcon, classes: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-400/10 dark:text-red-300 dark:border-red-400/25' },
    refused: { label: 'Refused', Icon: ShieldLockIcon, classes: 'bg-transparent text-gray-700 border-gray-300 dark:text-gray-200 dark:border-gray-600' },
    suggested: { label: 'Suggested', Icon: InfoIcon, classes: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-400/10 dark:text-blue-200 dark:border-blue-400/25' },
    simulation: { label: 'Simulation', Icon: FlaskConicalIcon, classes: 'bg-transparent text-gray-800 border-dashed border-gray-400 dark:text-gray-100 dark:border-gray-500' },
    stop: { label: 'Stop', Icon: PauseCircleIcon, classes: AMBER },
    resume: { label: 'Resume', Icon: PlayCircleIcon, classes: NEUTRAL },
};

const STOPPING_EVENTS = new Set(['stop_pressed', 'platform_stop_pressed', 'breaker_tripped']);

function chipKeyFor(row: AutonomousOpsRow): ChipKey {
    if (row.bucket === 'control') return row.controlEvent && STOPPING_EVENTS.has(row.controlEvent) ? 'stop' : 'resume';
    return row.bucket;
}

export const StateChip: React.FC<{ chip: ChipKey }> = ({ chip }) => {
    const { label, Icon, classes } = CHIPS[chip];
    return (
        <span className={`${CHIP_BASE} ${classes}`}>
            <Icon size={12} aria-hidden="true" />
            {label}
        </span>
    );
};

const SIM_PREFIX = 'Nothing was done.';
const SIM_LEAD = 'Nothing was done. This is what would have happened: ';

/** What the Result cell says. A simulation can never read as something that was carried out. */
export function resultFor(row: AutonomousOpsRow): string | null {
    if (row.bucket !== 'simulation') return row.resultText || null;
    if (!row.resultText) return SIM_PREFIX;
    return row.resultText.startsWith(SIM_PREFIX) ? row.resultText : `${SIM_LEAD}${row.resultText}`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

export function formatWhen(iso: string, now: number = Date.now()): { text: string; title: string } {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return { text: '—', title: '' };
    const title = at.toLocaleString();
    const age = now - at.getTime();
    if (age >= 0 && age < DAY_MS) {
        const minutes = Math.floor(age / 60_000);
        if (minutes < 1) return { text: 'Just now', title };
        if (minutes < 60) return { text: `${minutes} min ago`, title };
        return { text: `${Math.floor(minutes / 60)} hr ago`, title };
    }
    const text = at.toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    });
    return { text, title };
}

const Dash = '—';

const WhenLine: React.FC<{ row: AutonomousOpsRow; className?: string }> = ({ row, className = '' }) => {
    const when = formatWhen(row.createdAt);
    return (
        <time dateTime={row.createdAt} title={when.title} className={`text-xs text-gray-500 dark:text-gray-400 tabular-nums ${className}`}>
            {when.text}
        </time>
    );
};

const WhatRan: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => (
    <>
        <div className="text-sm font-semibold text-gray-900 dark:text-white break-words">{row.actionLabel}</div>
        {row.classLine && <div className="text-xs text-gray-500 dark:text-gray-400">{row.classLine}</div>}
    </>
);

const Why: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => (
    <>
        <div className="text-sm text-gray-600 dark:text-gray-400 break-words">{row.reasonText || Dash}</div>
        {row.ruleId && <div className="font-mono text-xs text-gray-500 dark:text-gray-400 break-all">{row.ruleId}</div>}
    </>
);

const Target: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => {
    if (!row.host && !row.target) return <span className="text-sm text-gray-600 dark:text-gray-400">{Dash}</span>;
    return (
        <>
            {row.host && <div className="text-sm font-semibold text-gray-900 dark:text-white break-words">{row.host}</div>}
            {row.target && <div className="font-mono text-xs text-gray-500 dark:text-gray-400 break-all">{row.target}</div>}
        </>
    );
};

const Result: React.FC<{ row: AutonomousOpsRow }> = ({ row }) => (
    <span className="text-sm text-gray-600 dark:text-gray-400 break-words">{resultFor(row) ?? Dash}</span>
);

const SIM_RULE = 'border-l-2 border-dashed border-gray-400 dark:border-gray-500';

const ActivityTable: React.FC<{ rows: AutonomousOpsRow[] }> = ({ rows }) => (
    <div className="hidden xl:block">
        <table className="w-full text-sm">
            <caption className="sr-only">Autonomous Ops activity</caption>
            <thead>
                <tr className="text-left text-xs font-semibold text-gray-500 dark:text-gray-400">
                    <th scope="col" className="w-40 px-4 py-4">State</th>
                    <th scope="col" className="w-56 px-4 py-4">What ran</th>
                    <th scope="col" className="min-w-[240px] px-4 py-4">Why (the rule)</th>
                    <th scope="col" className="w-48 px-4 py-4">Target</th>
                    <th scope="col" className="min-w-[200px] px-4 py-4">Result</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/10">
                {rows.map(row => (
                    <tr key={row.id}>
                        <td className={`px-4 py-4 align-top ${row.bucket === 'simulation' ? SIM_RULE : ''}`}>
                            <div className="flex flex-col items-start gap-2">
                                <StateChip chip={chipKeyFor(row)} />
                                <WhenLine row={row} />
                            </div>
                        </td>
                        <td className="px-4 py-4 align-top"><WhatRan row={row} /></td>
                        <td className="px-4 py-4 align-top"><Why row={row} /></td>
                        <td className="px-4 py-4 align-top"><Target row={row} /></td>
                        <td className="px-4 py-4 align-top"><Result row={row} /></td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const ActivityCards: React.FC<{ rows: AutonomousOpsRow[] }> = ({ rows }) => (
    <ul className="xl:hidden divide-y divide-gray-200 dark:divide-white/10">
        {rows.map(row => (
            <li key={row.id} className={`p-4 flex flex-col gap-2 ${row.bucket === 'simulation' ? SIM_RULE : ''}`}>
                <div className="flex items-center justify-between gap-2">
                    <StateChip chip={chipKeyFor(row)} />
                    <WhenLine row={row} />
                </div>
                <div><WhatRan row={row} /></div>
                <dl className="flex flex-col gap-2">
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Why</dt>
                        <dd><Why row={row} /></dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Target</dt>
                        <dd><Target row={row} /></dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Result</dt>
                        <dd><Result row={row} /></dd>
                    </div>
                </dl>
            </li>
        ))}
    </ul>
);

export interface ActivityListProps {
    /** `platform` reads the platform-scope list; `tenant` reads tenantId (platform staff) or the viewer's own tenant. */
    scope: { kind: 'tenant'; tenantId: string | null } | { kind: 'platform' };
    refreshSignal?: number;
}

export const AutonomousOpsActivityList: React.FC<ActivityListProps> = ({ scope, refreshSignal = 0 }) => {
    const bucket: AutonomousOpsBucket = 'all';
    const [rows, setRows] = useState<AutonomousOpsRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [failed, setFailed] = useState(false);
    const generation = useRef(0);
    const tenantId = scope.kind === 'tenant' ? scope.tenantId : null;
    const platform = scope.kind === 'platform';

    useEffect(() => {
        const mine = ++generation.current;
        setLoading(true);
        setFailed(false);
        const request: Promise<AutonomousOpsActionsPage> = platform
            ? fetchPlatformAutonomousOpsActions({ bucket, limit: PAGE_SIZE })
            : fetchAutonomousOpsActions({ bucket, limit: PAGE_SIZE, tenantId });
        request
            .then(page => { if (mine === generation.current) { setRows(page.items); setLoading(false); } })
            .catch(() => { if (mine === generation.current) { setFailed(true); setLoading(false); } });
    }, [platform, tenantId, bucket, refreshSignal]);

    return (
        <div className="card overflow-hidden" aria-busy={loading}>
            {loading ? (
                <div className="flex flex-col gap-2 p-4">
                    {Array.from({ length: 5 }, (_, i) => (
                        <div key={i} data-skeleton="row" className="h-24 xl:h-14 animate-pulse rounded-lg bg-gray-100 dark:bg-white/[0.06]" />
                    ))}
                </div>
            ) : failed ? (
                <div role="alert" className="p-4 text-sm text-red-700 dark:text-red-300">
                    Couldn't load activity. Check your connection and try again.
                </div>
            ) : (
                <>
                    <ActivityTable rows={rows} />
                    <ActivityCards rows={rows} />
                </>
            )}
        </div>
    );
};
