import React, { useState, useEffect } from 'react';
import { CheckCircleIcon, XCircleIcon, ClockIcon, AlertTriangleIcon, PlayCircleIcon } from './icons';

interface ApprovalRequest {
    id: string;
    deployment_id: string;
    stage: string;
    status: string;
    approvers: string[];
    created_at: string;
    expires_at: number;
    deployment_info?: {
        patch_ids: string[];
        current_stage: string;
        created_by: string;
    };
}

interface ApprovalDashboardProps {
    currentUser: { id: string; email: string };
}

export const ApprovalDashboard: React.FC<ApprovalDashboardProps> = ({ currentUser }) => {
    const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(null);
    const [comments, setComments] = useState('');
    const [rejectionReason, setRejectionReason] = useState('');
    const [showRejectModal, setShowRejectModal] = useState(false);

    useEffect(() => {
        fetchPendingApprovals();
        const interval = setInterval(fetchPendingApprovals, 30000); // Refresh every 30s
        return () => clearInterval(interval);
    }, []);

    const fetchPendingApprovals = async () => {
        try {
            const response = await fetch(`/api/deployments/approvals/pending?user_id=${currentUser.email}`);
            const data = await response.json();
            setApprovals(data.approvals || []);
        } catch (error) {
            console.error('Error fetching approvals:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (approvalId: string) => {
        try {
            const response = await fetch(`/api/deployments/approvals/${approvalId}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    approved_by: currentUser.email,
                    comments: comments
                })
            });

            const data = await response.json();

            if (data.success) {
                alert(`✅ Approved! Deployment is progressing to ${data.approval.stage} stage.`);
                fetchPendingApprovals();
                setSelectedApproval(null);
                setComments('');
            }
        } catch (error) {
            console.error('Error approving:', error);
            alert('Failed to approve deployment');
        }
    };

    const handleReject = async (approvalId: string) => {
        if (!rejectionReason.trim()) {
            alert('Please provide a reason for rejection');
            return;
        }

        try {
            const response = await fetch(`/api/deployments/approvals/${approvalId}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    rejected_by: currentUser.email,
                    reason: rejectionReason
                })
            });

            const data = await response.json();

            if (data.success) {
                alert('❌ Deployment rejected and halted.');
                fetchPendingApprovals();
                setShowRejectModal(false);
                setRejectionReason('');
                setSelectedApproval(null);
            }
        } catch (error) {
            console.error('Error rejecting:', error);
            alert('Failed to reject deployment');
        }
    };

    const getTimeRemaining = (expiresAt: number) => {
        const now = Date.now() / 1000;
        const remaining = expiresAt - now;

        if (remaining < 0) return 'Expired';

        const hours = Math.floor(remaining / 3600);
        const minutes = Math.floor((remaining % 3600) / 60);

        if (hours > 0) return `${hours}h ${minutes}m`;
        return `${minutes}m`;
    };

    const getStageColor = (stage: string) => {
        const colors: Record<string, string> = {
            test: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
            dev: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300',
            staging: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
            production: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300'
        };
        return colors[stage] || 'bg-gray-100 text-gray-800';
    };

    if (loading) {
        return <div className="p-6">Loading approval requests...</div>;
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white flex items-center">
                    <CheckCircleIcon size={28} className="mr-3 text-primary-500" />
                    Deployment Approval Queue
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    Review and approve patch deployments waiting for your authorization
                </p>
            </div>

            {/* Summary Badge */}
            {approvals.length > 0 && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <div className="flex items-center">
                        <ClockIcon size={20} className="text-blue-600 dark:text-blue-400 mr-2" />
                        <p className="text-sm text-blue-900 dark:text-blue-200 font-medium">
                            {approvals.length} deployment{approvals.length !== 1 ? 's' : ''} awaiting your approval
                        </p>
                    </div>
                </div>
            )}

            {/* Approval Cards */}
            {approvals.length === 0 ? (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-12 text-center">
                    <CheckCircleIcon size={64} className="mx-auto mb-4 text-green-500 opacity-50" />
                    <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        No Pending Approvals
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        All deployments have been reviewed or there are no pending requests for you.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4">
                    {approvals.map(approval => (
                        <div key={approval.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
                            <div className="p-6">
                                {/* Header Row */}
                                <div className="flex justify-between items-start mb-4">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                                                Deployment {approval.deployment_id}
                                            </h3>
                                            <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase ${getStageColor(approval.stage)}`}>
                                                {approval.stage}
                                            </span>
                                        </div>
                                        <p className="text-sm text-gray-600 dark:text-gray-400">
                                            Requested by: {approval.deployment_info?.created_by || 'Unknown'}
                                        </p>
                                        <p className="text-sm text-gray-600 dark:text-gray-400">
                                            Patches: {approval.deployment_info?.patch_ids?.length || 0}
                                        </p>
                                    </div>

                                    {/* Time Remaining */}
                                    <div className="text-right">
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Expires in</p>
                                        <p className="text-sm font-semibold text-orange-600 dark:text-orange-400">
                                            {getTimeRemaining(approval.expires_at)}
                                        </p>
                                    </div>
                                </div>

                                {/* Actions Row */}
                                <div className="flex items-center gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                                    <button
                                        onClick={() => {
                                            setSelectedApproval(approval);
                                            handleApprove(approval.id);
                                        }}
                                        className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center justify-center gap-2 font-medium transition-colors"
                                    >
                                        <CheckCircleIcon size={18} />
                                        Approve
                                    </button>
                                    <button
                                        onClick={() => {
                                            setSelectedApproval(approval);
                                            setShowRejectModal(true);
                                        }}
                                        className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 flex items-center justify-center gap-2 font-medium transition-colors"
                                    >
                                        <XCircleIcon size={18} />
                                        Reject
                                    </button>
                                    <button
                                        onClick={() => window.open(`/deployments/${approval.deployment_id}`, '_blank')}
                                        className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                                    >
                                        View Details
                                    </button>
                                </div>

                                {/* Optional Comments */}
                                {selectedApproval?.id === approval.id && !showRejectModal && (
                                    <div className="mt-4">
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                            Comments (Optional)
                                        </label>
                                        <textarea
                                            value={comments}
                                            onChange={(e) => setComments(e.target.value)}
                                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm"
                                            rows={2}
                                            placeholder="Add any comments about this approval..."
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Rejection Modal */}
            {showRejectModal && selectedApproval && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex items-center">
                            <AlertTriangleIcon size={24} className="mr-2 text-red-500" />
                            Reject Deployment
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                            Please provide a reason for rejecting this deployment. The deployment will be halted.
                        </p>
                        <textarea
                            value={rejectionReason}
                            onChange={(e) => setRejectionReason(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm mb-4"
                            rows={4}
                            placeholder="Enter rejection reason..."
                            required
                        />
                        <div className="flex gap-3">
                            <button
                                onClick={() => handleReject(selectedApproval.id)}
                                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium"
                            >
                                Confirm Rejection
                            </button>
                            <button
                                onClick={() => {
                                    setShowRejectModal(false);
                                    setRejectionReason('');
                                    setSelectedApproval(null);
                                }}
                                className="flex-1 px-4 py-2 bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-400 dark:hover:bg-gray-600 font-medium"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
