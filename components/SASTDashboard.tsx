import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, AlertTriangleIcon, CodeIcon, RefreshCwIcon, CheckCircleIcon, XCircleIcon } from './icons';

interface Scan {
    scan_id: string;
    project_name: string;
    repository_url: string;
    branch: string;
    scan_type: string;
    status: string;
    created_at: string;
    completed_at?: string;
    vulnerabilities_found: number;
    code_quality_score?: number;
}

interface Vulnerability {
    id: string;
    title: string;
    description: string;
    severity: string;
    severity_score: number;
    category: string;
    cwe_id: string;
    owasp_category: string;
    file_path: string;
    line_number: number;
    code_snippet: string;
    recommendation: string;
    status: string;
    false_positive: boolean;
}

interface CodeQualityMetrics {
    code_quality_score: number;
    total_vulnerabilities: number;
    severity_breakdown: Record<string, number>;
    metrics: {
        maintainability: number;
        reliability: number;
        security: number;
        coverage: number;
    };
}

interface Statistics {
    total_scans: number;
    scans_by_status: Record<string, number>;
    total_vulnerabilities: number;
    open_vulnerabilities: number;
    open_by_severity: Record<string, number>;
}

export const SASTDashboard: React.FC = () => {
    const [scans, setScans] = useState<Scan[]>([]);
    const [vulnerabilities, setVulnerabilities] = useState<Vulnerability[]>([]);
    const [stats, setStats] = useState<Statistics | null>(null);
    const [selectedScan, setSelectedScan] = useState<Scan | null>(null);
    const [codeQuality, setCodeQuality] = useState<CodeQualityMetrics | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'scans' | 'vulnerabilities' | 'quality'>('scans');
    const [showScanModal, setShowScanModal] = useState(false);

    // Form state
    const [formData, setFormData] = useState({
        project_name: '',
        repository_url: '',
        branch: 'main',
        scan_type: 'full'
    });

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [scansRes, vulnsRes, statsRes] = await Promise.all([
                fetch('/api/sast/history', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/sast/vulnerabilities?status=open', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/sast/statistics', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                })
            ]);

            if (scansRes.ok) setScans(await scansRes.json());
            if (vulnsRes.ok) setVulnerabilities(await vulnsRes.json());
            if (statsRes.ok) setStats(await statsRes.json());
        } catch (error) {
            console.error('Failed to load SAST data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleTriggerScan = async (e: React.FormEvent) => {
        e.preventDefault();

        try {
            const response = await fetch('/api/sast/scan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify(formData)
            });

            if (response.ok) {
                alert('Scan triggered successfully');
                setShowScanModal(false);
                setFormData({ project_name: '', repository_url: '', branch: 'main', scan_type: 'full' });
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to trigger scan');
            }
        } catch (error) {
            console.error('Failed to trigger scan:', error);
            alert('Failed to trigger scan');
        }
    };

    const handleViewScan = async (scan: Scan) => {
        setSelectedScan(scan);

        try {
            const response = await fetch(`/api/sast/quality/${scan.scan_id}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });

            if (response.ok) {
                setCodeQuality(await response.json());
                setActiveTab('quality');
            }
        } catch (error) {
            console.error('Failed to load code quality:', error);
        }
    };

    const handleMarkFalsePositive = async (vulnId: string) => {
        const reason = prompt('Reason for marking as false positive:');
        if (!reason) return;

        try {
            const response = await fetch('/api/sast/vulnerabilities/false-positive', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({ vulnerability_id: vulnId, reason })
            });

            if (response.ok) {
                alert('Marked as false positive');
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to mark false positive');
            }
        } catch (error) {
            console.error('Failed to mark false positive:', error);
            alert('Failed to mark false positive');
        }
    };

    const getSeverityColor = (severity: string) => {
        switch (severity.toLowerCase()) {
            case 'critical': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700';
            case 'high': return 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700';
            case 'medium': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700';
            case 'low': return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700';
            default: return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700';
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'completed': return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
            case 'running': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
            case 'failed': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
            default: return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
        }
    };

    const getQualityScoreColor = (score: number) => {
        if (score >= 80) return 'text-green-600';
        if (score >= 60) return 'text-amber-600';
        return 'text-red-600';
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-cyan-600 bg-clip-text text-transparent">
                        Static Application Security Testing
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        Shift-left security with automated code analysis
                    </p>
                </div>
                <button
                    onClick={() => setShowScanModal(true)}
                    className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors shadow-lg"
                >
                    Trigger Scan
                </button>
            </div>

            {/* Statistics Cards */}
            {stats && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-6 border border-blue-200 dark:border-blue-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <CodeIcon size={32} className="text-blue-600" />
                            <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">Total Scans</p>
                        </div>
                        <p className="text-3xl font-bold text-blue-900 dark:text-blue-100">{stats.total_scans}</p>
                    </div>

                    <div className="bg-gradient-to-br from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 rounded-xl p-6 border border-red-200 dark:border-red-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangleIcon size={32} className="text-red-600" />
                            <p className="text-sm font-semibold text-red-600 dark:text-red-400">Open Vulnerabilities</p>
                        </div>
                        <p className="text-3xl font-bold text-red-900 dark:text-red-100">{stats.open_vulnerabilities}</p>
                    </div>

                    <div className="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 rounded-xl p-6 border border-orange-200 dark:border-orange-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangleIcon size={32} className="text-orange-600" />
                            <p className="text-sm font-semibold text-orange-600 dark:text-orange-400">Critical</p>
                        </div>
                        <p className="text-3xl font-bold text-orange-900 dark:text-orange-100">{stats.open_by_severity.critical || 0}</p>
                    </div>

                    <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-xl p-6 border border-green-200 dark:border-green-700 shadow-lg">
                        <div className="flex items-center gap-3 mb-2">
                            <CheckCircleIcon size={32} className="text-green-600" />
                            <p className="text-sm font-semibold text-green-600 dark:text-green-400">Completed</p>
                        </div>
                        <p className="text-3xl font-bold text-green-900 dark:text-green-100">{stats.scans_by_status.completed || 0}</p>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                {(['scans', 'vulnerabilities', 'quality'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-6 py-3 font-semibold transition-all ${activeTab === tab
                                ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                            }`}
                    >
                        {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                ))}
            </div>

            {/* Scans Tab */}
            {activeTab === 'scans' && (
                <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Project</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Branch</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Status</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Vulnerabilities</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Quality Score</th>
                                <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Created</th>
                                <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scans.map((scan) => (
                                <tr key={scan.scan_id} className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="py-3 px-4 text-sm font-semibold text-gray-900 dark:text-gray-100">{scan.project_name}</td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">{scan.branch}</td>
                                    <td className="py-3 px-4">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${getStatusColor(scan.status)}`}>
                                            {scan.status.toUpperCase()}
                                        </span>
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">{scan.vulnerabilities_found}</td>
                                    <td className="py-3 px-4">
                                        {scan.code_quality_score !== null && scan.code_quality_score !== undefined ? (
                                            <span className={`text-sm font-bold ${getQualityScoreColor(scan.code_quality_score)}`}>
                                                {scan.code_quality_score.toFixed(1)}
                                            </span>
                                        ) : (
                                            <span className="text-sm text-gray-500">-</span>
                                        )}
                                    </td>
                                    <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300">
                                        {new Date(scan.created_at).toLocaleString()}
                                    </td>
                                    <td className="py-3 px-4 text-right">
                                        <button
                                            onClick={() => handleViewScan(scan)}
                                            className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                                        >
                                            View Details
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Vulnerabilities Tab */}
            {activeTab === 'vulnerabilities' && (
                <div className="space-y-4">
                    {vulnerabilities.map((vuln) => (
                        <div key={vuln.id} className={`rounded-xl border-2 p-6 ${getSeverityColor(vuln.severity)}`}>
                            <div className="flex items-start justify-between mb-4">
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-2">
                                        <span className={`px-3 py-1 rounded-full text-xs font-bold ${getSeverityColor(vuln.severity)}`}>
                                            {vuln.severity.toUpperCase()}
                                        </span>
                                        <span className="text-sm font-semibold text-gray-600 dark:text-gray-400">
                                            {vuln.cwe_id} | {vuln.owasp_category}
                                        </span>
                                    </div>
                                    <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">{vuln.title}</h3>
                                    <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">{vuln.description}</p>
                                    <div className="bg-gray-900 dark:bg-gray-950 rounded-lg p-3 mb-3">
                                        <p className="text-xs text-gray-400 mb-1">{vuln.file_path}:{vuln.line_number}</p>
                                        <code className="text-sm text-green-400 font-mono">{vuln.code_snippet}</code>
                                    </div>
                                    <p className="text-sm font-semibold text-blue-700 dark:text-blue-300">
                                        💡 {vuln.recommendation}
                                    </p>
                                </div>
                                <button
                                    onClick={() => handleMarkFalsePositive(vuln.id)}
                                    className="ml-4 px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg text-sm font-semibold transition-colors"
                                >
                                    Mark False Positive
                                </button>
                            </div>
                        </div>
                    ))}
                    {vulnerabilities.length === 0 && (
                        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-xl p-12 text-center">
                            <ShieldCheckIcon size={64} className="mx-auto mb-4 text-green-600 opacity-50" />
                            <p className="text-green-700 dark:text-green-300 font-semibold">No open vulnerabilities! ✅</p>
                        </div>
                    )}
                </div>
            )}

            {/* Quality Tab */}
            {activeTab === 'quality' && codeQuality && selectedScan && (
                <div className="space-y-6">
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                            Code Quality: {selectedScan.project_name}
                        </h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">Overall Quality Score</p>
                                <p className={`text-5xl font-bold ${getQualityScoreColor(codeQuality.code_quality_score)}`}>
                                    {codeQuality.code_quality_score.toFixed(1)}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">Total Vulnerabilities</p>
                                <p className="text-5xl font-bold text-red-600">{codeQuality.total_vulnerabilities}</p>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        {Object.entries(codeQuality.metrics).map(([key, value]) => (
                            <div key={key} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2 capitalize">{key}</p>
                                <p className={`text-3xl font-bold ${getQualityScoreColor(value)}`}>{value.toFixed(1)}</p>
                            </div>
                        ))}
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">Vulnerability Breakdown</h3>
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                            {Object.entries(codeQuality.severity_breakdown).map(([severity, count]) => (
                                <div key={severity} className={`rounded-lg border-2 p-4 ${getSeverityColor(severity)}`}>
                                    <p className="text-xs font-semibold uppercase mb-1">{severity}</p>
                                    <p className="text-2xl font-bold">{count}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Trigger Scan Modal */}
            {showScanModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
                        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Trigger SAST Scan</h2>
                        <form onSubmit={handleTriggerScan} className="space-y-4">
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Project Name</label>
                                <input
                                    type="text"
                                    value={formData.project_name}
                                    onChange={(e) => setFormData({ ...formData, project_name: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Repository URL</label>
                                <input
                                    type="text"
                                    value={formData.repository_url}
                                    onChange={(e) => setFormData({ ...formData, repository_url: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Branch</label>
                                <input
                                    type="text"
                                    value={formData.branch}
                                    onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Scan Type</label>
                                <select
                                    value={formData.scan_type}
                                    onChange={(e) => setFormData({ ...formData, scan_type: e.target.value })}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                >
                                    <option value="full">Full Scan</option>
                                    <option value="incremental">Incremental</option>
                                    <option value="quick">Quick Scan</option>
                                </select>
                            </div>
                            <div className="flex gap-3 pt-4">
                                <button
                                    type="button"
                                    onClick={() => setShowScanModal(false)}
                                    className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors"
                                >
                                    Start Scan
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
