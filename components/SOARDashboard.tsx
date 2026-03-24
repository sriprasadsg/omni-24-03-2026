import React, { useState, useEffect } from 'react';
import { PlayIcon, CheckCircleIcon, XCircleIcon, ClockIcon, AlertTriangleIcon, ZapIcon } from './icons';

interface PlaybookExecution {
    id: string;
    playbook_name: string;
    status: string;
    started_at: string;
    completed_at?: string;
    executed_by: string;
    steps: ExecutionStep[];
    error?: string;
}

interface ExecutionStep {
    index: number;
    name: string;
    type: string;
    status: string;
    started_at: string;
    completed_at?: string;
    output?: any;
    error?: string;
}

interface ApprovalRequest {
    id: string;
    execution_id: string;
    step_index: number;
    step_name: string;
    description: string;
    approvers: string[];
    status: string;
    created_at: string;
    approved_by?: string;
    approved_at?: string;
}

interface PlaybookTemplate {
    id: string;
    name: string;
    description: string;
    category: string;
    tags: string[];
}

interface PlaybookAnalytics {
    total_executions: number;
    overall_success_rate: number;
    playbook_stats: Array<{
        playbook_id: string;
        playbook_name: string;
        total_executions: number;
        success_rate: number;
        avg_duration_ms: number;
    }>;
}

interface SOARDashboardProps {
    tenantId: string;
}

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
    const styles = {
        pending: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300',
        running: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 animate-pulse',
        completed: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
        failed: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
        waiting_approval: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
        rejected: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
    };

    const icons = {
        pending: ClockIcon,
        running: PlayIcon,
        completed: CheckCircleIcon,
        failed: XCircleIcon,
        waiting_approval: AlertTriangleIcon,
        rejected: XCircleIcon,
    };

    const Icon = icons[status] || ClockIcon;

    return (
        <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold ${styles[status]}`}>
            <Icon size={14} />
            {status.toUpperCase().replace('_', ' ')}
        </span>
    );
};

export const SOARDashboard: React.FC<SOARDashboardProps> = ({ tenantId }) => {
    const [executions, setExecutions] = useState<PlaybookExecution[]>([]);
    const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
    const [templates, setTemplates] = useState<PlaybookTemplate[]>([]);
    const [analytics, setAnalytics] = useState<PlaybookAnalytics | null>(null);
    const [selectedExecution, setSelectedExecution] = useState<PlaybookExecution | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'executions' | 'approvals' | 'templates' | 'analytics'>('executions');

    useEffect(() => {
        loadData();

        // Auto-refresh every 10 seconds
        const interval = setInterval(loadData, 10000);
        return () => clearInterval(interval);
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [executionsRes, approvalsRes, templatesRes, analyticsRes] = await Promise.all([
                fetch('/api/playbooks/enhanced/executions', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/playbooks/enhanced/executions?status=waiting_approval', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/playbooks/enhanced/templates', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                }),
                fetch('/api/playbooks/enhanced/analytics', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                })
            ]);

            if (executionsRes.ok) setExecutions(await executionsRes.json());
            if (approvalsRes.ok) {
                const data = await approvalsRes.json();
                setApprovals(data);
            }
            if (templatesRes.ok) setTemplates(await templatesRes.json());
            if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
        } catch (error) {
            console.error('Failed to load SOAR data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleApproval = async (executionId: string, stepIndex: number, action: 'approve' | 'reject', comment?: string) => {
        try {
            const response = await fetch('/api/playbooks/enhanced/approve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({
                    execution_id: executionId,
                    step_index: stepIndex,
                    action,
                    comment
                })
            });

            if (response.ok) {
                await loadData();
                alert(`Step ${action}d successfully`);
            } else {
                const error = await response.json();
                alert(error.detail || `Failed to ${action} step`);
            }
        } catch (error) {
            console.error(`Failed to ${action} step:`, error);
            alert(`Failed to ${action} step`);
        }
    };

    const handleExecuteTemplate = async (templateId: string) => {
        const name = prompt('Enter playbook name:');
        if (!name) return;

        try {
            const response = await fetch(`/api/playbooks/enhanced/templates?template_id=${templateId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({ name })
            });

            if (response.ok) {
                const data = await response.json();
                alert(`Playbook created: ${data.playbook_id}`);
                await loadData();
            } else {
                const error = await response.json();
                alert(error.detail || 'Failed to create playbook');
            }
        } catch (error) {
            console.error('Failed to create playbook:', error);
            alert('Failed to create playbook');
        }
    };

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                        SOAR Automation
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-1">
                        Security Orchestration, Automation, and Response
                    </p>
                </div>
                <div className="flex gap-2">
                    {approvals.length > 0 && (
                        <div className="px-4 py-2 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-lg font-semibold">
                            {approvals.length} Pending Approvals
                        </div>
                    )}
                </div>
            </div>

            {/* Analytics Cards */}
            {analytics && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-6 border border-blue-200 dark:border-blue-700 shadow-lg">
                        <p className="text-sm text-blue-600 dark:text-blue-400 font-semibold">Total Executions</p>
                        <p className="text-3xl font-bold text-blue-900 dark:text-blue-100 mt-2">{analytics.total_executions}</p>
                    </div>
                    <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-xl p-6 border border-green-200 dark:border-green-700 shadow-lg">
                        <p className="text-sm text-green-600 dark:text-green-400 font-semibold">Success Rate</p>
                        <p className="text-3xl font-bold text-green-900 dark:text-green-100 mt-2">{analytics.overall_success_rate.toFixed(1)}%</p>
                    </div>
                    <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-xl p-6 border border-purple-200 dark:border-purple-700 shadow-lg">
                        <p className="text-sm text-purple-600 dark:text-purple-400 font-semibold">Templates Available</p>
                        <p className="text-3xl font-bold text-purple-900 dark:text-purple-100 mt-2">{templates.length}</p>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
                {(['executions', 'approvals', 'templates', 'analytics'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-6 py-3 font-semibold transition-all ${activeTab === tab
                                ? 'border-b-2 border-purple-600 text-purple-600 dark:text-purple-400'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                            }`}
                    >
                        {tab.charAt(0).toUpperCase() + tab.slice(1)}
                        {tab === 'approvals' && approvals.length > 0 && (
                            <span className="ml-2 px-2 py-1 bg-amber-500 text-white rounded-full text-xs">
                                {approvals.length}
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {/* Executions Tab */}
            {activeTab === 'executions' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Executions List */}
                    <div className="space-y-3">
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Recent Executions</h2>
                        {executions.length === 0 ? (
                            <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-xl">
                                <ZapIcon size={64} className="mx-auto mb-4 text-gray-400 opacity-50" />
                                <p className="text-gray-600 dark:text-gray-400">No playbook executions yet</p>
                            </div>
                        ) : (
                            executions.map((execution) => (
                                <div
                                    key={execution.id}
                                    onClick={() => setSelectedExecution(execution)}
                                    className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedExecution?.id === execution.id
                                            ? 'bg-purple-50 dark:bg-purple-900/20 border-purple-500 shadow-lg'
                                            : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:shadow-md'
                                        }`}
                                >
                                    <div className="flex items-center justify-between mb-2">
                                        <h3 className="font-bold text-gray-900 dark:text-gray-100">{execution.playbook_name}</h3>
                                        <StatusBadge status={execution.status} />
                                    </div>
                                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                                        <span>{new Date(execution.started_at).toLocaleString()}</span>
                                        <span>By: {execution.executed_by}</span>
                                    </div>
                                    {execution.steps && (
                                        <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                                            {execution.steps.filter(s => s.status === 'completed').length} / {execution.steps.length} steps completed
                                        </div>
                                    )}
                                </div>
                            ))
                        )}
                    </div>

                    {/* Execution Details */}
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-3">Execution Details</h2>
                        {selectedExecution ? (
                            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg space-y-4">
                                <div>
                                    <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">{selectedExecution.playbook_name}</h3>
                                    <StatusBadge status={selectedExecution.status} />
                                </div>

                                {selectedExecution.error && (
                                    <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg">
                                        <p className="text-sm text-red-700 dark:text-red-300 font-semibold">Error:</p>
                                        <p className="text-sm text-red-600 dark:text-red-400">{selectedExecution.error}</p>
                                    </div>
                                )}

                                {selectedExecution.steps && selectedExecution.steps.length > 0 && (
                                    <div>
                                        <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                                            Steps ({selectedExecution.steps.length})
                                        </h4>
                                        <div className="space-y-2 max-h-[400px] overflow-y-auto">
                                            {selectedExecution.steps.map((step, idx) => (
                                                <div
                                                    key={idx}
                                                    className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600"
                                                >
                                                    <div className="flex items-start justify-between mb-2">
                                                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                                            {step.index + 1}. {step.name}
                                                        </span>
                                                        <StatusBadge status={step.status} />
                                                    </div>
                                                    <p className="text-xs text-gray-600 dark:text-gray-400">Type: {step.type}</p>
                                                    {step.error && (
                                                        <p className="text-xs text-red-600 dark:text-red-400 mt-1">Error: {step.error}</p>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-12 text-center">
                                <ZapIcon size={64} className="mx-auto mb-4 text-gray-400 opacity-50" />
                                <p className="text-gray-600 dark:text-gray-400">Select an execution to view details</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Approvals Tab */}
            {activeTab === 'approvals' && (
                <div className="space-y-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Pending Approvals</h2>
                    {approvals.length === 0 ? (
                        <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-xl">
                            <CheckCircleIcon size={64} className="mx-auto mb-4 text-green-500" />
                            <p className="text-green-600 dark:text-green-400 font-semibold">No pending approvals!</p>
                        </div>
                    ) : (
                        approvals.map((approval) => (
                            <div key={approval.id} className="bg-white dark:bg-gray-800 rounded-xl border border-amber-200 dark:border-amber-700 p-6 shadow-lg">
                                <div className="flex items-start justify-between mb-4">
                                    <div>
                                        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">{approval.step_name}</h3>
                                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{approval.description}</p>
                                    </div>
                                    <StatusBadge status={approval.status} />
                                </div>
                                <div className="mb-4 text-sm text-gray-600 dark:text-gray-400">
                                    <p>Requested: {new Date(approval.created_at).toLocaleString()}</p>
                                    <p>Approvers: {approval.approvers.join(', ')}</p>
                                </div>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => handleApproval(approval.execution_id, approval.step_index, 'approve')}
                                        className="flex-1 px-6 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg font-semibold transition-colors"
                                    >
                                        ✓ Approve
                                    </button>
                                    <button
                                        onClick={() => {
                                            const comment = prompt('Rejection reason:');
                                            if (comment) handleApproval(approval.execution_id, approval.step_index, 'reject', comment);
                                        }}
                                        className="flex-1 px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold transition-colors"
                                    >
                                        ✗ Reject
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            )}

            {/* Templates Tab */}
            {activeTab === 'templates' && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {templates.map((template) => (
                        <div key={template.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg hover:shadow-xl transition-shadow">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">{template.name}</h3>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{template.description}</p>
                            <div className="flex flex-wrap gap-2 mb-4">
                                {template.tags.map((tag, idx) => (
                                    <span key={idx} className="px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded text-xs font-semibold">
                                        {tag}
                                    </span>
                                ))}
                            </div>
                            <button
                                onClick={() => handleExecuteTemplate(template.id)}
                                className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
                            >
                                Use Template
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Analytics Tab */}
            {activeTab === 'analytics' && analytics && (
                <div className="space-y-6">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">Playbook Performance</h2>
                    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-lg">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-gray-200 dark:border-gray-700">
                                    <th className="text-left py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Playbook</th>
                                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Executions</th>
                                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Success Rate</th>
                                    <th className="text-right py-3 px-4 text-sm font-semibold text-gray-700 dark:text-gray-300">Avg Duration</th>
                                </tr>
                            </thead>
                            <tbody>
                                {analytics.playbook_stats.map((stat, idx) => (
                                    <tr key={idx} className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                        <td className="py-3 px-4 text-sm text-gray-900 dark:text-gray-100">{stat.playbook_name}</td>
                                        <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 text-right">{stat.total_executions}</td>
                                        <td className={`py-3 px-4 text-sm text-right font-semibold ${stat.success_rate >= 90 ? 'text-green-600' : stat.success_rate >= 70 ? 'text-amber-600' : 'text-red-600'
                                            }`}>
                                            {stat.success_rate.toFixed(1)}%
                                        </td>
                                        <td className="py-3 px-4 text-sm text-gray-700 dark:text-gray-300 text-right">
                                            {(stat.avg_duration_ms / 1000).toFixed(1)}s
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};
