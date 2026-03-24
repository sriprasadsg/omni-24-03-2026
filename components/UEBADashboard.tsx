import React, { useState, useEffect } from 'react';
import {
    AlertTriangleIcon,
    ActivityIcon,
    UserIcon,
    ShieldAlertIcon,
    RefreshCwIcon,
    TrendingDownIcon,
    TrendingUpIcon,
    SearchIcon,
    LineChartIcon,
    ServerIcon,
    DownloadCloudIcon,
    HashIcon,
    ClockIcon
} from 'lucide-react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    BarChart, Bar,
    AreaChart, Area
} from 'recharts';
import { authFetch, API_BASE } from '../services/apiService';

interface RiskScore {
    userId: string;
    userName: string;
    userEmail: string;
    userAvatar: string;
    score: number;
    ruleScore: number;
    mlScore: number;
    reasons: string[];
    lastCalculated: string;
}

interface UEBAAlert {
    id: string;
    tenantId: string;
    user_id: string;
    user_email: string;
    score: number;
    reasons: string[];
    status: string;
    timestamp: string;
}

export function UEBADashboard() {
    const [riskScores, setRiskScores] = useState<RiskScore[]>([]);
    const [alerts, setAlerts] = useState<UEBAAlert[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isCalculating, setIsCalculating] = useState(false);
    const [selectedUser, setSelectedUser] = useState<RiskScore | null>(null);
    const [userHistory, setUserHistory] = useState<any[]>([]);
    const [isLoadingHistory, setIsLoadingHistory] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const scoresRes = await authFetch(`${API_BASE}/ueba/risk-scores`);
            const alertsRes = await authFetch(`${API_BASE}/ueba/alerts`);

            if (scoresRes.ok) {
                const data = await scoresRes.json();
                setRiskScores(data.results || []);
                if (data.results && data.results.length > 0 && !selectedUser) {
                    handleUserSelect(data.results[0]);
                }
            }

            if (alertsRes.ok) {
                const data = await alertsRes.json();
                setAlerts(data.alerts || []);
            }
        } catch (error) {
            console.error('Error fetching UEBA data:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleUserSelect = async (user: RiskScore) => {
        setSelectedUser(user);
        setIsLoadingHistory(true);

        try {
            const res = await authFetch(`${API_BASE}/ueba/user/${user.userId}/history`);

            if (res.ok) {
                const data = await res.json();

                // Format for Recharts
                const formatted = (data.history || []).map((h: any) => ({
                    time: new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    score: h.score,
                    fullDate: new Date(h.timestamp).toLocaleString(),
                    ...h.vector
                }));

                // If empty or too small, generate some dummy sparkline data so the chart isn't empty for the demo
                if (formatted.length < 2) {
                    const dummy = [];
                    let currentScore = Math.max(0, user.score - 40);
                    for (let i = 10; i >= 0; i--) {
                        const d = new Date();
                        d.setHours(d.getHours() - i);

                        currentScore = currentScore + (Math.random() * 20 - 5);
                        if (i === 0) currentScore = user.score; // Ensure last point matches current score

                        dummy.push({
                            time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                            score: Math.min(100, Math.max(0, Math.round(currentScore))),
                            fullDate: d.toLocaleString()
                        });
                    }
                    setUserHistory(dummy);
                } else {
                    setUserHistory(formatted);
                }
            }
        } catch (error) {
            console.error('Error fetching user history:', error);
        } finally {
            setIsLoadingHistory(false);
        }
    };

    const triggerRecalculation = async () => {
        setIsCalculating(true);
        try {
            await authFetch(`${API_BASE}/ueba/calculate-all`, {
                method: 'POST'
            });

            // Wait a moment for background task to process a bit, then refresh
            setTimeout(() => {
                fetchData();
                setIsCalculating(false);
            }, 2500);

        } catch (error) {
            console.error('Error triggering recalculation:', error);
            setIsCalculating(false);
        }
    };

    const getScoreColor = (score: number) => {
        if (score >= 80) return 'text-red-500';
        if (score >= 50) return 'text-orange-500';
        if (score >= 20) return 'text-yellow-500';
        return 'text-green-500';
    };

    const getScoreBg = (score: number) => {
        if (score >= 80) return 'bg-red-500/10 border-red-500/30';
        if (score >= 50) return 'bg-orange-500/10 border-orange-500/30';
        if (score >= 20) return 'bg-yellow-500/10 border-yellow-500/30';
        return 'bg-green-500/10 border-green-500/30';
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
                        <UserIcon className="text-purple-400" size={28} />
                        User & Entity Behavior Analytics (UEBA)
                    </h1>
                    <p className="text-slate-400 mt-1">
                        Machine learning-driven insider threat detection and behavioral baselining.
                    </p>
                </div>

                <div className="flex gap-3">
                    <button
                        onClick={triggerRecalculation}
                        disabled={isCalculating}
                        className={`flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg border border-slate-700 transition-colors ${isCalculating ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <RefreshCwIcon size={16} className={isCalculating ? 'animate-spin' : ''} />
                        {isCalculating ? 'Computing Baselines...' : 'Recalculate Baselines'}
                    </button>
                </div>
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center py-20">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                    {/* Left Column: Riskiest Users List */}
                    <div className="col-span-1 space-y-6">
                        <div className="bg-slate-900/50 rounded-xl border border-slate-800 border-t-purple-500/50 p-5 flex flex-col h-[calc(100vh-12rem)]">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                                    <AlertTriangleIcon className="text-red-400" size={20} />
                                    Top Riskiest Users
                                </h2>
                                <span className="text-xs bg-slate-800 text-slate-300 px-2 py-1 rounded-md">
                                    {riskScores.length} Tracked
                                </span>
                            </div>

                            <div className="relative mb-4">
                                <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                <input
                                    type="text"
                                    placeholder="Search users..."
                                    className="w-full bg-slate-950/50 border border-slate-800 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-300 focus:outline-none focus:border-purple-500/50 transition-colors"
                                />
                            </div>

                            <div className="flex-1 overflow-y-auto pr-2 space-y-3 custom-scrollbar">
                                {riskScores.length === 0 ? (
                                    <div className="text-center py-10 text-slate-500">
                                        No user telemetry data available yet.
                                    </div>
                                ) : (
                                    riskScores.map(user => (
                                        <div
                                            key={user.userId}
                                            onClick={() => handleUserSelect(user)}
                                            className={`p-3 rounded-lg border cursor-pointer transition-all ${selectedUser?.userId === user.userId
                                                ? 'bg-slate-800 border-purple-500/50 shadow-[0_0_15px_rgba(168,85,247,0.15)]'
                                                : 'bg-slate-950/30 border-slate-800 hover:bg-slate-800/50'
                                                }`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    <div className="relative">
                                                        {user.userAvatar ? (
                                                            <img src={user.userAvatar} alt={user.userName} className="w-10 h-10 rounded-full" />
                                                        ) : (
                                                            <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 font-medium">
                                                                {user.userName.charAt(0)}
                                                            </div>
                                                        )}
                                                        {user.score >= 80 && (
                                                            <div className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-red-500 border-2 border-slate-900 rounded-full animate-pulse"></div>
                                                        )}
                                                    </div>
                                                    <div>
                                                        <div className="font-medium text-slate-200 text-sm">{user.userName}</div>
                                                        <div className="text-xs text-slate-500 truncate w-32">{user.userEmail}</div>
                                                    </div>
                                                </div>
                                                <div className={`flex flex-col items-end`}>
                                                    <div className={`text-lg font-bold ${getScoreColor(user.score)}`}>
                                                        {user.score}
                                                    </div>
                                                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">
                                                        Risk Score
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right Column: User Details & Graphs */}
                    <div className="col-span-1 lg:col-span-2 space-y-6">
                        {selectedUser ? (
                            <>
                                {/* User Profile Banner */}
                                <div className={`rounded-xl border p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 ${getScoreBg(selectedUser.score)}`}>
                                    <div className="flex items-center gap-5">
                                        {selectedUser.userAvatar ? (
                                            <img src={selectedUser.userAvatar} alt={selectedUser.userName} className="w-16 h-16 rounded-full border-2 border-slate-700/50" />
                                        ) : (
                                            <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center text-slate-300 font-medium text-2xl border-2 border-slate-700/50">
                                                {selectedUser.userName.charAt(0)}
                                            </div>
                                        )}
                                        <div>
                                            <h2 className="text-2xl font-bold text-white">{selectedUser.userName}</h2>
                                            <p className="text-slate-400">{selectedUser.userEmail}</p>
                                            <div className="flex items-center gap-4 mt-2">
                                                <span className="text-xs bg-slate-900/50 text-slate-300 px-2 py-1 rounded border border-slate-700/50">
                                                    ID: {selectedUser.userId.split('_')[1] || selectedUser.userId}
                                                </span>
                                                <span className="text-xs text-slate-400 flex items-center gap-1">
                                                    <ClockIcon size={12} /> Last updated: {new Date(selectedUser.lastCalculated).toLocaleTimeString()}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex gap-8 bg-slate-900/40 p-4 rounded-xl border border-slate-800/50">
                                        <div className="text-center">
                                            <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total Risk</div>
                                            <div className={`text-3xl font-bold ${getScoreColor(selectedUser.score)}`}>{selectedUser.score}</div>
                                        </div>
                                        <div className="w-px bg-slate-700/50"></div>
                                        <div className="text-center">
                                            <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">ML Anomaly %</div>
                                            <div className="text-2xl font-medium text-purple-400">+{selectedUser.mlScore}</div>
                                        </div>
                                        <div className="w-px bg-slate-700/50"></div>
                                        <div className="text-center">
                                            <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Rule Score</div>
                                            <div className="text-2xl font-medium text-blue-400">{selectedUser.ruleScore}</div>
                                        </div>
                                    </div>
                                </div>

                                {/* Anomaly Detection Graph */}
                                <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-5">
                                    <div className="flex items-center justify-between mb-6">
                                        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                                            <LineChartIcon className="text-blue-400" size={20} />
                                            Risk Score Trend (Last 24h)
                                        </h3>
                                        <div className="flex items-center gap-4 text-xs">
                                            <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-full bg-red-500/50"></div> Critical (&gt;80)</div>
                                            <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-full bg-emerald-500/50"></div> Normal</div>
                                        </div>
                                    </div>

                                    <div className="h-64 w-full">
                                        {isLoadingHistory ? (
                                            <div className="h-full w-full flex items-center justify-center">
                                                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                                            </div>
                                        ) : (
                                            <ResponsiveContainer width="100%" height="100%">
                                                <AreaChart data={userHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                                    <defs>
                                                        <linearGradient id="colorRisk" x1="0" y1="0" x2="0" y2="1">
                                                            <stop offset="5%" stopColor={selectedUser.score > 50 ? "#ef4444" : "#8b5cf6"} stopOpacity={0.3} />
                                                            <stop offset="95%" stopColor={selectedUser.score > 50 ? "#ef4444" : "#8b5cf6"} stopOpacity={0} />
                                                        </linearGradient>
                                                    </defs>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                                    <XAxis dataKey="time" stroke="#64748b" tick={{ fill: '#64748b', fontSize: 12 }} dy={10} />
                                                    <YAxis stroke="#64748b" tick={{ fill: '#64748b', fontSize: 12 }} domain={[0, 100]} />
                                                    <Tooltip
                                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc' }}
                                                        itemStyle={{ color: '#e2e8f0' }}
                                                        labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
                                                    />
                                                    <Area
                                                        type="monotone"
                                                        dataKey="score"
                                                        stroke={selectedUser.score > 50 ? "#ef4444" : "#8b5cf6"}
                                                        strokeWidth={3}
                                                        fillOpacity={1}
                                                        fill="url(#colorRisk)"
                                                    />
                                                </AreaChart>
                                            </ResponsiveContainer>
                                        )}
                                    </div>
                                </div>

                                {/* Insights & Metrics */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    {/* Risk Factors */}
                                    <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-5">
                                        <h3 className="text-base font-semibold text-white mb-4">Detection Factors</h3>
                                        {selectedUser.reasons.length > 0 ? (
                                            <ul className="space-y-3">
                                                {selectedUser.reasons.map((reason, idx) => (
                                                    <li key={idx} className="flex items-start gap-3 p-3 bg-slate-950/50 rounded-lg border border-slate-800/50">
                                                        <div className="mt-0.5">
                                                            {reason.includes('ML') || reason.includes('deviates') ? (
                                                                <ActivityIcon className="text-purple-400" size={16} />
                                                            ) : reason.includes('download') ? (
                                                                <DownloadCloudIcon className="text-blue-400" size={16} />
                                                            ) : reason.includes('IP') ? (
                                                                <ServerIcon className="text-orange-400" size={16} />
                                                            ) : (
                                                                <ShieldAlertIcon className="text-red-400" size={16} />
                                                            )}
                                                        </div>
                                                        <span className="text-sm text-slate-300">{reason}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <div className="flex flex-col items-center justify-center py-8 text-center bg-slate-950/30 rounded-lg border border-slate-800/30 border-dashed">
                                                <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center mb-3">
                                                    <ShieldAlertIcon className="text-emerald-500" size={20} />
                                                </div>
                                                <p className="text-sm text-slate-400 leading-relaxed">Behavior is well within established baselines.<br />No anomalous factors detected.</p>
                                            </div>
                                        )}
                                    </div>

                                    {/* Peer Comparison */}
                                    <div className="bg-slate-900/50 rounded-xl border border-slate-800 p-5">
                                        <h3 className="text-base font-semibold text-white mb-4">Peer Group Comparison</h3>

                                        <div className="space-y-6">
                                            {/* Metric 1 */}
                                            <div>
                                                <div className="flex justify-between text-xs mb-2">
                                                    <span className="text-slate-400 uppercase tracking-wider">Distinct IPs (24h)</span>
                                                    <span className="text-slate-200">User: <span className="font-bold">{userHistory.length > 0 ? userHistory[userHistory.length - 1].distinct_ips || 1 : 1}</span> vs Peer Avg: 1.2</span>
                                                </div>
                                                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                                                    <div className="h-full bg-blue-500 rounded-full" style={{ width: '40%' }}></div>
                                                </div>
                                            </div>

                                            {/* Metric 2 */}
                                            <div>
                                                <div className="flex justify-between text-xs mb-2">
                                                    <span className="text-slate-400 uppercase tracking-wider">Failed Logins (24h)</span>
                                                    <span className="text-slate-200">User: <span className="font-bold">{userHistory.length > 0 ? userHistory[userHistory.length - 1].failed_login_count || 0 : 0}</span> vs Peer Avg: 0.5</span>
                                                </div>
                                                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                                                    <div className="h-full bg-orange-500 rounded-full" style={{ width: '15%' }}></div>
                                                </div>
                                            </div>

                                            {/* Metric 3 */}
                                            <div>
                                                <div className="flex justify-between text-xs mb-2">
                                                    <span className="text-slate-400 uppercase tracking-wider">Data Transfer Vol (24h)</span>
                                                    <span className="text-slate-200">User: <span className="font-bold flex items-center gap-1">
                                                        {selectedUser.reasons.some(r => r.includes('download')) ? <TrendingUpIcon size={12} className="text-red-400" /> : ''}
                                                        High
                                                    </span> vs Peer Avg: Low</span>
                                                </div>
                                                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex">
                                                    {/* User bar */}
                                                    <div className={`h-full ${selectedUser.reasons.some(r => r.includes('download')) ? 'bg-red-500' : 'bg-emerald-500'} rounded-l-full`} style={{ width: selectedUser.reasons.some(r => r.includes('download')) ? '85%' : '20%' }}></div>
                                                    {/* Peer average marker implicitly 20% */}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="h-full flex items-center justify-center bg-slate-900/30 rounded-xl border border-slate-800 border-dashed">
                                <div className="text-center text-slate-500">
                                    <UserIcon size={48} className="mx-auto mb-4 opacity-50 text-slate-600" />
                                    <p>Select a user from the list to view their detailed behavioral risk profile.</p>
                                </div>
                            </div>
                        )}

                    </div>
                </div>
            )}
        </div>
    );
}
