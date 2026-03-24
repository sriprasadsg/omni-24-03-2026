import React, { useState, useEffect } from 'react';
import { AlertTriangleIcon, ShieldAlertIcon, ActivityIcon, TrendingUpIcon } from './icons';

interface Correlation {
    id: string;
    tenant_id: string;
    type: string;
    pattern: string;
    event_count: number;
    confidence: number;
    severity: string;
    detected_at: string;
    event_ids?: string[];
    entity_type?: string;
    entity_value?: string;
    pattern_id?: string;
    mitre_attack?: string;
}

interface CorrelationStats {
    total_correlations: number;
    by_severity: Record<string, number>;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
}

interface CorrelationDashboardProps {
    tenantId: string;
}

const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
    const styles = {
        critical: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700',
        high: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700',
        medium: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700',
        low: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700',
    };

    return (
        <span className={`px-2 py-1 rounded-full text-xs font-bold border ${styles[severity] || styles.medium}`}>
            {severity.toUpperCase()}
        </span>
    );
};

const ConfidenceBar: React.FC<{ confidence: number }> = ({ confidence }) => {
    const percentage = Math.round(confidence * 100);
    const color = confidence > 0.7 ? 'bg-red-500' : confidence > 0.4 ? 'bg-amber-500' : 'bg-blue-500';

    return (
        <div className="w-full">
            <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-600 dark:text-gray-400">Confidence</span>
                <span className="font-bold text-gray-800 dark:text-gray-200">{percentage}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                    className={`${color} h-2 rounded-full transition-all duration-500`}
                    style={{ width: `${percentage}%` }}
                />
            </div>
        </div>
    );
};

export const CorrelationDashboard: React.FC<CorrelationDashboardProps> = ({ tenantId }) => {
    const [correlations, setCorrelations] = useState<Correlation[]>([]);
    const [stats, setStats] = useState<CorrelationStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [selectedSeverity, setSelectedSeverity] = useState<string | null>(null);

    useEffect(() => {
        loadCorrelations();
        loadStats();

        // Auto-refresh every 30 seconds
        const interval = setInterval(() => {
            loadCorrelations();
            loadStats();
        }, 30000);

        return () => clearInterval(interval);
    }, [tenantId, selectedSeverity]);

    const loadCorrelations = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            params.append('tenant_id', tenantId);
            if (selectedSeverity) params.append('severity', selectedSeverity);
            params.append('limit', '50');

            const response = await fetch(`/api/correlations?${params}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });

            if (response.ok) {
                const data = await response.json();
                setCorrelations(data);
            }
        } catch (error) {
            console.error('Failed to load correlations:', error);
        } finally {
            setLoading(false);
        }
    };

    const loadStats = async () => {
        try {
            const response = await fetch(`/api/correlations/stats?tenant_id=${tenantId}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });

            if (response.ok) {
                const data = await response.json();
                setStats(data);
            }
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    };

    const handleAnalyze = async () => {
        setAnalyzing(true);
        try {
            const response = await fetch('/api/correlations/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({
                    tenant_id: tenantId,
                    time_window_minutes: 60
                })
            });

            if (response.ok) {
                await loadCorrelations();
                await loadStats();
            }
        } catch (error) {
            console.error('Failed to analyze correlations:', error);
        } finally {
            setAnalyzing(false);
        }
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
                        SIEM Correlation Engine
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        AI-powered attack pattern detection and event correlation
                    </p>
                </div>
                <button
                    onClick={handleAnalyze}
                    disabled={analyzing}
                    className="px-6 py-3 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white rounded-lg font-semibold shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {analyzing ? (
                        <span className="flex items-center">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                            Analyzing...
                        </span>
                    ) : (
                        'Analyze Events'
                    )}
                </button>
            </div>

            {/* Stats Cards */}
            {stats && (
                <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                    <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-6 border border-blue-200 dark:border-blue-700 shadow-lg">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-blue-600 dark:text-blue-400 font-semibold">Total Correlations</p>
                                <p className="text-3xl font-bold text-blue-900 dark:text-blue-100 mt-2">{stats.total_correlations}</p>
                            </div>
                            <ActivityIcon size={40} className="text-blue-500 opacity-50" />
                        </div>
                    </div>

                    <div className="bg-gradient-to-br from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 rounded-xl p-6 border border-red-200 dark:border-red-700 shadow-lg">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-red-600 dark:text-red-400 font-semibold">Critical</p>
                                <p className="text-3xl font-bold text-red-900 dark:text-red-100 mt-2">{stats.critical_count}</p>
                            </div>
                            <ShieldAlertIcon size={40} className="text-red-500 opacity-50" />
                        </div>
                    </div>

                    <div className="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 rounded-xl p-6 border border-orange-200 dark:border-orange-700 shadow-lg">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-orange-600 dark:text-orange-400 font-semibold">High</p>
                                <p className="text-3xl font-bold text-orange-900 dark:text-orange-100 mt-2">{stats.high_count}</p>
                            </div>
                            <AlertTriangleIcon size={40} className="text-orange-500 opacity-50" />
                        </div>
                    </div>

                    <div className="bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-800/20 rounded-xl p-6 border border-amber-200 dark:border-amber-700 shadow-lg">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-amber-600 dark:text-amber-400 font-semibold">Medium</p>
                                <p className="text-3xl font-bold text-amber-900 dark:text-amber-100 mt-2">{stats.medium_count}</p>
                            </div>
                            <TrendingUpIcon size={40} className="text-amber-500 opacity-50" />
                        </div>
                    </div>

                    <div className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800/20 dark:to-gray-700/20 rounded-xl p-6 border border-gray-200 dark:border-gray-700 shadow-lg">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-600 dark:text-gray-400 font-semibold">Low</p>
                                <p className="text-3xl font-bold text-gray-900 dark:text-gray-100 mt-2">{stats.low_count}</p>
                            </div>
                            <ActivityIcon size={40} className="text-gray-500 opacity-50" />
                        </div>
                    </div>
                </div>
            )}

            {/* Severity Filter */}
            <div className="flex gap-2">
                <button
                    onClick={() => setSelectedSeverity(null)}
                    className={`px-4 py-2 rounded-lg font-semibold transition-all ${selectedSeverity === null
                            ? 'bg-purple-600 text-white shadow-lg'
                            : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                        }`}
                >
                    All
                </button>
                {['critical', 'high', 'medium', 'low'].map((severity) => (
                    <button
                        key={severity}
                        onClick={() => setSelectedSeverity(severity)}
                        className={`px-4 py-2 rounded-lg font-semibold transition-all ${selectedSeverity === severity
                                ? 'bg-purple-600 text-white shadow-lg'
                                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                            }`}
                    >
                        {severity.charAt(0).toUpperCase() + severity.slice(1)}
                    </button>
                ))}
            </div>

            {/* Correlations List */}
            <div className="space-y-4">
                {loading && correlations.length === 0 ? (
                    <div className="text-center py-12">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto mb-4"></div>
                        <p className="text-gray-600 dark:text-gray-400">Loading correlations...</p>
                    </div>
                ) : correlations.length === 0 ? (
                    <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
                        <ShieldAlertIcon size={64} className="mx-auto mb-4 text-gray-400 opacity-50" />
                        <p className="text-gray-600 dark:text-gray-400 text-lg">No correlations detected</p>
                        <p className="text-gray-500 dark:text-gray-500 text-sm mt-2">Click "Analyze Events" to detect attack patterns</p>
                    </div>
                ) : (
                    correlations.map((correlation) => (
                        <div
                            key={correlation.id}
                            className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg hover:shadow-xl transition-all"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-2">
                                        <SeverityBadge severity={correlation.severity} />
                                        <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded-full text-xs font-semibold">
                                            {correlation.type.replace('_', ' ').toUpperCase()}
                                        </span>
                                        {correlation.mitre_attack && (
                                            <span className="px-3 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full text-xs font-semibold">
                                                MITRE ATT&CK: {correlation.mitre_attack.replace('_', ' ').toUpperCase()}
                                            </span>
                                        )}
                                    </div>
                                    <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                                        {correlation.pattern}
                                    </h3>
                                    <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                                        <span>📊 {correlation.event_count} events</span>
                                        {correlation.entity_value && (
                                            <span>🎯 {correlation.entity_type}: {correlation.entity_value}</span>
                                        )}
                                        <span>🕐 {new Date(correlation.detected_at).toLocaleString()}</span>
                                    </div>
                                </div>
                            </div>
                            <ConfidenceBar confidence={correlation.confidence} />
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};
