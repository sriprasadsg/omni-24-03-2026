import React, { useState, useEffect } from 'react';
import { Asset } from '../types';
import { ShieldCheckIcon, ShieldAlertIcon, SearchIcon, ZapIcon, ClockIcon, AlertTriangleIcon, FileTextIcon } from './icons';
import * as api from '../services/apiService';

export const PersistenceDashboard: React.FC = () => {
    const [assets, setAssets] = useState<Asset[]>([]);
    const [selectedAsset, setSelectedAsset] = useState<string>('');
    const [results, setResults] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [scanning, setScanning] = useState(false);

    useEffect(() => {
        loadAssets();
    }, []);

    const loadAssets = async () => {
        try {
            const data = await api.fetchAssets();
            setAssets(data);
        } catch (e) {
            console.error("Failed to load assets", e);
        }
    };

    const handleScan = async () => {
        if (!selectedAsset) {
            alert("Please select an asset to scan");
            return;
        }
        setScanning(true);
        try {
            const res = await api.triggerPersistenceScan(selectedAsset);
            if (res.success) {
                alert("Persistence scan triggered! Results will appear shortly.");
                // Poll for results after a delay
                setTimeout(() => fetchResults(selectedAsset), 5000);
            }
        } catch (e) {
            alert("Failed to trigger scan");
        } finally {
            setScanning(false);
        }
    };

    const fetchResults = async (assetId: string) => {
        setLoading(true);
        try {
            const data = await api.fetchPersistenceResults(assetId);
            setResults(data);
        } catch (e) {
            console.error("Failed to fetch results", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (selectedAsset) {
            fetchResults(selectedAsset);
        } else {
            setResults(null);
        }
    }, [selectedAsset]);

    return (
        <div className="container mx-auto p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">Persistence Detection</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Scan for unauthorized persistence mechanisms on your assets.</p>
                </div>
                <div className="flex space-x-3">
                    <select
                        value={selectedAsset}
                        onChange={(e) => setSelectedAsset(e.target.value)}
                        className="rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm px-3 py-2 min-w-[200px]"
                    >
                        <option value="">Select an asset...</option>
                        {assets.map(asset => (
                            <option key={asset.id} value={asset.id}>{asset.hostname} ({asset.ipAddress})</option>
                        ))}
                    </select>
                    <button
                        onClick={handleScan}
                        disabled={scanning || !selectedAsset}
                        className={`flex items-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 ${scanning ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {scanning ? 'Scanning...' : 'Start Scan'}
                        {!scanning && <SearchIcon size={16} className="ml-2" />}
                    </button>
                </div>
            </div>

            {loading ? (
                <div className="flex justify-center items-center py-20">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
                </div>
            ) : results ? (
                <div className="space-y-6">
                    {/* Summary Stats */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
                            <div className="text-sm text-gray-500 dark:text-gray-400">Total Items</div>
                            <div className="text-2xl font-bold text-gray-900 dark:text-white">{results.count}</div>
                        </div>
                        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
                            <div className="text-sm text-gray-500 dark:text-gray-400">Suspicious Items</div>
                            <div className="text-2xl font-bold text-amber-600">{results.findings.filter((f: any) => f.severity !== 'Low').length}</div>
                        </div>
                        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
                            <div className="text-sm text-gray-500 dark:text-gray-400">Last Scan</div>
                            <div className="text-lg font-medium text-gray-900 dark:text-white">
                                {results.timestamp ? new Date(results.timestamp).toLocaleString() : 'N/A'}
                            </div>
                        </div>
                    </div>

                    {/* Findings Table */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                            <h3 className="text-lg font-semibold flex items-center">
                                <FileTextIcon className="mr-2 text-primary-500" />
                                Persistence Findings
                            </h3>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                    <tr>
                                        <th className="px-6 py-3">Type</th>
                                        <th className="px-6 py-3">Name</th>
                                        <th className="px-6 py-3">Location</th>
                                        <th className="px-6 py-3">Command / Details</th>
                                        <th className="px-6 py-3">Severity</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {results.findings.map((finding: any, idx: number) => (
                                        <tr key={idx} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className="px-2 py-1 bg-gray-100 dark:bg-gray-900 rounded text-xs font-mono">
                                                    {finding.type}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                                                {finding.name}
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono truncate max-w-xs" title={finding.location}>
                                                {finding.location}
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono truncate max-w-md" title={finding.command}>
                                                {finding.command}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${finding.severity === 'High' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' :
                                                        finding.severity === 'Medium' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' :
                                                            'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300'
                                                    }`}>
                                                    {finding.severity}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                    {results.findings.length === 0 && (
                                        <tr>
                                            <td colSpan={5} className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                                                No persistence mechanisms found.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-20 text-center">
                    <ShieldCheckIcon size={48} className="mx-auto text-gray-400 mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white">No Asset Selected</h3>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">Select an asset from the dropdown to view persistence findings or start a new scan.</p>
                </div>
            )}
        </div>
    );
};
