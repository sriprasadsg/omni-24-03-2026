import React from 'react';
import { RocketIcon, UploadIcon, AlertTriangleIcon } from './icons';

interface Props {
    activeTab: 'store' | 'repo' | 'history';
    packageId: string;
    action: 'install' | 'upgrade' | 'uninstall';
    installArgs: string;
    confirmUninstall: boolean;
    selectedAgentIds: Set<string>;
    repoFiles: any[];
    isDeploying: boolean;
    isDeployDisabled: boolean;
    taskStatuses: Record<string, any>;
    onPackageIdChange: (v: string) => void;
    onActionChange: (a: 'install' | 'upgrade' | 'uninstall') => void;
    onInstallArgsChange: (v: string) => void;
    onConfirmUninstallChange: (v: boolean) => void;
    onDeploy: () => void;
    onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onRepoUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

function deployButtonLabel(isDeploying: boolean, activeTab: string, action: string): string {
    if (isDeploying) return 'Dispatching…';
    if (activeTab === 'repo') return 'Deploy File';
    if (action === 'install') return 'Deploy Software';
    if (action === 'upgrade') return 'Upgrade Software';
    return 'Uninstall from Fleet';
}

export function SoftwareDeployConfigPanel({
    activeTab, packageId, action, installArgs, confirmUninstall,
    selectedAgentIds, repoFiles, isDeploying, isDeployDisabled, taskStatuses,
    onPackageIdChange, onActionChange, onInstallArgsChange, onConfirmUninstallChange,
    onDeploy, onFileUpload, onRepoUpload
}: Props) {
    const buttonLabel = deployButtonLabel(isDeploying, activeTab, action);

    return (
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
                                onChange={(e) => onPackageIdChange(e.target.value)}
                                placeholder="e.g. Google.Chrome"
                                className="w-full bg-slate-800/50 border border-slate-700/50 rounded px-4 py-2 focus:outline-none focus:border-blue-500/50 transition-colors"
                            />
                            <div className="flex justify-between items-center">
                                <p className="text-xs text-slate-500">Enter exact ID from repository.</p>
                                <label className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer flex items-center space-x-1">
                                    <UploadIcon className="w-3 h-3" />
                                    <span>Load List</span>
                                    <input type="file" className="hidden" accept=".json,.csv,.txt" onChange={onFileUpload} />
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
                                            onChange={() => onActionChange(a)}
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
                                        onChange={(e) => onConfirmUninstallChange(e.target.checked)}
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
                                onChange={onRepoUpload}
                            />
                        </div>

                        <div className="space-y-2">
                            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Select File to Deploy</label>
                            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                                {repoFiles.length === 0 && <p className="text-sm text-slate-500 italic">No files in repository.</p>}
                                {repoFiles.map(f => (
                                    <div
                                        key={f.filename}
                                        onClick={() => onPackageIdChange(f.filename)}
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
                                onChange={(e) => onInstallArgsChange(e.target.value)}
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
                        onClick={onDeploy}
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
                                <span>{buttonLabel}</span>
                            </>
                        )}
                    </button>
                </div>

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
    );
}
