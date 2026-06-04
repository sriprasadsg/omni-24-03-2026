import React from 'react';

export interface OsAssetPatch {
    agent_id: string;
    hostname: string;
    os: string;
    os_version: string;
    status: string;
    pending_count: number;
    last_checked: string;
    pending_updates: string[];
}

interface Props {
    osPatches: OsAssetPatch[];
    osPatchesMeta: { total_pending_os_patches: number; scanned_at: string } | null;
    osPatchesLoading: boolean;
    deployingAssetPatches: Set<string>;
    onRefresh: () => void;
    onApplyOsPatches: (agentId: string, patches: string[]) => void;
}

export function OsPatchesTab({ osPatches, osPatchesMeta, osPatchesLoading, deployingAssetPatches, onRefresh, onApplyOsPatches }: Props) {
    return (
        <div className="space-y-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex justify-between items-center">
                <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        OS-level pending patches across all agents (apt upgradable, winget upgrades, Windows HotFixes).
                    </p>
                    {osPatchesMeta && (
                        <p className="text-xs text-gray-400 mt-1">
                            Total pending: <strong className="text-red-500">{osPatchesMeta.total_pending_os_patches}</strong> · Last checked: {new Date(osPatchesMeta.scanned_at).toLocaleTimeString()}
                        </p>
                    )}
                </div>
                <button onClick={onRefresh} disabled={osPatchesLoading}
                    className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 rounded-lg hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300">
                    ↻ Refresh
                </button>
            </div>

            {osPatchesLoading ? (
                <div className="flex justify-center items-center py-16 text-gray-400">
                    <span className="animate-spin inline-block w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full mr-3" />
                    Loading OS patch data from agents...
                </div>
            ) : osPatches.length === 0 ? (
                <div className="text-center py-16 text-gray-400 dark:text-gray-500">
                    <p className="text-4xl mb-3">🖥️</p>
                    <p>No OS patch data available. Deploy agents to collect live data.</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {osPatches.map(asset => (
                        <div key={asset.agent_id} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                            <div className="flex justify-between items-start">
                                <div>
                                    <p className="font-semibold text-gray-900 dark:text-gray-100">{asset.hostname}</p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">{asset.os} · {asset.os_version}</p>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className={`px-2 py-1 rounded-full text-xs font-semibold ${asset.pending_count > 0 ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' : 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'}`}>
                                        {asset.pending_count > 0 ? `${asset.pending_count} pending` : 'Up to date'}
                                    </span>
                                    <span className={`px-2 py-1 rounded-full text-xs ${asset.status === 'online' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                                        {asset.status}
                                    </span>
                                    {asset.pending_count > 0 && asset.status === 'online' && (
                                        <button onClick={() => onApplyOsPatches(asset.agent_id, asset.pending_updates)}
                                            disabled={deployingAssetPatches.has(asset.agent_id)}
                                            className="ml-2 px-3 py-1 text-xs font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:bg-gray-400 transition-colors">
                                            {deployingAssetPatches.has(asset.agent_id) ? (
                                                <><span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full mr-1" />Deploying</>
                                            ) : '🚀 Deploy All'}
                                        </button>
                                    )}
                                </div>
                            </div>
                            {asset.pending_updates && asset.pending_updates.length > 0 && (
                                <div className="mt-3 flex flex-wrap gap-2">
                                    {asset.pending_updates.slice(0, 15).map((patch, i) => (
                                        <span key={i} className="px-2 py-0.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded text-xs font-mono text-amber-700 dark:text-amber-300">
                                            {patch}
                                        </span>
                                    ))}
                                    {asset.pending_updates.length > 15 && (
                                        <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs text-gray-500">
                                            +{asset.pending_updates.length - 15} more
                                        </span>
                                    )}
                                </div>
                            )}
                            {asset.last_checked && (
                                <p className="text-xs text-gray-400 mt-2">Last checked: {new Date(asset.last_checked).toLocaleString()}</p>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
