import React, { useState, useEffect, useContext } from 'react';
import {
    Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
    ResponsiveContainer, ComposedChart, Line, Area, Bar, XAxis, YAxis,
    CartesianGrid, Tooltip, Legend, Treemap, Cell
} from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';
import * as api from '../services/apiService';
import {
    TrendingUpIcon, ShieldCheckIcon, ActivityIcon,
    ZapIcon, BarChart3Icon, PieChartIcon, FilterIcon
} from './icons';

export const AdvancedBiDashboard: React.FC<{ tenantId?: string }> = ({ tenantId }) => {
    const { theme } = useContext(ThemeContext);
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadData();
    }, [tenantId]);

    const loadData = async () => {
        setLoading(true);
        const result = await api.fetchBiMetrics(tenantId);
        if (result) {
            setData(result);
        }
        setLoading(false);
    };

    const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
            </div>
        );
    }

    if (!data) {
        return <div className="p-10 text-center text-slate-500">Failed to load BI metrics.</div>;
    }

    return (
        <div className="p-6 space-y-8 bg-slate-50 dark:bg-slate-900 min-h-screen">
            {/* Header */}
            <div className="flex justify-between items-end">
                <div>
                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Advanced BI Analytics</h1>
                    <p className="text-slate-500 dark:text-slate-400">Deep operational insights and predictive risk modeling.</p>
                </div>
                <div className="flex space-x-3">
                    <button className="flex items-center px-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors">
                        <FilterIcon size={16} className="mr-2" /> Filter
                    </button>
                    <button className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors">
                        Export Report
                    </button>
                </div>
            </div>

            {/* Top Stats */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {[
                    { label: 'Avg MTTR', value: `${data.efficiency.mttr}h`, icon: ActivityIcon, color: 'text-blue-500', bg: 'bg-blue-500/10' },
                    { label: 'Automation Rate', value: `${data.efficiency.automation_rate}%`, icon: ZapIcon, color: 'text-amber-500', bg: 'bg-amber-500/10' },
                    { label: 'Patch Success', value: `${data.efficiency.patch_success_rate}%`, icon: ShieldCheckIcon, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
                    { label: 'Remediation Velocity', value: `${data.efficiency.remediation_velocity}/d`, icon: TrendingUpIcon, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
                ].map((stat, i) => (
                    <div key={i} className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm">
                        <div className="flex items-center justify-between mb-4">
                            <div className={`${stat.bg} p-3 rounded-xl`}>
                                <stat.icon size={24} className={stat.color} />
                            </div>
                            <span className="text-xs font-bold text-emerald-500">+12%</span>
                        </div>
                        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{stat.label}</p>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Main Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Risk Profile Radar */}
                <div className="bg-white dark:bg-slate-800 p-8 rounded-3xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-6 flex items-center">
                        <ShieldCheckIcon size={20} className="mr-2 text-indigo-500" /> Multi-dimensional Risk Profile
                    </h3>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data.risk_profile}>
                                <PolarGrid stroke={theme === 'dark' ? '#334155' : '#e2e8f0'} />
                                <PolarAngleAxis dataKey="subject" tick={{ fill: theme === 'dark' ? '#94a3b8' : '#64748b', fontSize: 12 }} />
                                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                                <Radar
                                    name="Current Risk"
                                    dataKey="A"
                                    stroke="#6366f1"
                                    fill="#6366f1"
                                    fillOpacity={0.5}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: theme === 'dark' ? '#1e293b' : '#ffffff', border: 'none', borderRadius: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                                />
                            </RadarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Predictive Trends */}
                <div className="bg-white dark:bg-slate-800 p-8 rounded-3xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-6 flex items-center">
                        <TrendingUpIcon size={20} className="mr-2 text-emerald-500" /> Security Posture Forecast
                    </h3>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart data={data.trends}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={theme === 'dark' ? '#334155' : '#f1f5f9'} />
                                <XAxis
                                    dataKey="name"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: theme === 'dark' ? '#94a3b8' : '#64748b', fontSize: 11 }}
                                />
                                <YAxis
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: theme === 'dark' ? '#94a3b8' : '#64748b', fontSize: 11 }}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: theme === 'dark' ? '#1e293b' : '#ffffff', border: 'none', borderRadius: '12px', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                                />
                                <Legend verticalAlign="top" align="right" iconType="circle" wrapperStyle={{ paddingBottom: '20px', fontSize: '12px' }} />
                                <Area type="monotone" dataKey="forecast" fill="#10b981" fillOpacity={0.1} stroke="none" />
                                <Bar dataKey="actual" barSize={20} fill="#6366f1" radius={[4, 4, 0, 0]} />
                                <Line type="monotone" dataKey="forecast" stroke="#10b981" strokeWidth={3} dot={{ r: 4, fill: '#10b981' }} strokeDasharray="5 5" />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Bottom Section: Treemap & Asset Distribution */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 bg-white dark:bg-slate-800 p-8 rounded-3xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-6 flex items-center">
                        <BarChart3Icon size={20} className="mr-2 text-amber-500" /> Asset Distribution Treemap
                    </h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <Treemap
                                data={data.asset_distribution}
                                dataKey="size"
                                stroke="#fff"
                                fill="#6366f1"
                            >
                                <Tooltip
                                    contentStyle={{ backgroundColor: theme === 'dark' ? '#1e293b' : '#ffffff', border: 'none', borderRadius: '12px' }}
                                />
                            </Treemap>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white dark:bg-slate-800 p-8 rounded-3xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-6 flex items-center">
                        <PieChartIcon size={20} className="mr-2 text-purple-500" /> Quick Insights
                    </h3>
                    <div className="space-y-4">
                        {[
                            { label: 'Critical Assets', value: '12', color: 'bg-red-500' },
                            { label: 'Compliant Nodes', value: '84%', color: 'bg-emerald-500' },
                            { label: 'Cloud Spend', value: '$4.2k', color: 'bg-indigo-500' },
                            { label: 'Risk Score', value: 'Low', color: 'bg-blue-500' },
                        ].map((insight, i) => (
                            <div key={i} className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50">
                                <div className="flex items-center">
                                    <div className={`w-2 h-2 rounded-full ${insight.color} mr-3`}></div>
                                    <span className="text-sm font-medium text-slate-600 dark:text-slate-300">{insight.label}</span>
                                </div>
                                <span className="text-sm font-bold text-slate-900 dark:text-white">{insight.value}</span>
                            </div>
                        ))}
                    </div>
                    <button className="w-full mt-6 py-3 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-sm font-bold hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors">
                        View Detailed Audit
                    </button>
                </div>
            </div>
        </div>
    );
};
