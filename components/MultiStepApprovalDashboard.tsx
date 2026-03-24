import React, { useState, useEffect } from 'react';
import { CheckIcon, XCircleIcon, ClockIcon, AlertTriangleIcon, UserIcon, BotMessageSquareIcon } from './icons';
import * as api from '../services/apiService';
import { useUser } from '../contexts/UserContext';

export const MultiStepApprovalDashboard: React.FC = () => {
    const { currentUser } = useUser();
    const [pendingRequests, setPendingRequests] = useState<any[]>([]);
    const [history, setHistory] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [selectedRequest, setSelectedRequest] = useState<any>(null);
    const [comments, setComments] = useState('');
    const [activeTab, setActiveTab] = useState<'pending' | 'history'>('pending');

    useEffect(() => {
        loadData();
    }, [currentUser]);

    const loadData = async () => {
        if (!currentUser) return;
        setLoading(true);
        try {
            const [pending, hist] = await Promise.all([
                api.fetchPendingApprovals(currentUser.email),
                api.fetchApprovalHistory()
            ]);
            setPendingRequests(pending);
            setHistory(hist);
        } catch (e) {
            console.error("Failed to load approval data", e);
        } finally {
            setLoading(false);
        }
    };

    const handleDecision = async (requestId: string, decision: 'approve' | 'reject') => {
        if (!currentUser) return;
        try {
            const res = await api.submitApprovalDecision(requestId, currentUser.email, decision, comments);
            if (res.success) {
                alert(`Request ${decision === 'approve' ? 'approved' : 'rejected'} successfully.`);
                setComments('');
                setSelectedRequest(null);
                loadData();
            }
        } catch (e) {
            alert("Failed to submit decision");
        }
    };

    const getStatusBadge = (status: string) => {
        const styles: any = {
            pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
            approved: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
            rejected: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300'
        };
        return (
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[status] || 'bg-gray-100 text-gray-800'}`}>
                {status.toUpperCase()}
            </span>
        );
    };

    return (
        <div className="container mx-auto p-6">
            <div className="mb-6">
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">Approval Workflows</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Review and authorize sensitive operations across the platform.</p>
            </div>

            <div className="flex border-b border-gray-200 dark:border-gray-700 mb-6">
                <button
                    onClick={() => setActiveTab('pending')}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'pending' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}`}
                >
                    Pending Approvals ({pendingRequests.length})
                </button>
                <button
                    onClick={() => setActiveTab('history')}
                    className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'history' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}`}
                >
                    Decision History
                </button>
            </div>

            {loading ? (
                <div className="flex justify-center items-center py-20">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* List of Requests */}
                    <div className="lg:col-span-1 space-y-4">
                        {(activeTab === 'pending' ? pendingRequests : history).map(req => (
                            <div
                                key={req.id}
                                onClick={() => setSelectedRequest(req)}
                                className={`p-4 rounded-lg border cursor-pointer transition-all ${selectedRequest?.id === req.id ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 shadow-sm' : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-primary-300'}`}
                            >
                                <div className="flex justify-between items-start mb-2">
                                    <span className="text-xs font-mono text-gray-500">{req.id}</span>
                                    {getStatusBadge(req.status)}
                                </div>
                                <h4 className="font-semibold text-gray-900 dark:text-white mb-1">{req.actionType}</h4>
                                <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{req.description}</p>
                                <div className="mt-3 flex items-center text-xs text-gray-400">
                                    <ClockIcon size={12} className="mr-1" />
                                    {new Date(req.createdAt).toLocaleString()}
                                </div>
                            </div>
                        ))}
                        {(activeTab === 'pending' ? pendingRequests : history).length === 0 && (
                            <div className="text-center py-10 text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 rounded-lg border border-dashed border-gray-300 dark:border-gray-700">
                                No {activeTab} requests found.
                            </div>
                        )}
                    </div>

                    {/* Detail View */}
                    <div className="lg:col-span-2">
                        {selectedRequest ? (
                            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
                                <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex justify-between items-start mb-4">
                                        <div>
                                            <h3 className="text-xl font-bold text-gray-900 dark:text-white">{selectedRequest.actionType}</h3>
                                            <p className="text-gray-500 dark:text-gray-400 mt-1">{selectedRequest.description}</p>
                                        </div>
                                        {getStatusBadge(selectedRequest.status)}
                                    </div>

                                    <div className="grid grid-cols-2 gap-4 text-sm mt-6">
                                        <div className="flex items-center text-gray-600 dark:text-gray-300">
                                            <UserIcon size={16} className="mr-2 text-gray-400" />
                                            <span className="font-medium mr-2">Requester:</span> {selectedRequest.requester}
                                        </div>
                                        <div className="flex items-center text-gray-600 dark:text-gray-300">
                                            <ClockIcon size={16} className="mr-2 text-gray-400" />
                                            <span className="font-medium mr-2">Created:</span> {new Date(selectedRequest.createdAt).toLocaleString()}
                                        </div>
                                    </div>
                                </div>

                                <div className="p-6 space-y-6">
                                    {/* Workflow Steps */}
                                    <div>
                                        <h5 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 uppercase tracking-wider">Approval Workflow</h5>
                                        <div className="space-y-4">
                                            {selectedRequest.steps.map((step: any, idx: number) => (
                                                <div key={idx} className="flex items-start">
                                                    <div className="flex flex-col items-center mr-4">
                                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step.status === 'approved' ? 'bg-green-500 text-white' :
                                                            step.status === 'rejected' ? 'bg-red-500 text-white' :
                                                                step.status === 'pending' ? 'bg-amber-500 text-white animate-pulse' :
                                                                    'bg-gray-200 dark:bg-gray-700 text-gray-500'
                                                            }`}>
                                                            {step.status === 'approved' ? <CheckIcon size={16} /> :
                                                                step.status === 'rejected' ? <XCircleIcon size={16} /> :
                                                                    idx + 1}
                                                        </div>
                                                        {idx < selectedRequest.steps.length - 1 && (
                                                            <div className="w-0.5 h-8 bg-gray-200 dark:bg-gray-700 my-1"></div>
                                                        )}
                                                    </div>
                                                    <div className="flex-1 pt-1">
                                                        <div className="flex justify-between items-start">
                                                            <div className="font-medium text-gray-900 dark:text-white">{step.role}</div>
                                                            <span className={`text-xs font-medium uppercase ${step.status === 'approved' ? 'text-green-600' :
                                                                step.status === 'rejected' ? 'text-red-600' :
                                                                    step.status === 'pending' ? 'text-amber-600' :
                                                                        'text-gray-400'
                                                                }`}>
                                                                {step.status}
                                                            </span>
                                                        </div>
                                                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                                            Approvers: {step.approvers.join(', ')}
                                                        </div>
                                                        {step.decided_by && (
                                                            <div className="mt-2 p-2 bg-gray-50 dark:bg-gray-900/50 rounded text-xs border border-gray-100 dark:border-gray-800">
                                                                <div className="font-medium text-gray-700 dark:text-gray-300">Decision by {step.decided_by}</div>
                                                                {step.comments && <div className="mt-1 italic">"{step.comments}"</div>}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Action Details */}
                                    <div className="bg-gray-50 dark:bg-gray-900/30 p-4 rounded-lg border border-gray-100 dark:border-gray-800">
                                        <h5 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Request Details</h5>
                                        <pre className="text-xs font-mono text-gray-600 dark:text-gray-400 overflow-x-auto">
                                            {JSON.stringify(selectedRequest.details, null, 2)}
                                        </pre>
                                    </div>

                                    {/* Decision Form */}
                                    {selectedRequest.status === 'pending' && selectedRequest.steps[selectedRequest.currentStep - 1].approvers.includes(currentUser?.email) && (
                                        <div className="pt-6 border-t border-gray-200 dark:border-gray-700">
                                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                                <BotMessageSquareIcon size={16} className="inline mr-2" />
                                                Decision Comments
                                            </label>
                                            <textarea
                                                value={comments}
                                                onChange={(e) => setComments(e.target.value)}
                                                className="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm px-3 py-2"
                                                rows={3}
                                                placeholder="Explain your decision..."
                                            />
                                            <div className="flex gap-3 mt-4">
                                                <button
                                                    onClick={() => handleDecision(selectedRequest.id, 'approve')}
                                                    className="flex-1 flex justify-center items-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                                                >
                                                    <CheckIcon size={16} className="mr-2" />
                                                    Approve Request
                                                </button>
                                                <button
                                                    onClick={() => handleDecision(selectedRequest.id, 'reject')}
                                                    className="flex-1 flex justify-center items-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                                                >
                                                    <XCircleIcon size={16} className="mr-2" />
                                                    Reject Request
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-20 text-center border border-dashed border-gray-300 dark:border-gray-700">
                                <AlertTriangleIcon size={48} className="mx-auto text-gray-400 mb-4" />
                                <h3 className="text-lg font-medium text-gray-900 dark:text-white">No Request Selected</h3>
                                <p className="text-gray-500 dark:text-gray-400 mt-1">Select a request from the list to view details and take action.</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};
