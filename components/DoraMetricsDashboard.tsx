import React, { useContext } from 'react';
import { DoraMetrics } from '../types';
import { GaugeIcon, GitPullRequestDraftIcon, ClockIcon, AlertTriangleIcon, RefreshCwIcon } from './icons';
import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';

interface DoraMetricsDashboardProps {
    metrics: DoraMetrics[];
}

const StatCard: React.FC<{ title: string; value: string; icon: React.ReactNode; color: string }> = ({ title, value, icon, color }) => (
    <div className={`glass-premium p-6 rounded-3xl flex items-center gap-4 group transition-all hover:scale-105 border-l-4 ${color}`}>
        <div className="p-3 bg-white/5 rounded-2xl group-hover:bg-white/10 transition-colors">
            {icon}
        </div>
        <div>
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{title}</p>
            <p className="text-3xl font-black text-gray-800 dark:text-gray-100 italic tracking-tighter">{value}</p>
        </div>
    </div>
);


export const DoraMetricsDashboard: React.FC<DoraMetricsDashboardProps> = ({ metrics }) => {
    const { theme } = useContext(ThemeContext);
    const gridColor = theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';
    const textColor = theme === 'dark' ? '#9ca3af' : '#4b5563';

    const latestMetrics: DoraMetrics = metrics[metrics.length - 1] || {
        tenantId: '',
        date: '',
        deploymentFrequency: 0,
        leadTimeForChanges: 0,
        changeFailureRate: 0,
        meanTimeToRecovery: 0,
    };

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent flex items-center gap-3">
                    <GaugeIcon size={36} className="text-indigo-500" />
                    DORA Metrics
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Measure and improve your DevOps performance with industry-standard metrics.
                </p>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard title="Deploy Frequency" value={`${latestMetrics.deploymentFrequency}/day`} icon={<GitPullRequestDraftIcon size={24} className="text-indigo-500" />} color="border-indigo-500" />
                <StatCard title="Lead Time" value={`${latestMetrics.leadTimeForChanges} hrs`} icon={<ClockIcon size={24} className="text-purple-500" />} color="border-purple-500" />
                <StatCard title="Failure Rate" value={`${latestMetrics.changeFailureRate}%`} icon={<AlertTriangleIcon size={24} className="text-pink-500" />} color="border-pink-500" />
                <StatCard title="Recovery MTTR" value={`${latestMetrics.meanTimeToRecovery} hrs`} icon={<RefreshCwIcon size={24} className="text-rose-500" />} color="border-rose-500" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div className="glass-premium p-8 rounded-3xl shadow-2xl overflow-hidden">
                    <h3 className="text-xl font-bold mb-8 flex items-center gap-2 italic uppercase tracking-tighter">
                        <div className="h-2 w-2 rounded-full bg-indigo-500" />
                        Velocity: Velocity & Lead Time
                    </h3>
                    <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={metrics}>
                                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                                <XAxis dataKey="date" stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis yAxisId="left" stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis yAxisId="right" orientation="right" stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '12px', fontSize: '12px', color: '#fff' }}
                                    itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                                />
                                <Legend wrapperStyle={{ fontSize: "10px", fontWeight: "900", textTransform: "uppercase" }} iconType="circle" />
                                <Bar yAxisId="left" dataKey="deploymentFrequency" name="Deploy/Day" fill="url(#bar-grad-1)" radius={[4, 4, 0, 0]} />
                                <Bar yAxisId="right" dataKey="leadTimeForChanges" name="Lead Time (hrs)" fill="url(#bar-grad-2)" radius={[4, 4, 0, 0]} />
                                <defs>
                                    <linearGradient id="bar-grad-1" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#6366f1" />
                                        <stop offset="100%" stopColor="#4f46e5" />
                                    </linearGradient>
                                    <linearGradient id="bar-grad-2" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#a855f7" />
                                        <stop offset="100%" stopColor="#9333ea" />
                                    </linearGradient>
                                </defs>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="glass-premium p-8 rounded-3xl shadow-2xl overflow-hidden">
                    <h3 className="text-xl font-bold mb-8 flex items-center gap-2 italic uppercase tracking-tighter">
                        <div className="h-2 w-2 rounded-full bg-rose-500" />
                        Stability: MTTR & Failure Rate
                    </h3>
                    <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={metrics}>
                                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                                <XAxis dataKey="date" stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke={textColor} fontSize={10} tickLine={false} axisLine={false} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: '12px', fontSize: '12px', color: '#fff' }}
                                    itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                                />
                                <Legend wrapperStyle={{ fontSize: "10px", fontWeight: "900", textTransform: "uppercase" }} iconType="circle" />
                                <Area type="monotone" dataKey="changeFailureRate" name="Failure Rate (%)" stroke="#f43f5e" fill="url(#area-grad-1)" strokeWidth={3} />
                                <Area type="monotone" dataKey="meanTimeToRecovery" name="MTTR (hrs)" stroke="#ec4899" fill="url(#area-grad-2)" strokeWidth={3} />
                                <defs>
                                    <linearGradient id="area-grad-1" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#f43f5e" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="area-grad-2" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#ec4899" stopOpacity={0.3} />
                                        <stop offset="100%" stopColor="#ec4899" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
};
