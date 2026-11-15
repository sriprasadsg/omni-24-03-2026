import React, { useState, useEffect, useMemo } from 'react';
import { authFetch } from '../services/apiService';
import { SparklesIcon, ActivityIcon, CpuIcon, RefreshCwIcon, UserIcon } from './icons';
import { Glyph } from './ui/Glyph';

interface RiskScore {
    userId: string;
    userName: string;
    userEmail: string;
    score: number;
    ruleScore: number;
    mlScore: number;
    reasons: string[];
    lastCalculated: string;
}

const SCORE_CLS = (s: number) => {
    if (s >= 80) return 'text-red-600 dark:text-red-400';
    if (s >= 50) return 'text-orange-700 dark:text-orange-400';
    if (s >= 20) return 'text-yellow-700 dark:text-yellow-400';
    return 'text-green-600 dark:text-green-400';
};

const DELTA_CLS = (d: number) => {
    if (d >= 20) return 'text-red-600 dark:text-red-400 font-bold';
    if (d >= 5)  return 'text-orange-700 dark:text-orange-400';
    if (d <= -5) return 'text-green-600 dark:text-green-400';
    return 'text-gray-600 dark:text-gray-400';
};

export const AIAnomalyDashboard: React.FC = () => {
    const [uebaScores, setUebaScores] = useState<RiskScore[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = async (silent = false) => {
        if (!silent) setLoading(true); else setRefreshing(true);
        setError(null);
        try {
            const uebaRes = await authFetch('/api/ueba/risk-scores').then(r => r.ok ? r.json() : { results: [] });
            setUebaScores(uebaRes.results || []);
        } catch (e) {
            setError('Failed to load anomaly data. Check your connection and try again.');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    useEffect(() => { load(); }, []);

    const topDeviators = useMemo(() =>
        [...uebaScores].sort((a, b) => b.mlScore - a.mlScore).slice(0, 12),
    [uebaScores]);

    const aiOnlyCount = useMemo(() =>
        uebaScores.filter(u => u.mlScore - u.ruleScore >= 15).length,
    [uebaScores]);

    const summaryCards = [
        {
            label: 'High-Risk Users',
            value: uebaScores.filter(u => u.mlScore >= 50).length,
            sub: 'AI score ≥ 50',
            color: 'text-red-600 dark:text-red-400',
            border: 'border-l-red-500',
            icon: <UserIcon size={18} className="text-red-600 dark:text-red-400" />,
        },
        {
            label: 'AI-Only Detections',
            value: aiOnlyCount,
            sub: 'ML leads rules by ≥15pts',
            color: 'text-orange-700 dark:text-orange-400',
            border: 'border-l-orange-500',
            icon: <SparklesIcon size={18} className="text-orange-700 dark:text-orange-400" />,
        },
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-600 dark:text-slate-400">
                <CpuIcon size={20} className="animate-spin mr-2" />
                Loading anomaly signals…
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {error && (
                <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-300 text-sm">
                    <span className="shrink-0"><Glyph e="⚠" /></span>
                    {error}
                    <button onClick={() => load(true)} className="ml-auto underline hover:no-underline">Retry</button>
                </div>
            )}
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="page-title flex items-center gap-2">
                        <SparklesIcon size={22} className="text-purple-600 dark:text-purple-400" />
                        AI Anomaly Detection
                    </h1>
                    <p className="text-sm text-gray-600 dark:text-slate-400 mt-0.5">
                        Behavioral deviation scores from UEBA (ML model)
                    </p>
                </div>
                <button
                    onClick={() => load(true)}
                    disabled={refreshing}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-700 dark:text-slate-300 border border-gray-300 dark:border-slate-600 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 disabled:opacity-50"
                >
                    <RefreshCwIcon size={14} className={refreshing ? 'animate-spin' : ''} />
                    Refresh
                </button>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 gap-3">
                {summaryCards.map(({ label, value, sub, color, border, icon }) => (
                    <div key={label} className={`bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700 border-l-4 ${border}`}>
                        <div className="flex items-center gap-2 mb-1">
                            {icon}
                            <p className="text-xs text-gray-600 dark:text-gray-400">{label}</p>
                        </div>
                        <p className={`text-2xl font-bold ${color}`}>{value}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{sub}</p>
                    </div>
                ))}
            </div>

            <div>
                {/* UEBA: Behavioral Deviators */}
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                        <ActivityIcon size={16} className="text-purple-600 dark:text-purple-400" />
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">Behavioral Deviators</span>
                        <span className="ml-auto text-xs text-gray-500">UEBA · sorted by AI score</span>
                    </div>
                    {topDeviators.length === 0 ? (
                        <div className="px-4 py-10 text-center text-gray-500 text-sm">No UEBA scores found</div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="text-xs uppercase bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-400">
                                    <tr>
                                        <th className="px-4 py-2 text-left">User</th>
                                        <th className="px-4 py-2 text-right">AI</th>
                                        <th className="px-4 py-2 text-right">Rules</th>
                                        <th className="px-4 py-2 text-right" title="mlScore − ruleScore">Delta</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-200 dark:divide-gray-700/50">
                                    {topDeviators.map(u => {
                                        const delta = u.mlScore - u.ruleScore;
                                        return (
                                            <tr key={u.userId} className="hover:bg-gray-100 dark:hover:bg-gray-700/30">
                                                <td className="px-4 py-2.5">
                                                    <p className="font-medium text-gray-800 dark:text-gray-200 text-xs leading-tight truncate max-w-[140px]">{u.userName}</p>
                                                    <p className="text-gray-500 text-xs truncate max-w-[140px]">{u.userEmail}</p>
                                                </td>
                                                <td className="px-4 py-2.5 text-right">
                                                    <span className={`font-bold text-base ${SCORE_CLS(u.mlScore)}`}>{u.mlScore}</span>
                                                </td>
                                                <td className="px-4 py-2.5 text-right text-gray-600 dark:text-gray-400 text-xs">{u.ruleScore}</td>
                                                <td className="px-4 py-2.5 text-right">
                                                    <span className={`text-xs ${DELTA_CLS(delta)}`}>
                                                        {delta >= 0 ? '+' : ''}{delta}
                                                    </span>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>

            {/* Legend */}
            <div className="text-xs text-gray-600 space-y-0.5">
                <p><span className="text-orange-700 dark:text-orange-400 font-semibold">Delta (AI − Rules)</span>: positive = AI model flags risk the rules missed; negative = rules caught it, AI uncertain</p>
            </div>
        </div>
    );
};
