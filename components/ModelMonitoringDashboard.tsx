import React, { useState, useEffect } from 'react';
import { ActivityIcon, TrendingUpIcon, AlertTriangleIcon, CheckCircleIcon } from './icons';

interface DriftMetrics {
    psi_score: number;
    kl_divergence: number;
    performance_drift: number;
}

interface DriftDetection {
    id?: string;
    model_id: string;
    tenant_id: string;
    drift_detected: boolean;
    severity: string;
    metrics: DriftMetrics;
    baseline_samples: number;
    current_samples: number;
    detected_at: string;
    recommendation: string;
}

interface ModelStatus {
    model_id: string;
    model_name: string;
    latest_drift: DriftDetection;
}

interface ModelMonitoringDashboardProps {
    tenantId: string;
}

const SeverityIndicator: React.FC<{ severity: string; drift: boolean }> = ({ severity, drift }) => {
    if (!drift) {
        return (
            <div className="flex items-center gap-2 px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full">
                <CheckCircleIcon size={16} />
                <span className="text-xs font-bold">STABLE</span>
            </div>
        );
    }

    const styles = {
        critical: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700',
        high: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700',
        medium: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700',
        low: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700',
    };

    return (
        <div className={`flex items-center gap-2 px-3 py-1 rounded-full border ${styles[severity] || styles.medium}`}>
            <AlertTriangleIcon size={16} />
            <span className="text-xs font-bold">DRIFT: {severity.toUpperCase()}</span>
        </div>
    );
};

const MetricCard: React.FC<{ label: string; value: number; threshold: number; unit?: string }> = ({
    label, value, threshold, unit = ''
}) => {
    const isHigh = value > threshold;
    const percentage = Math.min((value / (threshold * 2)) * 100, 100);

    return (
        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
            <div className="flex justify-between items-start mb-2">
                <span className="text-sm text-gray-600 dark:text-gray-400 font-semibold">{label}</span>
                <span className={`text-lg font-bold ${isHigh ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
                    {value.toFixed(4)}{unit}
                </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                <div
                    className={`h-2 rounded-full transition-all duration-500 ${isHigh ? 'bg-red-500' : 'bg-green-500'
                        }`}
                    style={{ width: `${percentage}%` }}
                />
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Threshold: {threshold.toFixed(4)}{unit}
            </div>
        </div>
    );
};

export const ModelMonitoringDashboard: React.FC<ModelMonitoringDashboardProps> = ({ tenantId }) => {
    const [modelsStatus, setModelsStatus] = useState<ModelStatus[]>([]);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [selectedModel, setSelectedModel] = useState<ModelStatus | null>(null);

    useEffect(() => {
        loadModelsStatus();

        // Auto-refresh every 60 seconds
        const interval = setInterval(loadModelsStatus, 60000);
        return () => clearInterval(interval);
    }, [tenantId]);

    const loadModelsStatus = async () => {
        setLoading(true);
        try {
            const response = await fetch(`/api/ml-monitoring/models-status?tenant_id=${tenantId}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });

            if (response.ok) {
                const data = await response.json();
                setModelsStatus(data);
                if (data.length > 0 && !selectedModel) {
                    setSelectedModel(data[0]);
                }
            }
        } catch (error) {
            console.error('Failed to load models status:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyzeAll = async () => {
        setAnalyzing(true);
        try {
            const response = await fetch('/api/ml-monitoring/analyze-all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({ tenant_id: tenantId })
            });

            if (response.ok) {
                setTimeout(loadModelsStatus, 2000); // Refresh after 2 seconds
            }
        } catch (error) {
            console.error('Failed to analyze models:', error);
        } finally {
            setAnalyzing(false);
        }
    };

    const driftCount = modelsStatus.filter(m => m.latest_drift?.drift_detected).length;
    const stableCount = modelsStatus.length - driftCount;

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-green-600 to-blue-600 bg-clip-text text-transparent">
                        ML Model Monitoring
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        Real-time drift detection and performance tracking
                    </p>
                </div>
                <button
                    onClick={handleAnalyzeAll}
                    disabled={analyzing}
                    className="px-6 py-3 bg-gradient-to-r from-green-600 to-blue-600 hover:from-green-700 hover:to-blue-700 text-white rounded-lg font-semibold shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {analyzing ? (
                        <span className="flex items-center">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                            Analyzing...
                        </span>
                    ) : (
                        'Analyze All Models'
                    )}
                </button>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-6 border border-blue-200 dark:border-blue-700 shadow-lg">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-blue-600 dark:text-blue-400 font-semibold">Total Models</p>
                            <p className="text-3xl font-bold text-blue-900 dark:text-blue-100 mt-2">{modelsStatus.length}</p>
                        </div>
                        <ActivityIcon size={40} className="text-blue-500 opacity-50" />
                    </div>
                </div>

                <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-xl p-6 border border-green-200 dark:border-green-700 shadow-lg">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-green-600 dark:text-green-400 font-semibold">Stable Models</p>
                            <p className="text-3xl font-bold text-green-900 dark:text-green-100 mt-2">{stableCount}</p>
                        </div>
                        <CheckCircleIcon size={40} className="text-green-500 opacity-50" />
                    </div>
                </div>

                <div className="bg-gradient-to-br from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 rounded-xl p-6 border border-red-200 dark:border-red-700 shadow-lg">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-red-600 dark:text-red-400 font-semibold">Drifting Models</p>
                            <p className="text-3xl font-bold text-red-900 dark:text-red-100 mt-2">{driftCount}</p>
                        </div>
                        <TrendingUpIcon size={40} className="text-red-500 opacity-50" />
                    </div>
                </div>
            </div>

            {/* Models List */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Models Sidebar */}
                <div className="space-y-3">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">AI Models</h2>
                    {loading ? (
                        <div className="text-center py-8">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                        </div>
                    ) : modelsStatus.length === 0 ? (
                        <div className="text-center py-8 bg-gray-50 dark:bg-gray-800 rounded-xl">
                            <p className="text-gray-600 dark:text-gray-400">No AI models found</p>
                        </div>
                    ) : (
                        modelsStatus.map((model) => (
                            <div
                                key={model.model_id}
                                onClick={() => setSelectedModel(model)}
                                className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedModel?.model_id === model.model_id
                                        ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 shadow-lg'
                                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:shadow-md'
                                    }`}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className="font-bold text-gray-900 dark:text-gray-100">{model.model_name}</h3>
                                    <SeverityIndicator
                                        severity={model.latest_drift?.severity || 'low'}
                                        drift={model.latest_drift?.drift_detected || false}
                                    />
                                </div>
                                {model.latest_drift && (
                                    <div className="text-xs text-gray-500 dark:text-gray-400">
                                        Last checked: {new Date(model.latest_drift.detected_at).toLocaleString()}
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                </div>

                {/* Model Details */}
                <div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">Drift Analysis</h2>
                    {selectedModel && selectedModel.latest_drift ? (
                        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg space-y-6">
                            <div>
                                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">
                                    {selectedModel.model_name}
                                </h3>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    Model ID: {selectedModel.model_id}
                                </p>
                            </div>

                            {/* Metrics */}
                            <div className="space-y-3">
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">Statistical Metrics</h4>
                                <MetricCard
                                    label="PSI (Population Stability Index)"
                                    value={selectedModel.latest_drift.metrics.psi_score}
                                    threshold={0.2}
                                />
                                <MetricCard
                                    label="KL Divergence"
                                    value={selectedModel.latest_drift.metrics.kl_divergence}
                                    threshold={0.1}
                                />
                                <MetricCard
                                    label="Performance Drift"
                                    value={Math.abs(selectedModel.latest_drift.metrics.performance_drift)}
                                    threshold={0.05}
                                    unit="%"
                                />
                            </div>

                            {/* Sample Info */}
                            <div className="grid grid-cols-2 gap-4">
                                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">Baseline Samples</p>
                                    <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                        {selectedModel.latest_drift.baseline_samples}
                                    </p>
                                </div>
                                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">Current Samples</p>
                                    <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                        {selectedModel.latest_drift.current_samples}
                                    </p>
                                </div>
                            </div>

                            {/* Recommendation */}
                            <div className={`p-4 rounded-lg ${selectedModel.latest_drift.drift_detected
                                    ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700'
                                    : 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700'
                                }`}>
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-2">
                                    {selectedModel.latest_drift.drift_detected ? (
                                        <AlertTriangleIcon size={20} className="text-amber-600" />
                                    ) : (
                                        <CheckCircleIcon size={20} className="text-green-600" />
                                    )}
                                    Recommendation
                                </h4>
                                <p className="text-sm text-gray-700 dark:text-gray-300">
                                    {selectedModel.latest_drift.recommendation}
                                </p>
                            </div>
                        </div>
                    ) : (
                        <div className="bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-12 text-center">
                            <ActivityIcon size={64} className="mx-auto mb-4 text-gray-400 opacity-50" />
                            <p className="text-gray-600 dark:text-gray-400">
                                Select a model to view drift analysis
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
