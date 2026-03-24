import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, AlertTriangleIcon, ClockIcon, TrendingUpIcon } from './icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

interface ComplianceDashboardProps {
    tenantId?: string;
}

interface ComplianceData {
    framework: string;
    compliance_rate: number;
    total_patches: number;
    compliant: number;
    at_risk: number;
    overdue: number;
    patches: {
        compliant: any[];
        at_risk: any[];
        overdue: any[];
    };
}

export const PatchComplianceDashboard: React.FC<ComplianceDashboardProps> = ({ tenantId }) => {
    const [selectedFramework, setSelectedFramework] = useState('SOC2');
    const [complianceData, setComplianceData] = useState<ComplianceData | null>(null);
    const [loading, setLoading] = useState(true);

    const frameworks = ['SOC2', 'PCI-DSS', 'HIPAA', 'ISO27001'];

    useEffect(() => {
        fetchComplianceData();
    }, [selectedFramework, tenantId]);

    const fetchComplianceData = async () => {
        setLoading(true);
        try {
            const url = `/api/patches/compliance-status?framework=${selectedFramework}${tenantId ? `&tenant_id=${tenantId}` : ''}`;
            const response = await fetch(url);
            const data = await response.json();
            setComplianceData(data);
        } catch (error) {
            console.error('Error fetching compliance data:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading || !complianceData) {
        return <div className="p-6">Loading compliance data...</div>;
    }

    const chartData = [
        { name: 'Compliant', value: complianceData.compliant, fill: '#10b981' },
        { name: 'At Risk', value: complianceData.at_risk, fill: '#f59e0b' },
        { name: 'Overdue', value: complianceData.overdue, fill: '#ef4444' }
    ];

    const getComplianceColor = (rate: number) => {
        if (rate >= 90) return 'text-green-600 dark:text-green-400';
        if (rate >= 70) return 'text-yellow-600 dark:text-yellow-400';
        return 'text-red-600 dark:text-red-400';
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white flex items-center">
                        <ShieldCheckIcon size={28} className="mr-3 text-primary-500" />
                        Patch Compliance Dashboard
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Track regulatory compliance and SLA adherence for patch management
                    </p>
                </div>

                {/* Framework Selector */}
                <select
                    value={selectedFramework}
                    onChange={(e) => setSelectedFramework(e.target.value)}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-800 dark:text-white"
                >
                    {frameworks.map(fw => (
                        <option key={fw} value={fw}>{fw}</option>
                    ))}
                </select>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Compliance Rate</p>
                    <p className={`text-3xl font-bold ${getComplianceColor(complianceData.compliance_rate)}`}>
                        {complianceData.compliance_rate.toFixed(1)}%
                    </p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1 flex items-center">
                        <ShieldCheckIcon size={14} className="mr-1 text-green-500" /> Compliant
                    </p>
                    <p className="text-3xl font-bold text-green-600 dark:text-green-400">
                        {complianceData.compliant}
                    </p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1 flex items-center">
                        <AlertTriangleIcon size={14} className="mr-1 text-yellow-500" /> At Risk
                    </p>
                    <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
                        {complianceData.at_risk}
                    </p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1 flex items-center">
                        <ClockIcon size={14} className="mr-1 text-red-500" /> Overdue
                    </p>
                    <p className="text-3xl font-bold text-red-600 dark:text-red-400">
                        {complianceData.overdue}
                    </p>
                </div>
            </div>

            {/* Visualization */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold mb-4">Compliance Distribution</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={chartData}
                                    cx="50%"
                                    cy="50%"
                                    outerRadius={80}
                                    dataKey="value"
                                    label={(props) => {
                                        const RADIAN = Math.PI / 180;
                                        const { cx, cy, midAngle, outerRadius, percent } = props;
                                        const radius = outerRadius + 25;
                                        const x = cx + radius * Math.cos(-midAngle * RADIAN);
                                        const y = cy + radius * Math.sin(-midAngle * RADIAN);

                                        return (
                                            <text
                                                x={x}
                                                y={y}
                                                fill="currentColor"
                                                textAnchor={x > cx ? 'start' : 'end'}
                                                dominantBaseline="central"
                                                className="text-sm font-bold"
                                            >
                                                {`${(percent * 100).toFixed(0)}%`}
                                            </text>
                                        );
                                    }}
                                    labelLine={{
                                        stroke: '#9ca3af',
                                        strokeWidth: 1
                                    }}
                                >
                                    {chartData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.fill} />
                                    ))}
                                </Pie>
                                <Tooltip />
                                <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '600' }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* SLA Information */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold mb-4">SLA Requirements - {selectedFramework}</h3>
                    <div className="space-y-3">
                        {[
                            { severity: 'Critical', hours: selectedFramework === 'PCI-DSS' ? 24 : selectedFramework === 'HIPAA' ? 48 : 72 },
                            { severity: 'High', hours: selectedFramework === 'PCI-DSS' ? 72 : selectedFramework === 'ISO27001' ? 336 : 168 },
                            { severity: 'Medium', hours: selectedFramework === 'ISO27001' ? 720 : 720 },
                            { severity: 'Low', hours: 2160 }
                        ].map(({ severity, hours }) => (
                            <div key={severity} className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                                <span className={`font-medium ${severity === 'Critical' ? 'text-red-600 dark:text-red-400' :
                                    severity === 'High' ? 'text-orange-600 dark:text-orange-400' :
                                        severity === 'Medium' ? 'text-yellow-600 dark:text-yellow-400' :
                                            'text-blue-600 dark:text-blue-400'
                                    }`}>
                                    {severity}
                                </span>
                                <span className="text-sm text-gray-700 dark:text-gray-300">
                                    {hours < 168 ? `${hours}h` : `${hours / 24}d`}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Overdue Patches Alert */}
            {complianceData.overdue > 0 && (
                <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 p-4 rounded-lg">
                    <div className="flex items-start">
                        <AlertTriangleIcon size={24} className="text-red-600 dark:text-red-400 mr-3 flex-shrink-0 mt-0.5" />
                        <div>
                            <h4 className="text-lg font-semibold text-red-900 dark:text-red-200">
                                {complianceData.overdue} Patches Overdue
                            </h4>
                            <p className="text-sm text-red-800 dark:text-red-300 mt-1">
                                These patches have exceeded their {selectedFramework} SLA deadline and require immediate attention.
                            </p>
                            <button className="mt-3 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium">
                                View Overdue Patches
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Detailed Tables */}
            <div className="grid grid-cols-1 gap-6">
                {/* At Risk Patches */}
                {complianceData.at_risk > 0 && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                            <h3 className="text-lg font-semibold flex items-center">
                                <AlertTriangleIcon size={20} className="mr-2 text-yellow-500" />
                                At-Risk Patches ({complianceData.at_risk})
                            </h3>
                            <p className="text-sm text-gray-500 mt-1">Less than 25% of SLA time remaining</p>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="bg-gray-50 dark:bg-gray-700">
                                    <tr>
                                        <th className="px-4 py-3 text-left font-semibold">Patch</th>
                                        <th className="px-4 py-3 text-left font-semibold">Severity</th>
                                        <th className="px-4 py-3 text-left font-semibold">Time Remaining</th>
                                        <th className="px-4 py-3 text-left font-semibold">Affected Assets</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                    {complianceData.patches.at_risk.slice(0, 10).map((patch: any) => (
                                        <tr key={patch.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                            <td className="px-4 py-3 font-medium">{patch.name}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-1 rounded text-xs font-semibold ${patch.severity === 'Critical' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' :
                                                    patch.severity === 'High' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300' :
                                                        'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300'
                                                    }`}>
                                                    {patch.severity}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-yellow-600 dark:text-yellow-400 font-medium">
                                                {Math.max(0, patch.time_remaining_hours).toFixed(1)}h
                                            </td>
                                            <td className="px-4 py-3">
                                                {patch.affectedAssets?.length || 0}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
