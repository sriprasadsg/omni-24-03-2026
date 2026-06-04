import React, { useState, useEffect, useMemo } from 'react';
import { authFetch } from '../services/apiService';
import { SparklesIcon, ActivityIcon, WifiIcon, CpuIcon, RefreshCwIcon, UserIcon } from './icons';

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

interface NDRAnomaly {
    id: string;
    type: string;
    severity: string;
    description: string;
    src_ip: string;
    dst_ip: string;
    protocol: string;
    confidence: number;
    detected_at: string;
    mitre_technique: string;
    status: string;
}

const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

const SEV_CLS: Record<string, string> = {
    critical: 'bg-red-900/40 text-red-300 border border-red-700',
    high: 'bg-orange-900/40 text-orange-300 border border-orange-700',
    medium: 'bg-yellow-900/40 text-yellow-300 border border-yellow-700',
    low: 'bg-gray-700 text-gray-300 border border-gray-600',
};

const SCORE_CLS = (s: number) => {
    if (s >= 80) return 'text-red-400';
    if (s >= 50) return 'text-orange-400';
    if (s >= 20) return 'text-yellow-400';
    return 'text-green-400';
};

const DELTA_CLS = (d: number) => {
    if (d >= 20) return 'text-red-400 font-bold';
    if (d >= 5)  return 'text-orange-400';
    if (d <= -5) return 'text-green-400';
    return 'text-gray-400';
};

const NDR_ICONS: Record<string, string> = {
    lateral_movement: '↔', data_exfiltration: '↑', port_scan: '⊛',
    dns_tunneling: '◉', c2_beacon: '⊕', brute_force: '⊗',
    protocol_anomaly: '⚠', bandwidth_spike: '↟', new_external_connection: '⊙',
};

export const AIAnomalyDashboard: React.FC = () => {
    const [uebaScores, setUebaScores] = useState<RiskScore[]>([]);
    const [ndrAnomalies, setNdrAnomalies] = useState<NDRAnomaly[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = async (silent = false) => {
        if (!silent) setLoading(true); else setRefreshing(true);
        setError(null);
        try {
            const [uebaRes, ndrRes] = await Promise.all([
                authFetch('/api/ueba/risk-scores').then(r => r.ok ? r.json() : { results: [] }),
                authFetch('/api/ndr/anomalies?limit=50').then(r => r.ok ? r.json() : { anomalies: [] }),
            ]);
            setUebaScores(uebaRes.results || []);
            setNdrAnomalies(ndrRes.anomalies || []);
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

    const sortedNdr = useMemo(() =>
        [...ndrAnomalies].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)).slice(0, 12),
    [ndrAnomalies]);

    const aiOnlyCount = useMemo(() =>
        uebaScores.filter(u => u.mlScore - u.ruleScore >= 15).length,
    [uebaScores]);

    const criticalNdr = useMemo(() =>
        ndrAnomalies.filter(a => a.severity === 'critical').length,
    [ndrAnomalies]);

    const summaryCards = [
        {
            label: 'High-Risk Users',
            value: uebaScores.filter(u => u.mlScore >= 50).length,
            sub: 'AI score ≥ 50',
            color: 'text-red-400',
            border: 'border-l-red-500',
            icon: <UserIcon size={18} className="text-red-400" />,
        },
        {
            label: 'AI-Only Detections',
            value: aiOnlyCount,
            sub: 'ML leads rules by ≥15pts',
            color: 'text-orange-400',
            border: 'border-l-orange-500',
            icon: <SparklesIcon size={18} className="text-orange-400" />,
        },
        {
            label: 'Network Anomalies',
            value: ndrAnomalies.length,
            sub: 'open NDR alerts',
            color: 'text-blue-400',
            border: 'border-l-blue-500',
            icon: <WifiIcon size={18} className="text-blue-400" />,
        },
        {
            label: 'Critical Network',
            value: criticalNdr,
            sub: 'critical severity',
            color: 'text-red-400',
            border: 'border-l-red-700',
            icon: <CpuIcon size={18} className="text-red-400" />,
        },
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64 text-slate-400">
                <CpuIcon size={20} className="animate-spin mr-2" />
                Loading anomaly signals…
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {error && (
                <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
                    <span className="shrink-0">⚠</span>
                    {error}
                    <button onClick={() => load(true)} className="ml-auto underline hover:no-underline">Retry</button>
                </div>
            )}
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                        <SparklesIcon size={22} className="text-purple-400" />
                        AI Anomaly Detection
                    </h2>
                    <p className="text-sm text-slate-400 mt-0.5">
                        Behavioral deviation scores aggregated from UEBA (ML model) and NDR (network baseline)
                    </p>
                </div>
                <button
                    onClick={() => load(true)}
                    disabled={refreshing}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 border border-slate-600 rounded-lg hover:bg-slate-700 disabled:opacity-50"
                >
                    <RefreshCwIcon size={14} className={refreshing ? 'animate-spin' : ''} />
                    Refresh
                </button>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {summaryCards.map(({ label, value, sub, color, border, icon }) => (
                    <div key={label} className={`bg-gray-800 rounded-lg p-4 border border-gray-700 border-l-4 ${border}`}>
                        <div className="flex items-center gap-2 mb-1">
                            {icon}
                            <p className="text-xs text-gray-400">{label}</p>
                        </div>
                        <p className={`text-2xl font-bold ${color}`}>{value}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{sub}</p>
                    </div>
                ))}
            </div>

            {/* Two-panel layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* UEBA: Behavioral Deviators */}
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
                        <ActivityIcon size={16} className="text-purple-400" />
                        <span className="text-sm font-semibold text-white">Behavioral Deviators</span>
                        <span className="ml-auto text-xs text-gray-500">UEBA · sorted by AI score</span>
                    </div>
                    {topDeviators.length === 0 ? (
                        <div className="px-4 py-10 text-center text-gray-500 text-sm">No UEBA scores found</div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="text-xs uppercase bg-gray-700/50 text-gray-400">
                                    <tr>
                                        <th className="px-4 py-2 text-left">User</th>
                                        <th className="px-4 py-2 text-right">AI</th>
                                        <th className="px-4 py-2 text-right">Rules</th>
                                        <th className="px-4 py-2 text-right" title="mlScore − ruleScore">Delta</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-700/50">
                                    {topDeviators.map(u => {
                                        const delta = u.mlScore - u.ruleScore;
                                        return (
                                            <tr key={u.userId} className="hover:bg-gray-700/30">
                                                <td className="px-4 py-2.5">
                                                    <p className="font-medium text-gray-200 text-xs leading-tight truncate max-w-[140px]">{u.userName}</p>
                                                    <p className="text-gray-500 text-xs truncate max-w-[140px]">{u.userEmail}</p>
                                                </td>
                                                <td className="px-4 py-2.5 text-right">
                                                    <span className={`font-bold text-base ${SCORE_CLS(u.mlScore)}`}>{u.mlScore}</span>
                                                </td>
                                                <td className="px-4 py-2.5 text-right text-gray-400 text-xs">{u.ruleScore}</td>
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

                {/* NDR: Network Anomalies */}
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
                        <WifiIcon size={16} className="text-blue-400" />
                        <span className="text-sm font-semibold text-white">Network Anomalies</span>
                        <span className="ml-auto text-xs text-gray-500">NDR · sorted by severity</span>
                    </div>
                    {sortedNdr.length === 0 ? (
                        <div className="px-4 py-10 text-center text-gray-500 text-sm">No network anomalies detected</div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="text-xs uppercase bg-gray-700/50 text-gray-400">
                                    <tr>
                                        <th className="px-4 py-2 text-left">Type</th>
                                        <th className="px-4 py-2 text-left">Severity</th>
                                        <th className="px-4 py-2 text-right">Conf.</th>
                                        <th className="px-4 py-2 text-left">MITRE</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-700/50">
                                    {sortedNdr.map(a => (
                                        <tr key={a.id} className="hover:bg-gray-700/30">
                                            <td className="px-4 py-2.5">
                                                <span className="mr-1.5 text-xs">{NDR_ICONS[a.type] || '?'}</span>
                                                <span className="text-gray-200 text-xs">{a.type.replace(/_/g, ' ')}</span>
                                                <p className="text-gray-500 text-xs mt-0.5 font-mono">{a.src_ip} → {a.dst_ip}</p>
                                            </td>
                                            <td className="px-4 py-2.5">
                                                <span className={`px-1.5 py-0.5 rounded text-xs capitalize ${SEV_CLS[a.severity] || SEV_CLS.low}`}>
                                                    {a.severity}
                                                </span>
                                            </td>
                                            <td className="px-4 py-2.5 text-right">
                                                <span className={`text-xs font-mono ${a.confidence >= 80 ? 'text-red-400' : a.confidence >= 60 ? 'text-orange-400' : 'text-gray-400'}`}>
                                                    {a.confidence ?? '—'}%
                                                </span>
                                            </td>
                                            <td className="px-4 py-2.5">
                                                {a.mitre_technique
                                                    ? <span className="text-xs font-mono text-indigo-400">{a.mitre_technique}</span>
                                                    : <span className="text-xs text-gray-600">—</span>
                                                }
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>

            {/* Legend */}
            <div className="text-xs text-gray-600 space-y-0.5">
                <p><span className="text-orange-400 font-semibold">Delta (AI − Rules)</span>: positive = AI model flags risk the rules missed; negative = rules caught it, AI uncertain</p>
                <p><span className="text-indigo-400 font-semibold">MITRE</span>: ATT&CK technique ID linked to the detected network behavior pattern</p>
            </div>
        </div>
    );
};
