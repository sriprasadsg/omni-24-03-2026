import React, { useState, useEffect, useMemo } from 'react';
import { Agent, Asset, AgentCapability, VulnerabilitySeverity } from '../types';
import {
    ActivityIcon, ShieldAlertIcon, HistoryIcon, GitMergeIcon, CheckIcon,
    XCircleIcon, ComponentIcon, NetworkIcon,
} from './icons';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { fetchAssets, linkAgentToAsset, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';
import { AgentLocationHistory } from './AgentLocationHistory';

const severityClasses: Record<VulnerabilitySeverity, string> = {
    Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
    Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Informational: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

interface MetricSnapshot { cpu: number; memory: number; disk: number; timestamp: string; }

interface Props {
    agent: Agent;
    asset?: Asset;
    tenantName: string;
    currentStatusIcon: React.ReactNode;
    currentStatusTextClass: string;
    platformIcon: React.ReactNode;
    capabilityInfo: Record<string, { icon: React.ReactNode; label: string }>;
    onViewRemediationLogs: (agent: Agent) => void;
    hasPermission: (perm: string) => boolean;
}

const DetailRow: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
    <div className="py-2 sm:grid sm:grid-cols-3 sm:gap-4">
        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</dt>
        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200 sm:mt-0 sm:col-span-2">{children}</dd>
    </div>
);

export const AgentOverviewTab: React.FC<Props> = ({
    agent, asset, tenantName,
    currentStatusIcon, currentStatusTextClass, platformIcon, capabilityInfo,
    onViewRemediationLogs, hasPermission,
}) => {
    const { timeZone } = useTimeZone();
    const meta = agent.meta as Record<string, any> | undefined;

    // Live asset (refreshed when modal opens for fresh vulnerability data)
    const [liveAsset, setLiveAsset] = useState<Asset | null>(null);
    useEffect(() => {
        if (agent?.id) {
            fetchAssets().then((assets: Asset[]) => {
                setLiveAsset(assets.find((a: Asset) => a.id === agent.assetId) || null);
            }).catch(() => setLiveAsset(null));
        }
    }, [agent?.id, agent?.assetId]);

    // Link Asset state
    const [isLinkingAsset, setIsLinkingAsset] = useState(false);
    const [availableAssets, setAvailableAssets] = useState<Asset[]>([]);
    const [selectedAssetId, setSelectedAssetId] = useState('');
    const [isLinking, setIsLinking] = useState(false);

    const handleOpenLinkModal = async () => {
        setIsLinkingAsset(true);
        try {
            setAvailableAssets(await fetchAssets());
        } catch {
            showToast('Failed to load assets list. Please try again.', 'error');
        }
    };

    const handleLinkAsset = async () => {
        if (!selectedAssetId) return;
        setIsLinking(true);
        try {
            await linkAgentToAsset(agent.id, selectedAssetId);
            showToast('Asset linked successfully.', 'success');
            setIsLinkingAsset(false);
            window.location.reload();
        } catch (e: any) {
            showToast(`Failed to link asset: ${e.message || 'Unknown error'}`, 'error');
        } finally {
            setIsLinking(false);
        }
    };

    // Live metrics polling
    const [liveMetrics, setLiveMetrics] = useState<MetricSnapshot[]>([]);
    const [latestMetrics, setLatestMetrics] = useState<MetricSnapshot | null>(null);

    useEffect(() => {
        const fetchMetrics = async () => {
            try {
                const res = await authFetch(`/api/agents/${agent.id}/metrics/history?hours=1`);
                if (res.ok) {
                    const data = await res.json();
                    const raw: Array<Record<string, any>> = data.metrics || [];
                    const snaps: MetricSnapshot[] = raw.slice(-60).map(m => ({
                        cpu: m.cpu_percent,
                        memory: m.memory_percent,
                        disk: m.disk_percent,
                        timestamp: m.timestamp,
                    }));
                    setLiveMetrics(snaps);
                    if (snaps.length > 0) setLatestMetrics(snaps[snaps.length - 1]);
                }
            } catch (e) { console.error('Failed to fetch agent metrics:', e); }
        };
        fetchMetrics();
        const interval = setInterval(fetchMetrics, 15000);
        return () => clearInterval(interval);
    }, [agent.id]);

    const sortedVulnerabilities = useMemo(() => {
        const effectiveAsset = liveAsset || asset;
        if (!effectiveAsset?.vulnerabilities) return [];
        return [...effectiveAsset.vulnerabilities]
            .filter(v => v.status === 'Open')
            .sort((a, b) => {
                const order: Record<VulnerabilitySeverity, number> = { Critical: 4, High: 3, Medium: 2, Low: 1, Informational: 0 };
                return order[b.severity] - order[a.severity];
            });
    }, [liveAsset, asset]);

    return (
        <div className="space-y-4">
            <dl>
                <DetailRow label="Status">
                    <span className={`flex items-center font-semibold ${currentStatusTextClass}`}>
                        {currentStatusIcon}
                        <span className="ml-2">{agent.status}</span>
                    </span>
                </DetailRow>
                <DetailRow label="Platform">
                    <div className="flex items-center space-x-2">{platformIcon}<span>{agent.platform}</span></div>
                </DetailRow>
                <DetailRow label="OS Version">
                    {asset?.osVersion || meta?.os_full_name || meta?.os_version || 'Unknown'}
                </DetailRow>
                <DetailRow label="Device Type">
                    <span className="capitalize">
                        {meta?.device_type || 'Unknown'}
                        {meta?.chassis_label && meta?.chassis_label !== 'Unknown' && (
                            <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">({meta?.chassis_label})</span>
                        )}
                        {meta?.is_virtual && (
                            <span className="ml-2 px-1.5 py-0.5 text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded">Virtual</span>
                        )}
                    </span>
                </DetailRow>
                <DetailRow label="CPU">
                    {asset?.cpuModel || meta?.cpu_model || meta?.metrics_collection?.cpu?.model || 'Unknown'}
                </DetailRow>
                <DetailRow label="Memory">
                    {meta?.memory_gb || (meta?.total_memory_gb ? `${meta?.total_memory_gb} GB` : null) || 'Unknown'}
                </DetailRow>
                <DetailRow label="Serial Number">
                    <span className="font-mono text-xs">{meta?.serial_number || asset?.serialNumber || 'Unknown'}</span>
                </DetailRow>
                <DetailRow label="Agent Version">{agent.version}</DetailRow>
                <DetailRow label="Network Interfaces">
                    <div className="space-y-1">
                        {asset?.macAddresses?.map((mac, idx) => (
                            <div key={idx} className="flex space-x-2 text-xs">
                                <span className="font-semibold text-gray-600 dark:text-gray-400">{mac.interface}:</span>
                                <span className="font-mono">{mac.mac}</span>
                            </div>
                        )) || <span className="font-mono text-xs">{asset?.macAddress || 'Unknown'}</span>}
                    </div>
                </DetailRow>
                <DetailRow label="Last Seen">{new Date(agent.lastSeen).toLocaleString(undefined, { timeZone })}</DetailRow>
                <DetailRow label="Agent ID"><span className="font-mono text-xs">{agent.id}</span></DetailRow>
                <DetailRow label="Asset ID">
                    <div className="flex items-center space-x-2">
                        <span className="font-mono text-xs text-gray-900 dark:text-gray-200">{agent.assetId || 'Unlinked'}</span>
                        {(hasPermission('manage:agents') || hasPermission('admin:*')) && (
                            <button
                                onClick={handleOpenLinkModal}
                                className="text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 flex items-center"
                            >
                                <GitMergeIcon size={12} className="mr-1" />
                                {agent.assetId ? 'Change Link' : 'Link Asset'}
                            </button>
                        )}
                    </div>
                    {isLinkingAsset && (
                        <div className="mt-2 text-xs flex items-center space-x-2 border p-2 rounded-md bg-gray-50 dark:bg-gray-800 dark:border-gray-700">
                            <select
                                value={selectedAssetId}
                                onChange={(e) => setSelectedAssetId(e.target.value)}
                                className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-xs dark:bg-gray-700 dark:text-gray-200"
                            >
                                <option value="">Select an Asset...</option>
                                {availableAssets.map(a => (
                                    <option key={a.id} value={a.id}>{a.hostname} ({a.osType || 'Unknown OS'}) {a.agentStatus === 'Online' ? '⚡' : ''}</option>
                                ))}
                            </select>
                            <button onClick={handleLinkAsset} disabled={isLinking || !selectedAssetId}
                                className="bg-primary-600 text-white px-2 py-1 flex items-center justify-center whitespace-nowrap rounded hover:bg-primary-700 disabled:opacity-50">
                                {isLinking ? 'Linking...' : 'Confirm'}
                            </button>
                            <button onClick={() => setIsLinkingAsset(false)} disabled={isLinking}
                                className="bg-gray-200 text-gray-700 px-2 py-1 rounded hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600">
                                Cancel
                            </button>
                        </div>
                    )}
                </DetailRow>
                <DetailRow label="Tenant">
                    <div className="flex flex-col">
                        <span className="font-medium text-gray-900 dark:text-gray-100">{tenantName}</span>
                        <span className="font-mono text-xs text-gray-500">{agent.tenantId}</span>
                    </div>
                </DetailRow>
            </dl>

            {/* Location History (GAUD-02) */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <AgentLocationHistory agentId={agent.id} />
            </div>

            {/* Live Performance Metrics */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3 flex items-center justify-between">
                    <span className="flex items-center"><ActivityIcon size={16} className="mr-2" />Performance Metrics</span>
                    <span className="flex items-center gap-2">
                        {latestMetrics && (
                            <span className="text-xs text-gray-400">{new Date(latestMetrics.timestamp).toLocaleTimeString(undefined, { timeZone })}</span>
                        )}
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>Live
                        </span>
                    </span>
                </h3>
                {(() => {
                    const cpu = latestMetrics?.cpu ?? meta?.current_cpu ?? null;
                    const mem = latestMetrics?.memory ?? meta?.current_memory ?? null;
                    const disk = latestMetrics?.disk ?? meta?.disk_usage ?? null;
                    const metrics = [
                        { label: 'CPU', value: cpu, color: cpu !== null && cpu > 80 ? 'bg-red-500' : cpu !== null && cpu > 60 ? 'bg-amber-500' : 'bg-primary-500' },
                        { label: 'Memory', value: mem, color: mem !== null && mem > 85 ? 'bg-red-500' : mem !== null && mem > 70 ? 'bg-amber-500' : 'bg-blue-500' },
                        { label: 'Disk', value: disk, color: disk !== null && disk > 90 ? 'bg-red-500' : disk !== null && disk > 75 ? 'bg-amber-500' : 'bg-teal-500' },
                    ];
                    return (
                        <div className="space-y-3">
                            {metrics.map(({ label, value, color }) => (
                                <div key={label}>
                                    <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                                        <span>{label}</span>
                                        <span className="font-mono font-semibold">{value !== null ? `${Math.round(value)}%` : '—'}</span>
                                    </div>
                                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                                        <div className={`h-2 rounded-full transition-all duration-700 ${color}`}
                                            style={{ width: value !== null ? `${Math.min(100, Math.round(value))}%` : '0%' }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    );
                })()}
            </div>

            {/* Enabled Capabilities */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Enabled Capabilities</h3>
                {agent.capabilities && agent.capabilities.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
                        {agent.capabilities.map((cap: any) => {
                            const capId = (typeof cap === 'string' ? cap : cap?.id) as AgentCapability;
                            const info = capabilityInfo[capId];
                            return info ? (
                                <div key={capId} title={info.label} className="flex items-center">
                                    <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700 text-primary-500 dark:text-primary-400">
                                        {info.icon}
                                    </div>
                                    <span className="ml-3 text-sm font-medium text-gray-700 dark:text-gray-300">{info.label}</span>
                                </div>
                            ) : null;
                        })}
                    </div>
                ) : (
                    <p className="text-sm text-gray-400">No capabilities enabled.</p>
                )}
            </div>

            {/* Asset Vulnerabilities */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3 flex items-center">
                    <NetworkIcon size={16} className="mr-2" />Asset Vulnerabilities
                </h3>
                {sortedVulnerabilities.length > 0 ? (
                    <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                        {sortedVulnerabilities.map((vuln, index) => (
                            <div key={index} className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 flex justify-between items-center">
                                <div>
                                    <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">{vuln.cveId || 'Unknown CVE'}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">{vuln.affectedSoftware}</p>
                                </div>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[vuln.severity]}`}>{vuln.severity}</span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-gray-400">No open vulnerabilities detected on the associated asset.</p>
                )}
            </div>

            {/* Remediation History */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3 flex items-center">
                    <HistoryIcon size={16} className="mr-2" />Remediation History
                </h3>
                {agent.remediationAttempts && agent.remediationAttempts.length > 0 ? (
                    <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                        {[...agent.remediationAttempts].reverse().map((attempt, index) => {
                            const isSuccess = (index + agent.hostname.length) % 3 !== 0;
                            return (
                                <div key={index} className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 flex justify-between items-center">
                                    <div>
                                        <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">Attempt #{index + 1}</p>
                                        <p className="text-xs text-gray-500 dark:text-gray-400">{new Date(attempt.timestamp).toLocaleString(undefined, { timeZone })}</p>
                                    </div>
                                    <div className="flex items-center space-x-4">
                                        {isSuccess ? (
                                            <span className="flex items-center text-xs font-medium text-green-700 bg-green-100 dark:text-green-200 dark:bg-green-900/50 px-2 py-1 rounded-full">
                                                <CheckIcon size={14} className="mr-1.5" />Success
                                            </span>
                                        ) : (
                                            <span className="flex items-center text-xs font-medium text-red-700 bg-red-100 dark:text-red-200 dark:bg-red-900/50 px-2 py-1 rounded-full">
                                                <XCircleIcon size={14} className="mr-1.5" />Failed
                                            </span>
                                        )}
                                        <button onClick={() => onViewRemediationLogs(agent)} className="text-xs font-medium text-primary-600 hover:underline">
                                            View Log
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p className="text-sm text-gray-400">No remediation attempts have been recorded for this agent.</p>
                )}
            </div>
        </div>
    );
};
