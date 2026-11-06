import React, { useState } from 'react';
import type { HealthRow, HostRow, RingView, SignalName } from '../../services/patchRollouts/types';
import { formatWhen } from '../AutonomousOpsActivityList';
import { SECONDARY_BUTTON } from '../AutonomousOpsHealthCards';
import { RolloutChip } from './RolloutChip';
import { HEALTH_SIGNALS, HEALTH_SIGNAL_NAMES, HEALTH_TITLES, HOST_STATE_CHIP, LINK_LABELS, SIGNAL_CHIP } from './rolloutCopy';

/**
 * The ring detail disclosure (84-18, UI-SPEC section 4): the evidence behind one ring. The health check as four rows
 * (a chip plus the server's text), the failure-rate and soak lines, and every computer of the ring as a table at lg and
 * wider or stacked cards below it. Every sentence is the server's and is rendered as React text; the browser only
 * orders the computers (problems first, then Waiting, then by name) and pages them 25 at a time. A signal that is
 * missing is never a pass: Waiting, No data and Not checked each have their own chip.
 */

export const HOSTS_PER_PAGE = 25;

const MUTED = 'break-words text-xs text-gray-500 dark:text-gray-400';
const RESULT = 'break-words text-sm text-gray-700 dark:text-gray-300';
const NO_COMPUTERS = 'No computers are in this ring.';
const TH = 'px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400';

const noDataText = (signal: SignalName) =>
    `No data for ${HEALTH_SIGNAL_NAMES[signal]} counts as a failure, so the ring halts.`;
const waitingText = (signal: SignalName) => `Waiting for ${HEALTH_SIGNAL_NAMES[signal]}.`;

/** The four rows in the fixed order. A signal the server has not sent yet reads as Waiting, never as a pass. */
function healthRows(rows: HealthRow[]): HealthRow[] {
    return HEALTH_SIGNALS.map(signal => {
        const found = rows.find(r => r.signal === signal);
        if (!found) return { signal, state: 'waiting' as const, text: waitingText(signal) };
        if (found.text) return found;
        if (found.state === 'no_data') return { ...found, text: noDataText(signal) };
        if (found.state === 'waiting') return { ...found, text: waitingText(signal) };
        return found;
    });
}

/** 0 for a computer that needs a person, 1 for one still waiting, 2 for the rest. */
const rank = (h: HostRow) => (h.state === 'failed' || h.state === 'not_reverted' ? 0 : h.state === 'waiting' ? 1 : 2);

export function orderHosts(hosts: HostRow[]): HostRow[] {
    return [...hosts].sort((a, b) => rank(a) - rank(b) || a.hostname.localeCompare(b.hostname));
}

const Changed: React.FC<{ at: string | null }> = ({ at }) => {
    if (!at) return <>—</>;
    const when = formatWhen(at);
    return <time dateTime={at} title={when.title} className="tabular-nums">{when.text}</time>;
};

const HostName: React.FC<{ host: HostRow }> = ({ host }) => (
    <>
        <p className="break-words text-sm font-semibold text-gray-900 dark:text-white">{host.hostname}</p>
        {host.os && <p className={MUTED}>{host.os}</p>}
    </>
);

const HostState: React.FC<{ host: HostRow }> = ({ host }) => (
    <RolloutChip spec={HOST_STATE_CHIP[host.state] ?? { label: 'Unknown', tone: 'neutral', icon: 'InfoIcon' }} />
);

const HostsTable: React.FC<{ hosts: HostRow[]; ringName: string }> = ({ hosts, ringName }) => (
    <div className="hidden overflow-x-auto lg:block">
        <table className="w-full text-left">
            <caption className="sr-only">{`Computers in ${ringName}`}</caption>
            <thead className="border-b border-gray-200 dark:border-white/10">
                <tr>
                    <th scope="col" className={`${TH} min-w-[200px]`}>Computer</th>
                    <th scope="col" className={`${TH} min-w-[150px]`}>State</th>
                    <th scope="col" className={`${TH} min-w-[300px]`}>Result</th>
                    <th scope="col" className={`${TH} min-w-[150px]`}>Changed</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/10">
                {hosts.map(host => (
                    <tr key={host.agentId || host.hostname}>
                        <td className="px-4 py-3 align-top"><HostName host={host} /></td>
                        <td className="px-4 py-3 align-top"><HostState host={host} /></td>
                        <td className="px-4 py-3 align-top"><p className={RESULT}>{host.result}</p></td>
                        <td className="px-4 py-3 align-top text-xs text-gray-500 dark:text-gray-400"><Changed at={host.changedAt} /></td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const HostCards: React.FC<{ hosts: HostRow[] }> = ({ hosts }) => (
    <ul className="space-y-3 lg:hidden">
        {hosts.map(host => (
            <li key={host.agentId || host.hostname} className="rounded-lg border border-gray-200 p-4 dark:border-white/10">
                <dl className="flex flex-col gap-2">
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Computer</dt>
                        <dd><HostName host={host} /></dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">State</dt>
                        <dd><HostState host={host} /></dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Result</dt>
                        <dd className="break-words text-sm text-gray-700 dark:text-gray-300">{host.result}</dd>
                    </div>
                    <div>
                        <dt className="text-xs text-gray-500 dark:text-gray-400">Changed</dt>
                        <dd className="text-xs text-gray-500 dark:text-gray-400"><Changed at={host.changedAt} /></dd>
                    </div>
                </dl>
            </li>
        ))}
    </ul>
);

export const RingDetail: React.FC<{ ring: RingView }> = ({ ring }) => {
    const [shown, setShown] = useState(HOSTS_PER_PAGE);
    const rows = healthRows(ring.health ?? []);
    const hosts = orderHosts(ring.hosts ?? []);
    const visible = hosts.slice(0, shown);
    const total = Math.max(ring.hostTotal ?? 0, hosts.length);

    return (
        <div className="flex flex-col gap-4">
            <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Health check</h4>
                <dl className="flex flex-col gap-3">
                    {rows.map(row => (
                        <div key={row.signal} className="flex flex-wrap items-start gap-x-4 gap-y-1">
                            <dt className="w-full text-sm font-semibold text-gray-900 dark:text-white sm:w-56">{HEALTH_TITLES[row.signal]}</dt>
                            <dd className="flex min-w-0 flex-1 flex-wrap items-start gap-2">
                                <RolloutChip spec={SIGNAL_CHIP[row.state] ?? SIGNAL_CHIP.waiting} />
                                <span className={`${MUTED} min-w-0 flex-1`}>{row.text}</span>
                            </dd>
                        </div>
                    ))}
                </dl>
            </div>
            <p className="break-words text-sm text-gray-700 dark:text-gray-300">{ring.failureRateText}</p>
            <p className="break-words text-sm text-gray-700 dark:text-gray-300">{ring.soakText}</p>
            <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Computers</h4>
                {hosts.length === 0 ? (
                    <p className={MUTED}>{NO_COMPUTERS}</p>
                ) : (
                    <>
                        <HostsTable hosts={visible} ringName={ring.name} />
                        <HostCards hosts={visible} />
                        {total > hosts.length && <p className={MUTED}>{`Showing ${hosts.length} of ${total} computers.`}</p>}
                        {visible.length < hosts.length && (
                            <div>
                                <button type="button" className={SECONDARY_BUTTON} onClick={() => setShown(n => n + HOSTS_PER_PAGE)}>
                                    {LINK_LABELS.showMoreComputers}
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

export default RingDetail;
