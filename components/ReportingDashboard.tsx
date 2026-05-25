import React, { useContext, useEffect, useState } from 'react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { ThemeContext } from '../contexts/ThemeContext';
import {
    exportReport,
    fetchExecutiveSummaryReport,
    fetchSlaReport,
    fetchVulnerabilityExposureReport,
    fetchChangeManagementReport,
    fetchComplianceFrameworks,
    generateComplianceReport,
    generateExcelComplianceReport,
    generatePDFComplianceReport,
    generateAllComplianceReport,
    downloadComplianceReport,
} from '../services/apiService';
import { BarChart3Icon, DownloadIcon, ActivityIcon, ShieldCheckIcon, TrendingUpIcon } from './icons';
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

const KpiCard: React.FC<{ label: string; value: string | number; sub?: string; color?: string }> = ({ label, value, sub, color = 'text-primary-600 dark:text-primary-400' }) => (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-5 shadow-md flex flex-col">
        <span className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">{label}</span>
        <span className={`text-3xl font-bold ${color}`}>{value}</span>
        {sub && <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">{sub}</span>}
    </div>
);

const SectionHeader: React.FC<{ icon: React.ReactNode; title: string; subtitle?: string }> = ({ icon, title, subtitle }) => (
    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center text-gray-800 dark:text-white">
            {icon}
            <span className="ml-2">{title}</span>
        </h3>
        {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>}
    </div>
);

const SEVERITY_COLORS: Record<string, string> = {
    Critical: '#ef4444',
    High: '#f97316',
    Medium: '#f59e0b',
    Low: '#22c55e',
};

export const ReportingDashboard: React.FC<ReportingDashboardProps> = ({ historicalData }) => {
    const [exportingType, setExportingType] = useState<string | null>(null);
    const [executiveSummary, setExecutiveSummary] = useState<any>(null);
    const [slaReport, setSlaReport] = useState<any>(null);
    const [vulnReport, setVulnReport] = useState<any>(null);
    const [changeReport, setChangeReport] = useState<any>(null);
    const [loadingReports, setLoadingReports] = useState(true);
    const [activeTab, setActiveTab] = useState<'sla' | 'vuln' | 'change'>('sla');

    const { theme } = useContext(ThemeContext);
    const { hasPermission } = useUser();
    const canExport = hasPermission('export:reports');

    const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';
    const textColor = theme === 'dark' ? '#d1d5db' : '#374151';

    useEffect(() => {
        Promise.all([
            fetchExecutiveSummaryReport(),
            fetchSlaReport(),
            fetchVulnerabilityExposureReport(),
            fetchChangeManagementReport(),
        ]).then(([exec, sla, vuln, change]) => {
            setExecutiveSummary(exec);
            setSlaReport(sla);
            setVulnReport(vuln);
            setChangeReport(change);
        }).finally(() => setLoadingReports(false));
    }, []);

    const handleExport = async (module: string, format: 'csv' | 'pdf') => {
        if (!canExport) {
            alert("Permission Denied: You do not have 'export:reports' scope.");
            return;
        }
        setExportingType(`${module}-${format}`);
        try {
            await exportReport(module, format);
        } catch (e) {
            alert(`Failed to export ${module}.`);
        } finally {
            setExportingType(null);
        }
    };

    const ExportCard: React.FC<{ title: string; onExport: (f: 'csv' | 'pdf') => void }> = ({ title, onExport }) => (
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex justify-between items-center">
            <h4 className="font-semibold text-gray-800 dark:text-white">{title}</h4>
            <div className="flex space-x-2">
                <button
                    onClick={() => onExport('csv')}
                    disabled={!canExport || !!exportingType}
                    className="px-3 py-1 text-xs font-medium text-gray-700 bg-gray-200 dark:bg-gray-700 dark:text-gray-200 rounded-md hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                    {exportingType === `${title}-csv` ? <ActivityIcon size={14} className="animate-spin mr-1" /> : null}
                    CSV
                </button>
                <button
                    onClick={() => onExport('pdf')}
                    disabled={!canExport || !!exportingType}
                    className="px-3 py-1 text-xs font-medium text-red-700 bg-red-100 dark:bg-red-900/50 dark:text-red-300 rounded-md hover:bg-red-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                    {exportingType === `${title}-pdf` ? <ActivityIcon size={14} className="animate-spin mr-1" /> : null}
                    PDF
                </button>
            </div>
        </div>
    );

    const FrameworkExportCard: React.FC = () => {
        const ALL_ID = '__all__';
        const [frameworks, setFrameworks] = useState<{ id: string; name: string }[]>([]);
        const [selectedId, setSelectedId] = useState(ALL_ID);
        const [busy, setBusy] = useState<string | null>(null);
        const [error, setError] = useState<string | null>(null);

        useEffect(() => {
            fetchComplianceFrameworks().then((list: any[]) => {
                const items = list.map((f: any) => ({ id: f.id || f._id || '', name: f.name || f.id || '' }))
                    .filter((f: { id: string; name: string }) => f.id);
                setFrameworks(items);
            });
        }, []);

        const isAll = selectedId === ALL_ID;

        const handleGenerate = async (format: 'csv' | 'excel' | 'pdf') => {
            if (!canExport) { alert("Permission Denied: You do not have 'export:reports' scope."); return; }
            setBusy(format);
            setError(null);
            try {
                let result: any;
                if (isAll) {
                    if (format === 'pdf') { setError('PDF is not supported for all-frameworks export. Use CSV or Excel.'); setBusy(null); return; }
                    result = await generateAllComplianceReport(format as 'csv' | 'excel');
                } else {
                    if (!selectedId) { alert('Please select a framework first.'); setBusy(null); return; }
                    if (format === 'csv')        result = await generateComplianceReport(selectedId);
                    else if (format === 'excel') result = await generateExcelComplianceReport(selectedId);
                    else                         result = await generatePDFComplianceReport(selectedId);
                }
                const filename = result?.filename ?? result?.report?.filename;
                if (!filename) throw new Error('No filename returned from server');
                await downloadComplianceReport(filename);
            } catch (e: any) {
                setError(e?.message || 'Export failed');
            } finally {
                setBusy(null);
            }
        };

        return (
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md col-span-1 md:col-span-2">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                        <h4 className="font-semibold text-gray-800 dark:text-white whitespace-nowrap">Compliance Framework Report</h4>
                        <select
                            value={selectedId}
                            onChange={e => setSelectedId(e.target.value)}
                            className="flex-1 min-w-0 text-xs px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200"
                        >
                            <option value={ALL_ID}>All Frameworks</option>
                            {frameworks.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                        </select>
                    </div>
                    <div className="flex gap-2 flex-shrink-0">
                        {(['csv', 'excel', 'pdf'] as const).map(fmt => {
                            const disabledAll = isAll && fmt === 'pdf';
                            return (
                                <button key={fmt} onClick={() => handleGenerate(fmt)}
                                    disabled={!canExport || !!busy || disabledAll}
                                    title={disabledAll ? 'PDF not available for all-frameworks export' : undefined}
                                    className={`px-3 py-1 text-xs font-medium rounded-md disabled:opacity-50 disabled:cursor-not-allowed flex items-center
                                        ${fmt === 'pdf' ? 'text-red-700 bg-red-100 dark:bg-red-900/50 dark:text-red-300 hover:bg-red-200'
                                        : fmt === 'excel' ? 'text-green-700 bg-green-100 dark:bg-green-900/50 dark:text-green-300 hover:bg-green-200'
                                        : 'text-gray-700 bg-gray-200 dark:bg-gray-700 dark:text-gray-200 hover:bg-gray-300'}`}>
                                    {busy === fmt ? <ActivityIcon size={14} className="animate-spin mr-1" /> : null}
                                    {fmt.toUpperCase()}
                                </button>
                            );
                        })}
                    </div>
                </div>
                {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {isAll
                        ? 'Exports all frameworks in one file — Overview sheet + Asset Summary & Control Details per framework (CSV/Excel only)'
                        : 'Includes all controls with asset scores, compliance verdicts, and collected evidence artifacts'}
                </p>
            </div>
        );
    };

    const kpis = executiveSummary?.kpis;

    const severityPieData = vulnReport?.severity_distribution
        ? Object.entries(vulnReport.severity_distribution).map(([name, value]) => ({ name, value }))
        : [];

    return (
        <div className="container mx-auto space-y-6">
            <div>
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-1">Reporting & Analytics</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Analyze historical trends and export data for compliance and strategic planning.</p>
            </div>

            {/* ── Executive Summary KPIs ── */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <SectionHeader
                    icon={<TrendingUpIcon className="text-primary-500" size={20} />}
                    title="Executive Summary"
                    subtitle="Live KPIs across security, compliance, and patch velocity"
                />
                {loadingReports ? (
                    <div className="p-6 text-center text-gray-500 dark:text-gray-400">Loading reports...</div>
                ) : (
                    <div className="p-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                        <KpiCard
                            label="SLA Compliance"
                            value={kpis ? `${kpis.compliance_rate}%` : '—'}
                            sub="Last 30 days"
                            color={kpis?.compliance_rate >= 90 ? 'text-green-600 dark:text-green-400' : kpis?.compliance_rate >= 70 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'}
                        />
                        <KpiCard label="Patches/Week" value={kpis ? kpis.patches_per_week : '—'} sub="Deployment velocity" />
                        <KpiCard
                            label="MTTR"
                            value={kpis ? `${kpis.mttr_hours}h` : '—'}
                            sub="Mean time to remediate"
                            color={kpis?.mttr_hours <= 24 ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}
                        />
                        <KpiCard
                            label="Asset Exposure"
                            value={kpis ? `${kpis.asset_exposure_rate}%` : '—'}
                            sub="Assets with open vulns"
                            color={kpis?.asset_exposure_rate > 30 ? 'text-red-600 dark:text-red-400' : 'text-primary-600 dark:text-primary-400'}
                        />
                        <KpiCard label="Critical Vulns" value={kpis ? kpis.critical_vulnerabilities : '—'} sub="Open critical CVEs" color="text-red-600 dark:text-red-400" />
                        <KpiCard label="High Exploit Risk" value={kpis ? kpis.high_exploit_risk : '—'} sub="EPSS > 50%" color="text-orange-600 dark:text-orange-400" />
                    </div>
                )}
            </div>

            {/* ── Historical Trends ── */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <SectionHeader icon={<BarChart3Icon className="text-primary-500" size={20} />} title="Historical Trends (6 Months)" />
                <div className="p-4 grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div>
                        <h4 className="text-sm font-semibold mb-3 text-gray-700 dark:text-gray-300">Alert Frequency</h4>
                        <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={historicalData.alerts || []}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="date" stroke={textColor} fontSize={11} />
                                    <YAxis stroke={textColor} fontSize={11} />
                                    <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#fff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                                    <Bar dataKey="Critical" stackId="a" fill="#ef4444" />
                                    <Bar dataKey="High" stackId="a" fill="#f97316" />
                                    <Bar dataKey="Medium" stackId="a" fill="#f59e0b" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold mb-3 text-gray-700 dark:text-gray-300">Compliance Posture</h4>
                        <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={historicalData.compliance || []}>
                                    <defs>
                                        <linearGradient id="compGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
                                            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="date" stroke={textColor} fontSize={11} />
                                    <YAxis domain={[0, 100]} unit="%" stroke={textColor} fontSize={11} />
                                    <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#fff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                                    <Area type="monotone" dataKey="score" stroke="#22c55e" fill="url(#compGrad)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold mb-3 text-gray-700 dark:text-gray-300">Open Vulnerabilities</h4>
                        <div className="h-56">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={historicalData.vulnerabilities || []}>
                                    <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                                    <XAxis dataKey="date" stroke={textColor} fontSize={11} />
                                    <YAxis stroke={textColor} fontSize={11} />
                                    <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? '#1f2937' : '#fff', border: `1px solid ${gridColor}`, borderRadius: '0.5rem' }} />
                                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                                    <Area type="monotone" dataKey="Critical" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.3} />
                                    <Area type="monotone" dataKey="High" stackId="1" stroke="#f97316" fill="#f97316" fillOpacity={0.3} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Analytical Reports ── */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <SectionHeader icon={<ShieldCheckIcon className="text-primary-500" size={20} />} title="Analytical Reports" subtitle="Live reports computed from your data" />
                <div className="border-b border-gray-200 dark:border-gray-700 px-4 flex space-x-1">
                    {(['sla', 'vuln', 'change'] as const).map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === tab
                                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                                : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                            }`}
                        >
                            {tab === 'sla' ? 'SLA Compliance' : tab === 'vuln' ? 'Vulnerability Exposure' : 'Change Management'}
                        </button>
                    ))}
                </div>

                <div className="p-4">
                    {loadingReports ? (
                        <div className="text-center py-8 text-gray-500 dark:text-gray-400">Loading...</div>
                    ) : activeTab === 'sla' && slaReport ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <KpiCard label="Total Patches" value={slaReport.summary?.total_patches ?? 0} sub={`Last ${slaReport.period?.days ?? 30} days`} />
                                <KpiCard label="Compliant" value={slaReport.summary?.compliant ?? 0} color="text-green-600 dark:text-green-400" />
                                <KpiCard label="Breached" value={slaReport.summary?.breached ?? 0} color="text-red-600 dark:text-red-400" />
                                <KpiCard label="At Risk" value={slaReport.summary?.at_risk ?? 0} color="text-yellow-600 dark:text-yellow-400" />
                            </div>
                            {slaReport.patches?.breached?.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">SLA Breaches</h4>
                                    <div className="overflow-auto max-h-56">
                                        <table className="w-full text-xs text-left">
                                            <thead className="bg-gray-50 dark:bg-gray-700">
                                                <tr>
                                                    {['CVE', 'Severity', 'SLA (h)', 'Breach (h)', 'Status'].map(h => (
                                                        <th key={h} className="px-3 py-2 font-medium text-gray-600 dark:text-gray-300">{h}</th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {slaReport.patches.breached.map((p: any, i: number) => (
                                                    <tr key={i} className="border-t border-gray-200 dark:border-gray-700">
                                                        <td className="px-3 py-2 font-mono">{p.cveId || p.id || '—'}</td>
                                                        <td className="px-3 py-2">
                                                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${p.severity === 'Critical' ? 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' : 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300'}`}>
                                                                {p.severity}
                                                            </span>
                                                        </td>
                                                        <td className="px-3 py-2">{p.sla_hours}</td>
                                                        <td className="px-3 py-2 text-red-600 dark:text-red-400">{p.breach_hours?.toFixed(1)}</td>
                                                        <td className="px-3 py-2">{p.status || 'overdue'}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}
                            {(!slaReport.patches?.breached?.length && slaReport.summary?.total_patches === 0) && (
                                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">No patch data in the last 30 days.</p>
                            )}
                        </div>
                    ) : activeTab === 'vuln' && vulnReport ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                                <KpiCard label="Total Assets" value={vulnReport.summary?.total_assets ?? 0} />
                                <KpiCard label="Exposed Assets" value={vulnReport.summary?.exposed_assets ?? 0} color="text-orange-600 dark:text-orange-400" sub={`${vulnReport.summary?.exposure_rate ?? 0}% exposure rate`} />
                                <KpiCard label="Pending Patches" value={vulnReport.summary?.pending_patches ?? 0} />
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {severityPieData.length > 0 && (
                                    <div>
                                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Severity Distribution</h4>
                                        <div className="h-48">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <PieChart>
                                                    <Pie data={severityPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, value }) => `${name}: ${value}`} labelLine={false} fontSize={11}>
                                                        {severityPieData.map((entry, i) => (
                                                            <Cell key={i} fill={SEVERITY_COLORS[entry.name] || '#6b7280'} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip />
                                                </PieChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </div>
                                )}
                                {vulnReport.critical_vulnerabilities?.length > 0 && (
                                    <div>
                                        <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Top Critical Vulnerabilities</h4>
                                        <div className="overflow-auto max-h-48">
                                            <table className="w-full text-xs text-left">
                                                <thead className="bg-gray-50 dark:bg-gray-700">
                                                    <tr>
                                                        {['CVE', 'CVSS', 'Status'].map(h => (
                                                            <th key={h} className="px-3 py-2 font-medium text-gray-600 dark:text-gray-300">{h}</th>
                                                        ))}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {vulnReport.critical_vulnerabilities.slice(0, 10).map((v: any, i: number) => (
                                                        <tr key={i} className="border-t border-gray-200 dark:border-gray-700">
                                                            <td className="px-3 py-2 font-mono">{v.cveId || v.id || '—'}</td>
                                                            <td className="px-3 py-2 text-red-600 dark:text-red-400">{v.cvss_score ?? '—'}</td>
                                                            <td className="px-3 py-2">{v.status || '—'}</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                            </div>
                            {(!vulnReport.critical_vulnerabilities?.length && severityPieData.length === 0) && (
                                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">No vulnerability data available.</p>
                            )}
                        </div>
                    ) : activeTab === 'change' && changeReport ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                <KpiCard label="Total Changes" value={changeReport.summary?.total_changes ?? 0} sub={`Last ${changeReport.period ? Math.round((new Date(changeReport.period.end).getTime() - new Date(changeReport.period.start).getTime()) / 86400000) : 30} days`} />
                                <KpiCard label="Deployments" value={changeReport.summary?.deployments ?? 0} />
                                <KpiCard label="Staged" value={changeReport.summary?.staged_deployments ?? 0} />
                                <KpiCard label="Rollbacks" value={changeReport.summary?.rollbacks ?? 0} color="text-red-600 dark:text-red-400" />
                            </div>
                            {changeReport.changes?.length > 0 ? (
                                <div className="overflow-auto max-h-64">
                                    <table className="w-full text-xs text-left">
                                        <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0">
                                            <tr>
                                                {['Type', 'Status', 'Created By', 'Date', 'Details'].map(h => (
                                                    <th key={h} className="px-3 py-2 font-medium text-gray-600 dark:text-gray-300">{h}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {changeReport.changes.map((c: any, i: number) => (
                                                <tr key={i} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                                    <td className="px-3 py-2">
                                                        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${c.type === 'rollback' ? 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' : 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300'}`}>
                                                            {c.type?.replace('_', ' ')}
                                                        </span>
                                                    </td>
                                                    <td className="px-3 py-2">{c.status || '—'}</td>
                                                    <td className="px-3 py-2">{c.created_by || '—'}</td>
                                                    <td className="px-3 py-2">{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</td>
                                                    <td className="px-3 py-2 text-gray-500">
                                                        {c.patch_count != null ? `${c.patch_count} patches` : ''}
                                                        {c.asset_count != null ? ` · ${c.asset_count} assets` : ''}
                                                        {c.reason ? `Reason: ${c.reason}` : ''}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">No change management records in the last 30 days.</p>
                            )}
                        </div>
                    ) : (
                        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">No data available for this report.</p>
                    )}
                </div>
            </div>

            {/* ── Data Export Center ── */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <SectionHeader icon={<DownloadIcon className="text-primary-500" size={20} />} title="Data Export Center" subtitle="Download raw data as CSV or PDF for any module" />
                <div className="p-4 space-y-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Asset & Patch</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <ExportCard title="Asset Inventory" onExport={f => handleExport('Asset Inventory', f)} />
                        <ExportCard title="Patch Management" onExport={f => handleExport('Patch Management', f)} />
                    </div>

                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 pt-2">Security Operations</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <ExportCard title="Security Events" onExport={f => handleExport('Security Events', f)} />
                        <ExportCard title="EDR Alerts" onExport={f => handleExport('EDR Alerts', f)} />
                        <ExportCard title="Incident Response" onExport={f => handleExport('Incident Response', f)} />
                        <ExportCard title="Threat Intelligence" onExport={f => handleExport('Threat Intelligence', f)} />
                    </div>

                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 pt-2">Vulnerability & Supply Chain</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <ExportCard title="Vulnerability" onExport={f => handleExport('Vulnerability', f)} />
                        <ExportCard title="SBOM" onExport={f => handleExport('SBOM', f)} />
                    </div>

                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 pt-2">Governance & Risk</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <ExportCard title="AI Risk Register" onExport={f => handleExport('AI Risk Register', f)} />
                        <ExportCard title="Secrets Management" onExport={f => handleExport('Secrets Management', f)} />
                    </div>

                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 pt-2">Compliance Framework Reports</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FrameworkExportCard />
                    </div>
                </div>
            </div>
        </div>
    );
};
