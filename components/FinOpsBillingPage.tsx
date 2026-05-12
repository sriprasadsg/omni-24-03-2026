import React, { useState, useEffect, useContext } from 'react';
import { Tenant } from '../types';
import { DollarSignIcon, BotIcon, TrendingUpIcon, CheckIcon, SparklesIcon, RefreshCwIcon } from './icons';
import {
    PieChart, Pie, Cell, Tooltip, Legend,
    ResponsiveContainer, XAxis, YAxis, CartesianGrid, Area, AreaChart,
} from 'recharts';
import { useUser } from '../contexts/UserContext';
import {
    fetchFinOpsCosts, getFinOpsAnalysis, recalculateFinOpsCosts,
} from '../services/apiService';
import { ThemeContext } from '../contexts/ThemeContext';

interface FinOpsBillingPageProps {
    tenants: Tenant[];
    isSuperAdminView: boolean;
}

const COLORS = ['#3b82f6', '#10b981', '#f97316', '#8b5cf6', '#ef4444', '#f59e0b'];

const fmt = (v: number) =>
    `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const StatCard: React.FC<{ title: string; value: string; sub?: string; icon: React.ReactNode; color?: string }> =
    ({ title, value, sub, icon, color = 'primary' }) => (
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex items-center gap-4">
            <div className={`p-3 bg-${color}-100 dark:bg-${color}-900/50 rounded-full text-${color}-500 dark:text-${color}-400 shrink-0`}>
                {icon}
            </div>
            <div className="min-w-0">
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{title}</p>
                <p className="text-2xl font-bold truncate">{value}</p>
                {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub}</p>}
            </div>
        </div>
    );

const Skeleton: React.FC<{ lines?: number }> = ({ lines = 3 }) => (
    <div className="space-y-3 animate-pulse">
        {Array.from({ length: lines }).map((_, i) => (
            <div key={i} className={`h-3 bg-gray-200 dark:bg-gray-700 rounded ${i === 0 ? 'w-1/3' : i % 2 === 0 ? 'w-5/6' : 'w-full'}`} />
        ))}
    </div>
);

interface CostSnapshot {
    total_spend: number;
    breakdown: Record<string, number>;
    currency: string;
    budget_usage_percent: number;
}
interface HistoryEntry { date: string; cost: number; }
interface Forecast { forecast_total: number; budget: number; status: string; }
interface Recommendation { id: string; title: string; savings: number; effort: string; category: string; }

export const FinOpsBillingPage: React.FC<FinOpsBillingPageProps> = ({ tenants, isSuperAdminView }) => {
    const { currentUser } = useUser();
    const { theme } = useContext(ThemeContext);
    const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
    const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

    const [snapshot, setSnapshot]           = useState<CostSnapshot | null>(null);
    const [history, setHistory]             = useState<HistoryEntry[]>([]);
    const [forecast, setForecast]           = useState<Forecast | null>(null);
    const [recommendations, setRecs]        = useState<Recommendation[]>([]);
    const [loading, setLoading]             = useState(true);
    const [error, setError]                 = useState('');

    const [analysis, setAnalysis]           = useState('');
    const [aiRecs, setAiRecs]               = useState<string[]>([]);
    const [aiLoading, setAiLoading]         = useState(false);
    const [isRecalculating, setRecalc]      = useState(false);

    const [selectedTenantId, setSelectedTenantId] = useState(
        isSuperAdminView ? '' : (currentUser?.tenantId || '')
    );

    // ── Load live cost data from the backend ────────────────────────────────
    const loadData = async () => {
        setLoading(true);
        setError('');
        try {
            const [costsRes, recsRes] = await Promise.allSettled([
                fetchFinOpsCosts(),
                // fetchFinOpsRecommendations lives at /api/finops/recommendations
                fetch('/api/finops/recommendations', {
                    headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
                }).then(r => r.ok ? r.json() : []),
            ]);

            if (costsRes.status === 'fulfilled' && costsRes.value) {
                const d = costsRes.value as { snapshot: CostSnapshot; history: HistoryEntry[]; forecast: Forecast };
                setSnapshot(d.snapshot ?? null);
                setHistory(d.history ?? []);
                setForecast(d.forecast ?? null);
            }
            if (recsRes.status === 'fulfilled') {
                setRecs(Array.isArray(recsRes.value) ? recsRes.value : []);
            }
        } catch (err) {
            setError('Failed to load FinOps data. Ensure the backend is running.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadData(); }, []);

    // ── Derived values ───────────────────────────────────────────────────────
    const breakdownArr = snapshot
        ? Object.entries(snapshot.breakdown)
            .filter(([, v]) => v > 0)
            .map(([service, cost]) => ({ service, cost }))
        : [];

    // Convert daily history to monthly buckets for the trend chart
    const monthlyHistory = React.useMemo(() => {
        const buckets: Record<string, number> = {};
        history.forEach(({ date, cost }) => {
            const key = date.slice(0, 7); // "YYYY-MM"
            buckets[key] = (buckets[key] ?? 0) + cost;
        });
        return Object.entries(buckets)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([month, cost]) => ({
                month: new Date(month + '-01').toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
                cost: Math.round(cost * 100) / 100,
            }));
    }, [history]);

    const potentialSavings = recommendations.reduce((s, r) => s + (r.savings ?? 0), 0);
    const budgetPct = snapshot?.budget_usage_percent ?? 0;
    const budgetColor = budgetPct > 100 ? 'red' : budgetPct > 85 ? 'yellow' : 'green';

    // ── Handlers ─────────────────────────────────────────────────────────────
    const handleGenerateAnalysis = async () => {
        if (!snapshot) return;
        setAiLoading(true);
        setAnalysis('');
        setAiRecs([]);
        try {
            const payload = {
                currentMonthCost: snapshot.total_spend,
                forecastedCost: forecast?.forecast_total ?? 0,
                potentialSavings,
                costBreakdown: breakdownArr,
            };
            const result = await getFinOpsAnalysis(payload);
            setAnalysis(result.analysis ?? '');
            setAiRecs(result.recommendations ?? []);
        } catch {
            setAnalysis('Analysis failed. Please try again.');
        } finally {
            setAiLoading(false);
        }
    };

    const handleRecalculate = async () => {
        const tid = isSuperAdminView ? selectedTenantId : currentUser?.tenantId;
        if (!tid) return;
        setRecalc(true);
        try {
            await recalculateFinOpsCosts(tid);
            await loadData();
        } catch {
            setError('Recalculation failed.');
        } finally {
            setRecalc(false);
        }
    };

    // ── Render ────────────────────────────────────────────────────────────────
    if (loading) {
        return (
            <div className="container mx-auto space-y-6">
                <h2 className="text-2xl font-semibold">FinOps & Cloud Costs</h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {[1, 2, 3].map(i => (
                        <div key={i} className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md h-24 animate-pulse" />
                    ))}
                </div>
                <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md"><Skeleton lines={5} /></div>
            </div>
        );
    }

    return (
        <div className="container mx-auto space-y-6">

            {/* ── Header ── */}
            <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">FinOps &amp; Cloud Costs</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Live cloud resource consumption and cost optimisation.
                    </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                    {isSuperAdminView && (
                        <select
                            value={selectedTenantId}
                            onChange={e => setSelectedTenantId(e.target.value)}
                            className="px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm"
                        >
                            <option value="">Platform Overview</option>
                            {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </select>
                    )}
                    <button
                        onClick={loadData}
                        className="flex items-center gap-1.5 px-3 py-2 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600"
                    >
                        <RefreshCwIcon size={14} /> Refresh
                    </button>
                    <button
                        onClick={handleRecalculate}
                        disabled={isRecalculating}
                        className="px-4 py-2 text-sm font-medium text-primary-600 bg-primary-100 dark:bg-primary-900/30 rounded-md hover:bg-primary-200 disabled:opacity-50"
                    >
                        {isRecalculating ? 'Recalculating…' : 'Recalculate Costs'}
                    </button>
                </div>
            </div>

            {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
                    {error}
                </div>
            )}

            {/* ── KPI Cards ── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                    title="Current Month Spend"
                    value={fmt(snapshot?.total_spend ?? 0)}
                    sub={`${budgetPct.toFixed(1)}% of monthly budget`}
                    icon={<DollarSignIcon size={22} />}
                    color={budgetColor}
                />
                <StatCard
                    title="Month-End Forecast"
                    value={fmt(forecast?.forecast_total ?? 0)}
                    sub={forecast ? `Budget: ${fmt(forecast.budget)} — ${forecast.status === 'ON_TRACK' ? '✓ On Track' : '⚠ Over Budget'}` : ''}
                    icon={<TrendingUpIcon size={22} />}
                    color={forecast?.status === 'ON_TRACK' ? 'green' : 'red'}
                />
                <StatCard
                    title="Potential Monthly Savings"
                    value={fmt(potentialSavings)}
                    sub={`${recommendations.length} optimisation${recommendations.length !== 1 ? 's' : ''} identified`}
                    icon={<SparklesIcon size={22} />}
                    color="primary"
                />
                <StatCard
                    title="Budget Utilisation"
                    value={`${budgetPct.toFixed(1)}%`}
                    sub={`Daily budget: ${fmt((forecast?.budget ?? 15000) / 30)}`}
                    icon={<CheckIcon size={22} />}
                    color={budgetColor}
                />
            </div>

            {/* ── Charts ── */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                {/* Pie */}
                <div className="lg:col-span-2 bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <h3 className="text-sm font-semibold mb-4 text-gray-800 dark:text-white">Cost Breakdown by Category</h3>
                    {breakdownArr.length > 0 ? (
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={breakdownArr}
                                        dataKey="cost"
                                        nameKey="service"
                                        cx="50%"
                                        cy="50%"
                                        outerRadius={80}
                                        label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                                    >
                                        {breakdownArr.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                                    </Pie>
                                    <Tooltip formatter={(v: number) => fmt(v)} />
                                    <Legend wrapperStyle={{ fontSize: 12 }} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
                            No cost breakdown data yet.
                        </div>
                    )}
                </div>

                {/* Area trend */}
                <div className="lg:col-span-3 bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <h3 className="text-sm font-semibold mb-4 text-gray-800 dark:text-white">Monthly Cost Trend (last 30 days)</h3>
                    {monthlyHistory.length > 0 ? (
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={monthlyHistory} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="month" stroke={textColor} fontSize={11} />
                                    <YAxis stroke={textColor} fontSize={11} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} />
                                    <Tooltip formatter={(v: number) => fmt(v)} />
                                    <Area type="monotone" dataKey="cost" name="Actual Cost" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
                            No cost history yet — runs after first usage records are ingested.
                        </div>
                    )}
                </div>
            </div>

            {/* ── Recommendations ── */}
            {recommendations.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h3 className="text-sm font-semibold text-gray-800 dark:text-white">
                            Cost Optimisation Recommendations
                        </h3>
                    </div>
                    <div className="divide-y divide-gray-100 dark:divide-gray-700">
                        {recommendations.map(rec => (
                            <div key={rec.id} className="p-4 flex items-start justify-between gap-4 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                                <div className="flex items-start gap-3 min-w-0">
                                    <CheckIcon className="shrink-0 h-4 w-4 text-green-500 mt-0.5" />
                                    <div className="min-w-0">
                                        <p className="text-sm font-medium text-gray-800 dark:text-white truncate">{rec.title}</p>
                                        <div className="flex gap-2 mt-1 flex-wrap">
                                            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">{rec.category}</span>
                                            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">Effort: {rec.effort}</span>
                                        </div>
                                    </div>
                                </div>
                                <span className="shrink-0 text-sm font-semibold text-green-600 dark:text-green-400 whitespace-nowrap">
                                    Save {fmt(rec.savings)}/mo
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ── AI Analysis ── */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                        <BotIcon className="text-primary-500" size={18} />
                        AI-Powered Cost Analysis
                    </h3>
                    <button
                        onClick={handleGenerateAnalysis}
                        disabled={aiLoading || !snapshot}
                        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-primary-400"
                    >
                        {aiLoading ? 'Analysing…' : 'Generate Analysis'}
                    </button>
                </div>
                <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <h4 className="text-sm font-semibold mb-2">Summary</h4>
                        {aiLoading && <Skeleton />}
                        {!aiLoading && !analysis && (
                            <p className="text-sm text-gray-400 dark:text-gray-500">
                                Click "Generate Analysis" to get an AI cost summary.
                            </p>
                        )}
                        {analysis && <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{analysis}</p>}
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold mb-2">Recommendations</h4>
                        {aiLoading && <Skeleton />}
                        {!aiLoading && aiRecs.length > 0 && (
                            <ul className="space-y-2">
                                {aiRecs.map((r, i) => (
                                    <li key={i} className="flex items-start gap-2 p-3 bg-green-50 dark:bg-green-900/30 rounded-lg text-sm border border-green-200 dark:border-green-800">
                                        <CheckIcon className="shrink-0 h-4 w-4 text-green-500 mt-0.5" />
                                        <span className="text-green-800 dark:text-green-200">{r}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Tenant table (Super Admin only) ── */}
            {isSuperAdminView && tenants.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h3 className="text-sm font-semibold text-gray-800 dark:text-white">Per-Tenant Overview</h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                            <thead className="bg-gray-50 dark:bg-gray-900">
                                <tr>
                                    {['Tenant', 'Tier', 'Current Month', 'Forecast', 'Budget', 'Status'].map(h => (
                                        <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {tenants.map(tenant => {
                                    const fd = tenant.finOpsData;
                                    const pct = fd ? (fd.currentMonthCost / (tenant.budget?.monthlyLimit || 1)) * 100 : 0;
                                    const over = pct > 100;
                                    const warn = pct > 85;
                                    return (
                                        <tr key={tenant.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                                            <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{tenant.name}</td>
                                            <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{tenant.subscriptionTier}</td>
                                            <td className="px-4 py-3">{fd ? fmt(fd.currentMonthCost) : '—'}</td>
                                            <td className="px-4 py-3 text-gray-500">{fd ? fmt(fd.forecastedCost) : '—'}</td>
                                            <td className="px-4 py-3">
                                                {tenant.budget ? fmt(tenant.budget.monthlyLimit) : 'N/A'}
                                                {tenant.budget && (
                                                    <div className="w-20 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
                                                        <div className={`h-full rounded-full ${over ? 'bg-red-500' : warn ? 'bg-yellow-500' : 'bg-green-500'}`}
                                                            style={{ width: `${Math.min(pct, 100)}%` }} />
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
                                                    over  ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' :
                                                    warn  ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300' :
                                                    fd    ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' :
                                                            'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                                                }`}>
                                                    {over ? 'Over Budget' : warn ? 'Warning' : fd ? 'Healthy' : 'No Data'}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};
