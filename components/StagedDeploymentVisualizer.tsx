import React, { useState, useEffect } from 'react';
import { CheckCircleIcon, XCircleIcon, ClockIcon, PlayCircleIcon, PauseCircleIcon, RefreshCcwIcon } from './icons';

interface StageData {
    stage: string;
    status: string;
    asset_count: number;
    success_count: number;
    failure_count: number;
    started_at: string | null;
    completed_at: string | null;
    approval_required: boolean;
    approval_status: string | null;
}

interface DeploymentData {
    id: string;
    status: string;
    current_stage: string;
    created_at: string;
    patch_ids: string[];
    all_asset_ids: string[];
    stages: StageData[];
    rollback_id?: string;
    rollback_reason?: string;
}

interface StagedDeploymentVisualizerProps {
    deploymentId: string;
}

export const StagedDeploymentVisualizer: React.FC<StagedDeploymentVisualizerProps> = ({ deploymentId }) => {
    const [deployment, setDeployment] = useState<DeploymentData | null>(null);
    const [loading, setLoading] = useState(true);
    const [autoRefresh, setAutoRefresh] = useState(true);

    useEffect(() => {
        fetchDeployment();

        if (autoRefresh) {
            const interval = setInterval(fetchDeployment, 10000); // Refresh every 10s
            return () => clearInterval(interval);
        }
    }, [deploymentId, autoRefresh]);

    const fetchDeployment = async () => {
        try {
            const response = await fetch(`/api/deployments/staged/${deploymentId}`);
            const data = await response.json();
            setDeployment(data);
        } catch (error) {
            console.error('Error fetching deployment:', error);
        } finally {
            setLoading(false);
        }
    };

    const getStageIcon = (status: string) => {
        switch (status) {
            case 'completed':
                return <CheckCircleIcon size={24} className="text-green-500" />;
            case 'failed':
            case 'rolled_back':
                return <XCircleIcon size={24} className="text-red-500" />;
            case 'in_progress':
                return <PlayCircleIcon size={24} className="text-blue-500 animate-pulse" />;
            case 'awaiting_approval':
                return <PauseCircleIcon size={24} className="text-yellow-500" />;
            default:
                return <ClockIcon size={24} className="text-gray-400" />;
        }
    };

    const getStageColor = (stage: string, isCurrent: boolean) => {
        const baseColors: Record<string, string> = {
            test: 'bg-blue-500',
            dev: 'bg-purple-500',
            staging: 'bg-yellow-500',
            production: 'bg-red-500'
        };

        if (isCurrent) return baseColors[stage];
        return baseColors[stage]?.replace('500', '300') || 'bg-gray-300';
    };

    const getSuccessRate = (stage: StageData) => {
        const total = stage.success_count + stage.failure_count;
        if (total === 0) return 0;
        return (stage.success_count / total) * 100;
    };

    if (loading || !deployment) {
        return <div className="p-6">Loading deployment...</div>;
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-start">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                        Staged Deployment: {deployment.id}
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {deployment.patch_ids.length} patches • {deployment.all_asset_ids.length} total assets
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="checkbox"
                            checked={autoRefresh}
                            onChange={(e) => setAutoRefresh(e.target.checked)}
                            className="rounded"
                        />
                        Auto-refresh
                    </label>
                    <button
                        onClick={fetchDeployment}
                        className="p-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600"
                    >
                        <RefreshCcwIcon size={18} />
                    </button>
                </div>
            </div>

            {/* Overall Status Badge */}
            <div className={`p-4 rounded-lg border-l-4 ${deployment.status === 'completed' ? 'bg-green-50 border-green-500 dark:bg-green-900/20' :
                deployment.status === 'failed' || deployment.status === 'rolled_back' ? 'bg-red-50 border-red-500 dark:bg-red-900/20' :
                    deployment.status === 'rejected' ? 'bg-red-50 border-red-500 dark:bg-red-900/20' :
                        'bg-blue-50 border-blue-500 dark:bg-blue-900/20'
                }`}>
                <p className="font-semibold text-sm">
                    Status: <span className="uppercase">{deployment.status.replace('_', ' ')}</span>
                </p>
                {deployment.current_stage && (
                    <p className="text-sm mt-1">
                        Current Stage: <span className="font-medium uppercase">{deployment.current_stage}</span>
                    </p>
                )}
                {deployment.rollback_reason && (
                    <p className="text-sm text-red-700 dark:text-red-300 mt-2">
                        ⚠️ Rollback Reason: {deployment.rollback_reason}
                    </p>
                )}
            </div>

            {/* Stage Pipeline Visualization */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold mb-6">Deployment Pipeline</h3>

                {/* Visual Pipeline */}
                <div className="relative mb-8">
                    <div className="flex items-center justify-between relative">
                        {/* Progress Line */}
                        <div className="absolute left-0 right-0 top-1/2 h-1 bg-gray-300 dark:bg-gray-700 -translate-y-1/2" />

                        {/* Stage Circles */}
                        {deployment.stages.map((stage, index) => {
                            const isCurrent = stage.stage === deployment.current_stage;
                            const isCompleted = stage.status === 'completed';
                            const isFailed = stage.status === 'failed' || stage.status === 'rolled_back';

                            return (
                                <div key={stage.stage} className="relative z-10 flex flex-col items-center">
                                    <div className={`w-16 h-16 rounded-full flex items-center justify-center ${isCompleted ? 'bg-green-500' :
                                        isFailed ? 'bg-red-500' :
                                            isCurrent ? getStageColor(stage.stage, true) :
                                                'bg-gray-300 dark:bg-gray-700'
                                        } ${isCurrent ? 'ring-4 ring-blue-300 dark:ring-blue-700' : ''}`}>
                                        {getStageIcon(stage.status)}
                                    </div>
                                    <p className="text-xs font-semibold uppercase mt-2 text-gray-700 dark:text-gray-300">
                                        {stage.stage}
                                    </p>
                                    {stage.status === 'awaiting_approval' && (
                                        <span className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                                            Awaiting Approval
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Detailed Stage Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {deployment.stages.map((stage) => {
                        const successRate = getSuccessRate(stage);
                        const total = stage.success_count + stage.failure_count;
                        const progress = stage.asset_count > 0 ? (total / stage.asset_count) * 100 : 0;

                        return (
                            <div key={stage.stage} className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                                <div className="flex items-center justify-between mb-3">
                                    <h4 className="font-semibold uppercase text-sm">{stage.stage}</h4>
                                    {getStageIcon(stage.status)}
                                </div>

                                <div className="space-y-2 text-xs">
                                    <div className="flex justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">Assets:</span>
                                        <span className="font-medium">{stage.asset_count}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-gray-600 dark:text-gray-400">Completed:</span>
                                        <span className="font-medium">{total}/{stage.asset_count}</span>
                                    </div>
                                    {total > 0 && (
                                        <>
                                            <div className="flex justify-between">
                                                <span className="text-green-600 dark:text-green-400">Success:</span>
                                                <span className="font-medium">{stage.success_count}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-red-600 dark:text-red-400">Failed:</span>
                                                <span className="font-medium">{stage.failure_count}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-gray-600 dark:text-gray-400">Success Rate:</span>
                                                <span className="font-medium">{successRate.toFixed(1)}%</span>
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Progress Bar */}
                                {stage.status === 'in_progress' && (
                                    <div className="mt-3">
                                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                            <div
                                                className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                                                style={{ width: `${progress}%` }}
                                            />
                                        </div>
                                        <p className="text-xs text-gray-500 mt-1 text-center">
                                            {progress.toFixed(0)}% complete
                                        </p>
                                    </div>
                                )}

                                {/* Timestamps */}
                                {stage.started_at && (
                                    <p className="text-xs text-gray-500 mt-3">
                                        Started: {new Date(stage.started_at).toLocaleString()}
                                    </p>
                                )}
                                {stage.completed_at && (
                                    <p className="text-xs text-gray-500">
                                        Completed: {new Date(stage.completed_at).toLocaleString()}
                                    </p>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};
