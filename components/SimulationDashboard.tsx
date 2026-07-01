import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { Activity, Play, AlertTriangle, CheckCircle, Server, FileText, Zap, Clock, History } from 'lucide-react';

interface SimulationResult {
    success_probability: number;
    impact_score: number;
    predicted_downtime: string;
    conflicts: string[];
    compliance_check: string;
}

interface SimulationRun extends SimulationResult {
    id: string;
    action_type: string;
    target_id: string;
    details: string;
    ran_by: string;
    ran_at: string;
}

interface TwinState {
    sync_status: string;
    last_sync: string;
    assets_modeled: number;
    network_segments?: number;
}

const ImpactBadge: React.FC<{ score: number }> = ({ score }) => {
    const color = score >= 75 ? 'bg-red-100 text-red-700 border-red-200'
        : score >= 40 ? 'bg-amber-100 text-amber-700 border-amber-200'
        : 'bg-green-100 text-green-700 border-green-200';
    return <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${color}`}>{score}/100</span>;
};

const SimulationDashboard: React.FC = () => {
    const [actionType, setActionType] = useState('patch');
    const [details, setDetails] = useState('');
    const [result, setResult] = useState<SimulationResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [twinState, setTwinState] = useState<TwinState | null>(null);
    const [history, setHistory] = useState<SimulationRun[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [activeTab, setActiveTab] = useState<'simulate' | 'history'>('simulate');

    useEffect(() => {
        fetchState();
        fetchHistory();
    }, []);

    const fetchState = async () => {
        try {
            const res = await authFetch('/api/digital_twin/state');
            if (res.ok) setTwinState(await res.json());
        } catch (err) { console.error(err); }
    };

    const fetchHistory = async () => {
        setHistoryLoading(true);
        try {
            const res = await authFetch('/api/digital_twin/history');
            if (res.ok) setHistory(await res.json());
        } catch (err) { console.error(err); }
        finally { setHistoryLoading(false); }
    };

    const runSimulation = async () => {
        setLoading(true);
        try {
            const res = await authFetch('/api/digital_twin/simulate', {
                method: 'POST',
                body: JSON.stringify({ action_type: actionType, target_id: 'global', details }),
            });
            const data = await res.json();
            setResult(data);
            // Refresh history after a short delay (backend persists after returning)
            setTimeout(fetchHistory, 800);
        } catch (err) { console.error(err); }
        finally { setLoading(false); }
    };

    return (
        <div className="p-6 space-y-6 bg-slate-50 dark:bg-gray-900 min-h-screen">
            {/* Header */}
            <div className="flex flex-wrap justify-between items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Digital Twin Simulation</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm">Predict the impact of changes before applying them to production</p>
                </div>
                {twinState && (
                    <div className="flex items-center gap-4 bg-white dark:bg-gray-800 px-4 py-2 rounded-lg shadow-sm border border-slate-100 dark:border-gray-700">
                        <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${twinState.sync_status === 'Synced' ? 'bg-green-500 animate-pulse' : 'bg-amber-500'}`} />
                            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{twinState.sync_status}</span>
                        </div>
                        <div className="w-px h-4 bg-slate-200 dark:bg-gray-600" />
                        <span className="text-xs text-slate-500 dark:text-slate-400">{twinState.assets_modeled} assets modeled</span>
                        {twinState.network_segments != null && (
                            <>
                                <div className="w-px h-4 bg-slate-200 dark:bg-gray-600" />
                                <span className="text-xs text-slate-500 dark:text-slate-400">{twinState.network_segments} segments</span>
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-white dark:bg-gray-800 rounded-lg p-1 w-fit shadow-sm border border-slate-100 dark:border-gray-700">
                {([['simulate', 'Run Simulation', Play], ['history', `History (${history.length})`, History]] as const).map(([tab, label, Icon]) => (
                    <button key={tab} onClick={() => setActiveTab(tab)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === tab ? 'bg-blue-600 text-white' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-gray-700'}`}>
                        <Icon size={15} />{label}
                    </button>
                ))}
            </div>

            {/* ── Simulate tab ─────────────────────────────────────── */}
            {activeTab === 'simulate' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Input */}
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-slate-100 dark:border-gray-700">
                        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-slate-800 dark:text-white">
                            <Play size={20} className="text-blue-600" /> Configure Simulation
                        </h2>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Action Type</label>
                                <select value={actionType} onChange={e => setActionType(e.target.value)}
                                    className="w-full p-2.5 border border-slate-200 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none">
                                    <option value="patch">Software Patch</option>
                                    <option value="config_change">Configuration Change</option>
                                    <option value="firewall_rule">Firewall Rule Update</option>
                                    <option value="scaling">Network Scaling</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Change Details</label>
                                <textarea value={details} onChange={e => setDetails(e.target.value)}
                                    className="w-full p-3 border border-slate-200 dark:border-gray-600 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none h-32 bg-white dark:bg-gray-700 dark:text-white"
                                    placeholder={actionType === 'patch' ? 'e.g., Deploy KB2026-Security-Fix to all Windows Servers'
                                        : actionType === 'firewall_rule' ? 'e.g., Allow traffic on port 443 from corporate network'
                                        : 'Describe the change…'} />
                            </div>
                            <button onClick={runSimulation} disabled={loading || !details.trim()}
                                className={`w-full py-2.5 px-4 rounded-lg font-medium text-white flex items-center justify-center gap-2 transition-colors ${loading || !details.trim() ? 'bg-slate-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'}`}>
                                {loading ? 'Simulating on Digital Twin…' : <><Activity size={18} /> Run Impact Analysis</>}
                            </button>
                        </div>
                    </div>

                    {/* Results */}
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-slate-100 dark:border-gray-700 min-h-[400px]">
                        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-slate-800 dark:text-white">
                            <FileText size={20} className="text-indigo-600" /> Simulation Results
                        </h2>
                        {!result ? (
                            <div className="h-64 flex flex-col items-center justify-center text-slate-400 border-2 border-dashed border-slate-100 dark:border-gray-700 rounded-lg">
                                <Server size={48} className="mb-2 opacity-20" />
                                <p className="text-sm">Run a simulation to see predicted impact</p>
                            </div>
                        ) : (
                            <div className="space-y-5">
                                <div className="grid grid-cols-2 gap-4">
                                    <div className={`p-4 rounded-lg border ${result.success_probability > 90 ? 'bg-green-50 border-green-100 dark:bg-green-900/20 dark:border-green-800' : 'bg-amber-50 border-amber-100 dark:bg-amber-900/20 dark:border-amber-800'}`}>
                                        <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide font-semibold mb-1">Success Probability</div>
                                        <div className={`text-2xl font-bold ${result.success_probability > 90 ? 'text-green-700 dark:text-green-400' : 'text-amber-700 dark:text-amber-400'}`}>
                                            {result.success_probability}%
                                        </div>
                                    </div>
                                    <div className={`p-4 rounded-lg border ${result.impact_score > 50 ? 'bg-red-50 border-red-100 dark:bg-red-900/20 dark:border-red-800' : 'bg-blue-50 border-blue-100 dark:bg-blue-900/20 dark:border-blue-800'}`}>
                                        <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide font-semibold mb-1">Risk / Impact Score</div>
                                        <div className={`text-2xl font-bold ${result.impact_score > 50 ? 'text-red-700 dark:text-red-400' : 'text-blue-700 dark:text-blue-400'}`}>
                                            {result.impact_score}/100
                                        </div>
                                    </div>
                                </div>
                                <div className="flex flex-wrap gap-3 text-sm">
                                    <div className="flex items-center gap-2 px-3 py-1 bg-slate-100 dark:bg-gray-700 rounded-full text-slate-700 dark:text-slate-300">
                                        <Zap size={14} /> Downtime: {result.predicted_downtime}
                                    </div>
                                    <div className={`flex items-center gap-2 px-3 py-1 rounded-full border ${result.compliance_check === 'PASSED' ? 'bg-green-50 border-green-200 text-green-700 dark:bg-green-900/30 dark:border-green-700 dark:text-green-300' : 'bg-red-50 border-red-200 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300'}`}>
                                        {result.compliance_check === 'PASSED' ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
                                        {result.compliance_check}
                                    </div>
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-2">Conflicts & Warnings</h3>
                                    {result.conflicts.length === 0 ? (
                                        <p className="text-sm text-green-600 dark:text-green-400 flex items-center gap-2"><CheckCircle size={16} /> No conflicts detected.</p>
                                    ) : (
                                        <div className="space-y-2">
                                            {result.conflicts.map((c, i) => (
                                                <div key={i} className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm border border-red-100 dark:border-red-800">
                                                    <AlertTriangle size={16} className="shrink-0 mt-0.5" />{c}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── History tab ──────────────────────────────────────── */}
            {activeTab === 'history' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-slate-100 dark:border-gray-700 overflow-hidden">
                    <div className="p-4 border-b border-slate-100 dark:border-gray-700 flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-800 dark:text-white flex items-center gap-2">
                            <Clock size={16} className="text-indigo-500" /> Past Simulation Runs
                        </h2>
                        <button onClick={fetchHistory} disabled={historyLoading}
                            className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 disabled:opacity-50">
                            <Activity size={13} className={historyLoading ? 'animate-spin' : ''} /> Refresh
                        </button>
                    </div>
                    {historyLoading ? (
                        <div className="p-10 text-center text-slate-400 dark:text-slate-500 text-sm">Loading history…</div>
                    ) : history.length === 0 ? (
                        <div className="p-10 text-center text-slate-400 dark:text-slate-500">
                            <History size={36} className="mx-auto mb-2 opacity-30" />
                            <p className="text-sm">No simulation runs yet. Run your first simulation above.</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left">
                                <thead className="text-xs uppercase bg-slate-50 dark:bg-gray-700 text-slate-600 dark:text-slate-300">
                                    <tr>
                                        <th className="px-4 py-3">Ran At</th>
                                        <th className="px-4 py-3">Action</th>
                                        <th className="px-4 py-3">Details</th>
                                        <th className="px-4 py-3">Success %</th>
                                        <th className="px-4 py-3">Impact</th>
                                        <th className="px-4 py-3">Compliance</th>
                                        <th className="px-4 py-3">Downtime</th>
                                        <th className="px-4 py-3">By</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-gray-700">
                                    {history.map(run => (
                                        <tr key={run.id} className="hover:bg-slate-50 dark:hover:bg-gray-700/40">
                                            <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                                {new Date(run.ran_at).toLocaleString()}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">
                                                    {run.action_type.replace('_', ' ')}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 max-w-[200px] truncate text-slate-600 dark:text-slate-300 text-xs" title={run.details}>
                                                {run.details}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`font-semibold ${run.success_probability > 90 ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}`}>
                                                    {run.success_probability}%
                                                </span>
                                            </td>
                                            <td className="px-4 py-3"><ImpactBadge score={run.impact_score} /></td>
                                            <td className="px-4 py-3">
                                                <span className={`text-xs font-medium ${run.compliance_check === 'PASSED' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                                    {run.compliance_check === 'PASSED' ? '✓ PASSED' : '✗ FAILED'}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{run.predicted_downtime}</td>
                                            <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">{run.ran_by}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default SimulationDashboard;
