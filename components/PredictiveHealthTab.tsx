import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, AreaChart, Area } from 'recharts';
import { LightbulbIcon, TrendingUpIcon, AlertTriangleIcon, ActivityIcon, ServerIcon, CpuIcon } from './icons';

interface PredictiveHealthTabProps {
    data?: {
        current_score: number;
        predictions: Array<{
            timestamp: string;
            cpu_prediction: number;
            memory_prediction: number;
            health_score: number;
        }>;
        warnings: string[];
    };
}

export const PredictiveHealthTab: React.FC<PredictiveHealthTabProps> = ({ data }) => {
    if (!data || !data.predictions || data.predictions.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-16 px-4">
                <div className="bg-slate-100 dark:bg-slate-800 p-4 rounded-full mb-6 relative">
                    <div className="absolute inset-0 bg-blue-400/20 rounded-full animate-pulse"></div>
                    <LightbulbIcon size={48} className="text-slate-400 relative z-10" />
                </div>
                <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Predictive Analytics Inactive</h3>
                <p className="text-slate-500 dark:text-slate-400 text-center max-w-md mb-8">
                    Not enough historical data to generate AI forecasts. The agent needs to run for at least 24 hours to build a predictive model.
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
                    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 rounded-lg shadow-sm">
                        <div className="flex items-center gap-3 mb-2">
                            <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-md">
                                <ActivityIcon size={18} className="text-blue-600 dark:text-blue-400" />
                            </div>
                            <h4 className="font-semibold text-slate-900 dark:text-slate-100">Data Requirements</h4>
                        </div>
                        <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-2 pl-1">
                            <li className="flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                                Minimum 50 data samples
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                                24H continuous runtime
                            </li>
                        </ul>
                    </div>

                    <div className="border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 rounded-lg shadow-sm">
                        <div className="flex items-center gap-3 mb-2">
                            <div className="p-2 bg-purple-50 dark:bg-purple-900/30 rounded-md">
                                <TrendingUpIcon size={18} className="text-purple-600 dark:text-purple-400" />
                            </div>
                            <h4 className="font-semibold text-slate-900 dark:text-slate-100">Future Capabilities</h4>
                        </div>
                        <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-2 pl-1">
                            <li className="flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                                CPU & Memory Forecasting
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                                Bottleneck Detection
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        );
    }

    const getScoreColor = (score: number) => {
        if (score >= 80) return 'text-emerald-600 dark:text-emerald-400';
        if (score >= 60) return 'text-amber-500 dark:text-amber-400';
        return 'text-rose-600 dark:text-rose-400';
    };

    const getScoreBg = (score: number) => {
        if (score >= 80) return 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-100 dark:border-emerald-800';
        if (score >= 60) return 'bg-amber-50 dark:bg-amber-900/20 border-amber-100 dark:border-amber-800';
        return 'bg-rose-50 dark:bg-rose-900/20 border-rose-100 dark:border-rose-800';
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Top Cards: Health Score & Warnings */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Health Score Card */}
                <div className={`col-span-1 rounded-xl p-6 border ${getScoreBg(data.current_score)} relative overflow-hidden`}>
                    <div className="relative z-10">
                        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1">AI Health Score</h3>
                        <div className="flex items-baseline gap-2">
                            <span className={`text-5xl font-bold ${getScoreColor(data.current_score)}`}>
                                {data.current_score}
                            </span>
                            <span className="text-slate-400 text-sm">/ 100</span>
                        </div>
                        <div className="mt-4 flex items-center gap-2">
                            <div className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${data.current_score >= 80 ? 'bg-emerald-100 text-emerald-700 border-emerald-200' :
                                    data.current_score >= 60 ? 'bg-amber-100 text-amber-700 border-amber-200' :
                                        'bg-rose-100 text-rose-700 border-rose-200'
                                }`}>
                                {data.current_score >= 80 ? 'Optimized' : data.current_score >= 60 ? 'Degrading' : 'Critical'}
                            </div>
                            <span className="text-xs text-slate-500">Updated just now</span>
                        </div>
                    </div>
                    {/* Background decoration */}
                    <ActivityIcon size={120} className="absolute -right-4 -bottom-4 opacity-5 text-current transform rotate-12" />
                </div>

                {/* Warnings / Insights Panel */}
                <div className="col-span-1 lg:col-span-2 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
                    <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-blue-500 to-purple-600"></div>
                    <div className="flex items-start justify-between mb-4">
                        <div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <LightbulbIcon size={20} className="text-amber-400 fill-amber-400" />
                                AI Insights & Risks
                            </h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                                Anomaly detection and capacity forecasting
                            </p>
                        </div>
                    </div>

                    <div className="space-y-3">
                        {data.warnings && data.warnings.length > 0 ? (
                            data.warnings.map((warning, idx) => (
                                <div key={idx} className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50 border border-slate-100 dark:border-slate-700">
                                    <AlertTriangleIcon size={18} className="text-amber-500 shrink-0 mt-0.5" />
                                    <span className="text-sm text-slate-700 dark:text-slate-300 font-medium">{warning}</span>
                                </div>
                            ))
                        ) : (
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-100 dark:border-emerald-800">
                                <div className="p-1 bg-emerald-100 rounded-full">
                                    <TrendingUpIcon size={14} className="text-emerald-600" />
                                </div>
                                <span className="text-sm text-emerald-700 dark:text-emerald-400 font-medium">No predicted risks for the next 24 hours.</span>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Main Forecast Chart */}
            <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h3 className="text-base font-bold text-slate-900 dark:text-white">24-Hour Health Forecast</h3>
                        <p className="text-xs text-slate-500">Projected system stability based on historical usage patterns</p>
                    </div>
                </div>
                <div className="h-[250px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data.predictions}>
                            <defs>
                                <linearGradient id="colorHealth" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                            <XAxis
                                dataKey="timestamp"
                                tick={{ fontSize: 11, fill: '#64748b' }}
                                axisLine={false}
                                tickLine={false}
                                minTickGap={30}
                            />
                            <YAxis
                                domain={[0, 100]}
                                tick={{ fontSize: 11, fill: '#64748b' }}
                                axisLine={false}
                                tickLine={false}
                                tickFormatter={(value) => `${value}%`}
                            />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: 'rgba(255, 255, 255, 0.95)',
                                    border: '1px solid #e2e8f0',
                                    borderRadius: '0.5rem',
                                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                                }}
                                itemStyle={{ color: '#1e293b', fontSize: '12px', fontWeight: 500 }}
                                labelStyle={{ color: '#64748b', marginBottom: '4px', fontSize: '11px' }}
                            />
                            <ReferenceLine y={60} stroke="#f59e0b" strokeDasharray="3 3" />
                            <Area
                                type="monotone"
                                dataKey="health_score"
                                stroke="#3b82f6"
                                strokeWidth={3}
                                fillOpacity={1}
                                fill="url(#colorHealth)"
                                name="Health Score"
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Resource Charts Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

                {/* CPU Forecast */}
                <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                        <CpuIcon size={18} className="text-slate-400" />
                        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">CPU Usage Forecast</h4>
                    </div>
                    <div className="h-[180px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={data.predictions}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis dataKey="timestamp" hide />
                                <YAxis domain={[0, 100]} hide />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#fff', borderRadius: '0.5rem', border: '1px solid #e2e8f0' }}
                                    formatter={(value: number) => [`${value}%`, 'CPU']}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="cpu_prediction"
                                    stroke="#f59e0b"
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 4 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Memory Forecast */}
                <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                        <ServerIcon size={18} className="text-slate-400" />
                        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">Memory Trend Forecast</h4>
                    </div>
                    <div className="h-[180px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={data.predictions}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis dataKey="timestamp" hide />
                                <YAxis domain={[0, 100]} hide />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#fff', borderRadius: '0.5rem', border: '1px solid #e2e8f0' }}
                                    formatter={(value: number) => [`${value}%`, 'Memory']}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="memory_prediction"
                                    stroke="#8b5cf6"
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 4 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
};
