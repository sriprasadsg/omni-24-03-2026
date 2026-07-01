/**
 * TicketReportsDashboard
 * ─────────────────────
 * Full reporting view for the ticketing system.
 *
 * Sections:
 *   1. Summary KPI row
 *   2. Volume trend   — area chart (opened vs closed)
 *   3. SLA compliance — ring chart + priority breakdown table
 *   4. Resolution time — avg/p50/p90 cards + bar chart by priority
 *   5. Assignee workload — horizontal bar chart
 *   6. Backlog ageing — bar chart with critical overlay
 *   7. CSV export button
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
    AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { authFetch, API_BASE } from '../services/apiService';

// ── Colour palette (matches project dark-mode aesthetic) ─────────────────────
const C = {
    teal:    '#14b8a6',
    indigo:  '#6366f1',
    red:     '#ef4444',
    amber:   '#f59e0b',
    green:   '#22c55e',
    slate:   '#64748b',
    purple:  '#a855f7',
    sky:     '#0ea5e9',
};

const PRIORITY_COLORS: Record<string, string> = {
    critical: C.red,
    high:     C.amber,
    medium:   C.indigo,
    low:      C.teal,
};

// ── Small reusable components ─────────────────────────────────────────────────

const KpiCard: React.FC<{
    label: string;
    value: string | number | null;
    sub?: string;
    color?: string;
    loading?: boolean;
}> = ({ label, value, sub, color = 'text-white', loading }) => (
    <div className="bg-slate-800/60 border border-slate-700/50 rounded-2xl p-5 flex flex-col gap-1">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</span>
        {loading
            ? <div className="h-8 w-20 bg-slate-700 rounded animate-pulse mt-1" />
            : <span className={`text-3xl font-bold ${color}`}>{value ?? '—'}</span>
        }
        {sub && <span className="text-[11px] text-slate-500 mt-0.5">{sub}</span>}
    </div>
);

const SectionHeader: React.FC<{ title: string; sub?: string }> = ({ title, sub }) => (
    <div className="mb-4">
        <h2 className="text-base font-bold text-white">{title}</h2>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
);

const ChartBox: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
    <div className={`bg-slate-800/60 border border-slate-700/50 rounded-2xl p-5 ${className}`}>
        {children}
    </div>
);

// ── Custom tooltip shared style ───────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-lg">
            <p className="text-slate-300 font-semibold mb-1">{label}</p>
            {payload.map((p: any) => (
                <p key={p.name} style={{ color: p.color }} className="font-medium">
                    {p.name}: {p.value}
                </p>
            ))}
        </div>
    );
};

// ── Donut / ring chart for SLA ────────────────────────────────────────────────
const SlaRing: React.FC<{ met: number; breached: number; pending: number }> = ({ met, breached, pending }) => {
    const data = [
        { name: 'Met',      value: met,      fill: C.green },
        { name: 'Breached', value: breached, fill: C.red   },
        { name: 'Pending',  value: pending,  fill: C.amber },
    ].filter(d => d.value > 0);

    const total = met + breached + pending;
    const rate  = total > 0 ? Math.round(met / (met + breached) * 100) : null;

    return (
        <div className="flex flex-col items-center">
            <div className="relative">
                <ResponsiveContainer width={180} height={180}>
                    <PieChart>
                        <Pie data={data} cx="50%" cy="50%" innerRadius={55} outerRadius={80}
                            dataKey="value" stroke="none" paddingAngle={2}>
                            {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                        </Pie>
                        <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-2xl font-black text-white">
                        {rate !== null ? `${rate}%` : '—'}
                    </span>
                    <span className="text-[10px] text-slate-400 font-semibold">SLA MET</span>
                </div>
            </div>
            <div className="flex gap-4 mt-1">
                {[{ label: 'Met', v: met, c: C.green }, { label: 'Breached', v: breached, c: C.red }, { label: 'Pending', v: pending, c: C.amber }].map(item => (
                    <div key={item.label} className="flex items-center gap-1 text-xs">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.c }} />
                        <span className="text-slate-400">{item.label}</span>
                        <span className="text-white font-semibold">{item.v}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtHours(h: number | null | undefined): string {
    if (h == null) return '—';
    if (h < 1) return `${Math.round(h * 60)}m`;
    if (h < 24) return `${h.toFixed(1)}h`;
    return `${(h / 24).toFixed(1)}d`;
}

// ── Main component ────────────────────────────────────────────────────────────

interface ReportsProps {
    /** tenant filter passed from parent (optional) */
    tenantId?: string;
}

const TicketReportsDashboard: React.FC<ReportsProps> = () => {
    const [days,    setDays]    = useState(30);
    const [period,  setPeriod]  = useState<'daily' | 'weekly'>('daily');
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);

    // Data state
    const [summary,    setSummary]    = useState<any>(null);
    const [trends,     setTrends]     = useState<any[]>([]);
    const [sla,        setSla]        = useState<any>(null);
    const [resolution, setResolution] = useState<any>(null);
    const [assignees,  setAssignees]  = useState<any[]>([]);
    const [ageing,     setAgeing]     = useState<any[]>([]);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [sumRes, trendRes, slaRes, resRes, asgRes, ageRes] = await Promise.all([
                authFetch(`${API_BASE}/tickets/reports/summary`),
                authFetch(`${API_BASE}/tickets/reports/trends?days=${days}&period=${period}`),
                authFetch(`${API_BASE}/tickets/reports/sla`),
                authFetch(`${API_BASE}/tickets/reports/resolution`),
                authFetch(`${API_BASE}/tickets/reports/assignee`),
                authFetch(`${API_BASE}/tickets/reports/ageing`),
            ]);

            if (sumRes.ok)   setSummary(await sumRes.json());
            if (trendRes.ok) setTrends((await trendRes.json()).data || []);
            if (slaRes.ok)   setSla(await slaRes.json());
            if (resRes.ok)   setResolution(await resRes.json());
            if (asgRes.ok)   setAssignees((await asgRes.json()).assignees || []);
            if (ageRes.ok)   setAgeing((await ageRes.json()).buckets || []);
        } catch (e) {
            console.error('Failed to load ticket reports', e);
        }
        setLoading(false);
    }, [days, period]);

    useEffect(() => { load(); }, [load]);

    const handleCsvExport = async () => {
        setExporting(true);
        try {
            const res = await authFetch(`${API_BASE}/tickets/export/csv`);
            if (!res.ok) throw new Error('Export failed');
            const blob = await res.blob();
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href     = url;
            a.download = `tickets_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        } catch { /* silent */ }
        setExporting(false);
    };

    // Resolution chart data
    const resolutionChartData = resolution
        ? ['critical','high','medium','low'].map(p => ({
            priority: p.charAt(0).toUpperCase() + p.slice(1),
            avg:  resolution.by_priority?.[p]?.avg ?? 0,
            p50:  resolution.by_priority?.[p]?.p50 ?? 0,
            p90:  resolution.by_priority?.[p]?.p90 ?? 0,
        }))
        : [];

    return (
        <div className="space-y-8 p-1">

            {/* ── Controls ─────────────────────────────────────────────── */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2">
                    {[7, 30, 90].map(d => (
                        <button key={d} onClick={() => setDays(d)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors
                                ${days === d
                                    ? 'bg-teal-600 text-white'
                                    : 'bg-slate-700/60 text-slate-300 hover:bg-slate-700'}`}>
                            {d}d
                        </button>
                    ))}
                    <span className="w-px h-5 bg-slate-700" />
                    {(['daily','weekly'] as const).map(p => (
                        <button key={p} onClick={() => setPeriod(p)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors capitalize
                                ${period === p
                                    ? 'bg-indigo-600 text-white'
                                    : 'bg-slate-700/60 text-slate-300 hover:bg-slate-700'}`}>
                            {p}
                        </button>
                    ))}
                </div>
                <button onClick={handleCsvExport} disabled={exporting}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold transition-colors">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    {exporting ? 'Exporting…' : 'Export CSV'}
                </button>
            </div>

            {/* ── 1. Summary KPIs ──────────────────────────────────────── */}
            <div>
                <SectionHeader title="Summary" sub="Key metrics across all tickets in the selected period" />
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                    <KpiCard label="Total Tickets"   value={summary?.total}                                     loading={loading} />
                    <KpiCard label="Open"            value={summary?.open}     color="text-amber-400"          loading={loading} />
                    <KpiCard label="Closed"          value={summary?.closed}   color="text-teal-400"           loading={loading} />
                    <KpiCard label="Overdue"         value={summary?.overdue}  color="text-red-400"            loading={loading} />
                    <KpiCard label="SLA Compliance"
                        value={summary?.sla_compliance_rate != null ? `${summary.sla_compliance_rate}%` : null}
                        color={summary?.sla_compliance_rate >= 90 ? 'text-green-400' : summary?.sla_compliance_rate >= 70 ? 'text-amber-400' : 'text-red-400'}
                        sub={`${summary?.sla_met ?? 0} met / ${summary?.sla_breached ?? 0} breached`}
                        loading={loading} />
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                    <KpiCard label="Escalated"        value={summary?.escalated}                                loading={loading} color="text-purple-400" />
                    <KpiCard label="Avg Resolution"
                        value={summary?.avg_resolution_hours != null ? fmtHours(summary.avg_resolution_hours) : null}
                        sub="time to close"
                        loading={loading} color="text-sky-400" />
                </div>
            </div>

            {/* ── 2. Volume Trend ───────────────────────────────────────── */}
            <div>
                <SectionHeader title="Ticket Volume" sub="Opened vs closed over time" />
                <ChartBox>
                    <ResponsiveContainer width="100%" height={220}>
                        <AreaChart data={trends} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                            <defs>
                                <linearGradient id="openedGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%"  stopColor={C.indigo} stopOpacity={0.3}/>
                                    <stop offset="95%" stopColor={C.indigo} stopOpacity={0}/>
                                </linearGradient>
                                <linearGradient id="closedGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%"  stopColor={C.teal} stopOpacity={0.3}/>
                                    <stop offset="95%" stopColor={C.teal} stopOpacity={0}/>
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                            <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} />
                            <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
                            <Tooltip content={<CustomTooltip />} />
                            <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                            <Area type="monotone" dataKey="opened" stroke={C.indigo} fill="url(#openedGrad)" strokeWidth={2} dot={false} name="Opened" />
                            <Area type="monotone" dataKey="closed"  stroke={C.teal}   fill="url(#closedGrad)"  strokeWidth={2} dot={false} name="Closed" />
                        </AreaChart>
                    </ResponsiveContainer>
                </ChartBox>
            </div>

            {/* ── 3. SLA Compliance ─────────────────────────────────────── */}
            <div>
                <SectionHeader title="SLA Compliance" sub="Percentage of tickets meeting their SLA target" />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* Ring chart */}
                    <ChartBox className="flex flex-col items-center justify-center">
                        {sla ? (
                            <SlaRing
                                met={sla.sla_met}
                                breached={sla.sla_breached}
                                pending={sla.sla_pending}
                            />
                        ) : (
                            <div className="h-44 flex items-center justify-center text-slate-500 text-sm">Loading…</div>
                        )}
                    </ChartBox>

                    {/* Priority breakdown table */}
                    <ChartBox>
                        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">By Priority</p>
                        {sla?.by_priority ? (
                            <div className="space-y-3">
                                {sla.by_priority.map((row: any) => (
                                    <div key={row.priority}>
                                        <div className="flex justify-between text-xs mb-1">
                                            <span className="capitalize font-semibold" style={{ color: PRIORITY_COLORS[row.priority] }}>{row.priority}</span>
                                            <span className="text-slate-300 font-bold">{row.rate != null ? `${row.rate}%` : '—'}</span>
                                        </div>
                                        <div className="w-full bg-slate-700 rounded-full h-1.5">
                                            <div className="h-1.5 rounded-full transition-all duration-700"
                                                style={{ width: `${row.rate ?? 0}%`, backgroundColor: row.rate >= 90 ? C.green : row.rate >= 70 ? C.amber : C.red }} />
                                        </div>
                                        <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
                                            <span>{row.met} met</span>
                                            <span>{row.breached} breached</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="h-32 flex items-center justify-center text-slate-500 text-sm">Loading…</div>
                        )}
                    </ChartBox>
                </div>
            </div>

            {/* ── 4. Resolution Time ───────────────────────────────────── */}
            <div>
                <SectionHeader title="Resolution Time" sub="How quickly tickets are being closed" />
                <div className="grid grid-cols-3 gap-3 mb-4">
                    {[
                        { label: 'Avg',    val: resolution?.overall?.avg, sub: 'mean resolution' },
                        { label: 'Median', val: resolution?.overall?.p50, sub: 'p50 resolution' },
                        { label: 'p90',    val: resolution?.overall?.p90, sub: '9 in 10 tickets' },
                    ].map(m => (
                        <KpiCard key={m.label} label={m.label} value={fmtHours(m.val)} sub={m.sub} color="text-sky-400" loading={loading} />
                    ))}
                </div>
                <ChartBox>
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Resolution Time by Priority (hours)</p>
                    <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={resolutionChartData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                            <XAxis dataKey="priority" tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} />
                            <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
                            <Tooltip content={<CustomTooltip />} />
                            <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                            <Bar dataKey="avg" name="Avg (h)"    fill={C.sky}    radius={[4,4,0,0]} />
                            <Bar dataKey="p50" name="p50 (h)"   fill={C.indigo} radius={[4,4,0,0]} />
                            <Bar dataKey="p90" name="p90 (h)"   fill={C.purple} radius={[4,4,0,0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </ChartBox>
            </div>

            {/* ── 5. Assignee Workload ──────────────────────────────────── */}
            {assignees.length > 0 && (
                <div>
                    <SectionHeader title="Assignee Workload" sub="Open, resolved, and overdue tickets per team member" />
                    <ChartBox>
                        <ResponsiveContainer width="100%" height={Math.max(200, assignees.length * 40)}>
                            <BarChart
                                layout="vertical"
                                data={assignees.slice(0, 10)}
                                margin={{ top: 5, right: 30, bottom: 0, left: 10 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                                <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
                                <YAxis type="category" dataKey="assignee" tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} width={100} />
                                <Tooltip content={<CustomTooltip />} />
                                <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                                <Bar dataKey="open"     name="Open"     fill={C.amber}  radius={[0,4,4,0]} stackId="a" />
                                <Bar dataKey="resolved" name="Resolved" fill={C.teal}   radius={[0,4,4,0]} stackId="a" />
                                <Bar dataKey="overdue"  name="Overdue"  fill={C.red}    radius={[0,4,4,0]} stackId="b" />
                            </BarChart>
                        </ResponsiveContainer>
                        {/* Resolution time mini-table */}
                        {assignees.some(a => a.avg_resolution_hours != null) && (
                            <div className="mt-4 border-t border-slate-700 pt-4">
                                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Avg Resolution Time</p>
                                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                                    {assignees.slice(0,10).map((a: any) => (
                                        a.avg_resolution_hours != null && (
                                            <div key={a.assignee} className="bg-slate-700/40 rounded-lg p-2 text-center">
                                                <p className="text-[10px] text-slate-400 truncate">{a.assignee}</p>
                                                <p className="text-sm font-bold text-sky-400">{fmtHours(a.avg_resolution_hours)}</p>
                                            </div>
                                        )
                                    ))}
                                </div>
                            </div>
                        )}
                    </ChartBox>
                </div>
            )}

            {/* ── 6. Backlog Ageing ─────────────────────────────────────── */}
            {ageing.length > 0 && (
                <div>
                    <SectionHeader title="Backlog Ageing" sub="How long open tickets have been waiting" />
                    <ChartBox>
                        <ResponsiveContainer width="100%" height={220}>
                            <BarChart data={ageing} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                                <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} />
                                <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
                                <Tooltip content={<CustomTooltip />} />
                                <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
                                <Bar dataKey="count"    name="Open"     fill={C.indigo} radius={[4,4,0,0]} />
                                <Bar dataKey="critical" name="Critical" fill={C.red}    radius={[4,4,0,0]} />
                            </BarChart>
                        </ResponsiveContainer>
                        {ageing.some((b: any) => b.count > 0) && (
                            <p className="text-[11px] text-slate-500 mt-3 text-center">
                                Older open tickets accumulate risk — prioritise the rightmost buckets.
                            </p>
                        )}
                    </ChartBox>
                </div>
            )}

            {/* Empty state */}
            {!loading && !summary?.total && (
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mb-4 opacity-40">
                        <path d="M9 19v-6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2zm0 0V9a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v10m-6 0a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2m0 0V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2z"/>
                    </svg>
                    <p className="font-medium">No ticket data yet</p>
                    <p className="text-sm mt-1">Create some tickets and check back here for insights.</p>
                </div>
            )}
        </div>
    );
};

export default TicketReportsDashboard;
