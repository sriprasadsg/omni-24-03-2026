import React, { useState, useEffect } from 'react';
import { TrendingUpIcon, ShieldCheckIcon, ClockIcon, AlertTriangleIcon } from './icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell } from 'recharts';

interface ExecutiveSummary {
    kpis: {
        compliance_rate: number;
        patches_per_week: number;
        mttr_hours: number;
        asset_exposure_rate: number;
        critical_vulnerabilities: number;
        high_exploit_risk: number;
    };
    sla_summary: any;
    vulnerability_summary: any;
}

export const ExecutiveDashboard: React.FC<{ tenantId?: string }> = ({ tenantId }) => {
    const [summary, setSummary] = useState<ExecutiveSummary | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchExecutiveSummary();
        const interval = setInterval(fetchExecutiveSummary, 60000); // Refresh every minute
        return () => clearInterval(interval);
    }, [tenantId]);

    const fetchExecutiveSummary = async () => {
        try {
            const url = `/api/reports/executive-summary${tenantId ? `?tenant_id=${tenantId}` : ''}`;
            const response = await fetch(url);
            const data = await response.json();
            setSummary(data);
        } catch (error) {
            console.error('Error fetching executive summary:', error);
        } finally {
            setLoading(false);
        }
    };

    const getStatusColor = (value: number, thresholds: { good: number; warning: number }) => {
        if (value >= thresholds.good) return 'text-green-600 dark:text-green-400';
        if (value >= thresholds.warning) return 'text-yellow-600 dark:text-yellow-400';
        return 'text-red-600 dark:text-red-400';
    };

    if (loading) {
        return <div className="p-6">Loading executive dashboard...</div>;
    }

    if (!summary) {
        return <div className="p-6">No data available</div>;
    }

    const { kpis } = summary;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Executive Dashboard</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    High-level security and compliance metrics
                </p>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {/* Compliance Rate */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border-l-4 border-green-500">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">SLA Compliance Rate</p>
                        <ShieldCheckIcon size={24} className="text-green-500" />
                    </div>
                    <p className={`text-4xl font-bold ${getStatusColor(kpis.compliance_rate, { good: 90, warning: 75 })}`}>
                        {kpis.compliance_rate.toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        {kpis.compliance_rate >= 90 ? '✓ Meeting SLA targets' : '⚠ Below target'}
                    </p>
                </div>

                {/* MTTR */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border-l-4 border-blue-500">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Mean Time To Remediate</p>
                        <ClockIcon size={24} className="text-blue-500" />
                    </div>
                    <p className="text-4xl font-bold text-blue-600 dark:text-blue-400">
                        {kpis.mttr_hours.toFixed(1)}h
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        Average patch deployment time
                    </p>
                </div>

                {/* Patch Velocity */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border-l-4 border-purple-500">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Patch Velocity</p>
                        <TrendingUpIcon size={24} className="text-purple-500" />
                    </div>
                    <p className="text-4xl font-bold text-purple-600 dark:text-purple-400">
                        {kpis.patches_per_week.toFixed(1)}/wk
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        Patches deployed per week
                    </p>
                </div>

                {/* Asset Exposure */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border-l-4 border-yellow-500">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Asset Exposure Rate</p>
                        <AlertTriangleIcon size={24} className="text-yellow-500" />
                    </div>
                    <p className={`text-4xl font-bold ${getStatusColor(100 - kpis.asset_exposure_rate, { good: 90, warning: 70 })}`}>
                        {kpis.asset_exposure_rate.toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        Assets with pending vulnerabilities
                    </p>
                </div>

                {/* Critical Vulnerabilities */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border-l-4 border-red-500">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Critical Vulnerabilities</p>
                        <AlertTriangleIcon size={24} className="text-red-500" />
                    </div>
                    <p className="text-4xl font-bold text-red-600 dark:text-red-400">
                        {kpis.critical_vulnerabilities}
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        Pending critical patches
                    </p>
                </div>

                {/* High Exploit Risk */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border-l-4 border-orange-500">
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">High Exploit Risk</p>
                        <AlertTriangleIcon size={24} className="text-orange-500" />
                    </div>
                    <p className="text-4xl font-bold text-orange-600 dark:text-orange-400">
                        {kpis.high_exploit_risk}
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                        EPSS score {'>'} 50%
                    </p>
                </div>
            </div>

            {/* Risk Summary */}
            {(kpis.critical_vulnerabilities > 0 || kpis.high_exploit_risk > 0) && (
                <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 p-6 rounded-lg">
                    <div className="flex items-start">
                        <AlertTriangleIcon size={32} className="text-red-600 dark:text-red-400 mr-4 flex-shrink-0" />
                        <div>
                            <h3 className="text-xl font-bold text-red-900 dark:text-red-200 mb-2">
                                Action Required: High-Risk Vulnerabilities Detected
                            </h3>
                            <div className="space-y-1 text-sm text-red-800 dark:text-red-300">
                                {kpis.critical_vulnerabilities > 0 && (
                                    <p>• {kpis.critical_vulnerabilities} critical vulnerability{kpis.critical_vulnerabilities !== 1 ? 'ies' : 'y'} requiring immediate attention</p>
                                )}
                                {kpis.high_exploit_risk > 0 && (
                                    <p>• {kpis.high_exploit_risk} patch{kpis.high_exploit_risk !== 1 ? 'es' : ''} with high exploit probability ({'>'} 50%)</p>
                                )}
                                {kpis.asset_exposure_rate > 30 && (
                                    <p>• {kpis.asset_exposure_rate.toFixed(1)}% of assets have pending security patches</p>
                                )}
                            </div>
                            <button className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium text-sm">
                                View Critical Patches
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Positive Message */}
            {kpis.compliance_rate >= 90 && kpis.critical_vulnerabilities === 0 && (
                <div className="bg-green-50 dark:bg-green-900/20 border-l-4 border-green-500 p-6 rounded-lg">
                    <div className="flex items-start">
                        <ShieldCheckIcon size={32} className="text-green-600 dark:text-green-400 mr-4 flex-shrink-0" />
                        <div>
                            <h3 className="text-xl font-bold text-green-900 dark:text-green-200 mb-2">
                                Excellent Security Posture ✓
                            </h3>
                            <div className="space-y-1 text-sm text-green-800 dark:text-green-300">
                                <p>• SLA compliance is above 90%</p>
                                <p>• No critical vulnerabilities outstanding</p>
                                <p>• Patch management operating effectively</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Additional Details */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* SLA Breakdown */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold mb-4">SLA Performance</h3>
                    <div className="space-y-3">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Compliant</span>
                            <span className="text-sm font-bold text-green-600 dark:text-green-400">
                                {summary.sla_summary.compliant}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">At Risk</span>
                            <span className="text-sm font-bold text-yellow-600 dark:text-yellow-400">
                                {summary.sla_summary.at_risk}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Breached</span>
                            <span className="text-sm font-bold text-red-600 dark:text-red-400">
                                {summary.sla_summary.breached}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Vulnerability Stats */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold mb-4">Vulnerability Overview</h3>
                    <div className="space-y-3">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Total Assets</span>
                            <span className="text-sm font-bold">
                                {summary.vulnerability_summary.total_assets}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Exposed Assets</span>
                            <span className="text-sm font-bold text-orange-600 dark:text-orange-400">
                                {summary.vulnerability_summary.exposed_assets}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Pending Patches</span>
                            <span className="text-sm font-bold">
                                {summary.vulnerability_summary.pending_patches}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
