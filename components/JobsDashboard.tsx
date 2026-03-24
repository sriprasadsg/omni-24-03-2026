import React, { useState, useEffect } from 'react';
import {
    RefreshCwIcon,
    CheckIcon as CheckCircleIcon,
    XIcon as XCircleIcon,
    ClockIcon,
    AlertCircleIcon
} from './icons';
// Mock icons if missing in icons.tsx
const PlayIcon = ({ size = 24, className = "" }: { size?: number | string, className?: string }) => (<svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>);
const PauseIcon = ({ size = 24, className = "" }: { size?: number | string, className?: string }) => (<svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>);
import * as api from '../services/apiService';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface Job {
    task_id: string;
    status: string;
    date_done: string | null;
    result: string;
    traceback: string | null;
}

export const JobsDashboard: React.FC = () => {
    const { timeZone } = useTimeZone();
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(false);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const fetchJobs = async () => {
        setLoading(true);
        try {
            const data = await api.getJobs();
            setJobs(data);
            setLastUpdated(new Date());
        } catch (error) {
            console.error("Failed to fetch jobs", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchJobs();
        const interval = setInterval(fetchJobs, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, []);

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'SUCCESS': return 'text-green-600 bg-green-100 dark:bg-green-900/30 dark:text-green-400';
            case 'FAILURE': return 'text-red-600 bg-red-100 dark:bg-red-900/30 dark:text-red-400';
            case 'STARTED': return 'text-blue-600 bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400';
            case 'PENDING': return 'text-yellow-600 bg-yellow-100 dark:bg-yellow-900/30 dark:text-yellow-400';
            default: return 'text-gray-600 bg-gray-100 dark:bg-gray-800 dark:text-gray-400';
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'SUCCESS': return <CheckCircleIcon size={16} className="mr-1.5" />;
            case 'FAILURE': return <XCircleIcon size={16} className="mr-1.5" />;
            case 'STARTED': return <PlayIcon size={16} className="mr-1.5" />;
            case 'PENDING': return <ClockIcon size={16} className="mr-1.5" />;
            default: return <AlertCircleIcon size={16} className="mr-1.5" />;
        }
    };

    const [isModalOpen, setIsModalOpen] = useState(false);
    const [newJobType, setNewJobType] = useState('generic_task');
    const [newJobDetails, setNewJobDetails] = useState('{}');

    const handleCreateJob = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const details = JSON.parse(newJobDetails);
            await api.createJob({ type: newJobType, details });
            setIsModalOpen(false);
            setNewJobDetails('{}');
            fetchJobs();
        } catch (error) {
            alert("Failed to create job. Ensure details are valid JSON.");
            console.error(error);
        }
    };

    return (
        <div className="p-6 bg-gray-50 dark:bg-gray-900 min-h-screen">
            <div className="max-w-7xl mx-auto">
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Job Orchestration</h1>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Monitor background agent tasks and system health</p>
                    </div>
                    <div className="flex items-center space-x-4">
                        {lastUpdated && (
                            <span className="text-xs text-gray-500">Updated: {lastUpdated.toLocaleTimeString()}</span>
                        )}
                        <button
                            onClick={() => setIsModalOpen(true)}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors"
                        >
                            + Create Job
                        </button>
                        <button
                            onClick={fetchJobs}
                            disabled={loading}
                            className="p-2 bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                        >
                            <RefreshCwIcon size={20} className={loading ? 'animate-spin' : ''} />
                        </button>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                            <thead className="bg-gray-50 dark:bg-gray-900/50">
                                <tr>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Task ID</th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Type</th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Completed At</th>
                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Result / Error</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                {jobs.length === 0 ? (
                                    <tr>
                                        <td colSpan={5} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                                            No recent jobs found
                                        </td>
                                    </tr>
                                ) : (
                                    jobs.map((job) => (
                                        <tr key={job.task_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                            <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-500 dark:text-gray-400">
                                                {(job.task_id || (job as any).id || "unknown").substring(0, 13)}...
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                                {/* @ts-ignore */}
                                                {job.type || 'generic_task'}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(job.status)}`}>
                                                    {getStatusIcon(job.status)}
                                                    {job.status}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                                {job.date_done ? new Date(job.date_done).toLocaleString(undefined, { timeZone }) : '-'}
                                            </td>
                                            <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-xs truncate">
                                                {job.traceback ? (
                                                    <span className="text-red-500 font-mono text-xs" title={job.traceback}>Exception: {job.traceback.substring(0, 50)}...</span>
                                                ) : (
                                                    <span title={job.result}>{job.result && job.result.length > 50 ? job.result.substring(0, 50) + '...' : job.result}</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {/* Create Job Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6">
                        <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">Create New Job</h2>
                        <form onSubmit={handleCreateJob}>
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Job Type</label>
                                <select
                                    value={newJobType}
                                    onChange={(e) => setNewJobType(e.target.value)}
                                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                >
                                    <option value="generic_task">Generic Task</option>
                                    <option value="maintenance">Maintenance</option>
                                    <option value="report_generation">Report Generation</option>
                                    <option value="data_sync">Data Sync</option>
                                </select>
                            </div>
                            <div className="mb-6">
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Details (JSON)</label>
                                <textarea
                                    value={newJobDetails}
                                    onChange={(e) => setNewJobDetails(e.target.value)}
                                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm h-32"
                                    placeholder='{"key": "value"}'
                                />
                            </div>
                            <div className="flex justify-end space-x-3">
                                <button
                                    type="button"
                                    onClick={() => setIsModalOpen(false)}
                                    className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                                >
                                    Create Job
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
