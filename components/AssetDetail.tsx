
import React, { useState, useEffect } from 'react';
import { Asset, Patch, Vulnerability, VulnerabilitySeverity, VulnerabilityStatus } from '../types';
// FIX: Replaced non-existent BoxIcon with BotIcon and added BoxIcon to icons.tsx.
import { CpuIcon, MemoryStickIcon, HardDriveIcon, BoxIcon, ShieldAlertIcon, FileShieldIcon, CheckIcon, AlertTriangleIcon, CogIcon, BarChart3Icon, XCircleIcon, TerminalIcon, ShieldLockIcon, UsbIcon } from './icons';
import { ConfirmationModal } from './ConfirmationModal';
import { MetricsChartsTab } from './MetricsChartsTab';
import { RemoteTerminal } from './RemoteTerminal';
import { FimAlertsPanel } from './FimAlertsPanel';
import { RemoteDesktop } from './RemoteDesktop';
import { fetchAgents, linkAssetToAgent, authFetch, fetchAssetById } from '../services/apiService';
import { MonitorIcon } from './icons';
import { showToast } from '../utils/toast';

interface AssetDetailProps {
    asset: Asset;
    patches: Patch[];
    onRunScan: (assetId: string) => Promise<void>;
    onDelete: (asset: Asset) => void;
}

type DetailTab = 'overview' | 'metrics' | 'vulnerabilities' | 'software' | 'patches' | 'integrity' | 'remote' | 'stream';

// Agents report RAM as a raw GB float (e.g. 31.433788). Render it as "31.4 GB"
// while leaving already-formatted or empty values untouched.
const formatRam = (ram: unknown): string => {
    if (ram === null || ram === undefined || ram === '') return '—';
    const n = typeof ram === 'number' ? ram : parseFloat(String(ram));
    if (Number.isNaN(n)) return String(ram);
    return /gb|mb|tb/i.test(String(ram)) ? String(ram) : `${n.toFixed(1)} GB`;
};

const DetailCard: React.FC<{ icon: React.ReactNode; label: string; value: string; }> = ({ icon, label, value }) => (
    <div className="flex items-center gap-3 p-3.5 rounded-xl bg-gray-50 dark:bg-white/[0.03] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
        <span className="grid place-items-center h-9 w-9 flex-shrink-0 rounded-xl text-primary-600 dark:text-primary-400 bg-primary-500/10 ring-1 ring-inset ring-primary-500/20">{icon}</span>
        <div className="min-w-0">
            <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
            <p className="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate" title={value}>{value || '—'}</p>
        </div>
    </div>
);

const vulnerabilitySeverityClasses: Record<VulnerabilitySeverity, string> = {
    Critical: 'text-red-700 dark:text-red-300 bg-red-500/10 ring-1 ring-inset ring-red-500/20',
    High: 'text-orange-700 dark:text-orange-300 bg-orange-500/10 ring-1 ring-inset ring-orange-500/20',
    Medium: 'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-1 ring-inset ring-amber-500/20',
    Low: 'text-blue-700 dark:text-blue-300 bg-blue-500/10 ring-1 ring-inset ring-blue-500/20',
    Informational: 'text-gray-700 dark:text-gray-300 bg-gray-500/10 ring-1 ring-inset ring-gray-500/20',
};

const vulnerabilityStatusClasses: Record<VulnerabilityStatus, string> = {
    Open: 'text-red-700 dark:text-red-300 bg-red-500/10 ring-1 ring-inset ring-red-500/20',
    Patched: 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 ring-1 ring-inset ring-emerald-500/20',
    'Risk Accepted': 'text-gray-700 dark:text-gray-300 bg-gray-500/10 ring-1 ring-inset ring-gray-500/20',
};

export const AssetDetail: React.FC<AssetDetailProps> = ({ asset, patches, onRunScan, onDelete }) => {
    const [activeTab, setActiveTab] = useState<DetailTab>('overview');
    const [isScanning, setIsScanning] = useState(false);
    const [enrichedAsset, setEnrichedAsset] = useState<Asset | null>(null);

    useEffect(() => {
        if (!asset?.id) return;
        fetchAssetById(asset.id).then(data => { if (data) setEnrichedAsset(data); });
    }, [asset?.id]);

    const displayAsset = enrichedAsset || asset;

    const [isTerminalOpen, setIsTerminalOpen] = useState(false);
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

    // Remote actions go to the agent linked to this asset. The asset id
    // ("asset-<host>") used to be sent instead, so no agent ever picked the
    // session up, and the Live Desktop tab never rendered a viewer at all.
    const linkedAgentId: string | undefined = (displayAsset as any).agentId || (asset as any).agentId;

    // Link Agent State
    const [isLinkingAgent, setIsLinkingAgent] = useState(false);
    const [availableAgents, setAvailableAgents] = useState<any[]>([]);
    const [selectedAgentId, setSelectedAgentId] = useState('');
    const [isLinking, setIsLinking] = useState(false);

    const handleOpenLinkModal = async () => {
        setIsLinkingAgent(true);
        try {
            const res = await fetchAgents();
            setAvailableAgents(res);
        } catch (e) {
            console.error("Failed to fetch agents", e);
            showToast("Failed to load agents list.", 'error');
        }
    };

    const handleLinkAgent = async () => {
        if (!selectedAgentId || !asset) return;

        setIsLinking(true);
        try {
            await linkAssetToAgent(asset.id, selectedAgentId);
            showToast("Agent linked successfully.", 'success');
            setIsLinkingAgent(false);
            window.location.reload(); // Reload to refresh data
        } catch (e: any) {
            console.error("Link Agent Error:", e);
            showToast(`Failed to link agent: ${e.message || "Unknown error"}`, 'error');
        } finally {
            setIsLinking(false);
        }
    };

    const applicablePatches = patches.filter(p => p.affectedAssets?.includes(asset.id) && p.status === 'Pending');
    const openVulnerabilities = asset.vulnerabilities?.filter(v => v.status === 'Open').length || 0;

    const detailTabs: { id: DetailTab; label: string; icon: React.ReactNode; count?: number }[] = [
        { id: 'overview', label: 'Overview', icon: <CpuIcon size={15} /> },
        { id: 'metrics', label: 'Metrics', icon: <BarChart3Icon size={15} /> },
        { id: 'vulnerabilities', label: 'Vulnerabilities', icon: <ShieldAlertIcon size={15} />, count: openVulnerabilities },
        { id: 'software', label: 'Software', icon: <BoxIcon size={15} /> },
        { id: 'patches', label: 'Patches', icon: <ShieldAlertIcon size={15} />, count: applicablePatches.length },
        { id: 'integrity', label: 'System Integrity', icon: <FileShieldIcon size={15} /> },
        { id: 'remote', label: 'RDP Config', icon: <ShieldLockIcon size={15} /> },
        { id: 'stream', label: 'Live Desktop', icon: <MonitorIcon size={15} /> },
    ];

    const handleRunScan = async () => {
        setIsScanning(true);
        await onRunScan(asset.id);
        setIsScanning(false);
    };

    const handleRdpAction = async (action: 'enable' | 'disable') => {
        if (!confirm(`${action === 'enable' ? 'Enable' : 'Disable'} Remote Access (RDP) on ${asset.hostname}?\n\nThis will send a command to the agent.`)) {
            return;
        }
        if (!linkedAgentId) {
            showToast('No agent is linked to this asset.', 'error');
            return;
        }
        try {
            const response = await authFetch('/api/agent/deploy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agentIds: [linkedAgentId],
                    action: `${action}_rdp`,
                    packageId: 'rdp-feature'
                })
            });
            const result = await response.json();
            if (response.ok) {
                showToast(`Command sent successfully. Task ID: ${result.task_id}`, 'success');
            } else {
                showToast(`Error: ${result.detail || 'Failed to send command'}`, 'error');
            }
        } catch (error) {
            console.error('Error sending RDP command:', error);
            showToast(`Error: ${error}`, 'error');
        }
    };

    const handleApplyPatch = async (vuln: Vulnerability) => {
        if (!confirm(`Deploy patch for ${vuln.cveId || vuln.id}?\n\nThis will:\n1. Create a patch deployment job\n2. Schedule installation for the next maintenance window\n3. Notify when complete`)) {
            return;
        }

        try {
            const response = await authFetch(`/api/vulnerabilities/${vuln.id}/apply-patch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    assetId: asset.id,
                    cveId: vuln.cveId || vuln.id,
                    affectedSoftware: vuln.affectedSoftware,
                    tenantId: asset.tenantId || 'default'
                })
            });

            const result = await response.json();

            if (result.success) {
                showToast(`Patch job created. Job ID: ${result.job.id}`, 'success');
            } else {
                showToast(`Error: ${result.error || 'Failed to create patch job'}`, 'error');
            }
        } catch (error) {
            console.error('Error applying patch:', error);
            showToast(`Failed to apply patch: ${error}`, 'error');
        }
    }

    return (
        <div className="h-full min-h-0 flex flex-col">
            <div className="px-5 pt-4 pb-3 flex flex-wrap justify-between items-start gap-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                        <h3 className="text-xl font-semibold tracking-[-0.02em] text-gray-900 dark:text-white truncate">{asset.hostname}</h3>
                        {displayAsset.agentStatus && (
                            <span className={`flex-shrink-0 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold ring-1 ring-inset ${displayAsset.agentStatus === 'Online'
                                ? 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 ring-emerald-500/20'
                                : 'text-gray-600 dark:text-gray-300 bg-gray-500/10 ring-gray-500/20'}`}>
                                <span className={`h-1.5 w-1.5 rounded-full ${displayAsset.agentStatus === 'Online' ? 'bg-emerald-500' : 'bg-gray-400'}`} aria-hidden="true" />
                                {displayAsset.agentStatus}
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5 truncate">{asset.id}</p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setIsTerminalOpen(true)}
                        className="flex items-center gap-2 h-9 px-3.5 text-sm font-medium text-gray-700 dark:text-gray-200 rounded-xl bg-gray-100 hover:bg-gray-200/80 dark:bg-white/[0.06] dark:hover:bg-white/10 ring-1 ring-inset ring-gray-200/80 dark:ring-white/[0.08] transition-colors"
                    >
                        <TerminalIcon size={15} className="text-primary-600 dark:text-primary-400" />
                        Remote Access
                    </button>
                    <button
                        onClick={() => setIsDeleteModalOpen(true)}
                        className="flex items-center gap-2 h-9 px-3.5 text-sm font-medium text-red-600 dark:text-red-400 rounded-xl hover:bg-red-500/10 ring-1 ring-inset ring-red-500/25 transition-colors"
                    >
                        <XCircleIcon size={15} />
                        Delete Asset
                    </button>
                </div>
            </div>

            <div className="border-b border-gray-100 dark:border-white/[0.06]">
                <nav className="-mb-px flex gap-5 px-5 overflow-x-auto" aria-label="Tabs">
                    {detailTabs.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            aria-current={activeTab === tab.id ? 'page' : undefined}
                            className={`flex items-center gap-1.5 whitespace-nowrap py-2.5 border-b-2 text-[13px] font-medium transition-colors ${activeTab === tab.id
                                ? 'border-primary-500 text-gray-900 dark:border-primary-400 dark:text-white'
                                : 'border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`}
                        >
                            <span className={activeTab === tab.id ? 'text-primary-600 dark:text-primary-400' : ''}>{tab.icon}</span>
                            {tab.label}
                            {tab.count !== undefined && (
                                <span className={`ml-0.5 px-1.5 py-px rounded-full text-[10px] font-semibold tabular-nums ${activeTab === tab.id ? 'bg-primary-500/15 text-primary-700 dark:text-primary-300' : 'bg-gray-100 text-gray-600 dark:bg-white/[0.06] dark:text-gray-400'}`}>{tab.count}</span>
                            )}
                        </button>
                    ))}
                </nav>
            </div>

            <div className="p-5 flex-1 overflow-y-auto">
                {activeTab === 'overview' && (
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <DetailCard icon={<CpuIcon size={20} />} label="CPU Model" value={displayAsset.cpuModel} />
                            <DetailCard icon={<MemoryStickIcon size={20} />} label="RAM" value={formatRam(displayAsset.ram)} />
                        </div>
                        <div>
                            <h4 className="text-[13px] font-semibold text-gray-900 dark:text-white mb-3">Storage devices</h4>
                            <div className="space-y-3">
                                {(displayAsset.disks || []).map((disk, idx) => (
                                    <div key={`${disk.device || 'disk'}-${idx}`}>
                                        <div className="flex justify-between items-center mb-1 text-sm">
                                            <span className="font-mono text-xs text-gray-800 dark:text-gray-200 flex items-center">
                                                {disk.isRemovable ? <UsbIcon size={14} className="mr-1 text-blue-500" title="Removable Device" /> : <HardDriveIcon size={14} className="mr-1 text-gray-400" />}
                                                {disk.device} ({(disk as any).type || (disk as any).fstype || ''})
                                                {disk.isRemovable && <span className="ml-2 px-1.5 py-0.5 text-[10px] bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded-md font-sans font-medium uppercase tracking-wider">Removable</span>}
                                            </span>
                                            <span className="text-gray-500 dark:text-gray-400 text-xs">
                                                Used: <span className="text-gray-700 dark:text-gray-300 font-medium">{disk.used}</span> / Total: <span className="text-gray-700 dark:text-gray-300 font-medium">{disk.total}</span> (Free: <span className="text-green-600 dark:text-green-400 font-medium">{disk.free}</span>)
                                            </span>
                                        </div>
                                        <div className="w-full bg-gray-200 dark:bg-white/10 rounded-full h-1.5 mb-3 overflow-hidden">
                                            <div
                                                className={`h-1.5 rounded-full transition-all duration-500 ${disk.usedPercent > 90 ? 'bg-red-500' : disk.usedPercent > 75 ? 'bg-amber-500' : 'bg-primary-500'}`}
                                                style={{ width: `${disk.usedPercent}%` }}
                                            ></div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <table className="w-full text-sm text-left">
                            <tbody>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">OS</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">
                                        {(displayAsset as any).osFullName || displayAsset.osEdition
                                            ? `${(displayAsset as any).osFullName || displayAsset.osEdition}`
                                            : displayAsset.osName || '—'}
                                    </td>
                                </tr>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">Version</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">
                                        {displayAsset.osDisplayVersion || displayAsset.osVersion || '—'}
                                    </td>
                                </tr>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">OS Build</td>
                                    <td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">
                                        {displayAsset.osBuild || displayAsset.kernel || '—'}
                                    </td>
                                </tr>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">Installed on</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">{displayAsset.osInstalledOn || '—'}</td>
                                </tr>
                                {displayAsset.osExperience && (
                                    <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                        <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">Experience</td>
                                        <td className="py-2 text-gray-800 dark:text-gray-200">{displayAsset.osExperience}</td>
                                    </tr>
                                )}
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">Kernel</td>
                                    <td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">
                                        {displayAsset.kernel || displayAsset.osBuild || '—'}
                                    </td>
                                </tr>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">Serial Number</td>
                                    <td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">
                                        {displayAsset.serialNumber && displayAsset.serialNumber !== 'Not Available' ? displayAsset.serialNumber : '—'}
                                    </td>
                                </tr>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">MAC Address</td>
                                    <td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">
                                        {displayAsset.macAddress && displayAsset.macAddress !== '00:00:00:00:00:00' ? displayAsset.macAddress : '—'}
                                    </td>
                                </tr>
                                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">IP Address</td>
                                    <td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">{displayAsset.ipAddress || '—'}</td>
                                </tr>
                                <tr><td className="py-2 pr-4 w-36 text-gray-500 dark:text-gray-400">Last Scanned</td><td className="py-2 text-gray-800 dark:text-gray-200">{new Date(displayAsset.lastScanned).toLocaleString()}</td></tr>
                                <tr className="border-t border-gray-100 dark:border-white/[0.06]">
                                    <td className="py-3 pr-2 font-medium text-gray-700 dark:text-gray-300">Linked Agent</td>
                                    <td className="py-3">
                                        <div className="flex flex-col space-y-2">
                                            <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                                                {displayAsset.agentStatus ? (
                                                    <>
                                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${displayAsset.agentStatus === 'Online' ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'}`}>
                                                            {displayAsset.agentStatus}
                                                        </span>
                                                        {(displayAsset as any).agentId && (
                                                            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">{(displayAsset as any).agentId}</span>
                                                        )}
                                                        {displayAsset.agentVersion && (
                                                            <span className="text-xs text-gray-400">v{displayAsset.agentVersion}</span>
                                                        )}
                                                    </>
                                                ) : (
                                                    <span className="text-sm text-gray-500 dark:text-gray-400">No Agent Linked</span>
                                                )}
                                                <button
                                                    onClick={handleOpenLinkModal}
                                                    className="text-xs px-2 py-1 text-primary-600 bg-primary-50 hover:bg-primary-100 rounded dark:text-primary-400 dark:bg-gray-700 dark:hover:bg-gray-600 font-medium"
                                                >
                                                    {displayAsset.agentStatus ? 'Change Link' : 'Link Agent'}
                                                </button>
                                            </div>
                                            {isLinkingAgent && (
                                                <div className="text-xs flex flex-col sm:flex-row items-start sm:items-center space-y-2 sm:space-y-0 sm:space-x-2 border p-3 rounded-md bg-gray-50 dark:bg-gray-800 dark:border-gray-600 w-full">
                                                    <select
                                                        value={selectedAgentId}
                                                        onChange={(e) => setSelectedAgentId(e.target.value)}
                                                        className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-xs dark:bg-gray-700 dark:text-gray-200"
                                                    >
                                                        <option value="">Select an Agent...</option>
                                                        {availableAgents.map(a => (
                                                            <option key={a.id} value={a.id}>{a.id} ({a.platform || 'Unknown OS'}) {a.status === 'Online' ? '✅' : '❌'}</option>
                                                        ))}
                                                    </select>
                                                    <div className="flex space-x-2">
                                                        <button
                                                            onClick={handleLinkAgent}
                                                            disabled={isLinking || !selectedAgentId}
                                                            className="bg-primary-600 text-white px-3 py-1.5 whitespace-nowrap rounded font-medium hover:bg-primary-700 disabled:opacity-50"
                                                        >
                                                            {isLinking ? 'Linking...' : 'Confirm'}
                                                        </button>
                                                        <button
                                                            onClick={() => setIsLinkingAgent(false)}
                                                            disabled={isLinking}
                                                            className="bg-gray-200 text-gray-700 px-3 py-1.5 whitespace-nowrap rounded font-medium hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                )}
                {activeTab === 'metrics' && (
                    <MetricsChartsTab assetId={asset.id} />
                )}
                {activeTab === 'vulnerabilities' && (
                    <div className="space-y-4">
                        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 p-4 rounded-xl bg-gray-50 dark:bg-white/[0.03] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                            <div>
                                <h4 className="font-semibold text-gray-800 dark:text-white">Vulnerability Scanner</h4>
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Last scanned: {new Date(asset.lastScanned).toLocaleString()}</p>
                            </div>
                            <button onClick={handleRunScan} disabled={isScanning} className="flex items-center justify-center h-9 px-4 text-sm font-semibold text-white bg-primary-600 rounded-xl hover:bg-primary-700 disabled:opacity-60 disabled:cursor-wait transition-colors">
                                {isScanning ? <><CogIcon size={16} className="mr-2 animate-spin" /> Scanning...</> : 'Run Vulnerability Scan'}
                            </button>
                        </div>
                        <div className="max-h-[450px] overflow-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 sticky top-0 z-[1]">
                                    <tr>
                                        <th scope="col" className="px-4 py-3">CVE ID</th>
                                        <th scope="col" className="px-4 py-3">Severity</th>
                                        <th scope="col" className="px-4 py-3">Affected Software</th>
                                        <th scope="col" className="px-4 py-3">Status</th>
                                        <th scope="col" className="px-4 py-3">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {asset.vulnerabilities?.map(vuln => (
                                        <tr key={vuln.id} className="border-b border-gray-100 dark:border-white/[0.06] hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                            <td className="px-4 py-3 font-mono text-xs font-bold text-gray-900 dark:text-white whitespace-nowrap">{vuln.cveId || vuln.id}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full ${vulnerabilitySeverityClasses[vuln.severity] || vulnerabilitySeverityClasses.Informational}`}>{vuln.severity}</span>
                                            </td>
                                            <td className="px-4 py-3 font-mono text-xs">{vuln.affectedSoftware}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-full ${vulnerabilityStatusClasses[vuln.status] || vulnerabilityStatusClasses['Risk Accepted']}`}>{vuln.status}</span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2 whitespace-nowrap">
                                                    <button
                                                        onClick={() => window.open(`https://nvd.nist.gov/vuln/detail/${vuln.cveId || vuln.id}`, '_blank')}
                                                        className="text-blue-600 dark:text-blue-400 hover:underline text-xs"
                                                        title="View CVE Details"
                                                    >
                                                        Details
                                                    </button>
                                                    {vuln.status === 'Open' && (
                                                        <>
                                                            <span className="text-gray-300 dark:text-gray-600">|</span>
                                                            <button
                                                                onClick={() => handleApplyPatch(vuln)}
                                                                className="text-green-600 dark:text-green-400 hover:underline text-xs"
                                                                title="Apply Patch"
                                                            >
                                                                Apply Patch
                                                            </button>
                                                            <span className="text-gray-300 dark:text-gray-600">|</span>
                                                            <button
                                                                onClick={async () => {
                                                                    if (confirm(`Mark ${vuln.cveId || vuln.id} as resolved?\n\nThis will update the status to 'Patched'.`)) {
                                                                        try {
                                                                            const response = await authFetch(`/api/vulnerabilities/${vuln.id}/resolve`, {
                                                                                method: 'POST',
                                                                                headers: { 'Content-Type': 'application/json' },
                                                                                body: JSON.stringify({ status: 'Patched' })
                                                                            });
                                                                            const result = await response.json();
                                                                            if (result.success) {
                                                                                showToast(`Success: ${result.message}`, 'success');
                                                                                // Ideally trigger refresh here, but for now reload
                                                                                window.location.reload();
                                                                            } else {
                                                                                showToast(`Error: ${result.error || 'Failed to resolve'}`, 'error');
                                                                            }
                                                                        } catch (e) {
                                                                            showToast(`Error: ${e}`, 'error');
                                                                        }
                                                                    }
                                                                }}
                                                                className="text-gray-600 dark:text-gray-400 hover:underline text-xs"
                                                                title="Mark as Resolved"
                                                            >
                                                                Mark Resolved
                                                            </button>
                                                        </>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                    {(asset.vulnerabilities?.length || 0) === 0 && (
                                        <tr><td colSpan={5} className="text-center py-4">No vulnerabilities detected on this asset.</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
                {activeTab === 'software' && (
                    <div className="max-h-[450px] overflow-y-auto">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                            <thead className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 sticky top-0 z-[1]">
                                <tr>
                                    <th scope="col" className="px-4 py-3">Package Name</th>
                                    <th scope="col" className="px-4 py-3">Version</th>
                                    <th scope="col" className="px-4 py-3">Install Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(asset.installedSoftware || []).map((pkg, index) => (
                                    <tr key={`${pkg.name}-${pkg.version}-${index}`} className="border-b border-gray-100 dark:border-white/[0.06] hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{pkg.name}</td>
                                        <td className="px-4 py-3">{pkg.version}</td>
                                        <td className="px-4 py-3">{pkg.installDate}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                {activeTab === 'patches' && (
                    <div className="max-h-[450px] overflow-y-auto">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                            <thead className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 sticky top-0 z-[1]">
                                <tr>
                                    <th scope="col" className="px-4 py-3">CVE ID</th>
                                    <th scope="col" className="px-4 py-3">Severity</th>
                                    <th scope="col" className="px-4 py-3">Description</th>
                                    <th scope="col" className="px-4 py-3">Release Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {applicablePatches.map(patch => (
                                    <tr key={patch.id} className="border-b border-gray-100 dark:border-white/[0.06] hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                        <td className="px-4 py-3 font-mono text-xs font-bold text-gray-900 dark:text-white">{patch.cveId}</td>
                                        <td className="px-4 py-3">{patch.severity}</td>
                                        <td className="px-4 py-3">{patch.description}</td>
                                        <td className="px-4 py-3">{patch.releaseDate}</td>
                                    </tr>
                                ))}
                                {applicablePatches.length === 0 && (
                                    <tr><td colSpan={4} className="text-center py-4">No pending patches for this asset.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
                {activeTab === 'integrity' && (
                    <div className="space-y-4">
                        {/* FIM Alerts Panel */}
                        <FimAlertsPanel changes={(asset as any).meta?.fim?.recent_changes} />

                        {/* Existing File Table */}
                        <div className="max-h-[450px] overflow-y-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 sticky top-0 z-[1]">
                                    <tr>
                                        <th scope="col" className="px-4 py-3">File Path</th>
                                        <th scope="col" className="px-4 py-3">Status</th>
                                        <th scope="col" className="px-4 py-3">Last Modified</th>
                                        <th scope="col" className="px-4 py-3">Checksum (SHA256)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(asset.criticalFiles || []).map(file => (
                                        <tr key={file.path} className={`border-b border-gray-100 dark:border-white/[0.06] hover:bg-gray-50 dark:hover:bg-white/[0.03] ${file.status === 'Mismatch' ? 'bg-red-500/[0.06]' : ''}`}>
                                            <td className="px-4 py-3 font-mono text-xs font-medium text-gray-900 dark:text-white">{file.path}</td>
                                            <td className="px-4 py-3">
                                                <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${file.status === 'Matched' ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300'}`}>
                                                    {file.status === 'Matched' ? <CheckIcon size={12} className="mr-1.5" /> : <AlertTriangleIcon size={12} className="mr-1.5" />}
                                                    {file.status}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">{new Date(file.lastModified).toLocaleString()}</td>
                                            <td className="px-4 py-3 font-mono text-xs">{file.checksum}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
                {activeTab === 'stream' && (
                    linkedAgentId ? (
                        <div className="h-[600px] rounded-lg overflow-hidden bg-black">
                            <RemoteDesktop agentId={linkedAgentId} hostname={asset.hostname} />
                        </div>
                    ) : (
                        <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                            <MonitorIcon size={48} className="mx-auto mb-4" />
                            <p>No agent is linked to this asset, so there is no desktop to show.</p>
                        </div>
                    )
                )}
                {activeTab === 'remote' && (
                    <div className="space-y-6">
                        <div className="p-6 rounded-xl text-center bg-gray-50 dark:bg-white/[0.03] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                            <ShieldLockIcon size={48} className="mx-auto text-primary-500 mb-4" />
                            <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Remote Access Management</h4>
                            <p className="text-gray-600 dark:text-gray-300 mb-6 max-w-lg mx-auto">
                                Manage remote connectivity to this asset. Enabling RDP allows direct desktop connections.
                                Ensure the asset is reachable on the network.
                            </p>

                            {(asset.osName || '').includes('Windows') ? (
                                <div className="flex flex-col sm:flex-row justify-center items-center gap-4">
                                    <button
                                        onClick={() => handleRdpAction('enable')}
                                        className="w-full sm:w-auto px-6 py-2.5 text-center text-white bg-green-600 rounded-lg hover:bg-green-700 focus:ring-4 focus:ring-green-300 dark:focus:ring-green-800 font-medium flex items-center justify-center transition-colors"
                                    >
                                        <CheckIcon size={18} className="mr-2" />
                                        Enable RDP Access
                                    </button>

                                    <button
                                        onClick={() => handleRdpAction('disable')}
                                        className="w-full sm:w-auto px-6 py-2.5 text-center text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:ring-4 focus:ring-gray-100 dark:bg-gray-800 dark:text-white dark:border-gray-600 dark:hover:bg-gray-700 font-medium flex items-center justify-center transition-colors"
                                    >
                                        <XCircleIcon size={18} className="mr-2" />
                                        Disable RDP
                                    </button>

                                    <div className="hidden sm:block w-px h-8 bg-gray-300 dark:bg-gray-600 mx-2"></div>

                                    <a
                                        href={`rdp://${asset.ipAddress || asset.hostname}`}
                                        className="w-full sm:w-auto px-6 py-2.5 text-center text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:ring-4 focus:ring-primary-300 dark:focus:ring-primary-800 font-medium flex items-center justify-center transition-colors"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <TerminalIcon size={18} className="mr-2" />
                                        Connect via RDP Client
                                    </a>
                                </div>
                            ) : (
                                <div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded text-yellow-800 dark:text-yellow-200">
                                    <p className="font-semibold">Not Supported</p>
                                    <p className="text-sm">RDP management is currently only available for Windows assets. This asset appears to be running {asset.osName}.</p>
                                </div>
                            )}
                        </div>

                        {(asset.osName || '').includes('Windows') && (
                            <div className="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-md border border-blue-100 dark:border-blue-900/30">
                                <h5 className="font-semibold text-blue-900 dark:text-blue-100 mb-2 flex items-center">
                                    <CogIcon size={16} className="mr-2" /> Technical Details
                                </h5>
                                <ul className="list-disc list-inside text-sm text-blue-800 dark:text-blue-200 space-y-1">
                                    <li>Enabling RDP modifies the registry key <code>fDenyTSConnections</code>.</li>
                                    <li>It also adds a firewall rule to allow inbound RDP traffic on port 3389.</li>
                                    <li>Changes may take up to 30 seconds to apply via the Agent.</li>
                                </ul>
                            </div>
                        )}
                    </div>
                )}

            </div>

            {isTerminalOpen && (
                <RemoteTerminal
                    agent={asset as unknown as import('../types').Agent}
                    onClose={() => setIsTerminalOpen(false)}
                />
            )}

            <ConfirmationModal
                isOpen={isDeleteModalOpen}
                onClose={() => setIsDeleteModalOpen(false)}
                onConfirm={() => onDelete(asset)}
                title="Delete Asset"
                message={`Are you sure you want to delete asset ${asset.hostname}? This action cannot be undone.`}
                confirmText="Delete"
                isDestructive={true}
            />
        </div>
    );
};
