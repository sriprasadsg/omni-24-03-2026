import React, { useState, useEffect, useCallback } from 'react';
import { ShieldAlertIcon, PlusIcon, ActivityIcon } from 'lucide-react';
import { RemediationTask } from '../types';
import * as api from '../services/apiService';
import { socketService } from '../services/socketService';
import { RemediationTaskModal } from './RemediationTaskModal';
import { showToast } from '../utils/toast';

const STATUS_COLORS: Record<string, string> = {
    open:        'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    resolved:    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    dismissed:   'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

const SLA_COLORS: Record<string, string> = {
    ok:       'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    at_risk:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    breached: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    none:     'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

const FILTER_LABELS: { value: string; label: string }[] = [
    { value: 'all',         label: 'All' },
    { value: 'open',        label: 'Open' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'resolved',    label: 'Resolved' },
];

export const RemediationDashboard: React.FC = () => {
    const [tasks, setTasks] = useState<RemediationTask[]>([]);
    const [loading, setLoading] = useState(false);
    const [fetchError, setFetchError] = useState(false);
    const [filterStatus, setFilterStatus] = useState<string>('all');
    const [isCreating, setIsCreating] = useState(false);
    const [editingTask, setEditingTask] = useState<RemediationTask | null>(null);

    const fetchTasks = useCallback(async () => {
        setLoading(true);
        setFetchError(false);
        try {
            const statusParam = filterStatus === 'all' ? undefined : filterStatus;
            const data = await api.getRemediationTasks(statusParam);
            setTasks(data);
        } catch (e) {
            console.error('Failed to fetch remediation tasks:', e);
            setFetchError(true);
            showToast('Failed to load tasks — check your connection and retry', 'error');
        } finally {
            setLoading(false);
        }
    }, [filterStatus]);

    useEffect(() => { fetchTasks(); }, [fetchTasks]);

    // WebSocket: live remediation_update events (REM-04)
    useEffect(() => {
        const onUpdate = (data: any) => {
            setTasks(prev => prev.map(t =>
                t.id === data.task_id ? { ...t, ...data } : t
            ));
        };
        socketService.on('remediation_update', onUpdate);
        return () => socketService.off('remediation_update', onUpdate);
    }, []);

    const handleMarkResolved = async (task: RemediationTask) => {
        if (!window.confirm('Mark this task as resolved? This will be recorded in the audit trail.')) return;
        try {
            await api.updateRemediationTask(task.id, { status: 'resolved' });
            fetchTasks();
        } catch (e) {
            console.error('Failed to resolve task:', e);
            showToast('Failed to update task — please try again', 'error');
        }
    };

    const openCreate = () => {
        setEditingTask(null);
        setIsCreating(true);
    };

    const openEdit = (task: RemediationTask) => {
        setEditingTask(task);
        setIsCreating(false);
    };

    const closeModal = () => {
        setIsCreating(false);
        setEditingTask(null);
    };

    const totalOpen     = tasks.filter(t => t.status === 'open').length;
    const totalProgress = tasks.filter(t => t.status === 'in_progress').length;
    const totalResolved = tasks.filter(t => t.status === 'resolved').length;

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div className="flex justify-between items-start">
                <div>
                    <h1 className="text-2xl font-bold dark:text-white flex items-center gap-2">
                        <ShieldAlertIcon className="text-indigo-600" />
                        Compliance Remediation
                        <span className="flex items-center gap-1 text-xs font-medium text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400 px-2 py-0.5 rounded-full border border-green-200 dark:border-green-800">
                            <ActivityIcon size={11} className="animate-pulse" /> Live
                        </span>
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">
                        Manage compliance remediation tasks — status updates in real time
                    </p>
                </div>
                <button
                    onClick={openCreate}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium"
                >
                    <PlusIcon size={16} /> Create Task
                </button>
            </div>

            {/* Stats bar */}
            <div className="grid grid-cols-3 gap-4">
                {[
                    { label: 'Open',        value: totalOpen,     color: 'text-red-600' },
                    { label: 'In Progress', value: totalProgress, color: 'text-yellow-600' },
                    { label: 'Resolved',    value: totalResolved, color: 'text-green-600' },
                ].map(s => (
                    <div key={s.label} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-center">
                        <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                        <div className="text-xs text-gray-500 mt-1">{s.label}</div>
                    </div>
                ))}
            </div>

            {/* Filter chips (REM-02) */}
            <div className="flex gap-2 flex-wrap">
                {FILTER_LABELS.map(f => (
                    <button
                        key={f.value}
                        onClick={() => setFilterStatus(f.value)}
                        className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors border
                            ${filterStatus === f.value
                                ? 'bg-indigo-600 text-white border-indigo-600'
                                : 'text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
                            }`}
                    >
                        {f.label}
                    </button>
                ))}
            </div>

            {/* Task table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                {loading ? (
                    <div className="p-8 text-center text-gray-400">Loading tasks...</div>
                ) : fetchError ? (
                    <div className="p-10 text-center">
                        <p className="text-red-500 font-medium mb-2">Failed to load tasks</p>
                        <p className="text-gray-500 text-sm mb-4">Check your connection and try again.</p>
                        <button onClick={fetchTasks} className="text-indigo-600 hover:text-indigo-800 text-sm font-medium underline">Retry</button>
                    </div>
                ) : (
                    <table className="w-full text-left text-sm">
                        <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                            <tr>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Task</th>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Control</th>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Assignee</th>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Due Date</th>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Status</th>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">SLA</th>
                                <th className="p-4 font-semibold text-xs text-gray-500 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {tasks.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="p-10 text-center text-gray-400">
                                        No remediation tasks found. Click <strong>Create Task</strong> to add one.
                                    </td>
                                </tr>
                            ) : tasks.map(task => (
                                <tr key={task.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors">
                                    <td className="p-4 max-w-xs">
                                        <div className="font-medium dark:text-white">{task.title}</div>
                                        {task.description && (
                                            <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">{task.description}</div>
                                        )}
                                    </td>
                                    <td className="p-4 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                        {task.control_id || '—'}
                                    </td>
                                    <td className="p-4 text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap">
                                        {task.assignee || '—'}
                                    </td>
                                    <td className="p-4 text-xs text-gray-600 dark:text-gray-300 whitespace-nowrap">
                                        {task.due_date || '—'}
                                    </td>
                                    <td className="p-4 whitespace-nowrap">
                                        <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${STATUS_COLORS[task.status] ?? STATUS_COLORS.open}`}>
                                            {task.status.replace('_', ' ')}
                                        </span>
                                    </td>
                                    <td className="p-4 whitespace-nowrap">
                                        <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${SLA_COLORS[task.sla_status ?? 'none'] ?? SLA_COLORS.none}`}>
                                            {(task.sla_status ?? 'none').replace('_', ' ')}
                                        </span>
                                    </td>
                                    <td className="p-4">
                                        <div className="flex items-center gap-3">
                                            <button
                                                onClick={() => openEdit(task)}
                                                className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
                                            >
                                                Edit
                                            </button>
                                            {task.status !== 'resolved' && (
                                                <button
                                                    onClick={() => handleMarkResolved(task)}
                                                    className="text-green-600 hover:text-green-800 text-xs font-medium"
                                                >
                                                    Mark Resolved
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Modal */}
            <RemediationTaskModal
                isOpen={isCreating || !!editingTask}
                task={editingTask}
                onClose={closeModal}
                onRefresh={fetchTasks}
            />
        </div>
    );
};
