import React, { useMemo, useState } from 'react';
import { authFetch } from '../services/apiService';
import { Network, Server, ArrowUpRight, ArrowDownLeft, AlertCircle, Search, ChevronUp, ChevronDown, BarChart3 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts';
import { StatTile, bigNumber } from './StatTile';
import { Skeleton } from './ui/skeleton';
import { PageHeader, LiveStatus, Panel, RankedList, SplitBar, EmptyNote, SERIES, ghostButton, useChartTheme, useLiveData } from './network/NetworkKit';
import { formatBytes, formatShare, type RankedItem } from './network/networkData';

interface AgentUtilization {
    id: string;
    hostname: string;
    ipAddress: string;
    os: string;
    bytesSent: number;
    bytesRecv: number;
}

interface UtilizationData {
    totalBytesSent: number;
    totalBytesRecv: number;
    agents: AgentUtilization[];
}

const fetchUtilization = async (): Promise<UtilizationData> => {
    const res = await authFetch('/api/agents/network-utilization');
    if (!res.ok) throw new Error(`Could not load utilization (HTTP ${res.status})`);
    const body = await res.json();
    return {
        totalBytesSent: Number(body?.totalBytesSent) || 0,
        totalBytesRecv: Number(body?.totalBytesRecv) || 0,
        agents: Array.isArray(body?.agents) ? body.agents : [],
    };
};

type SortKey = 'hostname' | 'bytesSent' | 'bytesRecv' | 'total';
const totalOf = (a: AgentUtilization) => (a.bytesSent || 0) + (a.bytesRecv || 0);

const ChartTooltip: React.FC<any> = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-xl border border-gray-200/80 dark:border-white/10 bg-white dark:bg-gray-800 shadow-lg px-3 py-2 text-[13px] min-w-[180px]">
            <p className="font-medium text-gray-900 dark:text-white truncate">{label}</p>
            {payload.map((p: any) => (
                <p key={p.dataKey} className="mt-1 flex items-center gap-2 text-gray-600 dark:text-gray-300">
                    <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} aria-hidden="true" />
                    {p.name}
                    <span className="ml-auto pl-4 tabular-nums">{formatBytes(p.value)}</span>
                </p>
            ))}
            <p className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-white/10 flex text-gray-900 dark:text-white">
                Total<span className="ml-auto pl-4 tabular-nums">{formatBytes(payload[0].payload.total)}</span>
            </p>
        </div>
    );
};

export const DataUtilizationDashboard: React.FC = () => {
    const live = useLiveData(fetchUtilization, 60_000);
    const chart = useChartTheme();
    const [query, setQuery] = useState('');
    const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'total', dir: 'desc' });

    const agents = live.data?.agents ?? [];
    const sent = live.data?.totalBytesSent ?? 0;
    const recv = live.data?.totalBytesRecv ?? 0;
    const total = sent + recv;
    const reporting = agents.filter(a => totalOf(a) > 0).length;

    const top = useMemo(() => [...agents].sort((a, b) => totalOf(b) - totalOf(a)).slice(0, 10).map(a => ({
        name: a.hostname, sent: a.bytesSent || 0, received: a.bytesRecv || 0, total: totalOf(a),
    })), [agents]);

    const shares = useMemo<RankedItem[]>(() => {
        const ranked = [...agents].sort((a, b) => totalOf(b) - totalOf(a));
        const items: RankedItem[] = ranked.slice(0, 6).map(a => ({ key: a.id || a.hostname, label: a.hostname, value: totalOf(a) }));
        const rest = ranked.slice(6);
        if (rest.length) items.push({ key: '__others', label: `Other endpoints (${rest.length})`, value: rest.reduce((s, a) => s + totalOf(a), 0) });
        return items.filter(i => i.value > 0);
    }, [agents]);

    const rows = useMemo(() => {
        const q = query.trim().toLowerCase();
        const filtered = q ? agents.filter(a => [a.hostname, a.ipAddress, a.os, a.id].some(v => String(v || '').toLowerCase().includes(q))) : agents;
        const value = (a: AgentUtilization) => sort.key === 'total' ? totalOf(a) : sort.key === 'hostname' ? a.hostname : a[sort.key];
        return [...filtered].sort((a, b) => {
            const va = value(a), vb = value(b);
            const cmp = typeof va === 'string' ? va.localeCompare(String(vb)) : (va as number) - (vb as number);
            return sort.dir === 'asc' ? cmp : -cmp;
        });
    }, [agents, query, sort]);

    const toggleSort = (key: SortKey) => setSort(s => s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'hostname' ? 'asc' : 'desc' });

    const header = (
        <PageHeader
            title="Data Utilization"
            subtitle="Bandwidth each agent endpoint has sent and received"
            status={<LiveStatus updatedAt={live.updatedAt} error={live.error} paused={live.paused} />}
            paused={live.paused}
            onTogglePause={() => live.setPaused(p => !p)}
            onRefresh={live.refresh}
            refreshing={live.loading}
        />
    );

    if (!live.data) {
        return (
            <div className="space-y-6 pb-12">
                {header}
                {live.error ? (
                    <div role="alert" className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-5 flex items-start gap-3">
                        <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" aria-hidden="true" />
                        <div className="flex-1">
                            <p className="font-medium text-red-800 dark:text-red-200">Utilization data could not be loaded</p>
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

    const sentColor = chart.dark ? SERIES.sent.dark : SERIES.sent.light;
    const recvColor = chart.dark ? SERIES.received.dark : SERIES.received.light;
    const sortIcon = (key: SortKey) => sort.key !== key ? null : sort.dir === 'asc'
        ? <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" /> : <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />;
    const ariaSort = (key: SortKey) => sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
    const sortHeader = (key: SortKey, label: string, right = false) => (
        <th scope="col" aria-sort={ariaSort(key)} className={`px-4 py-3 ${right ? 'text-right' : ''}`}>
            <button type="button" onClick={() => toggleSort(key)} className={`inline-flex items-center gap-1 uppercase hover:text-gray-900 dark:hover:text-white ${right ? 'flex-row-reverse' : ''}`}>
                {label}{sortIcon(key)}
            </button>
        </th>
    );

    return (
        <div className="space-y-6 pb-12">
            {header}

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                <StatTile icon={<Network className="w-[18px] h-[18px]" />} label="Total traffic" tone="primary" footnote="Running counters; they reset when a host restarts">
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{formatBytes(total)}</p>
                </StatTile>
                <StatTile icon={<ArrowUpRight className="w-[18px] h-[18px]" />} label="Sent" tone="primary" footnote={`${formatShare(sent, total)} of all traffic`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{formatBytes(sent)}</p>
                </StatTile>
                <StatTile icon={<ArrowDownLeft className="w-[18px] h-[18px]" />} label="Received" tone="orange" footnote={`${formatShare(recv, total)} of all traffic`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{formatBytes(recv)}</p>
                </StatTile>
                <StatTile icon={<Server className="w-[18px] h-[18px]" />} label="Endpoints reporting" tone="blue" footnote={`of ${agents.length} agent${agents.length === 1 ? '' : 's'}`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{reporting}</p>
                </StatTile>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <Panel className="xl:col-span-2" title="Top endpoints by traffic" note="Sent and received per endpoint, the ten busiest"
                    actions={
                        <ul aria-label="Legend" className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-300">
                            {[SERIES.sent, SERIES.received].map(s => (
                                <li key={s.name} className="flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-sm ${s.swatch}`} aria-hidden="true" />{s.name}</li>
                            ))}
                        </ul>
                    }>
                    {top.length === 0 || total === 0 ? (
                        <EmptyNote icon={<BarChart3 className="w-5 h-5" />} title="No traffic reported yet">
                            Endpoints appear here once their agents send network counters.
                        </EmptyNote>
                    ) : (
                        <ResponsiveContainer width="100%" height={Math.max(160, top.length * 36 + 32)}>
                            <BarChart data={top} layout="vertical" margin={{ top: 0, right: 72, left: 0, bottom: 0 }} barCategoryGap={10}>
                                <CartesianGrid horizontal={false} stroke={chart.grid} />
                                <XAxis type="number" tickFormatter={(v: any) => formatBytes(v)} tick={{ fill: chart.text, fontSize: 11 }} tickLine={false} axisLine={false} />
                                <YAxis type="category" dataKey="name" width={132} tick={{ fill: chart.text, fontSize: 12 }} tickLine={false} axisLine={false}
                                    tickFormatter={(n: any) => String(n).length > 18 ? `${String(n).slice(0, 17)}…` : n} />
                                <Tooltip cursor={{ fill: chart.cursor }} content={<ChartTooltip />} />
                                <Bar dataKey="sent" name={SERIES.sent.name} stackId="t" fill={sentColor} stroke={chart.surface} strokeWidth={2} maxBarSize={18} />
                                <Bar dataKey="received" name={SERIES.received.name} stackId="t" fill={recvColor} stroke={chart.surface} strokeWidth={2} maxBarSize={18} radius={[0, 4, 4, 0]}>
                                    <LabelList dataKey="total" position="right" formatter={(v: any) => formatBytes(v)} style={{ fill: chart.text, fontSize: 11 }} />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </Panel>

                <Panel title="Traffic mix" note="Direction of all traffic, and who carries it">
                    <SplitBar label="Traffic direction" segments={[
                        { label: 'Sent', value: sent, display: formatBytes(sent), swatch: SERIES.sent.swatch },
                        { label: 'Received', value: recv, display: formatBytes(recv), swatch: SERIES.received.swatch },
                    ]} />
                    <h3 className="mt-6 mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Share by endpoint</h3>
                    {shares.length ? <RankedList items={shares} format={v => formatBytes(v)} total={total} />
                        : <p className="text-sm text-gray-500 dark:text-gray-400">No endpoint has reported traffic yet.</p>}
                </Panel>
            </div>

            <Panel
                title="All endpoints"
                note={`${rows.length} of ${agents.length} shown`}
                actions={
                    <label className="relative block w-full sm:w-64">
                        <span className="sr-only">Filter endpoints</span>
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" aria-hidden="true" />
                        <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter by host, IP or OS"
                            className="w-full h-9 pl-9 pr-3 rounded-xl text-sm bg-gray-50 dark:bg-white/[0.04] border border-gray-200/80 dark:border-white/[0.08] text-gray-900 dark:text-white placeholder:text-gray-400" />
                    </label>
                }
            >
                <div className="-mx-5 -mb-5 overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="text-[11px] font-semibold text-gray-500 dark:text-gray-400">
                            <tr className="border-y border-gray-100 dark:border-white/[0.06]">
                                {sortHeader('hostname', 'Endpoint')}
                                <th scope="col" className="px-4 py-3 uppercase">IP address</th>
                                <th scope="col" className="px-4 py-3 uppercase">OS</th>
                                {sortHeader('bytesSent', 'Sent', true)}
                                {sortHeader('bytesRecv', 'Received', true)}
                                {sortHeader('total', 'Total', true)}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                            {rows.map(a => (
                                <tr key={a.id || a.hostname} className="hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors">
                                    <td className="px-4 py-3">
                                        <p className="font-medium text-gray-900 dark:text-white">{a.hostname}</p>
                                        <p className="font-mono text-[11px] text-gray-500 dark:text-gray-400 truncate max-w-[220px]" title={a.id}>{a.id}</p>
                                    </td>
                                    <td className="px-4 py-3 font-mono text-[13px] text-gray-700 dark:text-gray-300">{a.ipAddress}</td>
                                    <td className="px-4 py-3">
                                        <span className="inline-flex px-2 py-0.5 rounded-md text-xs bg-gray-100 dark:bg-white/[0.06] text-gray-700 dark:text-gray-300">{a.os}</span>
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatBytes(a.bytesSent)}</td>
                                    <td className="px-4 py-3 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatBytes(a.bytesRecv)}</td>
                                    <td className="px-4 py-3 text-right">
                                        <span className="tabular-nums font-semibold text-gray-900 dark:text-white">{formatBytes(totalOf(a))}</span>
                                        <span className="ml-2 text-xs tabular-nums text-gray-500 dark:text-gray-400">{formatShare(totalOf(a), total)}</span>
                                    </td>
                                </tr>
                            ))}
                            {rows.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                                        {agents.length ? 'No endpoint matches the filter.' : 'No endpoint data yet. Endpoints appear once their agents send network counters.'}
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </Panel>
        </div>
    );
};
