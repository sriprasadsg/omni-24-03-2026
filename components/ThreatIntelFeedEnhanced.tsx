import React, { useState, useEffect } from 'react';
import { ShieldSearchIcon, AlertTriangleIcon } from './icons';
import { scanArtifact, fetchThreatIntelFeed, fetchThreatIntelStats, ThreatIntelScan, ThreatIntelStats } from '../services/threatIntelService';

interface ThreatIntelFeedEnhancedProps {
    tenantId: string;
}

const VerdictIndicator: React.FC<{ verdict: string }> = ({ verdict }) => {
    const classes = {
        'Malicious': 'bg-red-500 animate-pulse',
        'Suspicious': 'bg-amber-500',
        'Harmless': 'bg-green-500',
        'Unknown': 'bg-gray-400',
        'Pending': 'bg-blue-500 animate-pulse',
    };
    return <span className={`inline-block h-2 w-2 rounded-full ${classes[verdict] || 'bg-gray-400'}`} title={verdict}></span>;
};

export const ThreatIntelFeedEnhanced: React.FC<ThreatIntelFeedEnhancedProps> = ({ tenantId }) => {
    const [feed, setFeed] = useState<ThreatIntelScan[]>([]);
    const [stats, setStats] = useState<ThreatIntelStats | null>(null);
    const [loading, setLoading] = useState(false);
    const [scanning, setScanning] = useState(false);
    const [artifact, setArtifact] = useState('');
    const [artifactType, setArtifactType] = useState<'ip' | 'domain' | 'url' | 'hash'>('ip');
    const [error, setError] = useState<string | null>(null);

    // Load feed and stats on mount
    useEffect(() => {
        loadFeed();
        loadStats();

        // Auto-refresh every 30 seconds
        const interval = setInterval(() => {
            loadFeed();
            loadStats();
        }, 30000);

        return () => clearInterval(interval);
    }, [tenantId]);

    const loadFeed = async () => {
        setLoading(true);
        try {
            const data = await fetchThreatIntelFeed(tenantId, 50);
            setFeed(data);
        } catch (err) {
            console.error('Failed to load threat feed:', err);
        } finally {
            setLoading(false);
        }
    };

    const loadStats = async () => {
        try {
            const data = await fetchThreatIntelStats(tenantId);
            setStats(data);
        } catch (err) {
            console.error('Failed to load stats:', err);
        }
    };

    const handleScan = async () => {
        if (!artifact.trim()) {
            setError('Please enter an artifact to scan');
            return;
        }

        setScanning(true);
        setError(null);

        try {
            const result = await scanArtifact(artifact, artifactType, tenantId);
            setFeed(prev => [result, ...prev]);
            setArtifact('');
            await loadStats();
        } catch (err: any) {
            setError(err.message || 'Failed to scan artifact');
        } finally {
            setScanning(false);
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-lg">
            {/* Header with Stats */}
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-gradient-to-r from-blue-50 to-purple-50 dark:from-gray-700 dark:to-gray-800">
                <div className="flex items-center justify-between mb-3">
                    <h3 className="text-lg font-bold flex items-center">
                        <ShieldSearchIcon className="mr-2 text-blue-600 dark:text-blue-400" size={24} />
                        Threat Intelligence Feed
                    </h3>
                    <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full font-semibold">
                        Powered by VirusTotal
                    </span>
                </div>

                {/* Stats Bar */}
                {stats && (
                    <div className="grid grid-cols-4 gap-2 text-center">
                        <div className="bg-white dark:bg-gray-700 rounded p-2">
                            <div className="text-2xl font-bold text-gray-800 dark:text-gray-100">{stats.total_scans}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">Total Scans</div>
                        </div>
                        <div className="bg-red-50 dark:bg-red-900/20 rounded p-2">
                            <div className="text-2xl font-bold text-red-600 dark:text-red-400">{stats.malicious_count}</div>
                            <div className="text-xs text-red-600 dark:text-red-400">Malicious</div>
                        </div>
                        <div className="bg-amber-50 dark:bg-amber-900/20 rounded p-2">
                            <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">{stats.suspicious_count}</div>
                            <div className="text-xs text-amber-600 dark:text-amber-400">Suspicious</div>
                        </div>
                        <div className="bg-green-50 dark:bg-green-900/20 rounded p-2">
                            <div className="text-2xl font-bold text-green-600 dark:text-green-400">{stats.harmless_count}</div>
                            <div className="text-xs text-green-600 dark:text-green-400">Harmless</div>
                        </div>
                    </div>
                )}
            </div>

            {/* Scan Input */}
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                <div className="flex gap-2">
                    <select
                        value={artifactType}
                        onChange={(e) => setArtifactType(e.target.value as any)}
                        className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="ip">IP Address</option>
                        <option value="domain">Domain</option>
                        <option value="url">URL</option>
                        <option value="hash">File Hash</option>
                    </select>
                    <input
                        type="text"
                        value={artifact}
                        onChange={(e) => setArtifact(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleScan()}
                        placeholder={`Enter ${artifactType} to scan...`}
                        className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                        onClick={handleScan}
                        disabled={scanning}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold text-sm disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {scanning ? 'Scanning...' : 'Scan'}
                    </button>
                </div>
                {error && (
                    <div className="mt-2 text-sm text-red-600 dark:text-red-400 flex items-center">
                        <AlertTriangleIcon size={16} className="mr-1" />
                        {error}
                    </div>
                )}
            </div>

            {/* Feed */}
            <div className="p-4 space-y-2 max-h-[400px] overflow-y-auto">
                {loading && feed.length === 0 ? (
                    <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
                        Loading threat intelligence feed...
                    </div>
                ) : feed.length === 0 ? (
                    <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                        <ShieldSearchIcon size={48} className="mx-auto mb-2 opacity-50" />
                        <p>No scans yet. Scan an artifact above to get started.</p>
                    </div>
                ) : (
                    feed.map(item => (
                        <div key={item.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 hover:shadow-md transition-shadow">
                            <div className="flex justify-between items-start">
                                <div className="flex items-start space-x-2 flex-1 overflow-hidden">
                                    <VerdictIndicator verdict={item.verdict} />
                                    <div className="flex-1 min-w-0">
                                        <p className="font-mono text-sm text-gray-800 dark:text-gray-200 truncate font-semibold">
                                            {item.artifact}
                                        </p>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${item.verdict === 'Malicious' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
                                                    item.verdict === 'Suspicious' ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' :
                                                        item.verdict === 'Harmless' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
                                                            'bg-gray-100 dark:bg-gray-600 text-gray-700 dark:text-gray-300'
                                                }`}>
                                                {item.verdict}
                                            </span>
                                            <span className="text-xs text-gray-500 dark:text-gray-400">
                                                {item.detection_ratio}
                                            </span>
                                            <span className="text-xs text-gray-400 dark:text-gray-500">
                                                {item.artifact_type.toUpperCase()}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className="text-xs text-gray-400 dark:text-gray-500 text-right ml-2">
                                    {new Date(item.scan_date).toLocaleString()}
                                </div>
                            </div>
                            {(item.malicious || 0) > 0 && (
                                <div className="mt-2 text-xs text-red-600 dark:text-red-400 font-semibold">
                                    ⚠️ {item.malicious} engines detected this as malicious
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};
