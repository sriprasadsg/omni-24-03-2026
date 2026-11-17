import React, { useMemo, useState } from 'react';
import { Activity, Globe, Cpu, Lock, Unlock, ServerCog, Search, AlertCircle } from 'lucide-react';
import { authFetch } from '../services/apiService';
import { StatTile, bigNumber } from './StatTile';
import { Skeleton } from './ui/skeleton';
import { PageHeader, LiveStatus, Panel, RankedList, SplitBar, EmptyNote, ghostButton, useLiveData } from './network/NetworkKit';
import { collectWebActivity, formatAgentTime, formatShare, isEncrypted, rankBy, type WebActivity, type WebConnection } from './network/networkData';

const PAGE_SIZE = 100;

/** Every agent the caller may see, page by page (one page holds at most 100). */
const fetchWebActivity = async (): Promise<WebActivity> => {
    const agents: any[] = [];
    for (let page = 1; page <= 20; page++) {
        const res = await authFetch(`/api/agents?page=${page}&page_size=${PAGE_SIZE}`);
        if (!res.ok) throw new Error(`Could not load agents (HTTP ${res.status})`);
        const body = await res.json();
        const items = Array.isArray(body) ? body : (body?.items ?? []);
        agents.push(...items);
        if (Array.isArray(body) || !body?.hasNext || items.length === 0) break;
    }
    return collectWebActivity(agents);
};

const ROWS_STEP = 25;

const ProtocolBadge: React.FC<{ port: number }> = ({ port }) => {
    const secure = isEncrypted(port);
    const name = secure ? 'HTTPS' : port === 80 || port === 8080 ? 'HTTP' : `Port ${port}`;
    const suffix = port === 8443 || port === 8080 ? ` :${port}` : '';
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${secure
            ? 'bg-gray-100 text-gray-700 dark:bg-white/[0.06] dark:text-gray-300'
            : 'bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300'}`}>
            {secure ? <Lock className="w-3 h-3" aria-hidden="true" /> : <Unlock className="w-3 h-3" aria-hidden="true" />}
            {name}{suffix}
        </span>
    );
};

export const WebMonitoringDashboard: React.FC = () => {
    const live = useLiveData(fetchWebActivity, 60_000);
    const [query, setQuery] = useState('');
    const [visible, setVisible] = useState(ROWS_STEP);

    const activity = live.data;
    const connections = activity?.connections ?? [];
    const logs = activity?.logs ?? [];

    const destinations = useMemo(() => {
        const ranked = rankBy(connections, c => c.destination, 8);
        return ranked.map(r => {
            const procs = new Set(connections.filter(c => c.destination === r.key).map(c => c.process));
            return { ...r, note: `${procs.size} process${procs.size === 1 ? '' : 'es'}` };
        });
    }, [connections]);
    const processes = useMemo(() => rankBy(connections, c => c.process, 6), [connections]);
    const uniqueDestinations = useMemo(() => new Set(connections.map(c => c.destination)).size, [connections]);
    const uniqueProcesses = useMemo(() => new Set(connections.map(c => `${c.hostname}/${c.process}`)).size, [connections]);
    const encrypted = connections.filter(c => isEncrypted(c.port)).length;
    const plain = connections.length - encrypted;
    const servers = useMemo(() => rankBy(logs, l => l.server, 4), [logs]);

    const rows = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return connections;
        return connections.filter((c: WebConnection) =>
            [c.hostname, c.process, c.destination, String(c.port), String(c.pid ?? '')].some(v => v.toLowerCase().includes(q)));
    }, [connections, query]);

    const header = (
        <PageHeader
            title="Web Monitoring"
            subtitle="Outbound request tracking and web server log analysis"
            status={<LiveStatus updatedAt={live.updatedAt} error={live.error} paused={live.paused} />}
            paused={live.paused}
            onTogglePause={() => live.setPaused(p => !p)}
            onRefresh={live.refresh}
            refreshing={live.loading}
        />
    );

    if (!activity) {
        return (
            <div className="space-y-6 pb-12">
                {header}
                {live.error ? (
                    <div role="alert" className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-5 flex items-start gap-3">
                        <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" aria-hidden="true" />
                        <div className="flex-1">
                            <p className="font-medium text-red-800 dark:text-red-200">Web activity could not be loaded</p>
                            <p className="mt-1 text-sm text-red-700 dark:text-red-300">{live.error}</p>
                        </div>
                        <button type="button" onClick={live.refresh} className={ghostButton}>Try again</button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" aria-busy="true">
                        {[0, 1, 2, 3].map(i => <Skeleton key={i} variant="card" height={118} />)}
                    </div>
                )}
            </div>
        );
    }

    const coverage = `From ${activity.reportingAgents} of ${activity.totalAgents} agent${activity.totalAgents === 1 ? '' : 's'}`;
    const noReporters = activity.reportingAgents === 0;

    return (
        <div className="space-y-6 pb-12">
            {header}

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                <StatTile icon={<Activity className="w-[18px] h-[18px]" />} label="Active connections" tone="primary" footnote={coverage}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{connections.length}</p>
                </StatTile>
                <StatTile icon={<Globe className="w-[18px] h-[18px]" />} label="Destinations" tone="blue" footnote="Distinct remote hosts">
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{uniqueDestinations}</p>
                </StatTile>
                <StatTile icon={<Cpu className="w-[18px] h-[18px]" />} label="Processes" tone="blue" footnote="Making web requests">
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{uniqueProcesses}</p>
                </StatTile>
                <StatTile icon={plain ? <Unlock className="w-[18px] h-[18px]" /> : <Lock className="w-[18px] h-[18px]" />} label="Unencrypted (HTTP)" tone={plain ? 'amber' : 'primary'}
                    footnote={connections.length ? `${formatShare(encrypted, connections.length)} use HTTPS` : 'No connections to check'}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{plain}</p>
                </StatTile>
            </div>

            {noReporters && (
                <div className="rounded-2xl border border-gray-200/80 dark:border-white/[0.07] bg-white dark:bg-gray-800 p-5 flex items-start gap-3">
                    <Globe className="w-5 h-5 text-gray-400 mt-0.5 flex-shrink-0" aria-hidden="true" />
                    <p className="text-sm text-gray-600 dark:text-gray-300">
                        None of your agents reports outbound web connections yet. They come from the agent's Web Monitor capability; agents without it, such as the current Windows agent, show none here.
                    </p>
                </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <Panel className="xl:col-span-2" title="Top destinations" note="Remote hosts with the most open web connections">
                    {destinations.length
                        ? <RankedList items={destinations} mono format={v => `${v} conn.`} />
                        : <EmptyNote icon={<Globe className="w-5 h-5" />} title="No outbound web traffic in the last report" />}
                </Panel>
                <Panel title="Encryption and processes" note="How connections are protected, and who opens them">
                    <SplitBar label="Connection encryption" segments={[
                        { label: 'HTTPS', value: encrypted, display: String(encrypted), swatch: 'bg-primary-500 dark:bg-primary-400', icon: <Lock className="w-3.5 h-3.5 text-gray-400" aria-hidden="true" /> },
                        { label: 'Plain HTTP', value: plain, display: String(plain), swatch: 'bg-amber-500', icon: <Unlock className="w-3.5 h-3.5 text-gray-400" aria-hidden="true" /> },
                    ]} />
                    <h3 className="mt-6 mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Top processes</h3>
                    {processes.length ? <RankedList items={processes} mono format={v => `${v} conn.`} />
                        : <p className="text-sm text-gray-500 dark:text-gray-400">No process has opened a web connection.</p>}
                </Panel>
            </div>

            <Panel title="Web server logs" note="Request lines found in the logs agents collect (Nginx, Apache, IIS)">
                {logs.length ? (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <RankedList items={servers} format={v => `${v} line${v === 1 ? '' : 's'}`} total={logs.length} />
                        <ul className="lg:col-span-2 space-y-2">
                            {logs.slice(0, 6).map((l, i) => (
                                <li key={i} className="rounded-xl bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.05] px-3 py-2">
                                    <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                                        <span className="font-medium text-gray-700 dark:text-gray-200">{l.hostname}</span>· {l.server}{l.time ? ` · ${formatAgentTime(l.time).text}` : ''}
                                    </p>
                                    <p className="mt-1 font-mono text-[12px] text-gray-800 dark:text-gray-200 line-clamp-2 break-all">{l.message}</p>
                                </li>
                            ))}
                        </ul>
                    </div>
                ) : (
                    <EmptyNote icon={<ServerCog className="w-5 h-5" />} title="No web server log lines collected">
                        Lines show up here when an agent's log collection picks up Nginx, Apache or IIS request logs.
                    </EmptyNote>
                )}
            </Panel>

            <Panel
                title="Recent web activity"
                note={`${rows.length} connection${rows.length === 1 ? '' : 's'} in the agents' last reports`}
                actions={
                    <label className="relative block w-full sm:w-64">
                        <span className="sr-only">Filter connections</span>
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" aria-hidden="true" />
                        <input type="search" value={query} onChange={e => { setQuery(e.target.value); setVisible(ROWS_STEP); }} placeholder="Filter by host, process, destination"
                            className="w-full h-9 pl-9 pr-3 rounded-xl text-sm bg-gray-50 dark:bg-white/[0.04] border border-gray-200/80 dark:border-white/[0.08] text-gray-900 dark:text-white placeholder:text-gray-400" />
                    </label>
                }
            >
                <div className="-mx-5 overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="text-[11px] font-semibold uppercase text-gray-500 dark:text-gray-400">
                            <tr className="border-y border-gray-100 dark:border-white/[0.06]">
                                <th scope="col" className="px-4 py-3">Endpoint</th>
                                <th scope="col" className="px-4 py-3">Process</th>
                                <th scope="col" className="px-4 py-3">Destination</th>
                                <th scope="col" className="px-4 py-3">Protocol</th>
                                <th scope="col" className="px-4 py-3">Collected</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                            {rows.slice(0, visible).map((c, idx) => {
                                const when = formatAgentTime(c.timestamp);
                                return (
                                    <tr key={`${c.hostname}-${c.pid}-${c.destination}-${c.port}-${idx}`} className="hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors">
                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{c.hostname}</td>
                                        <td className="px-4 py-3">
                                            <p className="font-mono text-[13px] text-gray-800 dark:text-gray-200">{c.process}</p>
                                            {c.pid !== undefined && <p className="text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">PID {c.pid}</p>}
                                        </td>
                                        <td className="px-4 py-3 font-mono text-[13px] text-gray-700 dark:text-gray-300">{c.destination}</td>
                                        <td className="px-4 py-3"><ProtocolBadge port={c.port} /></td>
                                        <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                                            {when.naive
                                                ? <span title="The agent's own clock; it reported no time zone" className="underline decoration-dotted underline-offset-2 cursor-help">{when.text}</span>
                                                : when.text}
                                        </td>
                                    </tr>
                                );
                            })}
                            {rows.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                                        {connections.length ? 'No connection matches the filter.' : 'No active web connections reported by agents.'}
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
                {rows.length > visible && (
                    <div className="pt-4 flex justify-center">
                        <button type="button" onClick={() => setVisible(v => v + ROWS_STEP * 4)} className={ghostButton}>
                            Show more ({rows.length - visible} left)
                        </button>
                    </div>
                )}
            </Panel>
        </div>
    );
};
