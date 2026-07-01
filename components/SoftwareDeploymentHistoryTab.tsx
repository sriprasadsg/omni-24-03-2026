import React from 'react';
import { DownloadIcon, AlertTriangleIcon } from './icons';

function elapsedLabel(seconds: number): string {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

interface Props {
    deployHistory: any[];
    activePendingCount: number;
    expandedRows: Set<string>;
    now: number;
    onToggleExpand: (id: string) => void;
    onRefresh: () => void;
}

export function SoftwareDeploymentHistoryTab({
    deployHistory, activePendingCount, expandedRows, now, onToggleExpand, onRefresh
}: Props) {
    return (
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
                <button onClick={onRefresh}
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
                                                    onClick={(e) => { e.stopPropagation(); onToggleExpand(taskId); }}
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
}
