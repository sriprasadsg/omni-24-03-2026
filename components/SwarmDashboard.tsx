import React, { useState, useEffect } from 'react';
import { Play, Activity, Shield, Cpu, MessageSquare, Terminal } from 'lucide-react';
import { fetchSwarmMissions, fetchSwarmTopology, startSwarmMission } from '../services/apiService';

interface AgentMessage {
    agent_name: string;
    role: string;
    message: string;
    timestamp: number;
}

interface Mission {
    id: string;
    goal: string;
    status: string;
    logs: AgentMessage[];
}

const SwarmDashboard: React.FC = () => {
    const [missionGoal, setMissionGoal] = useState('');
    const [activeMission, setActiveMission] = useState<Mission | null>(null);
    const [missions, setMissions] = useState<Mission[]>([]);
    const [topology, setTopology] = useState<any>(null);

    useEffect(() => {
        fetchMissions();
        fetchTopologyData();
        const interval = setInterval(fetchMissions, 2000); // Live polling
        return () => clearInterval(interval);
    }, []);

    const fetchMissions = async () => {
        try {
            const data = await fetchSwarmMissions();
            setMissions(data);
            if (data.length > 0 && !activeMission) {
                setActiveMission(data[0]);
            } else if (activeMission) {
                // Update active mission object
                const updated = data.find((m: Mission) => m.id === activeMission.id);
                if (updated) setActiveMission(updated);
            }
        } catch (err) {
            console.error(err);
        }
    };

    const fetchTopologyData = async () => {
        try {
            const data = await fetchSwarmTopology();
            setTopology(data);
        } catch (err) {
            console.error(err);
        }
    }

    const startMission = async () => {
        if (!missionGoal) return;
        try {
            await startSwarmMission(missionGoal);
            setMissionGoal('');
            fetchMissions();
        } catch (err) {
            console.error(err);
        }
    };

    return (
        <div className="p-6 space-y-6 bg-slate-50 min-h-screen">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Autonomous Agent Swarms</h1>
                    <p className="text-slate-500">Collaborative AI agents solving complex tasks autonomously</p>
                </div>
                <div className="flex gap-2">
                    <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium flex items-center gap-1">
                        <Activity size={16} /> Swarm Online
                    </span>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column: Mission Control */}
                <div className="space-y-6">
                    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100">
                        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                            <Terminal size={20} className="text-blue-600" /> Mission Control
                        </h2>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Mission Goal</label>
                                <textarea
                                    className="w-full p-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                                    rows={3}
                                    placeholder="e.g., Scan network segment 192.168.1.0/24 and patch critical vulnerabilities..."
                                    value={missionGoal}
                                    onChange={(e) => setMissionGoal(e.target.value)}
                                />
                            </div>
                            <button
                                onClick={startMission}
                                className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
                            >
                                <Play size={18} /> Dispatch Swarm
                            </button>
                        </div>
                    </div>

                    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100">
                        <h2 className="text-lg font-semibold mb-4">Active Missions</h2>
                        <div className="space-y-3">
                            {missions.length === 0 && <p className="text-sm text-slate-400">No active missions</p>}
                            {missions.map(m => (
                                <div
                                    key={m.id}
                                    onClick={() => setActiveMission(m)}
                                    className={`p-3 rounded-lg border cursor-pointer transition-all ${activeMission?.id === m.id ? 'border-blue-500 bg-blue-50' : 'border-slate-100 hover:bg-slate-50'}`}
                                >
                                    <div className="flex justify-between items-start mb-1">
                                        <span className="text-xs font-mono text-slate-400">{m.id.slice(0, 8)}</span>
                                        <span className={`text-[10px] px-2 py-0.5 rounded-full ${m.status === 'Completed' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                                            {m.status}
                                        </span>
                                    </div>
                                    <p className="text-sm font-medium text-slate-800 line-clamp-2">{m.goal}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Center: Live Swarm Chat */}
                <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-100 flex flex-col h-[600px]">
                    <div className="p-4 border-b border-slate-100 flex justify-between items-center">
                        <h2 className="font-semibold flex items-center gap-2">
                            <MessageSquare size={18} className="text-indigo-600" />
                            Swarm Intelligence Feed
                        </h2>
                        {activeMission && <span className="text-xs text-slate-500">Mission: {activeMission.id}</span>}
                    </div>

                    <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">
                        {!activeMission ? (
                            <div className="h-full flex items-center justify-center text-slate-400">Select a mission to view swarm logs</div>
                        ) : (
                            activeMission.logs.map((log, idx) => (
                                <div key={idx} className="flex gap-3">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${log.role === 'Manager' ? 'bg-purple-100 text-purple-600' :
                                        log.role === 'Researcher' ? 'bg-blue-100 text-blue-600' : 'bg-orange-100 text-orange-600'
                                        }`}>
                                        {log.role === 'Manager' ? <Shield size={14} /> : log.role === 'Researcher' ? <Activity size={14} /> : <Cpu size={14} />}
                                    </div>
                                    <div className="bg-white p-3 rounded-lg shadow-sm border border-slate-100 max-w-[80%]">
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="text-xs font-bold text-slate-700">{log.agent_name}</span>
                                            <span className="text-[10px] text-slate-400 border border-slate-100 px-1 rounded uppercase tracking-wider">{log.role}</span>
                                        </div>
                                        <p className="text-sm text-slate-600 leading-relaxed font-mono">{log.message}</p>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>

            </div>

            {/* Topology Nodes (Visual Mock) */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100">
                <h2 className="text-lg font-semibold mb-4">Swarm Topology</h2>
                <div className="flex flex-wrap gap-4">
                    {topology?.nodes?.map((node: any) => (
                        <div key={node.id} className="flex items-center gap-3 p-3 border border-slate-100 rounded-lg min-w-[150px]">
                            <div className={`w-3 h-3 rounded-full ${node.status === 'Active' ? 'bg-green-500 animate-pulse' : 'bg-slate-300'}`} />
                            <div>
                                <div className="text-sm font-medium">{node.name}</div>
                                <div className="text-xs text-slate-500">{node.role}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default SwarmDashboard;
