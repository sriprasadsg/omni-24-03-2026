import React, { useState, useEffect, useMemo } from 'react';
import {
    ServerIcon, CheckIcon, RocketIcon, DownloadIcon, UploadIcon, SearchIcon, AlertTriangleIcon
} from './icons';
import { fetchAgents, authFetch } from '../services/apiService';
import { Agent } from '../types';

function elapsedLabel(seconds: number): string {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export const SoftwareDeployment: React.FC = () => {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(new Set());
    const [packageId, setPackageId] = useState('');
    const [installArgs, setInstallArgs] = useState('');
    const [action, setAction] = useState<'install' | 'upgrade' | 'uninstall'>('install');
    const [isDeploying, setIsDeploying] = useState(false);
    const [deployResult, setDeployResult] = useState<{ success: boolean; message: string; taskIds?: string[] } | null>(null);
    const [showDeployModal, setShowDeployModal] = useState(false);
    const [filter, setFilter] = useState('');
    const [confirmUninstall, setConfirmUninstall] = useState(false);
    const [activeTab, setActiveTab] = useState<'store' | 'repo' | 'history'>('store');
    const [repoFiles, setRepoFiles] = useState<any[]>([]);
    const [activeTaskIds, setActiveTaskIds] = useState<string[]>([]);
    const [taskStatuses, setTaskStatuses] = useState<Record<string, any>>({});
    const [deployHistory, setDeployHistory] = useState<any[]>([]);
    const [now, setNow] = useState(Date.now());
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

    // Tick every second for elapsed time display in history
    useEffect(() => {
        const t = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        fetchAgents().then(setAgents);
        fetchRepoFiles();
        fetchDeployHistory();
    }, []);

    useEffect(() => {
        if (action !== 'uninstall') setConfirmUninstall(false);
    }, [action]);

    // Poll individual task statuses for the current dispatch
    useEffect(() => {
        if (activeTaskIds.length === 0) return;
        const interval = setInterval(async () => {
            const updates: Record<string, any> = {};
            let allDone = true;
            for (const taskId of activeTaskIds) {
                try {
                    const res = await authFetch(`/api/tasks/${taskId}`);
                    const data = await res.json();
                    updates[taskId] = data;
                    const s = (data.status || '').toLowerCase();
                    if (s === 'pending' || s === 'sent' || s === 'started') allDone = false;
                } catch (e) { console.error('Task poll error', e); }
            }
            setTaskStatuses(prev => ({ ...prev, ...updates }));
            if (allDone) {
                setActiveTaskIds([]);
                fetchDeployHistory();
            }
        }, 2000);
        return () => clearInterval(interval);
    }, [activeTaskIds]);

    // Poll history while any task is in-flight
    useEffect(() => {
        const hasPending = deployHistory.some(t => {
            const s = (t.status || '').toLowerCase();
            return s === 'pending' || s === 'sent';
        });
        if (!hasPending) return;
        const interval = setInterval(fetchDeployHistory, 4000);
        return () => clearInterval(interval);
    }, [deployHistory]);

    const fetchDeployHistory = async () => {
        try {
            const res = await authFetch('/api/software/tasks');
            if (res.ok) {
                const data = await res.json();
                setDeployHistory(Array.isArray(data) ? data : []);
            }
        } catch (e) { console.error('Failed to load deploy history', e); }
    };

    const fetchRepoFiles = async () => {
        try {
            const res = await authFetch('/api/software/repository');
            if (res.ok) setRepoFiles(await res.json());
        } catch (e) { console.error('Failed to load repo', e); }
    };

    const filteredAgents = useMemo(() =>
        agents.filter(a =>
            a.hostname.toLowerCase().includes(filter.toLowerCase()) ||
            a.platform.toLowerCase().includes(filter.toLowerCase())
        ), [agents, filter]);

    const handleSelectAll = () => {
        if (selectedAgentIds.size === filteredAgents.length) setSelectedAgentIds(new Set());
        else setSelectedAgentIds(new Set(filteredAgents.map(a => a.id)));
    };

    const toggleSelection = (id: string) => {
        const s = new Set(selectedAgentIds);
        s.has(id) ? s.delete(id) : s.add(id);
        setSelectedAgentIds(s);
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
            const res = await authFetch('/api/software/deploy', {
                method: 'POST',
                body: JSON.stringify({
                    agentIds: Array.from(selectedAgentIds),
                    packageId,
                    action: effectiveAction,
                    installArgs: activeTab === 'repo' ? installArgs : undefined
                })
            });
            const data = await res.json();
            if (data.success) {
                setDeployResult({ success: true, message: data.message, taskIds: data.taskIds });
                setShowDeployModal(true);
                if (data.taskIds) setActiveTaskIds(data.taskIds);
                setTimeout(fetchDeployHistory, 800);
            } else {
                setDeployResult({ success: false, message: data.error || 'Deployment failed' });
                setShowDeployModal(true);
            }
        } catch (e: any) {
            setDeployResult({ success: false, message: e.toString() });
        } finally {
            setIsDeploying(false);
        }
    };

    const handleRepoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        try {
            const token = sessionStorage.getItem('token');
            const res = await fetch('/api/software/upload', {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
                body: formData
            });
            if (res.ok) {
                alert('File uploaded successfully');
                fetchRepoFiles();
                setPackageId(file.name);
                setActiveTab('repo');
            } else {
                const err = await res.json();
                alert(`Upload failed: ${err.detail || 'Error'}`);
            }
        } catch (e) { alert('Upload error: ' + e); }
    };

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const text = event.target?.result as string;
                if (text.includes('\0') || text.startsWith('MZ')) {
                    alert('Error: Binary files are not supported. Upload a plain text package list.');
                    return;
                }
                if (text.trim().startsWith('{') || text.trim().startsWith('[')) {
                    const data = JSON.parse(text);
                    if (Array.isArray(data)) alert('Bulk upload parsed ' + data.length + ' items');
                } else {
                    const lines = text.split('\n').filter(l => l.trim());
                    if (lines.length > 0) {
                        setPackageId(lines[0]);
                        alert(`Loaded ${lines.length} packages. Populating first: ${lines[0]}`);
                    }
                }
            } catch { alert('Failed to parse file.'); }
        };
        reader.readAsText(file);
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

    const activePendingCount = deployHistory.filter(t => {
        const s = (t.status || '').toLowerCase();
        return s === 'pending' || s === 'sent';
    }).length;

    const toggleExpand = (id: string) => {
        setExpandedRows(prev => {
            const s = new Set(prev);
            s.has(id) ? s.delete(id) : s.add(id);
            return s;
        });
    };

    // ── History Tab ─────────────────────────────────────────────────────────
    const renderHistoryTab = () => (
        <div className="flex-1 flex flex-col min-h-0 glass-panel overflow-hidden">
            <div className="p-4 border-b border-slate-700/50 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center space-x-3">
                    <span className="text-sm text-slate-400">{deployHistory.length} deployment{deployHistory.length !== 1 ? 's' : ''}</span>
                    {activePendingCount > 0 && (
                        <span className="flex items-center space-x-1.5 text-xs bg-blue-500/15 text-blue-300 px-2.5 py-1 rounded-full border border-blue-500/20">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse inline-block" />
                            <span>{activePendingCount} in progress</span>
                        </span>
                    )}
                </div>
                <button onClick={fetchDeployHistory}
                    className="text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded border border-slate-700 hover:bg-slate-700 transition-colors">
                    ↻ Refresh
                </button>
            </div>

            {deployHistory.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-500">
                    <DownloadIcon className="w-12 h-12 mb-4 opacity-20" />
                    <p className="text-base font-medium">No deployments yet</p>
                    <p className="text-sm mt-1 text-slate-600">Deploy software from the Store or Repository tab to see history here.</p>
                </div>
            ) : (
                <div className="flex-1 overflow-y-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-slate-900/60 sticky top-0 z-10">
                            <tr>
                                <th className="p-3 font-medium text-slate-400 whitespace-nowrap w-40">Time</th>
                                <th className="p-3 font-medium text-slate-400">Package</th>
                                <th className="p-3 font-medium text-slate-400">Agent</th>
                                <th className="p-3 font-medium text-slate-400 w-28">Action</th>
                                <th className="p-3 font-medium text-slate-400 w-32">Status</th>
                                <th className="p-3 font-medium text-slate-400">Details / Reason</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-700/40">
                            {deployHistory.map((task: any) => {
                                const taskId: string = task.id || task._id || String(Math.random());
                                const instruction: string = task.instruction || '';
                                const actionMatch = instruction.match(/^([\w]+(?:_[\w]+)*):/);
                                const actionLabel = actionMatch
                                    ? actionMatch[1].replace(/_/g, ' ')
                                    : instruction.split(':')[0].replace(/_/g, ' ');
                                const packageName = task.payload?.package
                                    || instruction.split(':').slice(1).join(':').trim()
                                    || '—';
                                const st = (task.status || 'pending').toLowerCase();
                                const ageSeconds = task.created_at
                                    ? Math.floor((now - new Date(task.created_at).getTime()) / 1000)
                                    : 0;
                                const isActive = st === 'pending' || st === 'sent';
                                const isStuck = isActive && ageSeconds > 300;
                                const isFailed = st === 'failure' || st === 'error' || st === 'failed';
                                const isSuccess = st === 'success';
                                const isExpanded = expandedRows.has(taskId);

                                // Extract failure reason from result object
                                let failReason = '';
                                if (isFailed) {
                                    const r = task.result;
                                    if (typeof r === 'string') failReason = r;
                                    else if (r?.error) failReason = r.error;
                                    else if (r?.message) failReason = r.message;
                                    else if (r?.stderr) failReason = r.stderr;
                                    else if (r) failReason = JSON.stringify(r, null, 2);
                                    if (!failReason && task.error) failReason = task.error;
                                    if (!failReason) failReason = 'No details returned by agent.';
                                }

                                let successDetail = '';
                                if (isSuccess && task.result) {
                                    const r = task.result;
                                    if (typeof r === 'string') successDetail = r;
                                    else successDetail = r.message || r.output || '';
                                }

                                // Status cell
                                let statusCell: React.ReactNode;
                                if (isActive) {
                                    statusCell = (
                                        <div className={`flex items-center space-x-1.5 ${isStuck ? 'text-orange-400' : 'text-blue-400'}`}>
                                            <div className={`w-3 h-3 border-2 border-current border-t-transparent rounded-full flex-shrink-0 ${isStuck ? '' : 'animate-spin'}`} />
                                            <span className="text-xs font-semibold uppercase tracking-wide">
                                                {isStuck ? 'Stuck' : st}
                                            </span>
                                        </div>
                                    );
                                } else if (isFailed) {
                                    statusCell = <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-red-500/20 text-red-400">Failed</span>;
                                } else if (isSuccess) {
                                    statusCell = <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-green-500/20 text-green-400">Success</span>;
                                } else {
                                    statusCell = <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-slate-500/20 text-slate-400">{task.status || 'pending'}</span>;
                                }

                                // Details cell
                                let detailCell: React.ReactNode;
                                if (isActive) {
                                    detailCell = (
                                        <span className={`text-xs ${isStuck ? 'text-orange-300 font-medium' : 'text-slate-400'}`}>
                                            {isStuck
                                                ? `⚠ No response for ${elapsedLabel(ageSeconds)} — agent may be offline or installer is running`
                                                : `Running for ${elapsedLabel(ageSeconds)}…`}
                                        </span>
                                    );
                                } else if (isFailed) {
                                    const truncated = failReason.length > 100;
                                    detailCell = (
                                        <div className="space-y-0.5">
                                            <span className={`text-xs text-red-300 ${!isExpanded ? 'line-clamp-2' : ''}`}>
                                                {isExpanded ? failReason : failReason.substring(0, 100) + (truncated ? '…' : '')}
                                            </span>
                                            {truncated && (
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); toggleExpand(taskId); }}
                                                    className="text-[10px] text-red-400 hover:text-red-300 underline"
                                                >
                                                    {isExpanded ? 'Show less' : 'Show full error'}
                                                </button>
                                            )}
                                        </div>
                                    );
                                } else if (isSuccess && successDetail) {
                                    detailCell = <span className="text-xs text-green-400/70">{successDetail.substring(0, 100)}</span>;
                                } else {
                                    detailCell = <span className="text-slate-600 text-xs">—</span>;
                                }

                                return (
                                    <React.Fragment key={taskId}>
                                        <tr className={`transition-colors ${isStuck ? 'bg-orange-500/5' : isActive ? 'bg-blue-500/[0.03]' : isFailed ? 'hover:bg-red-500/5' : 'hover:bg-slate-800/30'}`}>
                                            <td className="p-3 text-slate-500 font-mono text-xs whitespace-nowrap">
                                                {task.created_at ? new Date(task.created_at).toLocaleString() : '—'}
                                            </td>
                                            <td className="p-3">
                                                <span className="font-medium text-slate-200 font-mono text-xs break-all">{packageName}</span>
                                            </td>
                                            <td className="p-3 text-slate-300 text-xs font-mono">{task.hostname || task.agent_id || '—'}</td>
                                            <td className="p-3 text-slate-400 text-xs capitalize">{actionLabel}</td>
                                            <td className="p-3">{statusCell}</td>
                                            <td className="p-3">{detailCell}</td>
                                        </tr>

                                        {/* Expanded full failure detail */}
                                        {isExpanded && isFailed && (
                                            <tr className="bg-red-950/30">
                                                <td colSpan={6} className="px-4 pb-4 pt-1">
                                                    <div className="bg-red-900/20 border border-red-500/20 rounded-lg p-4 space-y-2">
                                                        <p className="text-xs font-semibold text-red-400 flex items-center space-x-1">
                                                            <AlertTriangleIcon className="w-3.5 h-3.5" />
                                                            <span>Failure Details</span>
                                                        </p>
                                                        <pre className="text-xs text-red-300/80 whitespace-pre-wrap break-all font-mono leading-relaxed max-h-48 overflow-y-auto">{failReason}</pre>
                                                        {task.result?.exit_code !== undefined && (
                                                            <p className="text-xs text-slate-500">Exit code: <span className="font-mono text-red-400">{task.result.exit_code}</span></p>
                                                        )}
                                                        {task.result?.stdout && (
                                                            <details className="mt-1">
                                                                <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-300">stdout output</summary>
                                                                <pre className="text-xs text-slate-500 whitespace-pre-wrap mt-1 max-h-32 overflow-y-auto">{task.result.stdout}</pre>
                                                            </details>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );

    return (
        <div className="h-full flex flex-col space-y-6 p-6">

            {/* Header */}
            <div className="flex justify-between items-center flex-shrink-0">
                <div>
                    <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
                        Software Deployment Hub
                    </h1>
                    <p className="text-slate-400">Mass install, update, and uninstall software across your fleet</p>
                </div>
                {activeTab !== 'history' && (
                    <label className="btn-secondary cursor-pointer flex items-center space-x-2">
                        <UploadIcon className="w-4 h-4" />
                        <span>Upload Package List</span>
                        <input type="file" className="hidden" accept=".json,.csv,.txt" onChange={handleFileUpload} />
                    </label>
                )}
            </div>

            {/* Tab Bar */}
            <div className="flex space-x-1 bg-slate-800 p-1 rounded-lg w-fit flex-shrink-0">
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
                <button
                    onClick={() => setActiveTab('history')}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-2 ${activeTab === 'history' ? 'bg-slate-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}
                >
                    <span>Deployment History</span>
                    {activePendingCount > 0 && (
                        <span className="bg-blue-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center leading-tight">
                            {activePendingCount}
                        </span>
                    )}
                </button>
            </div>

            {/* Tab Content */}
            {activeTab === 'history' ? renderHistoryTab() : (
                <div className="grid grid-cols-12 gap-6 flex-1 min-h-0">

                    {/* Left: Deploy Config */}
                    <div className="col-span-4 space-y-6 overflow-y-auto">
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

                                    <div className="space-y-2">
                                        <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Action</label>
                                        <div className="flex space-x-4">
                                            {(['install', 'upgrade', 'uninstall'] as const).map(a => (
                                                <label key={a} className={`flex items-center space-x-2 cursor-pointer ${a === 'uninstall' ? 'text-red-400' : ''}`}>
                                                    <input
                                                        type="radio"
                                                        name="action"
                                                        checked={action === a}
                                                        onChange={() => setAction(a)}
                                                        className={`form-radio ${a === 'install' ? 'text-blue-500' : a === 'upgrade' ? 'text-green-500' : 'text-red-500'}`}
                                                    />
                                                    <span className={a === 'uninstall' ? 'font-medium' : ''}>
                                                        {a.charAt(0).toUpperCase() + a.slice(1)}
                                                    </span>
                                                </label>
                                            ))}
                                        </div>
                                    </div>

                                    {action === 'uninstall' && packageId && selectedAgentIds.size > 0 && (
                                        <div className="p-4 rounded-lg border border-red-500/30 bg-red-500/10 space-y-3">
                                            <div className="flex items-start space-x-2">
                                                <AlertTriangleIcon className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                                                <div className="text-sm text-red-300">
                                                    <p className="font-semibold">Confirm Uninstall</p>
                                                    <p className="text-red-400/80 mt-1">
                                                        Uninstall <span className="font-mono font-bold text-red-300">"{packageId}"</span> from{' '}
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
                                <div className="space-y-4">
                                    <div className="p-4 border border-dashed border-slate-600 rounded-lg flex flex-col items-center justify-center space-y-2 hover:bg-slate-800/30 transition-colors">
                                        <UploadIcon className="w-8 h-8 text-slate-400" />
                                        <div className="text-center">
                                            <p className="text-sm font-medium text-slate-300">Upload Installer or Script</p>
                                            <p className="text-xs text-slate-500">.exe .msi .ps1 .bat .cmd — Windows</p>
                                            <p className="text-xs text-slate-500">.sh .deb .rpm .pkg — Linux / macOS</p>
                                            <p className="text-xs text-slate-500">.py .jar — Cross-platform</p>
                                        </div>
                                        <input
                                            type="file"
                                            className="text-xs text-slate-400 file:mr-4 file:py-1 file:px-2 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-blue-500/10 file:text-blue-400 hover:file:bg-blue-500/20"
                                            onChange={handleRepoUpload}
                                        />
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
                                        <p className="text-xs text-slate-500">Custom flags for silent installation.</p>
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
                                            : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:shadow-lg hover:shadow-blue-500/20'}`}
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

                            {/* Current dispatch live status */}
                            {Object.keys(taskStatuses).length > 0 && (
                                <div className="mt-4 space-y-2">
                                    <h4 className="text-sm font-semibold text-slate-300">Current Dispatch</h4>
                                    <div className="space-y-2 max-h-40 overflow-y-auto pr-1 text-xs">
                                        {Object.values(taskStatuses).map((task: any) => {
                                            const s = (task.status || '').toLowerCase();
                                            const isOk = s === 'success';
                                            const isBad = s === 'failure' || s === 'error' || s === 'failed';
                                            return (
                                                <div key={task.task_id} className="bg-slate-800/50 p-2 rounded border border-slate-700">
                                                    <div className="flex justify-between items-center mb-1">
                                                        <span className="font-mono text-slate-400">{(task.task_id || 'unknown').substring(0, 8)}…</span>
                                                        <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${isOk ? 'bg-green-500/20 text-green-400' : isBad ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                                                            {task.status}
                                                        </span>
                                                    </div>
                                                    {task.result && (
                                                        <div className="text-slate-300 break-words">
                                                            {typeof task.result === 'string'
                                                                ? task.result
                                                                : task.result.message || task.result.error || JSON.stringify(task.result)}
                                                        </div>
                                                    )}
                                                    {task.error && <div className="text-red-400">{task.error}</div>}
                                                </div>
                                            );
                                        })}
                                    </div>
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
                                <div className="text-sm text-slate-400">Showing {filteredAgents.length} agents</div>
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
                                                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${agent.status === 'Online' ? 'bg-green-500/10 text-green-400' : 'bg-slate-500/10 text-slate-400'}`}>
                                                        {agent.status}
                                                    </span>
                                                </td>
                                                <td className="p-4 text-slate-400 font-mono text-sm">{agent.ipAddress}</td>
                                            </tr>
                                        ))}
                                        {filteredAgents.length === 0 && (
                                            <tr>
                                                <td colSpan={5} className="p-8 text-center text-slate-500">No agents found matching filter.</td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Deploy Modal */}
            {showDeployModal && deployResult && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className={`bg-slate-900 border rounded-xl p-8 max-w-md w-full max-h-[90vh] overflow-y-auto shadow-2xl ${deployResult.success ? 'border-green-500/50' : 'border-red-500/50'}`}>
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center space-x-3">
                                {deployResult.success ? (
                                    <div className="w-12 h-12 bg-green-500/20 rounded-xl flex items-center justify-center">
                                        <CheckIcon className="w-6 h-6 text-green-400" />
                                    </div>
                                ) : (
                                    <div className="w-12 h-12 bg-red-500/20 rounded-xl flex items-center justify-center">
                                        <AlertTriangleIcon className="w-6 h-6 text-red-400" />
                                    </div>
                                )}
                                <div>
                                    <h3 className="text-xl font-bold text-slate-100">
                                        {deployResult.success ? 'Deployment Dispatched!' : 'Deployment Failed'}
                                    </h3>
                                    <p className="text-slate-400 text-sm">{deployResult.taskIds?.length || 0} Agent(s) Targeted</p>
                                </div>
                            </div>
                            <button onClick={() => setShowDeployModal(false)} className="p-2 hover:bg-slate-800 rounded-lg transition-colors">
                                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                                </svg>
                            </button>
                        </div>
                        <div className="space-y-4 mb-6">
                            <div className="bg-slate-800/50 p-4 rounded-lg">
                                <p className={`font-semibold ${deployResult.success ? 'text-green-400' : 'text-red-400'}`}>{deployResult.message}</p>
                            </div>
                            {deployResult.taskIds && deployResult.taskIds.length > 0 && (
                                <div>
                                    <p className="text-sm text-slate-400 mb-2">Task ID{deployResult.taskIds.length > 1 ? 's' : ''}:</p>
                                    <div className="flex flex-wrap gap-2">
                                        {deployResult.taskIds.map(id => (
                                            <span key={id} className="bg-blue-500/20 text-blue-300 px-3 py-1 rounded-full text-xs font-mono">
                                                {id.substring(0, 8)}…
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                        <div className="flex gap-3 pt-4 border-t border-slate-700">
                            <button
                                onClick={() => setShowDeployModal(false)}
                                className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 px-4 rounded-lg transition-colors font-medium"
                            >
                                Close
                            </button>
                            {deployResult.success && (
                                <button
                                    onClick={() => { setShowDeployModal(false); setActiveTab('history'); }}
                                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg transition-colors font-medium"
                                >
                                    View in History
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
