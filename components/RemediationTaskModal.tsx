import React, { useState, useEffect } from 'react';
import { SaveIcon, SparklesIcon, TicketIcon, ExternalLinkIcon } from 'lucide-react';
import { RemediationTask } from '../types';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
import { EscalationHistoryPanel } from './EscalationHistoryPanel';
import { Modal } from './Modal';

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
    const [creatingTicket, setCreatingTicket] = useState(false);
    const [ticketProvider, setTicketProvider] = useState<'jira' | 'servicenow'>('jira');
    const [hasJira, setHasJira] = useState(false);
    const [hasServiceNow, setHasServiceNow] = useState(false);

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

    // Load ticketing provider availability (best-effort, safe default false/false)
    useEffect(() => {
        if (!isOpen) return;
        (async () => {
            const config = await api.getTicketingConfig();
            setHasJira(!!config?.jira_url);
            setHasServiceNow(!!config?.snow_instance);
        })();
    }, [isOpen]);

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
            showToast('AI suggestion unavailable — please try again', 'error');
        } finally {
            setSuggesting(false);
        }
    };

    const handleCreateTicket = async (provider: 'jira' | 'servicenow') => {
        if (!task?.id) return;
        setCreatingTicket(true);
        try {
            await api.createTicketForRemediationTask(task.id, provider);
            showToast('Ticket created.', 'success');
            onRefresh();
        } catch (e) {
            console.error('Ticket creation failed:', e);
            showToast('Failed to create ticket — please try again.', 'error');
        } finally {
            setCreatingTicket(false);
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
                    assignee_type: assigneeType,
                    due_date: dueDate || undefined,
                    description: description || undefined,
                    priority,
                });
            }
            onClose();
            onRefresh();
        } catch (e) {
            console.error('Failed to save remediation task:', e);
            showToast('Failed to save — please try again', 'error');
        } finally {
            setSaving(false);
        }
    };

    const footer = (
        <>
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
        </>
    );

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={task ? 'Edit Remediation Task' : 'Create Remediation Task'}
            size="lg"
            footer={footer}
        >
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

                        {/* Ticketing */}
                        {task?.ticket_ref ? (
                            <div>
                                <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                    Ticket
                                </label>
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span
                                        className={`px-2 py-0.5 text-xs font-semibold rounded-full ${task.ticket_provider === 'jira'
                                            ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                                            : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                            }`}
                                    >
                                        {task.ticket_provider === 'jira' ? 'Jira' : 'ServiceNow'}
                                    </span>
                                    <span className="text-xs text-gray-700 dark:text-gray-300">{task.ticket_ref}</span>
                                    {task.ticket_url && (
                                        <a
                                            href={task.ticket_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400 hover:underline"
                                        >
                                            {task.ticket_provider === 'jira' ? 'View in Jira' : 'View in ServiceNow'}
                                            <ExternalLinkIcon size={12} />
                                        </a>
                                    )}
                                </div>
                            </div>
                        ) : (
                            task?.id && (hasJira || hasServiceNow) && (
                                <div>
                                    <label className="block text-sm font-medium dark:text-gray-300 mb-1">
                                        Ticketing
                                    </label>
                                    {hasJira && hasServiceNow && (
                                        <div className="mb-2">
                                            <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                                                Choose a provider
                                            </span>
                                            <div className="grid grid-cols-2 gap-2">
                                                {(['jira', 'servicenow'] as const).map(p => (
                                                    <label
                                                        key={p}
                                                        className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer text-sm transition-colors focus-within:ring-2 focus-within:ring-indigo-500 focus-within:ring-offset-1 dark:focus-within:ring-offset-gray-800 ${ticketProvider === p
                                                            ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-900/20'
                                                            : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'
                                                            }`}
                                                    >
                                                        <input
                                                            type="radio"
                                                            name="ticketProvider"
                                                            value={p}
                                                            checked={ticketProvider === p}
                                                            onChange={() => setTicketProvider(p)}
                                                            className="sr-only"
                                                        />
                                                        <span className="text-gray-800 dark:text-gray-100 text-sm font-medium leading-tight">
                                                            {p === 'jira' ? 'Jira' : 'ServiceNow'}
                                                        </span>
                                                    </label>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    <button
                                        onClick={() => handleCreateTicket(hasJira && hasServiceNow ? ticketProvider : (hasJira ? 'jira' : 'servicenow'))}
                                        disabled={creatingTicket}
                                        className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded flex items-center gap-2 text-sm"
                                    >
                                        {creatingTicket ? (
                                            <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        ) : (
                                            <TicketIcon size={14} />
                                        )}
                                        {creatingTicket ? 'Creating...' : 'Create Ticket'}
                                    </button>
                                </div>
                            )
                        )}
                    </div>

                    {/* Escalation History (SLA-02) — read-only, append-only, no edit/delete controls */}
                    {task?.id && <EscalationHistoryPanel taskId={task.id} />}
        </Modal>
    );
};
