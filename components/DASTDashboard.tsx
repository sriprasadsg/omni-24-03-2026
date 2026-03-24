import React, { useState, useEffect } from 'react';
import { fetchDastScans, startDastScan } from '../services/apiService';
import { DastScan, DastFinding } from '../types';
import { Shield, Play, AlertTriangle, CheckCircle, Activity } from 'lucide-react';

export const DASTDashboard: React.FC = () => {
    const [scans, setScans] = useState<DastScan[]>([]);
    const [loading, setLoading] = useState(true);
    const [targetUrl, setTargetUrl] = useState('https://test.app.internal');
    const [scanning, setScanning] = useState(false);

    useEffect(() => {
        loadScans();
    }, []);

    const loadScans = async () => {
        setLoading(true);
        try {
            const data = await fetchDastScans();
            setScans(data);
        } catch (e) {
            console.error("Failed to load DAST scans", e);
        } finally {
            setLoading(false);
        }
    };

    const handleStartScan = async () => {
        setScanning(true);
        try {
            await startDastScan(targetUrl);
            await loadScans();
        } catch (e) {
            console.error("Failed to start scan", e);
        } finally {
            setScanning(false);
        }
    };

    const getSeverityColor = (severity: string) => {
        switch (severity.toLowerCase()) {
            case 'critical': return 'text-red-500';
            case 'high': return 'text-orange-500';
            case 'medium': return 'text-yellow-500';
            case 'low': return 'text-blue-500';
            default: return 'text-gray-500';
        }
    };

    return (
        <div className="p-6 space-y-6">
            <h1 className="text-2xl font-bold flex items-center gap-2">
                <Activity className="text-blue-400" />
                Dynamic Application Security Testing (DAST)
            </h1>
            <p className="text-gray-400">Run dynamic scans against running applications to find runtime vulnerabilities.</p>

            {/* Actions */}
            <div className="bg-gray-800 p-4 rounded-lg flex items-center gap-4">
                <input
                    type="text"
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                    className="bg-gray-700 text-white px-4 py-2 rounded flex-1 border border-gray-600 focus:border-blue-500 outline-none"
                    placeholder="Enter target URL (e.g. https://staging.app.com)"
                />
                <button
                    onClick={handleStartScan}
                    disabled={scanning}
                    className={`px-6 py-2 rounded font-medium flex items-center gap-2 ${scanning ? 'bg-gray-600 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'}`}
                >
                    <Play />
                    {scanning ? 'Scanning...' : 'Start New Scan'}
                </button>
            </div>

            {/* Recent Scans */}
            <div className="bg-gray-800 rounded-lg overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-700">
                    <h2 className="text-lg font-semibold">Recent Scans</h2>
                </div>
                {loading ? (
                    <div className="p-8 text-center text-gray-400">Loading scans...</div>
                ) : scans.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No scans found. Start a scan above.</div>
                ) : (
                    <div className="divide-y divide-gray-700">
                        {scans.map(scan => (
                            <div key={scan.id} className="p-6 hover:bg-gray-750 transition-colors">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <div className="flex items-center gap-3">
                                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${scan.status === 'Completed' ? 'bg-green-900 text-green-200' : 'bg-yellow-900 text-yellow-200'}`}>
                                                {scan.status.toUpperCase()}
                                            </span>
                                            <h3 className="font-medium text-lg">{scan.targetUrl}</h3>
                                        </div>
                                        <div className="text-sm text-gray-400 mt-1">
                                            ID: {scan.id} • Started: {new Date(scan.startTime).toLocaleString()}
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-2xl font-bold">{scan.riskScore}</div>
                                        <div className="text-xs text-gray-500">Risk Score</div>
                                    </div>
                                </div>

                                {scan.findings.length > 0 && (
                                    <div className="bg-gray-900 rounded p-4 mt-2">
                                        <h4 className="text-sm font-semibold mb-2 text-gray-300">Findings ({scan.findingsCount})</h4>
                                        <div className="space-y-2">
                                            {scan.findings.map(finding => (
                                                <div key={finding.id} className="flex justify-between items-center text-sm p-2 bg-gray-800 rounded border border-gray-700">
                                                    <div className="flex items-center gap-3">
                                                        <AlertTriangle className={getSeverityColor(finding.severity)} />
                                                        <span className="font-medium">{finding.title}</span>
                                                    </div>
                                                    <span className={`text-xs px-2 py-1 rounded bg-gray-700 ${getSeverityColor(finding.severity)}`}>
                                                        {finding.severity}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
