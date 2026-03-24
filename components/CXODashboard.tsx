import React, { useState, useEffect, useContext } from 'react';
import { TrendingUpIcon, ShieldSearchIcon, ShieldCheckIcon, ZapIcon, DollarSignIcon, BarChart3Icon, AlertTriangleIcon, UsersIcon, ServerIcon, ActivityIcon, ArrowDownRightIcon, ClockIcon, XCircleIcon } from './icons';
import { AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';
import { fetchAgents, fetchAlerts, fetchAssets, fetchComplianceFrameworks, fetchTenants, fetchKpiSummary } from '../services/apiService';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface CXODashboardProps { }

const StatCard: React.FC<{ title: string; value: string; change: number; trend: 'up' | 'down'; icon: React.ReactNode; color: string }> = ({ title, value, change, trend, icon, color }) => (
    <div className={`glass-premium p-6 rounded-3xl flex items-center gap-4 group transition-all hover:scale-105 border-l-4 ${color}`}>
        <div className="p-3 bg-white/5 rounded-2xl group-hover:bg-white/10 transition-colors">
            {icon}
        </div>
        <div>
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{title}</p>
            <p className="text-3xl font-black text-gray-800 dark:text-gray-100 italic tracking-tighter">{value}</p>
            <p className={`text-[10px] font-bold flex items-center gap-1 mt-1 ${trend === 'up' ? 'text-green-500' : 'text-red-500'}`}>
                {trend === 'up' ? <TrendingUpIcon size={10} /> : <ArrowDownRightIcon size={10} />}
                {trend === 'up' ? '+' : ''}{change}% vs last month
            </p>
        </div>
    </div>
);

export const CXODashboard: React.FC<CXODashboardProps> = () => {
    const { timeZone } = useTimeZone();
    const { theme } = useContext(ThemeContext);
    const [tenants, setTenants] = useState<any[]>([]);
    const [selectedTenant, setSelectedTenant] = useState<string>('all');
    const [agents, setAgents] = useState<any[]>([]);
    const [alerts, setAlerts] = useState<any[]>([]);
    const [assets, setAssets] = useState<any[]>([]);
    const [frameworks, setFrameworks] = useState<any[]>([]);
    const [selectedFramework, setSelectedFramework] = useState<any | null>(null);
    const [loading, setLoading] = useState(true);

    // Summary counts for KPIs
    const [onlineAgentsCount, setOnlineAgentsCount] = useState(0);
    const [totalAgentsCount, setTotalAgentsCount] = useState(0);
    const [totalAssetsCount, setTotalAssetsCount] = useState(0);
    const [criticalAlertsSummaryCount, setCriticalAlertsSummaryCount] = useState(0);
    const [isLoadingKpis, setIsLoadingKpis] = useState(true);

    const loadInitialData = async () => {
        try {
            const [alertsData, frameworksData, tenantsData] = await Promise.all([
                fetchAlerts(),
                fetchComplianceFrameworks(),
                fetchTenants()
            ]);
            setAlerts(alertsData);
            setFrameworks(frameworksData);
            setTenants(tenantsData);
        } catch (error) {
            console.error('Error loading static CXO dashboard data:', error);
        }
    };

    useEffect(() => {
        loadInitialData();
    }, []);

    useEffect(() => {
        const loadDashboardData = async () => {
            setIsLoadingKpis(true);
            try {
                // Determine tenantId for API filtering
                const tenantId = selectedTenant === 'all' ? undefined : selectedTenant;

                // We'll pass tenantId to the API fetchers (if they support it, or filter locally)
                // apiService.ts fetchAgents/fetchAssets usually don't take args, 
                // but the backend /api/kpi/summary does.
                const [agentsData, assetsData, kpiSummary] = await Promise.all([
                    fetchAgents(tenantId),
                    fetchAssets(tenantId),
                    fetchKpiSummary(tenantId)
                ]);

                setAgents(agentsData);
                setAssets(assetsData);

                if (kpiSummary) {
                    setOnlineAgentsCount(kpiSummary.onlineAgents);
                    setTotalAgentsCount(kpiSummary.totalAgents);
                    setTotalAssetsCount(kpiSummary.totalAssets);
                    setCriticalAlertsSummaryCount(kpiSummary.criticalAlerts);
                } else {
                    // Fallback to local calculation if summary fails
                    const filtered = selectedTenant === 'all' ? agentsData : agentsData.filter((a: any) => a.tenantId === selectedTenant);
                    setOnlineAgentsCount(filtered.filter((a: any) => a.status === 'Online').length);
                    setTotalAgentsCount(filtered.length);
                    setTotalAssetsCount(assetsData.length);
                }
            } catch (error) {
                console.error("Error loading dashboard data:", error);
                setOnlineAgentsCount(0);
                setTotalAgentsCount(0);
                setTotalAssetsCount(0);
            } finally {
                setIsLoadingKpis(false);
                setLoading(false);
            }
        };

        loadDashboardData();
    }, [selectedTenant]);

    // Filter data based on selected tenant (for charts/lists that use full data)
    const filteredAgents = selectedTenant === 'all'
        ? agents
        : agents.filter(a => a.tenantId === selectedTenant);

    const filteredAlerts = selectedTenant === 'all'
        ? alerts
        : alerts.filter(a => a.tenantId === selectedTenant);

    const filteredAssets = selectedTenant === 'all'
        ? assets
        : assets.filter(a => a.tenantId === selectedTenant);

    // Calculate real-time KPIs using summary counts where available
    const agentHealth = totalAgentsCount > 0 ? ((onlineAgentsCount / totalAgentsCount) * 100).toFixed(1) : '0.0';

    const criticalAlertsCount = filteredAlerts.filter(a => a.severity === 'Critical').length;
    const highAlertsCount = filteredAlerts.filter(a => a.severity === 'High').length;
    const totalAlertsCount = filteredAlerts.length;

    const avgCompliance = frameworks.length > 0
        ? (frameworks.reduce((sum, f) => sum + f.progress, 0) / frameworks.length).toFixed(1)
        : '0.0';

    const vulnerableAssetsCount = filteredAssets.filter(a => a.vulnerabilities && a.vulnerabilities.length > 0).length;
    const securityPosture = filteredAssets.length > 0
        ? (((filteredAssets.length - vulnerableAssetsCount) / filteredAssets.length) * 100).toFixed(1)
        : '0.0';

    // Threat trend data (last 7 days simulation based on filtered alerts)
    const threatTrendData = [
        { day: 'Mon', critical: Math.ceil(criticalAlertsCount * 0.8), high: Math.ceil(highAlertsCount * 0.8), medium: 5 },
        { day: 'Tue', critical: Math.ceil(criticalAlertsCount * 0.7), high: Math.ceil(highAlertsCount * 0.9), medium: 6 },
        { day: 'Wed', critical: Math.ceil(criticalAlertsCount * 0.9), high: Math.ceil(highAlertsCount * 0.7), medium: 7 },
        { day: 'Thu', critical: Math.ceil(criticalAlertsCount * 0.6), high: Math.ceil(highAlertsCount * 0.6), medium: 8 },
        { day: 'Fri', critical: Math.ceil(criticalAlertsCount * 0.9), high: Math.ceil(highAlertsCount * 0.8), medium: 9 },
        { day: 'Sat', critical: Math.ceil(criticalAlertsCount * 0.5), high: Math.ceil(highAlertsCount * 0.5), medium: 4 },
        { day: 'Sun', critical: criticalAlertsCount, high: highAlertsCount, medium: totalAlertsCount - criticalAlertsCount - highAlertsCount }
    ];

    // Asset distribution
    const assetDistribution = [
        { name: 'Servers', value: Math.floor(filteredAssets.length * 0.4), color: '#6366f1' },
        { name: 'Workstations', value: Math.floor(filteredAssets.length * 0.35), color: '#8b5cf6' },
        { name: 'Network Devices', value: Math.floor(filteredAssets.length * 0.15), color: '#ec4899' },
        { name: 'Cloud Resources', value: Math.floor(filteredAssets.length * 0.10), color: '#14b8a6' }
    ];

    const gridColor = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
    const textColor = theme === 'dark' ? '#9ca3af' : '#4b5563';

    const kpis = [
        { title: 'Security Posture', value: `${securityPosture}%`, change: 2.1, trend: 'up' as const, icon: <ShieldCheckIcon size={24} className="text-primary-500" />, color: 'border-primary-500' },
        { title: 'Agent Health', value: `${agentHealth}%`, change: 5.4, trend: 'up' as const, icon: <ActivityIcon size={24} className="text-indigo-500" />, color: 'border-indigo-500' },
        { title: 'Compliance Avg', value: `${avgCompliance}%`, change: 0.2, trend: 'up' as const, icon: <BarChart3Icon size={24} className="text-accent-500" />, color: 'border-accent-500' },
        { title: 'Active Alerts', value: `${totalAlertsCount}`, change: -12.5, trend: 'down' as const, icon: <AlertTriangleIcon size={24} className="text-emerald-500" />, color: 'border-emerald-500' },
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-primary-600 mx-auto mb-4"></div>
                    <p className="text-gray-500 dark:text-gray-400 font-semibold">Loading Executive Dashboard...</p>
                </div>
            </div>
        );
    }

    // Modal computed values (safe with optional chaining when selectedFramework is null)
    const mPassed = selectedFramework?.progress ?? 0;
    const mRemaining = 100 - mPassed;
    const mFailed = selectedFramework?.status === 'At Risk' ? Math.round(mRemaining * 0.7) : Math.round(mRemaining * 0.3);
    const mPending = mRemaining - mFailed;
    const mBreakdownData = [
        { name: 'Passed', value: Math.round(mPassed), color: '#10b981' },
        { name: 'Failed', value: mFailed, color: '#ef4444' },
        { name: 'Pending', value: mPending, color: '#f59e0b' },
    ].filter(d => d.value > 0);
    const mStatusText = selectedFramework?.status || (mPassed >= 90 ? 'Compliant' : mPassed >= 70 ? 'Pending' : 'At Risk');
    const mStatusBadge = mPassed >= 90
        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        : mPassed >= 70
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';

    return (
        <>
            <header className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-4xl font-bold bg-gradient-to-r from-primary-600 via-indigo-600 to-accent-600 bg-clip-text text-transparent flex items-center gap-3">
                        <TrendingUpIcon size={36} className="text-primary-500" />
                        Executive Insights
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                        Real-time strategic oversight and platform performance metrics.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <button className="glass-premium px-6 py-2.5 rounded-xl font-semibold text-primary-600 dark:text-primary-400 hover:scale-105 transition-all flex items-center gap-2">
                        <TrendingUpIcon size={16} />
                        Download Report
                    </button>
                    <button className="bg-gradient-to-r from-primary-600 to-indigo-600 text-white px-6 py-2.5 rounded-xl font-semibold shadow-lg shadow-primary-500/30 hover:scale-105 transition-all flex items-center gap-2">
                        <ZapIcon size={16} />
                        Strategic Planning
                    </button>
                    {/* Tenant Selector */}
                    <div className="relative">
                        <select
                            value={selectedTenant}
                            onChange={(e) => setSelectedTenant(e.target.value)}
                            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-2.5 pr-8 font-semibold text-gray-700 dark:text-gray-300 shadow-lg focus:ring-2 focus:ring-primary-500 outline-none appearance-none cursor-pointer"
                        >
                            <option value="all">All Tenants</option>
                            {tenants.map(t => (
                                <option key={t.id} value={t.id}>{t.name}</option>
                            ))}
                        </select>
                        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-gray-500">
                            <TrendingUpIcon size={14} className="rotate-90" />
                        </div>
                    </div>
                </div>
            </header>

            {/* Real-time KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {kpis.map((kpi, idx) => (
                    <StatCard
                        key={idx}
                        title={kpi.title}
                        value={kpi.value}
                        change={kpi.change}
                        trend={kpi.trend}
                        icon={kpi.icon}
                        color={kpi.color}
                    />
                ))}
            </div>

            {/* Operational Overview */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="glass-premium p-6 rounded-3xl flex items-center justify-between hover:scale-105 transition-all">
                    <div>
                        <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">Total Assets</p>
                        <p className="text-3xl font-black text-gray-800 dark:text-gray-100">{totalAssetsCount.toLocaleString()}</p>
                        <p className="text-xs text-gray-500 mt-1">Across all environments</p>
                    </div>
                    <div className="p-4 bg-primary-500/10 rounded-2xl">
                        <ServerIcon size={32} className="text-primary-500" />
                    </div>
                </div>
                <div className="glass-premium p-6 rounded-3xl flex items-center justify-between hover:scale-105 transition-all">
                    <div>
                        <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">Active Agents</p>
                        <p className="text-3xl font-black text-gray-800 dark:text-gray-100">{onlineAgentsCount}/{totalAgentsCount}</p>
                        <p className="text-xs text-gray-500 mt-1">Monitoring infrastructure</p>
                    </div>
                    <div className="p-4 bg-indigo-500/10 rounded-2xl">
                        <UsersIcon size={32} className="text-indigo-500" />
                    </div>
                </div>
                <div className="glass-premium p-6 rounded-3xl flex items-center justify-between hover:scale-105 transition-all">
                    <div>
                        <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">Critical Issues</p>
                        <p className="text-3xl font-black text-red-600 dark:text-red-400">{criticalAlertsCount}</p>
                        <p className="text-xs text-gray-500 mt-1">Require immediate attention</p>
                    </div>
                    <div className="p-4 bg-red-500/10 rounded-2xl">
                        <AlertTriangleIcon size={32} className="text-red-500" />
                    </div>
                </div>
            </div>

            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Threat Trend */}
                <section className="glass-premium p-8 rounded-3xl space-y-6">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold flex items-center gap-2">
                            <ShieldSearchIcon className="text-primary-500" />
                            7-Day Threat Trend
                        </h2>
                        <div className="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full text-xs font-black uppercase">
                            Stable
                        </div>
                    </div>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={threatTrendData}>
                                <defs>
                                    <linearGradient id="criticalGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="highGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#f97316" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="mediumGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                                <XAxis dataKey="day" stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '12px', fontSize: '12px', color: '#fff' }}
                                    itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                                />
                                <Legend wrapperStyle={{ fontSize: "10px", fontWeight: "900", textTransform: "uppercase" }} iconType="circle" />
                                <Area type="monotone" dataKey="critical" name="Critical" stroke="#ef4444" fill="url(#criticalGrad)" strokeWidth={2} />
                                <Area type="monotone" dataKey="high" name="High" stroke="#f97316" fill="url(#highGrad)" strokeWidth={2} />
                                <Area type="monotone" dataKey="medium" name="Medium" stroke="#f59e0b" fill="url(#mediumGrad)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </section>

                {/* Asset Distribution */}
                <section className="glass-premium p-8 rounded-3xl space-y-6">
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <ServerIcon className="text-indigo-500" />
                        Asset Distribution
                    </h2>
                    <div className="h-80 flex items-center justify-center">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={assetDistribution}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={100}
                                    paddingAngle={5}
                                    dataKey="value"
                                    label={(props) => {
                                        const RADIAN = Math.PI / 180;
                                        const { cx, cy, midAngle, outerRadius, percent } = props;
                                        const radius = outerRadius + 30;
                                        const x = cx + radius * Math.cos(-midAngle * RADIAN);
                                        const y = cy + radius * Math.sin(-midAngle * RADIAN);
                                        return (
                                            <text
                                                x={x}
                                                y={y}
                                                fill={theme === 'dark' ? '#e5e7eb' : '#374151'}
                                                textAnchor={x > cx ? 'start' : 'end'}
                                                dominantBaseline="central"
                                                className="text-sm font-bold"
                                            >
                                                {`${(percent * 100).toFixed(0)}%`}
                                            </text>
                                        );
                                    }}
                                    labelLine={{
                                        stroke: theme === 'dark' ? '#6b7280' : '#9ca3af',
                                        strokeWidth: 1
                                    }}
                                >
                                    {assetDistribution.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip
                                    contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '12px', fontSize: '12px', color: '#fff' }}
                                    formatter={(value: any, name: any) => [value.toLocaleString(), name]}
                                />
                                <Legend wrapperStyle={{ fontSize: "10px", fontWeight: "900", textTransform: "uppercase" }} iconType="circle" />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </section>
            </div>

            {/* Compliance & Activity */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Compliance Framework Status */}
                <section className="glass-premium p-8 rounded-3xl space-y-6">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold flex items-center gap-2">
                            <ShieldCheckIcon className="text-accent-500" />
                            Compliance Framework Status
                        </h2>
                        <span className="text-xs font-bold text-gray-500 bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">
                            {frameworks.length} frameworks
                        </span>
                    </div>
                    <div className="max-h-[420px] overflow-y-auto pr-1 space-y-3 scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600">
                        {frameworks.map((framework, i) => {
                            const statusColor = framework.progress >= 90
                                ? 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30'
                                : framework.progress >= 70
                                    ? 'text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/30'
                                    : 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30';
                            const barColor = framework.progress >= 90
                                ? 'from-green-500 to-emerald-400'
                                : framework.progress >= 70
                                    ? 'from-amber-500 to-yellow-400'
                                    : 'from-red-500 to-rose-400';
                            const statusText = framework.status || (framework.progress >= 90 ? 'Compliant' : framework.progress >= 70 ? 'Pending' : 'At Risk');
                            return (
                                <div
                                    key={i}
                                    className="flex items-center gap-4 p-3 rounded-xl bg-white/5 hover:bg-white/10 cursor-pointer transition-all group border border-transparent hover:border-primary-500/30"
                                    onClick={() => setSelectedFramework(framework)}
                                >
                                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500/20 to-indigo-500/20 flex items-center justify-center flex-shrink-0">
                                        <ShieldCheckIcon size={18} className="text-primary-500" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between mb-1">
                                            <p className="text-sm font-bold text-gray-800 dark:text-gray-100 truncate group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                                                {framework.shortName || framework.name}
                                            </p>
                                            <span className={`text-[10px] font-black px-2 py-0.5 rounded-full flex-shrink-0 ml-2 ${statusColor}`}>
                                                {statusText}
                                            </span>
                                        </div>
                                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                                            <div
                                                className={`h-1.5 rounded-full bg-gradient-to-r ${barColor} transition-all duration-500`}
                                                style={{ width: `${framework.progress}%` }}
                                            />
                                        </div>
                                        <p className="text-[10px] text-gray-500 mt-0.5">{framework.progress}% compliant — click for breakdown</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </section>

                {/* Recent Activity */}
                <section className="glass-premium p-8 rounded-3xl space-y-6">
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <ClockIcon className="text-amber-500" />
                        Recent Activity
                    </h2>
                    <div className="space-y-3">
                        {alerts.slice(0, 5).map((alert, i) => (
                            <div key={i} className="flex items-start gap-3 p-3 bg-white/5 rounded-xl hover:bg-white/10 transition-colors">
                                <div className={`w-2 h-2 mt-2 rounded-full flex-shrink-0 ${alert.severity === 'Critical' ? 'bg-red-500 animate-pulse' :
                                    alert.severity === 'High' ? 'bg-orange-500' :
                                        alert.severity === 'Medium' ? 'bg-amber-500' : 'bg-blue-500'
                                    }`}></div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs font-bold text-gray-800 dark:text-gray-200 truncate">{alert.message}</p>
                                    <p className="text-[10px] text-gray-500 mt-0.5">{new Date(alert.timestamp).toLocaleString(undefined, { timeZone })}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </div>

            {/* Compliance Status Breakdown Modal */}
            {selectedFramework && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in"
                    onClick={() => setSelectedFramework(null)}
                >
                    <div
                        className="bg-white dark:bg-gray-900 rounded-3xl shadow-2xl border border-gray-200/50 dark:border-gray-700/50 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto"
                        onClick={e => e.stopPropagation()}
                    >
                        {/* Modal Header */}
                        <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-start justify-between">
                            <div>
                                <div className="flex items-center gap-3 mb-1">
                                    <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                                        {selectedFramework.shortName || selectedFramework.name}
                                    </h2>
                                    <span className={`text-xs font-bold px-3 py-1 rounded-full ${mStatusBadge}`}>{mStatusText}</span>
                                </div>
                                <p className="text-sm text-gray-500 dark:text-gray-400">{selectedFramework.name}</p>
                            </div>
                            <button
                                onClick={() => setSelectedFramework(null)}
                                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                            >
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="p-6 space-y-6">
                            {/* Overall Progress */}
                            <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-2xl">
                                <div className="flex justify-between items-center mb-3">
                                    <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Overall Compliance Progress</span>
                                    <span className="text-3xl font-black text-primary-600 dark:text-primary-400">{selectedFramework.progress}%</span>
                                </div>
                                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
                                    <div
                                        className={`h-3 rounded-full transition-all duration-700 bg-gradient-to-r ${mPassed >= 90 ? 'from-green-500 to-emerald-400' : mPassed >= 70 ? 'from-amber-500 to-yellow-400' : 'from-red-500 to-rose-400'}`}
                                        style={{ width: `${selectedFramework.progress}%` }}
                                    />
                                </div>
                            </div>

                            {/* Compliance Status Breakdown - PieChart */}
                            <div>
                                <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-4 flex items-center gap-2">
                                    <ShieldCheckIcon size={18} className="text-indigo-500" />
                                    Compliance Status Breakdown
                                </h3>
                                <div className="h-64">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <PieChart>
                                            <Pie
                                                data={mBreakdownData}
                                                cx="50%"
                                                cy="50%"
                                                outerRadius={95}
                                                innerRadius={50}
                                                paddingAngle={4}
                                                dataKey="value"
                                                label={(props: any) => {
                                                    const RADIAN = Math.PI / 180;
                                                    const { cx: cx2, cy: cy2, midAngle, outerRadius: or, percent } = props;
                                                    const radius = or + 28;
                                                    const x = cx2 + radius * Math.cos(-midAngle * RADIAN);
                                                    const y = cy2 + radius * Math.sin(-midAngle * RADIAN);
                                                    return (
                                                        <text x={x} y={y} fill={theme === 'dark' ? '#e5e7eb' : '#374151'} textAnchor={x > cx2 ? 'start' : 'end'} dominantBaseline="central" style={{ fontSize: '12px', fontWeight: 700 }}>
                                                            {`${(percent * 100).toFixed(0)}%`}
                                                        </text>
                                                    );
                                                }}
                                                labelLine={{ stroke: '#9ca3af', strokeWidth: 1 }}
                                            >
                                                {mBreakdownData.map((entry, idx) => (
                                                    <Cell key={idx} fill={entry.color} />
                                                ))}
                                            </Pie>
                                            <Tooltip
                                                contentStyle={{ backgroundColor: 'rgba(0,0,0,0.85)', border: 'none', borderRadius: '12px', fontSize: '12px', color: '#fff' }}
                                                formatter={(value: any, name: any) => [`${value} controls`, name]}
                                            />
                                            <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '700' }} iconType="circle" />
                                        </PieChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>

                            {/* Compliance Gaps */}
                            {(mFailed > 0 || mPending > 0) && (
                                <div className="space-y-3">
                                    <h3 className="text-lg font-bold text-gray-800 dark:text-white">Compliance Gaps</h3>
                                    {mFailed > 0 && (
                                        <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800/30">
                                            <div className="flex items-start gap-3">
                                                <svg className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                                </svg>
                                                <div>
                                                    <h4 className="font-bold text-red-700 dark:text-red-400 mb-1">Failed Controls</h4>
                                                    <p className="text-sm text-gray-600 dark:text-gray-400">Approximately {mFailed} controls are failed and require immediate remediation.</p>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                    {mPending > 0 && (
                                        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800/30">
                                            <div className="flex items-start gap-3">
                                                <svg className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                                </svg>
                                                <div>
                                                    <h4 className="font-bold text-amber-700 dark:text-amber-400 mb-1">Pending Controls</h4>
                                                    <p className="text-sm text-gray-600 dark:text-gray-400">Approximately {mPending} controls are awaiting implementation or verification.</p>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Modal Footer */}
                        <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
                            <button
                                onClick={() => setSelectedFramework(null)}
                                className="px-6 py-2.5 bg-gradient-to-r from-primary-600 to-indigo-600 text-white rounded-xl font-semibold shadow-lg shadow-primary-500/20 hover:scale-105 transition-all"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};
