import React, { useContext } from 'react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';
import { exportReport } from '../services/apiService';
import { BarChart3Icon, DownloadIcon, ActivityIcon } from './icons';
import { Asset, HistoricalData } from '../types';
import { useUser } from '../contexts/UserContext';

interface ReportingDashboardProps {
    historicalData: {
        alerts: HistoricalData[];
        compliance: HistoricalData[];
        vulnerabilities: HistoricalData[];
    };
    assets: Asset[];
}

export const ReportingDashboard: React.FC<ReportingDashboardProps> = ({ historicalData, assets }) => {
    const [exportingType, setExportingType] = React.useState<string | null>(null);
    const { theme } = useContext(ThemeContext);
    const { hasPermission } = useUser();
    const canExport = hasPermission('export:reports');

    const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
    const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

    const handleExport = async (module: string, format: 'csv' | 'pdf') => {
        if (!canExport) {
            alert("Permission Denied: You do not have 'export:reports' scope.");
            return;
        }

        setExportingType(`${module}-${format}`);
        try {
            await exportReport(module, format);
        } catch (e) {
            alert(`Failed to export ${module}. Please check console.`);
        } finally {
            setExportingType(null);
        }
    };

    const ExportCard: React.FC<{ title: string; onExport: (format: 'csv' | 'pdf') => void }> = ({ title, onExport }) => (
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex justify-between items-center">
            <h4 className="font-semibold text-gray-800 dark:text-white">{title}</h4>
            <div className="flex space-x-2">
                <button
                    onClick={() => onExport('csv')}
                    disabled={!canExport || !!exportingType}
                    title={!canExport ? "Permission Denied" : "Export as CSV"}
                    className="px-3 py-1 text-xs font-medium text-gray-700 bg-gray-200 dark:bg-gray-700 dark:text-gray-200 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                    {exportingType === `${title}-csv` ? (
                        <ActivityIcon size={14} className="animate-spin mr-1" />
                    ) : null}
                    CSV
                </button>
                <button
                    onClick={() => onExport('pdf')}
                    disabled={!canExport || !!exportingType}
                    title={!canExport ? "Permission Denied" : "Export as PDF"}
                    className="px-3 py-1 text-xs font-medium text-red-700 bg-red-100 dark:bg-red-900/50 dark:text-red-300 rounded-md hover:bg-red-200 dark:hover:bg-red-900 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                    {exportingType === `${title}-pdf` ? (
                        <ActivityIcon size={14} className="animate-spin mr-1" />
                    ) : null}
                    PDF
                </button>
            </div>
        </div>
    );

    return (
        <div className="container mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Reporting & Analytics</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Analyze historical trends and export data for compliance and strategic planning.</p>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md mb-6">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold flex items-center">
                        <BarChart3Icon className="mr-2 text-primary-500" />
                        Historical Trends
                    </h3>
                </div>
                <div className="p-4 grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                        <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Alert Frequency (6 Months)</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={historicalData.alerts}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="date" stroke={textColor} fontSize={12} />
                                    <YAxis stroke={textColor} fontSize={12} />
                                    <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                                    <Legend wrapperStyle={{ fontSize: "12px" }} />
                                    <Bar dataKey="Critical" stackId="a" fill="#ef4444" />
                                    <Bar dataKey="High" stackId="a" fill="#f97316" />
                                    <Bar dataKey="Medium" stackId="a" fill="#f59e0b" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                        <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Compliance Posture Trend</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={historicalData.compliance}>
                                    <defs>
                                        <linearGradient id="complianceColor" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
                                            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="date" stroke={textColor} fontSize={12} />
                                    <YAxis domain={[70, 100]} unit="%" stroke={textColor} fontSize={12} />
                                    <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                                    <Area type="monotone" dataKey="score" stroke="#22c55e" fill="url(#complianceColor)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                        <h3 className="text-md font-semibold mb-4 text-gray-800 dark:text-white">Open Vulnerabilities Trend</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={historicalData.vulnerabilities}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="date" stroke={textColor} fontSize={12} />
                                    <YAxis stroke={textColor} fontSize={12} />
                                    <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#ffffff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                                    <Legend wrapperStyle={{ fontSize: "12px" }} />
                                    <Area type="monotone" dataKey="Critical" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.3} />
                                    <Area type="monotone" dataKey="High" stackId="1" stroke="#f97316" fill="#f97316" fillOpacity={0.3} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold flex items-center">
                        <DownloadIcon className="mr-2 text-primary-500" />
                        Data Export Center
                    </h3>
                </div>
                <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <ExportCard title="Asset Inventory" onExport={(format) => handleExport('Asset Inventory', format)} />
                    <ExportCard title="Patch Management Report" onExport={(format) => handleExport('Patch Management', format)} />
                    <ExportCard title="AI Risk Register" onExport={(format) => handleExport('AI Risk Register', format)} />
                    <ExportCard title="Security Events (Last 30 days)" onExport={(format) => handleExport('Security Events', format)} />
                </div>
            </div>
        </div>
    );
};
