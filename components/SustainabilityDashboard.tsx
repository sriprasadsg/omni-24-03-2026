import React, { useState, useEffect } from 'react';
import { CarbonFootprint, SustainabilityMetric } from '../types';
import { fetchCarbonFootprint, fetchSustainabilityMetrics } from '../services/apiService';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { TrendingUpIcon, ArrowDownIcon, ActivityIcon, ZapIcon } from './icons';

export const SustainabilityDashboard: React.FC = () => {
    const [carbonData, setCarbonData] = useState<CarbonFootprint[]>([]);
    const [metrics, setMetrics] = useState<SustainabilityMetric[]>([]);
    const [loading, setLoading] = useState(true);
    const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d'>('30d');

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const [carbonData, metricsData] = await Promise.all([
                fetchCarbonFootprint(),
                fetchSustainabilityMetrics()
            ]);

            setCarbonData(carbonData.reverse());
            setMetrics(metricsData);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching sustainability data:', error);
            setLoading(false);
        }
    };

    const totalEmissions = carbonData.reduce((sum, d) => sum + d.totalEmissions, 0);
    const avgEmissions = totalEmissions / carbonData.length;

    const latestBreakdown = carbonData[carbonData.length - 1]?.breakdown;
    const breakdownData = latestBreakdown ? [
        { name: 'Compute', value: latestBreakdown.compute, color: '#10b981' },
        { name: 'Storage', value: latestBreakdown.storage, color: '#3b82f6' },
        { name: 'Network', value: latestBreakdown.network, color: '#f59e0b' }
    ] : [];

    const chartData = carbonData.map(d => ({
        date: new Date(d.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        total: d.totalEmissions,
        compute: d.breakdown.compute,
        storage: d.breakdown.storage,
        network: d.breakdown.network
    }));

    if (loading) {
        return <div className="p-6">Loading sustainability metrics...</div>;
    }

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex justify-between items-start">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center">
                        <ActivityIcon size={28} className="mr-3 text-green-600" />
                        Sustainability & Green IT
                    </h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Track carbon emissions, energy efficiency, and ESG metrics
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setTimeRange('7d')}
                        className={`px-3 py-1 rounded ${timeRange === '7d' ? 'bg-primary-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'}`}
                    >
                        7 Days
                    </button>
                    <button
                        onClick={() => setTimeRange('30d')}
                        className={`px-3 py-1 rounded ${timeRange === '30d' ? 'bg-primary-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'}`}
                    >
                        30 Days
                    </button>
                    <button
                        onClick={() => setTimeRange('90d')}
                        className={`px-3 py-1 rounded ${timeRange === '90d' ? 'bg-primary-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'}`}
                    >
                        90 Days
                    </button>
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {metrics.map(metric => (
                    <div key={metric.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                        <div className="flex justify-between items-start mb-2">
                            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">{metric.name}</h3>
                            {metric.trend === 'improving' ? (
                                <ArrowDownIcon size={16} className="text-green-600" />
                            ) : metric.trend === 'worsening' ? (
                                <TrendingUpIcon size={16} className="text-red-600" />
                            ) : null}
                        </div>
                        <div className="flex items-baseline gap-2">
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">{metric.value}</span>
                            <span className="text-sm text-gray-500">{metric.unit}</span>
                        </div>
                        {metric.target && (
                            <div className="mt-2">
                                <div className="flex justify-between text-xs text-gray-500 mb-1">
                                    <span>Target: {metric.target}{metric.unit}</span>
                                    <span>{Math.round((metric.value / metric.target) * 100)}%</span>
                                </div>
                                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                    <div
                                        className={`h-2 rounded-full ${metric.value <= metric.target ? 'bg-green-600' : 'bg-red-600'
                                            }`}
                                        style={{ width: `${Math.min((metric.value / metric.target) * 100, 100)}%` }}
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Carbon Footprint Trends */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                        Carbon Emissions Trend
                    </h2>
                    <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="date" stroke="#9ca3af" />
                            <YAxis stroke="#9ca3af" label={{ value: 'kg CO2e', angle: -90, position: 'insideLeft' }} />
                            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
                            <Legend />
                            <Line type="monotone" dataKey="total" stroke="#10b981" strokeWidth={2} name="Total Emissions" />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                        Emissions Breakdown
                    </h2>
                    <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                            <Pie
                                data={breakdownData}
                                cx="50%"
                                cy="50%"
                                outerRadius={80}
                                fill="#8884d8"
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
                                {breakdownData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip />
                            <Legend wrapperStyle={{ fontSize: '12px', fontWeight: '600' }} />
                        </PieChart>
                    </ResponsiveContainer>
                    <div className="mt-4 space-y-2">
                        {breakdownData.map(item => (
                            <div key={item.name} className="flex justify-between items-center text-sm">
                                <div className="flex items-center gap-2">
                                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                                    <span className="text-gray-700 dark:text-gray-300">{item.name}</span>
                                </div>
                                <span className="font-semibold text-gray-900 dark:text-white">
                                    {item.value.toFixed(2)} kg CO2e
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Stacked Area Chart */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                    Emissions by Category
                </h2>
                <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#9ca3af" />
                        <YAxis stroke="#9ca3af" label={{ value: 'kg CO2e', angle: -90, position: 'insideLeft' }} />
                        <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
                        <Legend />
                        <Bar dataKey="compute" stackId="a" fill="#10b981" name="Compute" />
                        <Bar dataKey="storage" stackId="a" fill="#3b82f6" name="Storage" />
                        <Bar dataKey="network" stackId="a" fill="#f59e0b" name="Network" />
                    </BarChart>
                </ResponsiveContainer>
            </div>

            {/* Recommendations */}
            <div className="bg-gradient-to-r from-green-50 to-blue-50 dark:from-green-900/20 dark:to-blue-900/20 rounded-lg shadow-md p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                    <ZapIcon size={20} className="mr-2 text-green-600" />
                    Carbon Reduction Recommendations
                </h2>
                <div className="space-y-3">
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
                        <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                            Right-size compute instances
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Potential savings: <span className="font-semibold text-green-600">145 kg CO2e/month</span>
                        </p>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
                        <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                            Enable carbon-aware workload scheduling
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Run batch jobs during low-carbon hours. Potential savings: <span className="font-semibold text-green-600">89 kg CO2e/month</span>
                        </p>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
                        <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                            Migrate to greener regions
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Consider us-west-2 (renewable energy: 85%). Potential savings: <span className="font-semibold text-green-600">230 kg CO2e/month</span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};
