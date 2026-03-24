import React from 'react';
import { CheckIcon, XIcon, AlertTriangleIcon, ShieldCheckIcon } from './icons';

export interface ComplianceRule {
    id: string;
    title: string;
    status: 'passed' | 'failed' | 'warning';
    category: string;
    description?: string;
    remediation?: string;
    evidence?: string;
    checkName?: string; // Original, untransformed check name for remediation
}

export interface ComplianceData {
    score: number;
    total_rules: number;
    passed: number;
    failed: number;
    warnings: number;
    rules?: ComplianceRule[];
    compliance_checks?: any[]; // Fallback for raw meta
    framework: string;
}

interface AgentComplianceTabProps {
    data?: ComplianceData;
    agentId: string;
    onRefresh?: () => void;
}

export const AgentComplianceTab: React.FC<AgentComplianceTabProps> = ({ data, agentId, onRefresh }) => {
    const [isRefreshing, setIsRefreshing] = React.useState(false);

    const handleRefresh = async () => {
        if (onRefresh) {
            setIsRefreshing(true);
            try {
                await onRefresh();
            } finally {
                setTimeout(() => setIsRefreshing(false), 1000);
            }
        }
    };

    // Normalize Data: Support both 'rules' (Transformed) and 'compliance_checks' (Raw Meta)
    const rules: ComplianceRule[] = React.useMemo(() => {
        if (data?.rules) return data.rules;
        if (data?.compliance_checks) {
            return data.compliance_checks.map((check: any) => ({
                id: check.check,
                title: check.check,
                checkName: check.check,
                status: (check.status?.toLowerCase() === 'pass' || check.status?.toLowerCase() === 'compliant') ? 'passed' :
                    (check.status?.toLowerCase() === 'fail' || check.status?.toLowerCase() === 'non-compliant') ? 'failed' : 'warning',
                category: 'System',
                description: check.details,
                evidence: check.evidence_content,
                remediation: check.remediation
            }));
        }
        return [];
    }, [data]);

    const stats = React.useMemo(() => {
        if (data?.rules && data.score !== undefined) {
            return {
                score: data.score,
                passed: data.passed,
                failed: data.failed,
                warnings: data.warnings,
                total: data.total_rules
            };
        }
        const passed = rules.filter(r => r.status === 'passed').length;
        const failed = rules.filter(r => r.status === 'failed').length;
        const warnings = rules.filter(r => r.status === 'warning').length;
        const total = rules.length;
        const score = total > 0 ? Math.round((passed / total) * 100) : 0;

        return { score, passed, failed, warnings, total };
    }, [data, rules]);

    if (!data || (!data.rules && !data.compliance_checks)) {
        // ... existing empty state ...
        return (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <ShieldCheckIcon size={48} className="mx-auto mb-3 opacity-50" />
                <p>No compliance data available</p>
                <div className="mt-4">
                    <button
                        onClick={handleRefresh}
                        disabled={isRefreshing}
                        className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50 flex items-center mx-auto"
                    >
                        <svg className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        {isRefreshing ? 'Scanning...' : 'Run Compliance Scan'}
                    </button>
                </div>
            </div>
        );
    }

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'passed':
                return <CheckIcon size={16} className="text-green-600 dark:text-green-400" />;
            case 'failed':
                return <XIcon size={16} className="text-red-600 dark:text-red-400" />;
            case 'warning':
                return <AlertTriangleIcon size={16} className="text-yellow-600 dark:text-yellow-400" />;
            default:
                return null;
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'passed':
                return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
            case 'failed':
                return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300';
            case 'warning':
                return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300';
            default:
                return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300';
        }
    };

    const categories = [...new Set(rules.map(r => r.category))];

    // NEW: Auto-Fix Handler
    const handleFix = async (rule: ComplianceRule) => {
        // Prefer the explicit checkName, fallback to title if not available
        const fixTarget = rule.checkName || rule.title;

        console.log(`[Fix] Button clicked for rule: "${rule.title}"`);
        console.log(`[Fix] Using target check name: "${fixTarget}"`);
        console.log(`[Fix] Using Agent ID: "${agentId}"`);

        if (!agentId) {
            alert("Agent ID is missing, cannot trigger fix.");
            return;
        }

        try {
            console.log(`[Fix] Sending POST request to /api/agents/${agentId}/compliance/fix`);
            const formData = new FormData();
            formData.append('check_name', fixTarget);

            const response = await fetch(`/api/agents/${agentId}/compliance/fix`, {
                method: 'POST',
                body: formData
            });

            console.log(`[Fix] Response received. Status: ${response.status}`);

            const result = await response.json();
            console.log(`[Fix] Response body:`, result);

            if (result.success) {
                alert(`Fix instruction sent for: ${fixTarget}. \nPlease wait for the agent to process it.`);
            } else {
                alert(`Failed to trigger fix: ${result.message}`);
            }
        } catch (error) {
            console.error("[Fix] Error caught:", error);
            alert(`Error connecting to backend: ${error}`);
        }
    };

    return (
        <div className="space-y-6">
            <div className="bg-gradient-to-br from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-800/20 rounded-lg p-6 border border-primary-200 dark:border-primary-700">
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                            {data.framework || 'System'} Compliance Score
                        </h3>
                        <div className="flex items-baseline space-x-3">
                            <div className="text-5xl font-bold text-primary-600 dark:text-primary-400">
                                {stats.score}%
                            </div>
                            <div className="text-sm text-gray-600 dark:text-gray-400">
                                {stats.passed} of {stats.total} checks passed
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center space-x-4">
                        {onRefresh && (
                            <button
                                onClick={handleRefresh}
                                disabled={isRefreshing}
                                className="px-3 py-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-md text-sm font-medium border border-gray-200 dark:border-gray-600 shadow-sm transition-colors disabled:opacity-50 flex items-center"
                                title="Run new compliance scan"
                            >
                                <svg className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                                {isRefreshing ? 'Scanning...' : 'Refresh'}
                            </button>
                        )}
                        <ShieldCheckIcon size={64} className="text-primary-500 opacity-20" />
                    </div>
                </div>

                <div className="mt-4">
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                        <div
                            className="bg-primary-600 h-3 rounded-full transition-all duration-500"
                            style={{ width: `${stats.score}%` }}
                        />
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-gray-200 dark:bg-gray-800 dark:border-gray-700 rounded-xl p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-semibold text-green-600 dark:text-green-400 mb-1">Passed</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.passed}</p>
                        </div>
                        <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                            <CheckIcon size={24} className="text-green-500" />
                        </div>
                    </div>
                </div>

                <div className="bg-white border border-gray-200 dark:bg-gray-800 dark:border-gray-700 rounded-xl p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-semibold text-red-600 dark:text-red-400 mb-1">Failed</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.failed}</p>
                        </div>
                        <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                            <XIcon size={24} className="text-red-500" />
                        </div>
                    </div>
                </div>

                <div className="bg-white border border-gray-200 dark:bg-gray-800 dark:border-gray-700 rounded-xl p-6 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-semibold text-amber-600 dark:text-amber-400 mb-1">Warnings</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.warnings}</p>
                        </div>
                        <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                            <AlertTriangleIcon size={24} className="text-amber-500" />
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Compliance Rules</h4>
                <div className="space-y-4">
                    {categories.map(category => {
                        const categoryRules = rules.filter(r => r.category === category);
                        const failedRules = categoryRules.filter(r => r.status === 'failed');

                        return (
                            <div key={category} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                                <div className="bg-gray-50 dark:bg-gray-700/50 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center justify-between">
                                        <h5 className="font-medium text-gray-900 dark:text-white">{category}</h5>
                                        <span className="text-sm text-gray-500 dark:text-gray-400">
                                            {categoryRules.length} rules
                                            {failedRules.length > 0 && (
                                                <span className="ml-2 text-red-600 dark:text-red-400">
                                                    ({failedRules.length} failed)
                                                </span>
                                            )}
                                        </span>
                                    </div>
                                </div>

                                <div className="divide-y divide-gray-200 dark:divide-gray-700">
                                    {categoryRules.map(rule => (
                                        <div key={rule.id} className="px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                                            <div className="flex items-start justify-between">
                                                <div className="flex items-start space-x-3 flex-grow">
                                                    <div className="mt-0.5">
                                                        {getStatusIcon(rule.status)}
                                                    </div>

                                                    <div className="flex-grow">
                                                        <div className="flex items-center justify-between">
                                                            <p className="text-sm font-medium text-gray-900 dark:text-gray-200">
                                                                {rule.title}
                                                            </p>
                                                            {/* Fix Button for Failed Checks */}
                                                            {rule.status === 'failed' && (
                                                                <button
                                                                    onClick={() => handleFix(rule)}
                                                                    className="ml-4 px-3 py-1 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-all flex items-center"
                                                                >
                                                                    <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                                                    Fix Issue
                                                                </button>
                                                            )}
                                                        </div>
                                                        {rule.description && (
                                                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                                                {rule.description}
                                                            </p>
                                                        )}

                                                        {/* Remediation Suggestion */}
                                                        {rule.remediation && (
                                                            <div className="mt-2 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-md">
                                                                <div className="flex items-start">
                                                                    <div className="flex-shrink-0">
                                                                        <svg className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                                                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                                                                        </svg>
                                                                    </div>
                                                                    <div className="ml-2">
                                                                        <h4 className="text-xs font-semibold text-blue-800 dark:text-blue-300">Remediation Suggestion:</h4>
                                                                        <p className="text-xs text-blue-700 dark:text-blue-200 mt-0.5">
                                                                            {rule.remediation}
                                                                        </p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        )}

                                                        {/* Evidence Display */}
                                                        {rule.evidence && (
                                                            <div className="mt-2 p-2 bg-gray-100 dark:bg-gray-900/50 rounded text-xs font-mono text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700">
                                                                <span className="font-semibold select-none">Evidence: </span>
                                                                {rule.evidence}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                                <span className={`px-2 py-1 text-xs font-medium rounded-full whitespace-nowrap ml-3 ${getStatusColor(rule.status)}`}>
                                                    {rule.status.toUpperCase()}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-sm text-blue-800 dark:text-blue-200">
                <p className="font-medium">📋 Note: Displaying {data.framework} compliance data</p>
                <p className="text-xs mt-1">Data collected from agent's compliance_enforcement capability.</p>
            </div>
        </div>
    );
};
