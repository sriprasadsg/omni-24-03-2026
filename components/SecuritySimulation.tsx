import React, { useState, useEffect } from 'react';
import { Asset } from '../types';
import { BombIcon, ZapIcon, CheckIcon, XCircleIcon, ClockIcon, ShieldAlertIcon, TerminalIcon } from './icons';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

export const SecuritySimulation: React.FC = () => {
    const [assets, setAssets] = useState<Asset[]>([]);
    const [selectedAsset, setSelectedAsset] = useState<string>('');
    const [technique, setTechnique] = useState<string>('memory_write');
    const [target, setTarget] = useState<string>('notepad.exe');
    const [history, setHistory] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [triggering, setTriggering] = useState(false);

    const [activeTab, setActiveTab] = useState<'sim' | 'validation'>('sim');

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [assetsData, historyData] = await Promise.all([
                api.fetchAssets(),
                api.fetchSimulationHistory()
            ]);
            setAssets(assetsData);
            setHistory(historyData);
        } catch (e) {
            console.error("Failed to load simulation data", e);
        } finally {
            setLoading(false);
        }
    };

    const handleTrigger = async () => {
        if (!selectedAsset) {
            showToast("Please select a target asset", 'error');
            return;
        }
        setTriggering(true);
        try {
            const res = await api.triggerProcessInjectionSimulation(selectedAsset, technique, target);
            if (res.success) {
                showToast(`Simulation triggered! Case ID: ${res.caseId}`, 'success');
                loadData();
            }
        } catch (e) {
            showToast("Failed to trigger simulation", 'error');
        } finally {
            setTriggering(false);
        }
    };

    const mitreTactics = [
        { id: 'recon', name: 'Reconnaissance', coverage: 45 },
        { id: 'resource', name: 'Resource Development', coverage: 20 },
        { id: 'initial', name: 'Initial Access', coverage: 85 },
        { id: 'execution', name: 'Execution', coverage: 92 },
        { id: 'persistence', name: 'Persistence', coverage: 78 },
        { id: 'privilege', name: 'Privilege Escalation', coverage: 65 },
        { id: 'defense', name: 'Defense Evasion', coverage: 88 },
        { id: 'credential', name: 'Credential Access', coverage: 72 },
        { id: 'discovery', name: 'Discovery', coverage: 50 },
        { id: 'lateral', name: 'Lateral Movement', coverage: 40 },
        { id: 'collection', name: 'Collection', coverage: 30 },
        { id: 'command', name: 'Command & Control', coverage: 60 },
        { id: 'exfiltration', name: 'Exfiltration', coverage: 25 },
        { id: 'impact', name: 'Impact', coverage: 15 },
    ];

    const renderValidationLab = () => (
        <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                <div className="lg:col-span-1 bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">Overall Coverage</h3>
                    <div className="relative flex items-center justify-center h-48">
                        <svg className="w-40 h-40 transform -rotate-90">
                            <circle cx="80" cy="80" r="70" stroke="currentColor" strokeWidth="12" fill="transparent" className="text-slate-100 dark:text-slate-700" />
                            <circle cx="80" cy="80" r="70" stroke="currentColor" strokeWidth="12" fill="transparent" strokeDasharray={440} strokeDashoffset={440 * (1 - 0.62)} className="text-indigo-600 transition-all duration-1000" strokeLinecap="round" />
                        </svg>
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                            <span className="text-4xl font-black text-slate-900 dark:text-white">62%</span>
                            <span className="text-[10px] font-bold text-slate-400 uppercase">Detection Rate</span>
                        </div>
                    </div>
                    <div className="mt-4 space-y-2">
                        <div className="flex justify-between text-xs font-bold">
                            <span className="text-slate-500 uppercase">Verified Techniques</span>
                            <span className="text-indigo-600">142/228</span>
                        </div>
                        <div className="w-full bg-slate-100 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                            <div className="bg-indigo-600 h-full rounded-full" style={{ width: '62%' }}></div>
                        </div>
                    </div>
                </div>

                <div className="lg:col-span-3 bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden relative">
                    <div className="absolute top-0 right-0 p-6">
                        <span className="px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-[10px] font-bold border border-emerald-200 animate-pulse">LIVE ANALYTICS</span>
                    </div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-6">MITRE ATT&CK® Coverage Matrix</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
                        {mitreTactics.map(tactic => (
                            <div key={tactic.id} className="group relative">
                                <div className={`aspect-square rounded-lg border flex flex-col items-center justify-center p-2 transition-all cursor-help ${
                                    tactic.coverage > 80 ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600' :
                                    tactic.coverage > 50 ? 'bg-amber-500/10 border-amber-500/30 text-amber-600' :
                                    'bg-red-500/10 border-red-500/30 text-red-600'
                                }`}>
                                    <span className="text-[9px] font-black uppercase tracking-tighter text-center leading-tight mb-1">{tactic.name}</span>
                                    <span className="text-xs font-black">{tactic.coverage}%</span>
                                </div>
                                <div className="absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-2 w-32 p-2 bg-slate-900 text-white text-[10px] rounded shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                                    <p className="font-bold border-b border-white/20 pb-1 mb-1">{tactic.name}</p>
                                    <p className="text-white/70">Verified: {Math.floor(tactic.coverage * 0.2)} techniques</p>
                                    <p className="text-white/70">Gap: {Math.floor((100 - tactic.coverage) * 0.2)} techniques</p>
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-8 flex items-center gap-4 text-[10px] font-bold text-slate-400">
                        <span className="flex items-center"><span className="w-3 h-3 bg-emerald-500/20 border border-emerald-500/40 rounded mr-1"></span> HIGH ({'>'}80%)</span>
                        <span className="flex items-center"><span className="w-3 h-3 bg-amber-500/20 border border-amber-500/40 rounded mr-1"></span> MEDIUM (50-80%)</span>
                        <span className="flex items-center"><span className="w-3 h-3 bg-red-500/20 border border-red-500/40 rounded mr-1"></span> LOW ({'<'}50%)</span>
                    </div>
                </div>
            </div>

            <div className="bg-gradient-to-r from-slate-900 to-indigo-900 p-8 rounded-2xl text-white border border-indigo-500/30">
                <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                    <div className="max-w-xl">
                        <h3 className="text-xl font-bold mb-2">Automated Adversary Simulation</h3>
                        <p className="text-indigo-200 text-sm">
                            Generate a comprehensive gap analysis report by running our "Adversary Pack 2026". This will simulate known advanced persistent threat (APT) behaviors across your environment.
                        </p>
                    </div>
                    <button className="px-8 py-3 bg-white text-indigo-900 rounded-xl font-black hover:bg-indigo-50 transition-all shadow-xl shadow-indigo-500/20 whitespace-nowrap">
                        RUN ADVERSARY PACK
                    </button>
                </div>
            </div>
        </div>
    );

    return (
        <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-900 min-h-screen">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-2">
                <div>
                    <h2 className="text-2xl font-black text-slate-900 dark:text-white flex items-center tracking-tight">
                        <BombIcon size={28} className="mr-3 text-red-600" />
                        Security Simulation & Validation
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Test and validate your detection capabilities with benign attack simulations.
                    </p>
                </div>
                <div className="flex bg-white dark:bg-slate-800 p-1 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700">
                    <button 
                        onClick={() => setActiveTab('sim')}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeTab === 'sim' ? 'bg-red-600 text-white shadow-lg shadow-red-500/20' : 'text-slate-500 hover:text-slate-900'}`}
                    >
                        Simulation Lab
                    </button>
                    <button 
                        onClick={() => setActiveTab('validation')}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeTab === 'validation' ? 'bg-red-600 text-white shadow-lg shadow-red-500/20' : 'text-slate-500 hover:text-slate-900'}`}
                    >
                        Detection Validation
                    </button>
                </div>
            </div>

            {activeTab === 'validation' ? renderValidationLab() : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Configuration Card */}
                    <div className="lg:col-span-1">
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-6">
                            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-6 flex items-center">
                                <BombIcon className="mr-2 text-red-500" />
                                New Simulation
                            </h3>

                            <div className="space-y-5">
                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Target Asset</label>
                                    <select
                                        value={selectedAsset}
                                        onChange={(e) => setSelectedAsset(e.target.value)}
                                        className="w-full rounded-xl border-slate-200 shadow-sm focus:border-red-500 focus:ring-red-500 dark:bg-slate-900 dark:border-slate-700 dark:text-white text-sm px-4 py-3"
                                    >
                                        <option value="">Select an asset...</option>
                                        {assets.map(asset => (
                                            <option key={asset.id} value={asset.id}>{asset.hostname} ({asset.ipAddress})</option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Injection Technique</label>
                                    <select
                                        value={technique}
                                        onChange={(e) => setTechnique(e.target.value)}
                                        className="w-full rounded-xl border-slate-200 shadow-sm focus:border-red-500 focus:ring-red-500 dark:bg-slate-900 dark:border-slate-700 dark:text-white text-sm px-4 py-3"
                                    >
                                        <option value="memory_write">Remote Memory Write</option>
                                        <option value="thread_injection">Remote Thread Injection (Suspicious)</option>
                                        <option value="dll_injection">DLL Injection (Simulation)</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Target Process</label>
                                    <input
                                        type="text"
                                        value={target}
                                        onChange={(e) => setTarget(e.target.value)}
                                        placeholder="e.g., notepad.exe"
                                        className="w-full rounded-xl border-slate-200 shadow-sm focus:border-red-500 focus:ring-red-500 dark:bg-slate-900 dark:border-slate-700 dark:text-white text-sm px-4 py-3"
                                    />
                                </div>

                                <div className="pt-4">
                                    <button
                                        onClick={handleTrigger}
                                        disabled={triggering || !selectedAsset}
                                        className={`w-full flex justify-center items-center py-4 px-4 border border-transparent rounded-xl shadow-xl shadow-red-500/20 text-sm font-black text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-all ${triggering ? 'opacity-50 cursor-not-allowed' : ''}`}
                                    >
                                        {triggering ? 'Dispatching...' : 'Launch Simulation'}
                                        {!triggering && <ZapIcon size={16} className="ml-2" />}
                                    </button>
                                    <p className="mt-4 text-[10px] text-slate-400 text-center font-bold">
                                        This will trigger a benign simulation flagged by EDR.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* History Card */}
                    <div className="lg:col-span-2">
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center">
                                <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center">
                                    <ShieldAlertIcon className="mr-2 text-amber-500" />
                                    Simulation History
                                </h3>
                                <button onClick={loadData} className="text-slate-400 hover:text-slate-600"><ClockIcon size={18} /></button>
                            </div>

                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-slate-50 dark:bg-slate-900/50 text-[10px] uppercase font-black text-slate-400 tracking-widest">
                                        <tr>
                                            <th className="px-6 py-4">Timestamp</th>
                                            <th className="px-6 py-4">Asset</th>
                                            <th className="px-6 py-4">Technique</th>
                                            <th className="px-6 py-4">Status</th>
                                            <th className="px-6 py-4">Case ID</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                                        {history.map(sim => (
                                            <tr key={sim.id} className="hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors">
                                                <td className="px-6 py-4 font-medium text-slate-600 dark:text-slate-400">
                                                    {new Date(sim.timestamp).toLocaleString()}
                                                </td>
                                                <td className="px-6 py-4 font-black text-slate-900 dark:text-white">
                                                    {assets.find(a => a.id === sim.agentId)?.hostname || sim.agentId}
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span className="px-2 py-1 bg-slate-100 dark:bg-slate-900 rounded text-[10px] font-black font-mono">
                                                        {sim.technique.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300">
                                                        {sim.status.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4 text-red-600 dark:text-red-400 font-black font-mono text-[10px]">
                                                    {sim.caseId}
                                                </td>
                                            </tr>
                                        ))}
                                        {history.length === 0 && (
                                            <tr>
                                                <td colSpan={5} className="px-6 py-12 text-center text-slate-400 font-bold">
                                                    No simulations recorded yet.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
