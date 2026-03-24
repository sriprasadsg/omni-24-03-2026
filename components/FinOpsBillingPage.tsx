import React, { useState, useMemo, useContext, useEffect } from 'react';
import { Tenant } from '../types';
import { DollarSignIcon, BotIcon, TrendingUpIcon, CheckIcon, SparklesIcon } from './icons';
import { BarChart, Bar, PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Area, AreaChart } from 'recharts';
import { useUser } from '../contexts/UserContext';
import { getFinOpsAnalysis, recalculateFinOpsCosts } from '../services/apiService';
import { ThemeContext } from '../contexts/ThemeContext';

interface FinOpsBillingPageProps {
    tenants: Tenant[];
    isSuperAdminView: boolean;
}

const COLORS = ['#3b82f6', '#10b981', '#f97316', '#8b5cf6', '#ef4444', '#f59e0b'];

const StatCard: React.FC<{ title: string; value: string; icon: React.ReactNode; }> = ({ title, value, icon }) => (
    <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex items-center">
        <div className="p-3 bg-primary-100 dark:bg-primary-900/50 rounded-full mr-4 text-primary-500 dark:text-primary-400">
            {icon}
        </div>
        <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
        </div>
    </div>
);

const LoadingSkeleton: React.FC = () => (
    <div className="space-y-4 animate-pulse">
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-5/6"></div>
    </div>
);


export const FinOpsBillingPage: React.FC<FinOpsBillingPageProps> = ({ tenants, isSuperAdminView }) => {
    const { currentUser } = useUser();
    const { theme } = useContext(ThemeContext);
    const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
    const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

    // Initial state logic: if super admin, start with Overview (empty string) unless only 1 tenant?
    // Actually, usually overview is best.
    const [selectedTenantId, setSelectedTenantId] = useState<string>(isSuperAdminView ? '' : (tenants.find(t => t.id === currentUser?.tenantId)?.id || ''));

    // Ensure we don't get stuck with an invalid ID if props change
    useEffect(() => {
        if (!isSuperAdminView && currentUser?.tenantId && selectedTenantId !== currentUser.tenantId) {
            setSelectedTenantId(currentUser.tenantId);
        }
    }, [isSuperAdminView, currentUser, selectedTenantId]);

    const [analysis, setAnalysis] = useState<string>('');
    const [recommendations, setRecommendations] = useState<string[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isRecalculating, setIsRecalculating] = useState(false);
    const [error, setError] = useState<string>('');

    const activeTenant = useMemo(() => {
        if (!isSuperAdminView) {
            return tenants.find(t => t.id === currentUser?.tenantId);
        }
        return tenants.find(t => t.id === selectedTenantId);
    }, [tenants, isSuperAdminView, currentUser, selectedTenantId]);

    const finOpsData = activeTenant?.finOpsData;

    const handleGenerateAnalysis = async () => {
        if (!finOpsData) return;
        setIsLoading(true);
        setError('');
        setAnalysis('');
        setRecommendations([]);

        try {
            const result = await getFinOpsAnalysis(finOpsData);
            setAnalysis(result.analysis);
            setRecommendations(result.recommendations);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to generate analysis.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleRecalculate = async () => {
        if (!activeTenant) return;
        setIsRecalculating(true);
        setError('');
        try {
            await recalculateFinOpsCosts(activeTenant.id);
            // Ideally trigger refresh of tenants here
            // window.location.reload(); // Too aggressive
            alert(`Costs recalculated for ${activeTenant.name}. (Data refresh required to see changes)`);
        } catch (err) {
            setError('Failed to recalculate costs.');
        } finally {
            setIsRecalculating(false);
        }
    };

    const formatCurrency = (value: number) => `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    // Render Tenant Overview for Super Admin if no tenant selected
    if (isSuperAdminView && !selectedTenantId) {
        return (
            <div className="container mx-auto space-y-6">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">FinOps Overview (All Tenants)</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Aggregate cost monitoring across the platform.</p>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-900">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Tenant</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Current Month</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Forecast</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Budget</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {tenants.map((tenant) => {
                                const usagePercent = tenant.finOpsData ? (tenant.finOpsData.currentMonthCost / (tenant.budget?.monthlyLimit || 1)) * 100 : 0;
                                const isOverBudget = usagePercent > 100;
                                const isNearBudget = usagePercent > 85;

                                return (
                                    <tr key={tenant.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm font-medium text-gray-900 dark:text-white">{tenant.name}</div>
                                            <div className="text-xs text-gray-500 dark:text-gray-400">{tenant.subscriptionTier}</div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm text-gray-900 dark:text-white">
                                                {tenant.finOpsData ? formatCurrency(tenant.finOpsData.currentMonthCost) : '-'}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm text-gray-500 dark:text-gray-400">
                                                {tenant.finOpsData ? formatCurrency(tenant.finOpsData.forecastedCost) : '-'}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm text-gray-900 dark:text-white">
                                                {tenant.budget ? formatCurrency(tenant.budget.monthlyLimit) : 'N/A'}
                                            </div>
                                            {tenant.budget && (
                                                <div className="w-24 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full mt-1 overflow-hidden">
                                                    <div
                                                        className={`h-full rounded-full ${isOverBudget ? 'bg-red-500' : isNearBudget ? 'bg-yellow-500' : 'bg-green-500'}`}
                                                        style={{ width: `${Math.min(usagePercent, 100)}%` }}
                                                    />
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {tenant.finOpsData ? (
                                                isOverBudget ? (
                                                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300">Over Budget</span>
                                                ) : isNearBudget ? (
                                                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300">Warning</span>
                                                ) : (
                                                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300">Healthy</span>
                                                )
                                            ) : (
                                                <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">No Data</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                            <button
                                                onClick={() => setSelectedTenantId(tenant.id)}
                                                className="text-primary-600 dark:text-primary-400 hover:text-primary-900 dark:hover:text-primary-300 hover:underline"
                                            >
                                                View Details
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        )
    }

    // If no data and not super admin, show empty state
    if (!finOpsData && !isSuperAdminView) {
        return (
            <div className="container mx-auto">
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">FinOps & Billing Dashboard</h2>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md h-96 flex items-center justify-center">
                    <div className="text-center text-gray-500 dark:text-gray-400">
                        <DollarSignIcon size={48} className="mx-auto text-gray-400 dark:text-gray-500" />
                        <p className="mt-4 font-semibold">No FinOps Data Available</p>
                        <p className="text-sm">Cost and billing data has not been configured for this tenant.</p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="container mx-auto space-y-6">
            <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                <div>
                    {isSuperAdminView && (
                        <button
                            onClick={() => setSelectedTenantId('')}
                            className="text-sm text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white mb-1 flex items-center"
                        >
                            &larr; Back to Overview
                        </button>
                    )}
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">
                        {activeTenant ? `${activeTenant.name} - FinOps` : 'FinOps & Billing'}
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Monitor and manage your cloud resource consumption and costs.</p>
                </div>
                {isSuperAdminView && (
                    <select
                        value={selectedTenantId}
                        onChange={(e) => setSelectedTenantId(e.target.value)}
                        className="w-full sm:w-auto px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm"
                    >
                        <option value="">Platform Overview</option>
                        {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                )}
            </div>

            {finOpsData ? (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">

                        <StatCard title="Current Month Cost" value={formatCurrency(finOpsData.currentMonthCost)} icon={<DollarSignIcon size={24} />} />
                        <StatCard title="Forecasted Month-End Cost" value={formatCurrency(finOpsData.forecastedCost)} icon={<TrendingUpIcon size={24} />} />
                        <StatCard title="Potential Monthly Savings" value={formatCurrency(finOpsData.potentialSavings)} icon={<SparklesIcon size={24} />} />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                        <div className="lg:col-span-2 bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                            <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Cost Breakdown by Service</h3>
                            <div className="h-64">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={finOpsData.costBreakdown}
                                            dataKey="cost"
                                            nameKey="service"
                                            cx="50%"
                                            cy="50%"
                                            outerRadius={80}
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
                                                        fill={theme === 'dark' ? '#e5e7eb' : '#374151'}
                                                        textAnchor={x > cx ? 'start' : 'end'}
                                                        dominantBaseline="central"
                                                        className="text-sm font-bold"
                                                    >
                                                        {`${(percent * 100).toFixed(0)}%`}
                                                    </text>
                                                );
                                            }}
                                            labelLine={{
                                                stroke: theme === 'dark' ? '#6b7280' : '#9ca3af',
                                                strokeWidth: 1
                                            }}
                                        >
                                            {finOpsData.costBreakdown.map((entry, index) => <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />)}
                                        </Pie>
                                        <Tooltip formatter={(value: number) => formatCurrency(value)} />
                                        <Legend wrapperStyle={{ fontSize: "12px", fontWeight: '600' }} />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                        <div className="lg:col-span-3 bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                            <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Cost Trend (Last 6 Months)</h3>
                            <div className="h-64">
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={finOpsData.costTrend} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                        <XAxis dataKey="month" stroke={textColor} fontSize={12} />
                                        <YAxis stroke={textColor} fontSize={12} tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`} />
                                        <Tooltip formatter={(value: number) => formatCurrency(value)} />
                                        <Legend wrapperStyle={{ fontSize: "12px" }} />
                                        <Area type="monotone" dataKey="actual" name="Actual Cost" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
                                        <Area type="monotone" dataKey="forecast" name="Forecasted" stroke="#f97316" fill="#f97316" fillOpacity={0.2} strokeDasharray="5 5" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                            <h3 className="text-lg font-semibold flex items-center">
                                <BotIcon className="mr-2 text-primary-500" />
                                AI-Powered Cost Analysis & Recommendations
                            </h3>
                            <div className="flex gap-2">
                                <button onClick={handleRecalculate} disabled={isRecalculating} className="px-4 py-2 text-sm font-medium text-primary-600 bg-primary-100 dark:bg-primary-900/30 rounded-lg hover:bg-primary-200 dark:hover:bg-primary-900/50 disabled:opacity-50">
                                    {isRecalculating ? 'Recalculating...' : 'Recalculate Costs'}
                                </button>
                                <button onClick={handleGenerateAnalysis} disabled={isLoading} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-primary-400">
                                    {isLoading ? 'Analyzing...' : 'Generate Analysis'}
                                </button>
                            </div>
                        </div>
                        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <h4 className="font-semibold mb-2">Analysis Summary</h4>
                                {isLoading && <LoadingSkeleton />}
                                {error && <p className="text-red-500 text-sm">{error}</p>}
                                {analysis && <p className="text-sm text-gray-600 dark:text-gray-300 prose prose-sm dark:prose-invert max-w-none">{analysis}</p>}
                            </div>
                            <div>
                                <h4 className="font-semibold mb-2">Cost Saving Recommendations</h4>
                                {isLoading && <LoadingSkeleton />}
                                {recommendations.length > 0 && (
                                    <ul className="space-y-3">
                                        {recommendations.map((rec, index) => (
                                            <li key={index} className="flex items-start p-3 bg-green-50 dark:bg-green-900/50 rounded-lg text-sm border border-green-200 dark:border-green-800">
                                                <CheckIcon className="flex-shrink-0 h-5 w-5 text-green-500 mr-3 mt-0.5" />
                                                <span className="text-green-800 dark:text-green-200">{rec}</span>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        </div>
                    </div>

                </>
            ) : null}
        </div>
    );
};
