import React, { useState, useEffect } from 'react';
import { ActivityIcon, TrendingUpIcon, AlertTriangleIcon, CheckCircleIcon, ClockIcon, ZapIcon } from './icons';

interface EndpointMetric {
    endpoint: string;
    total_requests: number;
    error_count: number;
    error_rate: number;
    slow_count: number;
    latency: {
        avg: number;
        p50: number;
        p95: number;
        p99: number;
    };
    throughput_per_min: number;
    health_status: string;
}

interface SystemHealth {
    status: string;
    total_requests: number;
    error_rate: number;
    avg_p95_latency: number;
    endpoints_monitored: number;
    critical_endpoints: number;
    warning_endpoints: number;
}

interface DatabasePerformance {
    collections: Array<{
        collection: string;
        avg_duration_ms: number;
        max_duration_ms: number;
        query_count: number;
        slow_queries: number;
    }>;
    total_queries: number;
    total_slow_queries: number;
}

interface APMDashboardProps {
    tenantId: string;
}

const HealthStatusBadge: React.FC<{ status: string }> = ({ status }) => {
    const styles = {
        healthy: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
        degraded: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
        warning: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
        critical: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
        unknown: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300',
    };

    const icons = {
        healthy: CheckCircleIcon,
        degraded: AlertTriangleIcon,
        warning: AlertTriangleIcon,
        critical: AlertTriangleIcon,
        unknown: ActivityIcon,
    };

    const Icon = icons[status] || ActivityIcon;

    return (
        <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold ${styles[status]}`}>
            <Icon size={14} />
            {status.toUpperCase()}
        </span>
    );
};

const LatencyBar: React.FC<{ latency: number; threshold: number }> = ({ latency, threshold }) => {
    const percentage = Math.min((latency / (threshold * 2)) * 100, 100);
    const color = latency > threshold ? 'bg-red-500' : latency > threshold * 0.7 ? 'bg-amber-500' : 'bg-green-500';

    return (
        <div className="w-full">
            <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-600 dark:text-gray-400">p95 Latency</span>
                <span className="font-bold text-gray-800 dark:text-gray-200">{latency.toFixed(0)}ms</span>
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

export const APMDashboard: React.FC<APMDashboardProps> = ({ tenantId }) => {
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [endpoints, setEndpoints] = useState<EndpointMetric[]>([]);
    const [slowestEndpoints, setSlowestEndpoints] = useState<EndpointMetric[]>([]);
    const [errorProneEndpoints, setErrorProneEndpoints] = useState<EndpointMetric[]>([]);
    const [dbPerformance, setDbPerformance] = useState<DatabasePerformance | null>(null);
    const [loading, setLoading] = useState(true);
    const [timeWindow, setTimeWindow] = useState(60); // minutes

    useEffect(() => {
        loadMetrics();

        // Auto-refresh every 10 seconds
        const interval = setInterval(loadMetrics, 10000);
        return () => clearInterval(interval);
    }, [timeWindow]);

    const loadMetrics = async () => {
        setLoading(true);
        try {
            // Load all metrics in parallel
            const [healthRes, endpointsRes, slowestRes, errorsRes, dbRes] = await Promise.all([
                fetch('/api/apm/health', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch(`/api/apm/endpoints?time_window_minutes=${timeWindow}`, {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch(`/api/apm/endpoints/slowest?limit=5&time_window_minutes=${timeWindow}`, {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch(`/api/apm/endpoints/errors?limit=5&time_window_minutes=${timeWindow}`, {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch(`/api/apm/database?time_window_minutes=${timeWindow}`, {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                })
            ]);

            if (healthRes.ok) setHealth(await healthRes.json());
            if (endpointsRes.ok) setEndpoints(await endpointsRes.json());
            if (slowestRes.ok) setSlowestEndpoints(await slowestRes.json());
            if (errorsRes.ok) setErrorProneEndpoints(await errorsRes.json());
            if (dbRes.ok) setDbPerformance(await dbRes.json());
        } catch (error) {
            console.error('Failed to load APM metrics:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
                        Application Performance Monitoring
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        Real-time performance metrics and SLA monitoring
                    </p>
                </div>
                <div className="flex gap-2">
                    {[5, 15, 60, 240].map((minutes) => (
                        <button
                            key={minutes}
                            onClick={() => setTimeWindow(minutes)}
                            className={`px-4 py-2 rounded-lg font-semibold transition-all ${timeWindow === minutes
                                    ? 'bg-purple-600 text-white shadow-lg'
                                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                        >
                            {minutes < 60 ? `${minutes}m` : `${minutes / 60}h`}
                        </button>
                    ))}
                </div>
            </div>

            {/* System Health */}
            {health && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">System Health</h2>
                        <HealthStatusBadge status={health.status} />
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Total Requests</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{health.total_requests.toLocaleString()}</p>
                        </div>
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Error Rate</p>
                            <p className={`text-2xl font-bold ${health.error_rate > 1 ? 'text-red-600' : 'text-green-600'}`}>
                                {health.error_rate.toFixed(2)}%
                            </p>
                        </div>
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Avg p95 Latency</p>
                            <p className={`text-2xl font-bold ${health.avg_p95_latency > 500 ? 'text-red-600' : 'text-green-600'}`}>
                                {health.avg_p95_latency.toFixed(0)}ms
                            </p>
                        </div>
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Endpoints Monitored</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{health.endpoints_monitored}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Slowest Endpoints */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
                        <ClockIcon size={24} className="text-orange-500" />
                        Slowest Endpoints
                    </h2>
                    {slowestEndpoints.length === 0 ? (
                        <p className="text-gray-500 dark:text-gray-400 text-center py-8">No data available</p>
                    ) : (
                        <div className="space-y-3">
                            {slowestEndpoints.map((endpoint, idx) => (
                                <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                                            {endpoint.endpoint}
                                        </span>
                                        <HealthStatusBadge status={endpoint.health_status} />
                                    </div>
                                    <LatencyBar latency={endpoint.latency.p95} threshold={500} />
                                    <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mt-2">
                                        <span>p50: {endpoint.latency.p50.toFixed(0)}ms</span>
                                        <span>p99: {endpoint.latency.p99.toFixed(0)}ms</span>
                                        <span>{endpoint.total_requests} reqs</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Error-Prone Endpoints */}
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
                        <AlertTriangleIcon size={24} className="text-red-500" />
                        Error-Prone Endpoints
                    </h2>
                    {errorProneEndpoints.length === 0 ? (
                        <div className="text-center py-8">
                            <CheckCircleIcon size={48} className="mx-auto mb-2 text-green-500" />
                            <p className="text-green-600 dark:text-green-400 font-semibold">No errors detected!</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {errorProneEndpoints.map((endpoint, idx) => (
                                <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                                            {endpoint.endpoint}
                                        </span>
                                        <span className="text-sm font-bold text-red-600 dark:text-red-400">
                                            {endpoint.error_rate.toFixed(2)}%
                                        </span>
                                    </div>
                                    <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400">
                                        <span>{endpoint.error_count} errors</span>
                                        <span>{endpoint.total_requests} total requests</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Database Performance */}
            {dbPerformance && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
                        <ZapIcon size={24} className="text-blue-500" />
                        Database Performance
                    </h2>
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                            <p className="text-sm text-blue-600 dark:text-blue-400">Total Queries</p>
                            <p className="text-2xl font-bold text-blue-900 dark:text-blue-100">{dbPerformance.total_queries.toLocaleString()}</p>
                        </div>
                        <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
                            <p className="text-sm text-red-600 dark:text-red-400">Slow Queries</p>
                            <p className="text-2xl font-bold text-red-900 dark:text-red-100">{dbPerformance.total_slow_queries}</p>
                        </div>
                    </div>
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                        {dbPerformance.collections.slice(0, 10).map((collection, idx) => (
                            <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{collection.collection}</span>
                                    <div className="flex gap-4 text-xs text-gray-600 dark:text-gray-400">
                                        <span>Avg: {collection.avg_duration_ms.toFixed(1)}ms</span>
                                        <span>Max: {collection.max_duration_ms.toFixed(0)}ms</span>
                                        <span>{collection.query_count} queries</span>
                                        {collection.slow_queries > 0 && (
                                            <span className="text-red-600 dark:text-red-400 font-semibold">
                                                {collection.slow_queries} slow
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* All Endpoints Table */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">All Endpoints</h2>
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-200 dark:border-gray-700">
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Endpoint</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Requests</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Error Rate</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">p50</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">p95</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">p99</th>
                                <th className="text-center py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {endpoints.slice(0, 20).map((endpoint, idx) => (
                                <tr key={idx} className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="py-3 px-4 text-sm text-gray-900 dark:text-gray-100 font-mono truncate max-w-xs">
                                        {endpoint.endpoint}
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 text-right">
                                        {endpoint.total_requests.toLocaleString()}
                                    </td>
                                    <td className={`py-3 px-4 text-sm text-right font-semibold ${endpoint.error_rate > 1 ? 'text-red-600' : 'text-green-600'
                                        }`}>
                                        {endpoint.error_rate.toFixed(2)}%
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 text-right">
                                        {endpoint.latency.p50.toFixed(0)}ms
                                    </td>
                                    <td className={`py-3 px-4 text-sm text-right font-semibold ${endpoint.latency.p95 > 500 ? 'text-red-600' : 'text-green-600'
                                        }`}>
                                        {endpoint.latency.p95.toFixed(0)}ms
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 text-right">
                                        {endpoint.latency.p99.toFixed(0)}ms
                                    </td>
                                    <td className="py-3 px-4 text-center">
                                        <HealthStatusBadge status={endpoint.health_status} />
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
