import React from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { ShieldCheckIcon } from './icons';

interface Props {
    framework: any;
    theme: string;
    onClose: () => void;
}

export function ComplianceFrameworkModal({ framework, theme, onClose }: Props) {
    const mPassed = framework?.progress ?? 0;
    const mRemaining = 100 - mPassed;
    const mFailed = framework?.status === 'At Risk' ? Math.round(mRemaining * 0.7) : Math.round(mRemaining * 0.3);
    const mPending = mRemaining - mFailed;
    const mBreakdownData = [
        { name: 'Passed', value: Math.round(mPassed), color: '#10b981' },
        { name: 'Failed', value: mFailed, color: '#ef4444' },
        { name: 'Pending', value: mPending, color: '#f59e0b' },
    ].filter(d => d.value > 0);
    const mStatusText = framework?.status || (mPassed >= 90 ? 'Compliant' : mPassed >= 70 ? 'Pending' : 'At Risk');
    const mStatusBadge = mPassed >= 90
        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        : mPassed >= 70
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in"
            onClick={onClose}>
            <div className="bg-white dark:bg-gray-900 rounded-3xl shadow-2xl border border-gray-200/50 dark:border-gray-700/50 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto"
                onClick={e => e.stopPropagation()}>
                <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-start justify-between">
                    <div>
                        <div className="flex items-center gap-3 mb-1">
                            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                                {framework.shortName || framework.name}
                            </h2>
                            <span className={`text-xs font-bold px-3 py-1 rounded-full ${mStatusBadge}`}>{mStatusText}</span>
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{framework.name}</p>
                    </div>
                    <button onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="p-6 space-y-6">
                    <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-2xl">
                        <div className="flex justify-between items-center mb-3">
                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Overall Compliance Progress</span>
                            <span className="text-3xl font-black text-primary-600 dark:text-primary-400">{framework.progress}%</span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
                            <div className={`h-3 rounded-full transition-all duration-700 bg-gradient-to-r ${mPassed >= 90 ? 'from-green-500 to-emerald-400' : mPassed >= 70 ? 'from-amber-500 to-yellow-400' : 'from-red-500 to-rose-400'}`}
                                style={{ width: `${framework.progress}%` }} />
                        </div>
                    </div>

                    <div>
                        <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-4 flex items-center gap-2">
                            <ShieldCheckIcon size={18} className="text-indigo-500" />
                            Compliance Status Breakdown
                        </h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={mBreakdownData} cx="50%" cy="50%" outerRadius={95} innerRadius={50} paddingAngle={4} dataKey="value"
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
                                        labelLine={{ stroke: '#9ca3af', strokeWidth: 1 }}>
                                        {mBreakdownData.map((entry, idx) => (
                                            <Cell key={idx} fill={entry.color} />
                                        ))}
                                    </Pie>
                                    <Tooltip contentStyle={{ backgroundColor: 'rgba(0,0,0,0.85)', border: 'none', borderRadius: '12px', fontSize: '12px', color: '#fff' }}
                                        formatter={(value: any, name: any) => [`${value} controls`, name]} />
                                    <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '700' }} iconType="circle" />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

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

                <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
                    <button onClick={onClose}
                        className="px-6 py-2.5 bg-gradient-to-r from-primary-600 to-indigo-600 text-white rounded-xl font-semibold shadow-lg shadow-primary-500/20 hover:scale-105 transition-all">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}
