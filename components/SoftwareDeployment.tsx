import React, { useState, useEffect, useMemo } from 'react';
import {
    ServerIcon, CheckIcon, RocketIcon, DownloadIcon, UploadIcon, SearchIcon, AlertTriangleIcon
} from './icons';
import { fetchAgents } from '../services/apiService';
import { Agent } from '../types';

const API_BASE = 'http://localhost:5000';

export const SoftwareDeployment: React.FC = () => {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(new Set());
    const [packageId, setPackageId] = useState('');
    const [installArgs, setInstallArgs] = useState('');
    const [action, setAction] = useState<'install' | 'upgrade' | 'uninstall'>('install');
    const [isDeploying, setIsDeploying] = useState(false);
    const [deployResult, setDeployResult] = useState<{ success: boolean, message: string } | null>(null);
    const [filter, setFilter] = useState('');
    const [confirmUninstall, setConfirmUninstall] = useState(false);

    const [activeTab, setActiveTab] = useState<'store' | 'repo'>('store');
    const [repoFiles, setRepoFiles] = useState<any[]>([]);

    const [activeTaskIds, setActiveTaskIds] = useState<string[]>([]);
    const [taskStatuses, setTaskStatuses] = useState<Record<string, any>>({});

    // Load Agents & Repo
    useEffect(() => {
        fetchAgents().then(setAgents);
        fetchRepoFiles();
    }, []);

    // Reset confirm when action changes away from uninstall
    useEffect(() => {
        if (action !== 'uninstall') setConfirmUninstall(false);
    }, [action]);

    // Poll Tasks
    useEffect(() => {
        if (activeTaskIds.length === 0) return;

        const interval = setInterval(async () => {
            const updates: Record<string, any> = {};
            let allDone = true;

            for (const taskId of activeTaskIds) {
                try {
                    const res = await fetch(`${API_BASE}/api/tasks/${taskId}`);
                    const data = await res.json();
                    updates[taskId] = data;
                    if (data.status === 'PENDING' || data.status === 'STARTED') {
                        allDone = false;
                    }
                } catch (e) {
                    console.error("Task poll error", e);
                }
            }
            setTaskStatuses(prev => ({ ...prev, ...updates }));

            if (allDone) {
                setActiveTaskIds([]); // Stop polling
            }
        }, 2000);

        return () => clearInterval(interval);
    }, [activeTaskIds]);

    const fetchRepoFiles = async () => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`${API_BASE}/api/repo/packages`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setRepoFiles(data);
            }
        } catch (e) {
            console.error("Failed to load repo", e);
        }
    };

    const filteredAgents = useMemo(() => {
        return agents.filter(a =>
            a.hostname.toLowerCase().includes(filter.toLowerCase()) ||
            a.platform.toLowerCase().includes(filter.toLowerCase())
        );
    }, [agents, filter]);

    const handleSelectAll = () => {
        if (selectedAgentIds.size === filteredAgents.length) {
            setSelectedAgentIds(new Set());
        } else {
            setSelectedAgentIds(new Set(filteredAgents.map(a => a.id)));
        }
    };

    const toggleSelection = (id: string) => {
        const newSet = new Set(selectedAgentIds);
        if (newSet.has(id)) newSet.delete(id);
        else newSet.add(id);
        setSelectedAgentIds(newSet);
    };

    const handleDeploy = async () => {
        if (!packageId || selectedAgentIds.size === 0) return;
        if (action === 'uninstall' && !confirmUninstall) return;

        setIsDeploying(true);
        setDeployResult(null);
        setTaskStatuses({});
        setConfirmUninstall(false);

        try {
            const effectiveAction = activeTab === 'repo' ? 'install_from_repo' : action;
            const payload = {
                agentIds: Array.from(selectedAgentIds),
                packageId,
                action: effectiveAction,
                installArgs: activeTab === 'repo' ? installArgs : undefined
            };

            const res = await fetch(`${API_BASE}/api/software/deploy`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (data.success) {
                setDeployResult({ success: true, message: data.message });
                if (data.taskIds) {
                    setActiveTaskIds(data.taskIds);
                }
            } else {
                setDeployResult({ success: false, message: data.error || 'Deployment failed' });
            }
        } catch (e: any) {
            setDeployResult({ success: false, message: e.toString() });
        } finally {
            setIsDeploying(false);
        }
    };

    const [pkgType, setPkgType] = useState('pip');

    const handleRepoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`${API_BASE}/api/repo/upload?pkg_type=${pkgType}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            if (res.ok) {
                const data = await res.json();
                alert("File uploaded successfully");
                fetchRepoFiles();
                setPackageId(file.name);
                setActiveTab('repo');
            } else {
                const err = await res.json();
                alert(`Upload failed: ${err.detail || 'Error'}`);
            }
        } catch (e) {
            alert("Upload error: " + e);
        }
    };

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                try {
                    const text = event.target?.result as string;
                    if (text.includes('\0') || text.startsWith('MZ')) {
                        alert("Error: Binary/executable files are not supported. Please upload a plain text list of package IDs.");
                        return;
                    }
                    if (text.trim().startsWith('{') || text.trim().startsWith('[')) {
                        const data = JSON.parse(text);
                        if (Array.isArray(data)) {
                            alert("Bulk upload parsed " + data.length + " items (Mock check)");
                        }
                    } else {
                        const lines = text.split('\n').filter(l => l.trim());
                        if (lines.length > 0) {
                            setPackageId(lines[0]);
                            alert(`Loaded ${lines.length} packages from file. Populating first one: ${lines[0]}`);
                        }
                    }
                } catch (err) {
                    alert("Failed to parse file. Please upload a valid text or JSON file.");
                }
            };
            reader.readAsText(file);
        }
    };

    const deployButtonLabel = () => {
        if (isDeploying) return 'Dispatching…';
        if (activeTab === 'repo') return 'Deploy File';
        if (action === 'install') return 'Deploy Software';
        if (action === 'upgrade') return 'Upgrade Software';
        return 'Uninstall from Fleet';
    };

    const isDeployDisabled = isDeploying || !packageId || selectedAgentIds.size === 0
        || (action === 'uninstall' && !confirmUninstall);

    return (
        <div className="h-full flex flex-col space-y-6 p-6">

            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
                        Software Deployment Hub
                    </h1>
                    <p className="text-slate-400">Mass install, update, and uninstall software across your fleet</p>
                </div>
                <div className="flex items-center space-x-3">
                    <label className="btn-secondary cursor-pointer flex items-center space-x-2">
                        <UploadIcon className="w-4 h-4" />
                        <span>Upload Package List</span>
                        <input type="file" className="hidden" accept=".json,.csv,.txt" onChange={handleFileUpload} />
                    </label>
                </div>
            </div>

            <div className="flex space-x-1 bg-slate-800 p-1 rounded-lg w-fit">
                <button
                    onClick={() => { setActiveTab('store'); setConfirmUninstall(false); }}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'store' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}
                >
                    Official Store (Winget)
                </button>
                <button
                    onClick={() => { setActiveTab('repo'); setConfirmUninstall(false); }}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'repo' ? 'bg-purple-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}
                >
                    Custom Repository
                </button>
            </div>

            <div className="grid grid-cols-12 gap-6 h-full min-h-0">

                {/* Left: Configuration */}
                <div className="col-span-4 space-y-6">
                    <div className="glass-panel p-6 space-y-6">
                        <h3 className="text-lg font-semibold flex items-center space-x-2">
                            <RocketIcon className="w-5 h-5 text-purple-400" />
                            <span>Deployment Config</span>
                        </h3>

                        {activeTab === 'store' ? (
                            <>
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Package ID (Winget/Apt)</label>
                                    <input
                                        type="text"
                                        value={packageId}
                                        onChange={(e) => setPackageId(e.target.value)}
                                        placeholder="e.g. Google.Chrome"
                                        className="w-full bg-slate-800/50 border border-slate-700/50 rounded px-4 py-2 focus:outline-none focus:border-blue-500/50 transition-colors"
                                    />
                                    <div className="flex justify-between items-center">
                                        <p className="text-xs text-slate-500">Enter exact ID from repository.</p>
                                        <label className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer flex items-center space-x-1">
                                            <UploadIcon className="w-3 h-3" />
                                            <span>Load List</span>
                                            <input type="file" className="hidden" accept=".json,.csv,.txt" onChange={handleFileUpload} />
                                        </label>
                                    </div>
                                </div>

                                {/* Action Selector */}
                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Action</label>
                                    <div className="flex space-x-4">
                                        <label className="flex items-center space-x-2 cursor-pointer">
                                            <input
                                                type="radio"
                                                name="action"
                                                checked={action === 'install'}
                                                onChange={() => setAction('install')}
                                                className="form-radio text-blue-500"
                                            />
                                            <span>Install</span>
                                        </label>
                                        <label className="flex items-center space-x-2 cursor-pointer">
                                            <input
                                                type="radio"
                                                name="action"
                                                checked={action === 'upgrade'}
                                                onChange={() => setAction('upgrade')}
                                                className="form-radio text-green-500"
                                            />
                                            <span>Upgrade</span>
                                        </label>
                                        <label className="flex items-center space-x-2 cursor-pointer text-red-400">
                                            <input
                                                type="radio"
                                                name="action"
                                                checked={action === 'uninstall'}
                                                onChange={() => setAction('uninstall')}
                                                className="form-radio text-red-500"
                                            />
                                            <span className="font-medium">Uninstall</span>
                                        </label>
                                    </div>
                                </div>

                                {/* Uninstall Confirmation Banner */}
                                {action === 'uninstall' && packageId && selectedAgentIds.size > 0 && (
                                    <div className="p-4 rounded-lg border border-red-500/30 bg-red-500/10 space-y-3">
                                        <div className="flex items-start space-x-2">
                                            <AlertTriangleIcon className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                                            <div className="text-sm text-red-300">
                                                <p className="font-semibold">Confirm Uninstall</p>
                                                <p className="text-red-400/80 mt-1">
                                                    You are about to uninstall <span className="font-mono font-bold text-red-300">"{packageId}"</span> from{' '}
                                                    <span className="font-bold">{selectedAgentIds.size} host{selectedAgentIds.size > 1 ? 's' : ''}</span>.
                                                    This cannot be undone automatically.
                                                </p>
                                            </div>
                                        </div>
                                        <label className="flex items-center space-x-2 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={confirmUninstall}
                                                onChange={(e) => setConfirmUninstall(e.target.checked)}
                                                className="rounded bg-slate-800 border-red-500/50 text-red-500 focus:ring-0"
                                            />
                                            <span className="text-sm text-red-300">I understand — proceed with uninstall</span>
                                        </label>
                                    </div>
                                )}
                            </>
                        ) : (
                            /* REPO TAB CONTENT */
                            <div className="space-y-4">
                                <div className="p-4 border border-dashed border-slate-600 rounded-lg flex flex-col items-center justify-center space-y-2 hover:bg-slate-800/30 transition-colors">
                                    <UploadIcon className="w-8 h-8 text-slate-400" />
                                    <div className="text-center">
                                        <p className="text-sm font-medium text-slate-300">Upload Installer</p>
                                        <p className="text-xs text-slate-500">.exe, .msi, .deb, .rpm</p>
                                    </div>
                                    <input type="file" className="text-xs text-slate-400 file:mr-4 file:py-1 file:px-2 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-blue-500/10 file:text-blue-400 hover:file:bg-blue-500/20" onChange={handleRepoUpload} />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Select File to Deploy</label>
                                    <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                                        {repoFiles.length === 0 && <p className="text-sm text-slate-500 italic">No files in repository.</p>}
                                        {repoFiles.map(f => (
                                            <div
                                                key={f.filename}
                                                onClick={() => setPackageId(f.filename)}
                                                className={`p-3 rounded border cursor-pointer transition-all ${packageId === f.filename
                                                    ? 'bg-purple-500/20 border-purple-500 text-purple-200'
                                                    : 'bg-slate-800/50 border-slate-700 hover:border-slate-500'}`}
                                            >
                                                <div className="flex justify-between items-center">
                                                    <span className="text-sm font-medium truncate">{f.filename}</span>
                                                    <span className="text-xs text-slate-500">{(f.size / 1024 / 1024).toFixed(2)} MB</span>
                                                </div>
                                                <div className="text-xs text-slate-600 mt-1">Uploaded: {new Date(f.upload_date).toLocaleDateString()}</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Install Arguments (Optional)</label>
                                    <input
                                        type="text"
                                        value={installArgs}
                                        onChange={(e) => setInstallArgs(e.target.value)}
                                        placeholder="e.g. /S /silent /quiet"
                                        className="w-full bg-slate-800/50 border border-slate-700/50 rounded px-4 py-2 focus:outline-none focus:border-blue-500/50 transition-colors font-mono text-sm"
                                    />
                                    <p className="text-xs text-slate-500">Provide custom flags for silent installation if defaults fail.</p>
                                </div>
                            </div>
                        )}

                        <div className="pt-4 border-t border-slate-700/50">
                            <div className="flex justify-between items-center mb-2">
                                <span className="text-sm text-slate-400">Selected Agents</span>
                                <span className="font-mono text-lg">{selectedAgentIds.size}</span>
                            </div>
                            <button
                                onClick={handleDeploy}
                                disabled={isDeployDisabled}
                                className={`w-full py-3 rounded font-medium flex justify-center items-center space-x-2 transition-all ${isDeployDisabled
                                    ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
                                    : action === 'uninstall'
                                        ? 'bg-gradient-to-r from-red-700 to-red-600 hover:shadow-lg hover:shadow-red-500/20'
                                        : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:shadow-lg hover:shadow-blue-500/20'
                                    }`}
                            >
                                {isDeploying ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        <span>Dispatching...</span>
                                    </>
                                ) : (
                                    <>
                                        <RocketIcon className="w-4 h-4" />
                                        <span>{deployButtonLabel()}</span>
                                    </>
                                )}
                            </button>
                        </div>

                        {/* Task Status */}
                        {Object.keys(taskStatuses).length > 0 && (
                            <div className="mt-4 space-y-2">
                                <h4 className="text-sm font-semibold text-slate-300">Deployment Progress</h4>
                                <div className="space-y-2 max-h-40 overflow-y-auto pr-1 text-xs">
                                    {Object.values(taskStatuses).map((task: any) => (
                                        <div key={task.task_id} className="bg-slate-800/50 p-2 rounded border border-slate-700">
                                            <div className="flex justify-between items-center mb-1">
                                                <span className="font-mono text-slate-400">{task.task_id.substring(0, 8)}...</span>
                                                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${task.status === 'SUCCESS' ? 'bg-green-500/20 text-green-400' :
                                                    task.status === 'FAILURE' ? 'bg-red-500/20 text-red-400' :
                                                        'bg-blue-500/20 text-blue-400'
                                                    }`}>
                                                    {task.status}
                                                </span>
                                            </div>
                                            {task.result && (
                                                <div className="text-slate-300 break-words">
                                                    {typeof task.result === 'string' ? task.result :
                                                        task.result.message ? task.result.message : JSON.stringify(task.result)}
                                                </div>
                                            )}
                                            {task.error && <div className="text-red-400">{task.error}</div>}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {deployResult && (
                            <div className={`p-4 rounded text-sm border ${deployResult.success
                                ? 'bg-green-500/10 border-green-500/20 text-green-400'
                                : 'bg-red-500/10 border-red-500/20 text-red-400'
                                }`}>
                                {deployResult.message}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Agent Selector */}
                <div className="col-span-8 flex flex-col min-h-0">
                    <div className="glass-panel flex-1 flex flex-col min-h-0 overflow-hidden">
                        <div className="p-4 border-b border-slate-700/50 flex items-center justify-between">
                            <div className="relative w-64">
                                <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 w-4 h-4" />
                                <input
                                    type="text"
                                    placeholder="Filter agents..."
                                    value={filter}
                                    onChange={(e) => setFilter(e.target.value)}
                                    className="w-full bg-slate-900 border border-slate-700/50 rounded pl-9 pr-4 py-1.5 focus:outline-none focus:border-blue-500/50"
                                />
                            </div>
                            <div className="text-sm text-slate-400">
                                Showing {filteredAgents.length} agents
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-slate-900/50 sticky top-0 z-10 backdrop-blur-md">
                                    <tr>
                                        <th className="p-4 w-12 text-center">
                                            <input
                                                type="checkbox"
                                                checked={filteredAgents.length > 0 && selectedAgentIds.size === filteredAgents.length}
                                                onChange={handleSelectAll}
                                                className="rounded bg-slate-800 border-slate-600 text-blue-500 focus:ring-0"
                                            />
                                        </th>
                                        <th className="p-4 font-medium text-slate-400">Hostname</th>
                                        <th className="p-4 font-medium text-slate-400">Platform</th>
                                        <th className="p-4 font-medium text-slate-400">Status</th>
                                        <th className="p-4 font-medium text-slate-400">IP Address</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-700/50">
                                    {filteredAgents.map(agent => (
                                        <tr
                                            key={agent.id}
                                            className={`hover:bg-slate-800/30 transition-colors cursor-pointer ${selectedAgentIds.has(agent.id) ? 'bg-blue-500/5' : ''}`}
                                            onClick={() => toggleSelection(agent.id)}
                                        >
                                            <td className="p-4 text-center" onClick={(e) => e.stopPropagation()}>
                                                <input
                                                    type="checkbox"
                                                    checked={selectedAgentIds.has(agent.id)}
                                                    onChange={() => toggleSelection(agent.id)}
                                                    className="rounded bg-slate-800 border-slate-600 text-blue-500 focus:ring-0"
                                                />
                                            </td>
                                            <td className="p-4 flex items-center space-x-3">
                                                <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center">
                                                    <ServerIcon className="w-4 h-4 text-slate-400" />
                                                </div>
                                                <span className="font-medium text-slate-200">{agent.hostname}</span>
                                            </td>
                                            <td className="p-4 text-slate-300">{agent.platform}</td>
                                            <td className="p-4">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${agent.status === 'Online'
                                                    ? 'bg-green-500/10 text-green-400'
                                                    : 'bg-slate-500/10 text-slate-400'
                                                    }`}>
                                                    {agent.status}
                                                </span>
                                            </td>
                                            <td className="p-4 text-slate-400 font-mono text-sm">{agent.ipAddress}</td>
                                        </tr>
                                    ))}
                                    {filteredAgents.length === 0 && (
                                        <tr>
                                            <td colSpan={5} className="p-8 text-center text-slate-500">
                                                No agents found matching filter.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
