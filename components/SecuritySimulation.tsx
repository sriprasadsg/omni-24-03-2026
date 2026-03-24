import React, { useState, useEffect } from 'react';
import { Asset } from '../types';
import { BombIcon, ZapIcon, CheckIcon, XCircleIcon, ClockIcon, ShieldAlertIcon, TerminalIcon } from './icons';
import * as api from '../services/apiService';

export const SecuritySimulation: React.FC = () => {
    const [assets, setAssets] = useState<Asset[]>([]);
    const [selectedAsset, setSelectedAsset] = useState<string>('');
    const [technique, setTechnique] = useState<string>('memory_write');
    const [target, setTarget] = useState<string>('notepad.exe');
    const [history, setHistory] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [triggering, setTriggering] = useState(false);

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
            alert("Please select a target asset");
            return;
        }
        setTriggering(true);
        try {
            const res = await api.triggerProcessInjectionSimulation(selectedAsset, technique, target);
            if (res.success) {
                alert(`Simulation triggered! Case ID: ${res.caseId}`);
                loadData();
            }
        } catch (e) {
            alert("Failed to trigger simulation");
        } finally {
            setTriggering(false);
        }
    };

    return (
        <div className="container mx-auto p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">Security Simulations</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Test your detection capabilities with benign attack simulations.</p>
                </div>
                <div className="flex space-x-3">
                    <button
                        onClick={loadData}
                        className="p-2 text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400"
                    >
                        <ClockIcon size={20} />
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Configuration Card */}
                <div className="lg:col-span-1">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                        <h3 className="text-lg font-semibold mb-4 flex items-center">
                            <BombIcon className="mr-2 text-red-500" />
                            New Simulation
                        </h3>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Target Asset</label>
                                <select
                                    value={selectedAsset}
                                    onChange={(e) => setSelectedAsset(e.target.value)}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm px-3 py-2"
                                >
                                    <option value="">Select an asset...</option>
                                    {assets.map(asset => (
                                        <option key={asset.id} value={asset.id}>{asset.hostname} ({asset.ipAddress})</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Injection Technique</label>
                                <select
                                    value={technique}
                                    onChange={(e) => setTechnique(e.target.value)}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm px-3 py-2"
                                >
                                    <option value="memory_write">Remote Memory Write</option>
                                    <option value="thread_injection">Remote Thread Injection (Suspicious)</option>
                                    <option value="dll_injection">DLL Injection (Simulation)</option>
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Target Process</label>
                                <input
                                    type="text"
                                    value={target}
                                    onChange={(e) => setTarget(e.target.value)}
                                    placeholder="e.g., notepad.exe"
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm px-3 py-2"
                                />
                            </div>

                            <div className="pt-4">
                                <button
                                    onClick={handleTrigger}
                                    disabled={triggering || !selectedAsset}
                                    className={`w-full flex justify-center items-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 ${triggering ? 'opacity-50 cursor-not-allowed' : ''}`}
                                >
                                    {triggering ? 'Dispatching...' : 'Launch Simulation'}
                                    {!triggering && <ZapIcon size={16} className="ml-2" />}
                                </button>
                                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 text-center">
                                    This will trigger a benign simulation that may be flagged by EDR.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* History Card */}
                <div className="lg:col-span-2">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                            <h3 className="text-lg font-semibold flex items-center">
                                <ShieldAlertIcon className="mr-2 text-amber-500" />
                                Simulation History
                            </h3>
                        </div>

                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                    <tr>
                                        <th className="px-6 py-3">Timestamp</th>
                                        <th className="px-6 py-3">Asset</th>
                                        <th className="px-6 py-3">Technique</th>
                                        <th className="px-6 py-3">Status</th>
                                        <th className="px-6 py-3">Case</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {history.map(sim => (
                                        <tr key={sim.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                {new Date(sim.timestamp).toLocaleString()}
                                            </td>
                                            <td className="px-6 py-4 font-mono text-xs">
                                                {assets.find(a => a.id === sim.agentId)?.hostname || sim.agentId}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-900 rounded text-xs font-mono">
                                                    {sim.technique}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300">
                                                    {sim.status}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-primary-600 dark:text-primary-400 font-medium">
                                                {sim.caseId}
                                            </td>
                                        </tr>
                                    ))}
                                    {history.length === 0 && (
                                        <tr>
                                            <td colSpan={5} className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
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
        </div>
    );
};
