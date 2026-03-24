import React, { useState, useEffect } from 'react';
import { Activity, Play, AlertTriangle, CheckCircle, Server, FileText, Zap } from 'lucide-react';

interface SimulationResult {
    success_probability: number;
    impact_score: number;
    predicted_downtime: string;
    conflicts: string[];
    compliance_check: string;
}

interface TwinState {
    sync_status: string;
    last_sync: string;
    assets_modeled: number;
}

const SimulationDashboard: React.FC = () => {
    const [actionType, setActionType] = useState('patch');
    const [details, setDetails] = useState('');
    const [result, setResult] = useState<SimulationResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [twinState, setTwinState] = useState<TwinState | null>(null);

    useEffect(() => {
        fetchState();
    }, []);

    const fetchState = async () => {
        try {
            const res = await fetch('/api/digital_twin/state');
            const data = await res.json();
            setTwinState(data);
        } catch (err) {
            console.error(err);
        }
    }

    const runSimulation = async () => {
        setLoading(true);
        try {
            const res = await fetch('/api/digital_twin/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action_type: actionType,
                    target_id: "global",
                    details: details
                })
            });
            const data = await res.json();
            setResult(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6 space-y-6 bg-slate-50 min-h-screen">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Digital Twin Simulation</h1>
                    <p className="text-slate-500">Predict the impact of changes before applying them to production</p>
                </div>
                <div className="flex items-center gap-4 bg-white px-4 py-2 rounded-lg shadow-sm">
                    <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${twinState?.sync_status === 'Synced' ? 'bg-green-500' : 'bg-amber-500'}`} />
                        <span className="text-sm font-medium text-slate-700">Model Status: {twinState?.sync_status || 'Unknown'}</span>
                    </div>
                    <div className="w-px h-4 bg-slate-200" />
                    <span className="text-xs text-slate-500">Assets Modeled: {twinState?.assets_modeled || 0}</span>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Input Panel */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                        <Play size={20} className="text-blue-600" /> Configure Simulation
                    </h2>

                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">Action Type</label>
                            <select
                                value={actionType}
                                onChange={(e) => setActionType(e.target.value)}
                                className="w-full p-2.5 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                            >
                                <option value="patch">Software Patch</option>
                                <option value="config_change">Configuration Change</option>
                                <option value="firewall_rule">Firewall Rule Update</option>
                                <option value="scaling">Network Scaling</option>
                            </select>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">Change Details (Prompt)</label>
                            <textarea
                                value={details}
                                onChange={(e) => setDetails(e.target.value)}
                                className="w-full p-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none h-32"
                                placeholder={
                                    actionType === 'patch' ? "e.g., Deploy KB2026-Security-Fix to all Windows Servers" :
                                        actionType === 'firewall_rule' ? "e.g., Allow all traffic on port 22 from 0.0.0.0/0" :
                                            "Describe the change..."
                                }
                            />
                        </div>

                        <button
                            onClick={runSimulation}
                            disabled={loading || !details}
                            className={`w-full py-2.5 px-4 rounded-lg font-medium text-white flex items-center justify-center gap-2 transition-colors ${loading ? 'bg-slate-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
                                }`}
                        >
                            {loading ? (
                                <>Simulating on Digital Twin...</>
                            ) : (
                                <><Activity size={18} /> Run Impact Analysis</>
                            )}
                        </button>
                    </div>
                </div>

                {/* Results Panel */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100 min-h-[400px]">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                        <FileText size={20} className="text-indigo-600" /> Simulation Results
                    </h2>

                    {!result ? (
                        <div className="h-64 flex flex-col items-center justify-center text-slate-400 border-2 border-dashed border-slate-100 rounded-lg">
                            <Server size={48} className="mb-2 opacity-20" />
                            <p>Run a simulation to see predicted impact</p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Score Cards */}
                            <div className="grid grid-cols-2 gap-4">
                                <div className={`p-4 rounded-lg border ${result.success_probability > 90 ? 'bg-green-50 border-green-100' : 'bg-amber-50 border-amber-100'}`}>
                                    <div className="text-xs text-slate-500 uppercase tracking-wide font-semibold">Success Probability</div>
                                    <div className={`text-2xl font-bold ${result.success_probability > 90 ? 'text-green-700' : 'text-amber-700'}`}>
                                        {result.success_probability}%
                                    </div>
                                </div>
                                <div className={`p-4 rounded-lg border ${result.impact_score > 50 ? 'bg-red-50 border-red-100' : 'bg-blue-50 border-blue-100'}`}>
                                    <div className="text-xs text-slate-500 uppercase tracking-wide font-semibold">Risk / Impact Score</div>
                                    <div className={`text-2xl font-bold ${result.impact_score > 50 ? 'text-red-700' : 'text-blue-700'}`}>
                                        {result.impact_score}/100
                                    </div>
                                </div>
                            </div>

                            {/* Compliance & Downtime */}
                            <div className="flex gap-4 text-sm">
                                <div className="flex items-center gap-2 px-3 py-1 bg-slate-100 rounded-full text-slate-700">
                                    <Zap size={14} /> Downtime: {result.predicted_downtime}
                                </div>
                                <div className={`flex items-center gap-2 px-3 py-1 rounded-full border ${result.compliance_check === 'PASSED' ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
                                    {result.compliance_check === 'PASSED' ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
                                    Compliance: {result.compliance_check}
                                </div>
                            </div>

                            {/* Conflicts List */}
                            <div>
                                <h3 className="text-sm font-semibold text-slate-800 mb-2">Detected Conflicts & Warnings</h3>
                                {result.conflicts.length === 0 ? (
                                    <p className="text-sm text-green-600 flex items-center gap-2"><CheckCircle size={16} /> No conflicts detected.</p>
                                ) : (
                                    <div className="space-y-2">
                                        {result.conflicts.map((conflict, idx) => (
                                            <div key={idx} className="flex items-start gap-2 p-3 bg-red-50 text-red-700 rounded-lg text-sm border border-red-100">
                                                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                                                <span>{conflict}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default SimulationDashboard;
