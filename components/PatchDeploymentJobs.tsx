import React, { useState } from 'react';
import { PatchDeploymentJob, PatchDeploymentJobStatus } from '../types';
import { UploadCloudIcon, ZapIcon, ChevronDownIcon, ClockIcon, CheckIcon, AlertTriangleIcon, XCircleIcon, CogIcon, TerminalSquareIcon, XIcon, RefreshCwIcon } from './icons';

const statusInfo: Record<string, { icon: React.ReactNode; classes: string; }> = {
    Scheduled: { icon: <ClockIcon size={14} />, classes: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300' },
    Queued: { icon: <ClockIcon size={14} />, classes: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300' },
    'In Progress': { icon: <CogIcon size={14} className="animate-spin" />, classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' },
    Completed: { icon: <CheckIcon size={14} />, classes: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' },
    'Completed with errors': { icon: <AlertTriangleIcon size={14} />, classes: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-400' },
    'Partially Completed': { icon: <AlertTriangleIcon size={14} />, classes: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-400' },
    Failed: { icon: <XCircleIcon size={14} />, classes: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' },
    'Rolled Back': { icon: <RefreshCwIcon size={14} />, classes: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300' },
};

const getStatusDisplay = (status: string) => {
    return statusInfo[status] || { icon: <AlertTriangleIcon size={14} />, classes: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300' };
};

const JobLogModal: React.FC<{ isOpen: boolean; job: PatchDeploymentJob | null; onClose: () => void }> = ({ isOpen, job, onClose }) => {
    if (!isOpen || !job) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center"><TerminalSquareIcon className="mr-3 text-primary-500" /> Deployment Log</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{job.id}</p>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>
                <div className="flex-grow p-3 bg-gray-900 dark:bg-black rounded-md overflow-y-auto font-mono text-xs">
                    {job.statusLog.map((log, index) => (
                        <div key={index} className="flex items-start">
                            <span className="text-gray-500 mr-3 whitespace-nowrap">{new Date(log.timestamp).toLocaleTimeString()}</span>
                            <p className={`whitespace-pre-wrap ${log.message.includes('ERROR') ? 'text-red-400' : 'text-gray-300'}`}>{log.message}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

interface PatchDeploymentJobsProps {
    jobs: PatchDeploymentJob[];
}

export const PatchDeploymentJobs: React.FC<PatchDeploymentJobsProps> = ({ jobs }) => {
    const [isOpen, setIsOpen] = useState(true);
    const [viewingJobLogs, setViewingJobLogs] = useState<PatchDeploymentJob | null>(null);
    const [rollingBack, setRollingBack] = useState<string | null>(null);

    const handleRollback = async (jobId: string) => {
        if (!window.confirm('Are you sure you want to rollback this deployment? This will uninstall the patches from all affected assets.')) {
            return;
        }

        setRollingBack(jobId);
        try {
            const response = await fetch(`/api/deployments/${jobId}/rollback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: 'Manual rollback from UI' })
            });

            if (response.ok) {
                alert('Rollback initiated successfully.');
                // In a real app, we would refresh the jobs list here
            } else {
                const error = await response.json();
                alert(`Failed to initiate rollback: ${error.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error rolling back:', error);
            alert('Error connecting to server.');
        } finally {
            setRollingBack(null);
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <button onClick={() => setIsOpen(!isOpen)} className="w-full p-4 flex justify-between items-center text-left">
                <h3 className="text-lg font-semibold">Patch Deployment Jobs</h3>
                <ChevronDownIcon size={20} className={`text-gray-500 dark:text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>
            {isOpen && (
                <div className="p-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="overflow-x-auto max-h-80 overflow-y-auto">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                            <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400 sticky top-0">
                                <tr>
                                    <th className="px-4 py-3">Job ID</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3">Progress</th>
                                    <th className="px-4 py-3">Details</th>
                                    <th className="px-4 py-3">Scheduled At</th>
                                    <th className="px-4 py-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {jobs.map(job => (
                                    <tr key={job.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                        <td className="px-4 py-3 font-mono text-xs">{job.id}</td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${getStatusDisplay(job.status).classes}`}>
                                                {getStatusDisplay(job.status).icon} <span className="ml-1.5">{job.status}</span>
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center">
                                                <div className="w-24 bg-gray-200 dark:bg-gray-600 rounded-full h-1.5 mr-2">
                                                    <div className="bg-primary-600 h-1.5 rounded-full" style={{ width: `${job.progress}%` }}></div>
                                                </div>
                                                <span className="text-xs font-medium">{job.progress}%</span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-xs">{(job.patchIds || job.targetPatchIds || []).length} Patches to {(job.targetAssets || job.targetAssetIds || []).length} Assets</td>
                                        <td className="px-4 py-3 text-xs">{new Date(job.startTime || job.scheduledAt).toLocaleString()}</td>
                                        <td className="px-4 py-3 text-right">
                                            <div className="flex justify-end gap-2">
                                                <button
                                                    onClick={() => setViewingJobLogs(job)}
                                                    className="p-1.5 text-gray-500 hover:text-primary-600"
                                                    title="View Logs"
                                                >
                                                    <TerminalSquareIcon size={14} />
                                                </button>
                                                {(job.status === 'Completed' || job.status === 'Failed' || job.status === 'Partially Completed') && (
                                                    <button
                                                        onClick={() => handleRollback(job.id)}
                                                        disabled={rollingBack === job.id}
                                                        className={`p-1.5 text-gray-500 hover:text-red-600 ${rollingBack === job.id ? 'animate-spin' : ''}`}
                                                        title="Rollback Deployment"
                                                    >
                                                        <RefreshCwIcon size={14} />
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {jobs.length === 0 && (
                                    <tr>
                                        <td colSpan={6} className="text-center py-4 text-gray-500 dark:text-gray-400">No patch deployment jobs found.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
            <JobLogModal isOpen={!!viewingJobLogs} job={viewingJobLogs} onClose={() => setViewingJobLogs(null)} />
        </div>
    );
};
