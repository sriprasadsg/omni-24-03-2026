import React, { useState, useEffect } from 'react';
import {
    ShieldCheckIcon,
    AlertTriangleIcon,
    CheckIcon,
    XCircleIcon,
    ClockIcon,
    ServerIcon,
    ActivityIcon
} from './icons';

interface ApprovalRequest {
    id: string;
    agent_id: string;
    action_type: string;
    description: string;
    risk_score: number;
    reasoning: string;
    details: any;
    timestamp: string;
}

const AgentApprovalDashboard: React.FC = () => {
    const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);
    const [history, setHistory] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    // Poll for updates
    useEffect(() => {
        fetchApprovals();
        const interval = setInterval(fetchApprovals, 5000); // 5s poll
        return () => clearInterval(interval);
    }, []);

    const fetchApprovals = async () => {
        try {
            const res = await fetch('/api/agents/approvals/pending');
            if (res.ok) {
                const data = await res.json();
                setPendingApprovals(data);
            }
        } catch (err) {
            console.error("Failed to fetch approvals:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleDecision = async (id: string, decision: 'approve' | 'reject') => {
        try {
            const res = await fetch(`/api/agents/approvals/${id}/decide`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ decision, reason: "User manual decision via UI" })
            });

            if (res.ok) {
                // Optimistic update
                setPendingApprovals(prev => prev.filter(p => p.id !== id));
                fetchApprovals(); // Sync
            }
        } catch (err) {
            console.error("Decision failed:", err);
        }
    };

    const getRiskColor = (score: number) => {
        if (score >= 8) return 'text-red-500';
        if (score >= 5) return 'text-yellow-500';
        return 'text-green-500';
    };

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-8">

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <ShieldCheckIcon size={32} className="text-blue-500" />
                        Agent Autonomous Approvals
                    </h1>
                    <p className="text-gray-400 mt-1">Review and authorize pending autonomous actions from agents.</p>
                </div>
                <div className="flex items-center gap-2 bg-gray-800 px-4 py-2 rounded-lg">
                    <ActivityIcon size={16} className="text-green-400 animate-pulse" />
                    <span className="text-sm font-mono text-green-400">Agentic Mode Active</span>
                </div>
            </div>

            {/* Pending List */}
            <div className="space-y-4">
                <h2 className="text-xl font-semibold flex items-center gap-2">
                    <ClockIcon size={20} className="text-yellow-500" />
                    Pending Requests ({pendingApprovals.length})
                </h2>

                {loading ? (
                    <div className="text-center py-12 text-gray-500 animate-pulse">Checking for requests...</div>
                ) : pendingApprovals.length === 0 ? (
                    <div className="bg-gray-800/50 rounded-xl p-12 text-center border border-gray-700 border-dashed">
                        <ShieldCheckIcon size={48} className="text-green-500/50 mx-auto mb-4" />
                        <h3 className="text-lg font-medium text-gray-300">All Clear</h3>
                        <p className="text-gray-500">No actions waiting for approval right now.</p>
                    </div>
                ) : (
                    <div className="grid gap-4">
                        {pendingApprovals.map(req => (
                            <div key={req.id} className="bg-gray-800 rounded-xl p-6 border border-gray-700 shadow-lg flex flex-col md:flex-row gap-6">

                                {/* Status Indicator */}
                                <div className="hidden md:flex flex-col items-center justify-center p-4 bg-gray-900/50 rounded-lg min-w-[120px]">
                                    <AlertTriangleIcon size={32} className={`${getRiskColor(req.risk_score)} mb-2`} />
                                    <span className="text-xs text-gray-500 uppercase tracking-wider">Risk Score</span>
                                    <span className={`text-2xl font-bold ${getRiskColor(req.risk_score)}`}>{req.risk_score}/10</span>
                                </div>

                                {/* Content */}
                                <div className="flex-1 space-y-3">
                                    <div className="flex items-start justify-between">
                                        <div>
                                            <h3 className="text-lg font-bold text-white flex items-center gap-2">
                                                {req.action_type}
                                                <span className="text-sm font-normal text-gray-400 bg-gray-700 px-2 py-0.5 rounded-full">
                                                    {req.agent_id}
                                                </span>
                                            </h3>
                                            <p className="text-gray-300 mt-1">{req.description}</p>
                                        </div>
                                        <span className="text-sm text-gray-500 font-mono">
                                            {new Date(req.timestamp).toLocaleTimeString()}
                                        </span>
                                    </div>

                                    <div className="bg-gray-900/50 p-3 rounded-lg border border-gray-700/50">
                                        <p className="text-sm text-gray-400 font-mono">
                                            <span className="text-blue-400">Reasoning:</span> {req.reasoning}
                                        </p>
                                    </div>
                                </div>

                                {/* Actions */}
                                <div className="flex flex-row md:flex-col gap-3 justify-center min-w-[140px]">
                                    <button
                                        onClick={() => handleDecision(req.id, 'approve')}
                                        className="flex-1 bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
                                    >
                                        <CheckIcon size={16} />
                                        Approve
                                    </button>
                                    <button
                                        onClick={() => handleDecision(req.id, 'reject')}
                                        className="flex-1 bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
                                    >
                                        <XCircleIcon size={16} />
                                        Reject
                                    </button>
                                </div>

                            </div>
                        ))}
                    </div>
                )}
            </div>

        </div>
    );
};

export default AgentApprovalDashboard;
