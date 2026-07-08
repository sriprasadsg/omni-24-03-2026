import React, { useState, useEffect } from 'react';
import { SaveIcon, SparklesIcon } from 'lucide-react';
import { RemediationTask } from '../types';
import * as api from '../services/apiService';

interface RemediationTaskModalProps {
    isOpen: boolean;
    onClose: () => void;
    task: RemediationTask | null;
    controlId?: string;
    assetId?: string;
    frameworkId?: string;
    onRefresh: () => void;
}

export const RemediationTaskModal: React.FC<RemediationTaskModalProps> = ({
    isOpen,
    onClose,
    task,
    controlId,
    assetId,
    frameworkId,
    onRefresh,
}) => {
    // CR-04: all hooks must be called unconditionally before any early return
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [assignee, setAssignee] = useState('');
    const [assigneeType, setAssigneeType] = useState<'agent' | 'user'>('user');
    const [dueDate, setDueDate] = useState('');
    const [priority, setPriority] = useState('medium');
    const [suggesting, setSuggesting] = useState(false);
    const [saving, setSaving] = useState(false);

    // Initialize from task when editing
    useEffect(() => {
        if (!isOpen) return;
        if (task) {
            setTitle(task.title || '');
            setDescription(task.description || '');
            setAssignee(task.assignee || '');
            setAssigneeType((task.assignee_type as 'agent' | 'user') || 'user');
            setDueDate(task.due_date || '');
            setPriority(task.priority || 'medium');
        } else {
            setTitle('');
            setDescription('');
            setAssignee('');
            setAssigneeType('user');
            setDueDate('');
            setPriority('medium');
        }
    }, [task, isOpen]);

    if (!isOpen) return null;

    const effectiveControlId = task?.control_id || controlId || '';

    const handleSuggest = async () => {
        if (!task?.id) return;
        setSuggesting(true);
        try {
            const result = await api.suggestRemediation(task.id);
            if (result?.suggestion) {
                setDescription(result.suggestion);
            }
        } catch (e) {
            console.error('AI suggestion failed:', e);
        } finally {
            setSuggesting(false);
        }
    };

    const handleSave = async () => {
        if (!title.trim()) return;
        setSaving(true);
        try {
            if (task) {
                await api.updateRemediationTask(task.id, {
                    description,
                    assignee,
                    due_date: dueDate || undefined,
                });
            } else {
                await api.createRemediationTask({
                    title: title.trim(),
                    control_id: effectiveControlId || undefined,
                    asset_id: assetId || undefined,
                    framework_id: frameworkId || undefined,
                    assignee: assignee || undefined,
                    due_date: dueDate || undefined,
                    description: description || undefined,
                    priority,
                });
            }
            onClose();
            onRefresh();
        } catch (e) {
            console.error('Failed to save remediation task:', e);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 w-full max-w-lg">
                <div className="p-6">
                    <h2 className="text-lg font-semibold mb-4 dark:text-white">
                        {task ? 'Edit Remediation Task' : 'Create Remediation Task'}
                    </h2>

                    <div className="space-y-4">
                        {/* Control ID (read-only) */}
                        {effectiveControlId && (
                            <div>
                                <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                    Control ID
                                </label>
                                <input
                                    type="text"
                                    value={effectiveControlId}
                                    readOnly
                                    className="w-full p-2 border rounded bg-gray-50 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-400 text-gray-500 cursor-not-allowed"
                                />
                            </div>
                        )}

                        {/* Title */}
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                Title <span className="text-red-500">*</span>
                            </label>
                            <input
                                type="text"
                                value={title}
                                onChange={e => setTitle(e.target.value)}
                                disabled={!!task}
                                className={`w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white ${task ? 'opacity-70 cursor-not-allowed' : ''}`}
                                placeholder="Remediation task title"
                            />
                        </div>

                        {/* Description with AI suggest */}
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <label className="block text-sm font-medium dark:text-gray-300">
                                    Description
                                </label>
                                <button
                                    onClick={handleSuggest}
                                    disabled={!task?.id || suggesting}
                                    title={!task?.id ? 'Save the task first to get AI suggestions' : 'Suggest remediation steps with AI'}
                                    className={`flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors
                                        ${!task?.id
                                            ? 'text-gray-400 dark:text-gray-600 cursor-not-allowed'
                                            : 'text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/20'
                                        }`}
                                >
                                    {suggesting ? (
                                        <span className="inline-block w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                                    ) : (
                                        <SparklesIcon size={12} />
                                    )}
                                    {suggesting ? 'Suggesting...' : 'Suggest steps'}
                                </button>
                            </div>
                            <textarea
                                value={description}
                                onChange={e => setDescription(e.target.value)}
                                rows={4}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                placeholder="Describe the remediation steps..."
                            />
                        </div>

                        {/* Assignee type */}
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                Assignee Type
                            </label>
                            <select
                                value={assigneeType}
                                onChange={e => setAssigneeType(e.target.value as 'agent' | 'user')}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            >
                                <option value="user">User</option>
                                <option value="agent">Agent</option>
                            </select>
                        </div>

                        {/* Assignee */}
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                Assignee
                            </label>
                            <input
                                type="text"
                                value={assignee}
                                onChange={e => setAssignee(e.target.value)}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                placeholder={assigneeType === 'agent' ? 'Agent ID' : 'User ID or email'}
                            />
                        </div>

                        {/* Due Date */}
                        <div>
                            <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                Due Date
                            </label>
                            <input
                                type="date"
                                value={dueDate}
                                onChange={e => setDueDate(e.target.value)}
                                className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                            />
                        </div>

                        {/* Priority */}
                        {!task && (
                            <div>
                                <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                    Priority
                                </label>
                                <select
                                    value={priority}
                                    onChange={e => setPriority(e.target.value)}
                                    className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                >
                                    <option value="low">Low</option>
                                    <option value="medium">Medium</option>
                                    <option value="high">High</option>
                                    <option value="critical">Critical</option>
                                </select>
                            </div>
                        )}
                    </div>

                    {/* Buttons */}
                    <div className="flex justify-end gap-3 mt-6">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 border rounded text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={!title.trim() || saving}
                            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded flex items-center gap-2 text-sm"
                        >
                            {saving ? (
                                <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            ) : (
                                <SaveIcon size={14} />
                            )}
                            {saving ? 'Saving...' : 'Save Task'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
