import React, { useId, useMemo, useState } from 'react';
import { formatBytes } from '../networkData';
import { formatBitRate, type OpsConnection, type OpsEndpoint, type TrafficSummary } from '../opsData';

export type OpsSelection = { kind: 'endpoint'; agentId: string } | { kind: 'connection'; connection: OpsConnection };

const STATUS_STYLE: Record<OpsEndpoint['status'], string> = {
    Live: 'bg-green-50 text-green-700 dark:bg-green-500/10 dark:text-green-300',
    Idle: 'bg-gray-100 text-gray-700 dark:bg-white/[0.06] dark:text-gray-300',
    Down: 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300',
};

export const StatusBadge: React.FC<{ status: OpsEndpoint['status'] }> = ({ status }) => (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLE[status]}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${status === 'Live' ? 'bg-green-500' : status === 'Down' ? 'bg-red-500' : 'bg-gray-400'}`} aria-hidden="true" />{status}
    </span>
);

export const ProtocolBadge: React.FC<{ protocol: string; port: number | null }> = ({ protocol, port }) => (
    <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-mono font-medium ${protocol === 'HTTP'
        ? 'bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300'
        : 'bg-gray-100 text-gray-700 dark:bg-white/[0.06] dark:text-gray-300'}`}>
        {protocol}{port && port !== 443 && port !== 80 ? `:${port}` : ''}
    </span>
);

const Chips = <T extends string>({ label, options, value, onChange }: { label: string; options: T[]; value: T; onChange: (v: T) => void }) => (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
        {options.map(o => (
            <button key={o} type="button" aria-pressed={value === o} onClick={() => onChange(o)}
                className={`h-7 px-2.5 rounded-lg text-xs font-medium transition-colors ${value === o
                    ? 'bg-primary-500/10 text-primary-700 dark:text-primary-300'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/[0.05]'}`}>{o}</button>
        ))}
    </div>
);

const th = 'px-3 py-2.5 text-left';
const td = 'px-3 py-2';
const mono = 'font-mono tabular-nums text-[12.5px]';

export const OpsTables: React.FC<{ data: TrafficSummary; query: string; rangeLabel: string; onOpen: (s: OpsSelection) => void }> = ({ data, query, rangeLabel, onOpen }) => {
    const [tab, setTab] = useState<'talkers' | 'connections'>('talkers');
    const [status, setStatus] = useState<'All' | OpsEndpoint['status']>('All');
    const [protocol, setProtocol] = useState<'All' | 'HTTPS' | 'HTTP' | 'Internal'>('All');
    const id = useId();
    const q = query.trim().toLowerCase();

    const talkers = useMemo(() => data.endpoints.filter(e =>
        (status === 'All' || e.status === status) &&
        (!q || [e.hostname, e.ip, e.gateway?.ip, e.os].some(v => String(v || '').toLowerCase().includes(q)))), [data.endpoints, status, q]);
    const connections = useMemo(() => data.connections.filter(c =>
        (protocol === 'All' || (protocol === 'Internal' ? c.scope === 'Internal' : c.protocol === protocol && c.scope === 'External')) &&
        (!q || [c.hostname, c.sourceIp, c.destination, c.destinationIp, c.process, String(c.port ?? '')].some(v => String(v || '').toLowerCase().includes(q)))),
    [data.connections, protocol, q]);

    const tabs = [['talkers', `Top talkers (${talkers.length})`], ['connections', `Connections (${connections.length})`]] as const;

    return (
        <section aria-label="Live flow and top talkers" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-3">
                <div role="tablist" aria-label="Table" className="flex gap-1">
                    {tabs.map(([key, label]) => (
                        <button key={key} type="button" role="tab" id={`${id}-${key}`} aria-selected={tab === key} aria-controls={`${id}-panel`}
                            onClick={() => setTab(key)}
                            className={`h-8 px-3 rounded-lg text-sm font-medium transition-colors ${tab === key
                                ? 'bg-gray-100 dark:bg-white/[0.07] text-gray-900 dark:text-white'
                                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}>{label}</button>
                    ))}
                </div>
                {tab === 'talkers'
                    ? <Chips label="Status" options={['All', 'Live', 'Idle', 'Down'] as const as any} value={status} onChange={setStatus as any} />
                    : <Chips label="Protocol" options={['All', 'HTTPS', 'HTTP', 'Internal'] as const as any} value={protocol} onChange={setProtocol as any} />}
            </div>

            <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${tab}`} className="mt-2 overflow-x-auto">
                {tab === 'talkers' ? (
                    <table className="w-full text-sm">
                        <thead className="text-[11px] font-semibold uppercase text-gray-500 dark:text-gray-400">
                            <tr className="border-y border-gray-100 dark:border-white/[0.06]">
                                <th scope="col" className={th}>Endpoint</th><th scope="col" className={th}>Source IP</th><th scope="col" className={th}>Gateway</th>
                                <th scope="col" className={`${th} text-right`}>Inbound</th><th scope="col" className={`${th} text-right`}>Outbound</th>
                                <th scope="col" className={`${th} text-right`}>Moved ({rangeLabel})</th><th scope="col" className={th}>Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                            {talkers.map(e => (
                                <tr key={e.agentId} onClick={() => onOpen({ kind: 'endpoint', agentId: e.agentId })} className="cursor-pointer hover:bg-gray-50/80 dark:hover:bg-white/[0.03]">
                                    <td className={td}>
                                        <button type="button" onClick={ev => { ev.stopPropagation(); onOpen({ kind: 'endpoint', agentId: e.agentId }); }}
                                            className="font-medium text-left text-gray-900 dark:text-white hover:text-primary-700 dark:hover:text-primary-300">{e.hostname}</button>
                                        {e.os && <span className="block text-[11px] text-gray-500 dark:text-gray-400 truncate max-w-[16rem]">{e.os}</span>}
                                    </td>
                                    <td className={`${td} ${mono} text-gray-700 dark:text-gray-300`}>{e.ip || '—'}</td>
                                    <td className={`${td} ${mono} text-gray-700 dark:text-gray-300`}>{e.gateway?.ip || '—'}</td>
                                    <td className={`${td} ${mono} text-right text-gray-800 dark:text-gray-200`}>{formatBitRate(e.rxBps)}</td>
                                    <td className={`${td} ${mono} text-right text-gray-800 dark:text-gray-200`}>{formatBitRate(e.txBps)}</td>
                                    <td className={`${td} ${mono} text-right text-gray-700 dark:text-gray-300`}>{formatBytes(e.rangeRxBytes + e.rangeTxBytes)}</td>
                                    <td className={td}><StatusBadge status={e.status} /></td>
                                </tr>
                            ))}
                            {!talkers.length && <tr><td colSpan={7} className="px-3 py-8 text-center text-gray-500 dark:text-gray-400">{data.endpoints.length ? 'No endpoint matches.' : 'No endpoints yet. They appear when their agents check in.'}</td></tr>}
                        </tbody>
                    </table>
                ) : (
                    <>
                        <table className="w-full text-sm">
                            <thead className="text-[11px] font-semibold uppercase text-gray-500 dark:text-gray-400">
                                <tr className="border-y border-gray-100 dark:border-white/[0.06]">
                                    <th scope="col" className={th}>Source</th><th scope="col" className={th}>Destination</th><th scope="col" className={th}>Protocol</th>
                                    <th scope="col" className={th}>Process</th><th scope="col" className={th}>Scope</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                                {connections.map((c, i) => (
                                    <tr key={`${c.agentId}-${c.pid}-${c.destination}-${c.port}-${i}`} onClick={() => onOpen({ kind: 'connection', connection: c })} className="cursor-pointer hover:bg-gray-50/80 dark:hover:bg-white/[0.03]">
                                        <td className={td}>
                                            <button type="button" onClick={ev => { ev.stopPropagation(); onOpen({ kind: 'connection', connection: c }); }}
                                                className={`${mono} text-left text-gray-900 dark:text-white hover:text-primary-700 dark:hover:text-primary-300`}>{c.sourceIp || c.hostname}</button>
                                            <span className="block text-[11px] text-gray-500 dark:text-gray-400">{c.hostname}</span>
                                        </td>
                                        <td className={`${td} ${mono} text-gray-800 dark:text-gray-200`}>{c.destination}</td>
                                        <td className={td}><ProtocolBadge protocol={c.protocol} port={c.port} /></td>
                                        <td className={`${td} ${mono} text-gray-700 dark:text-gray-300`}>{c.process || '—'}{c.pid != null && <span className="text-gray-500 dark:text-gray-400"> · {c.pid}</span>}</td>
                                        <td className={`${td} text-xs text-gray-600 dark:text-gray-300`}>{c.scope}</td>
                                    </tr>
                                ))}
                                {!connections.length && <tr><td colSpan={5} className="px-3 py-8 text-center text-gray-500 dark:text-gray-400">{data.connections.length ? 'No connection matches.' : 'No open web connections in the latest reports. Only Linux agents report them today.'}</td></tr>}
                            </tbody>
                        </table>
                        <p className="px-4 py-2.5 text-[11px] text-gray-500 dark:text-gray-400 border-t border-gray-100 dark:border-white/[0.06]">
                            From each endpoint's latest report. Bandwidth and latency per connection are not collected yet.
                        </p>
                    </>
                )}
            </div>
        </section>
    );
};
