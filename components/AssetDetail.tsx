
import React, { useState } from 'react';
import { Asset, Patch, Vulnerability, VulnerabilitySeverity, VulnerabilityStatus } from '../types';
// FIX: Replaced non-existent BoxIcon with BotIcon and added BoxIcon to icons.tsx.
import { CpuIcon, MemoryStickIcon, HardDriveIcon, BoxIcon, ShieldAlertIcon, FileShieldIcon, CheckIcon, AlertTriangleIcon, CogIcon, BarChart3Icon, XCircleIcon, TerminalIcon, ShieldLockIcon, UsbIcon } from './icons';
import { ConfirmationModal } from './ConfirmationModal';
import { MetricsChartsTab } from './MetricsChartsTab';
import { RemoteTerminal } from './RemoteTerminal';
import { FimAlertsPanel } from './FimAlertsPanel';
import { RemoteDesktop } from './RemoteDesktop';
import { startRemoteSession, fetchAgents, linkAssetToAgent } from '../services/apiService';
import { MonitorIcon } from './icons';

interface AssetDetailProps {
    asset: Asset;
    patches: Patch[];
    onRunScan: (assetId: string) => Promise<void>;
    onDelete: (asset: Asset) => void;
}

type DetailTab = 'overview' | 'metrics' | 'vulnerabilities' | 'software' | 'patches' | 'integrity' | 'remote' | 'stream';

const DetailCard: React.FC<{ icon: React.ReactNode; label: string; value: string; }> = ({ icon, label, value }) => (
    <div className="flex items-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
        <div className="mr-3 text-primary-500">{icon}</div>
        <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
            <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">{value}</p>
        </div>
    </div>
);

const vulnerabilitySeverityClasses: Record<VulnerabilitySeverity, string> = {
    Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
    Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Informational: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

const vulnerabilityStatusClasses: Record<VulnerabilityStatus, string> = {
    Open: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    Patched: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    'Risk Accepted': 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

export const AssetDetail: React.FC<AssetDetailProps> = ({ asset, patches, onRunScan, onDelete }) => {
    const [activeTab, setActiveTab] = useState<DetailTab>('overview');
    const [isScanning, setIsScanning] = useState(false);

    const [isTerminalOpen, setIsTerminalOpen] = useState(false);
    const [desktopSessionId, setDesktopSessionId] = useState<string | null>(null);
    const [isStartingStream, setIsStartingStream] = useState(false);
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

    const handleStartStream = async () => {
        if (desktopSessionId) return;
        setIsStartingStream(true);
        const newSessionId = `desktop-${asset.hostname}-${Date.now()}`;
        try {
            // startRemoteSession(agentId, protocol, type)
            await startRemoteSession(asset.id, 'vnc', 'desktop');
            setDesktopSessionId(newSessionId);
        } catch (e) {
            console.error("Failed to start stream", e);
            alert("Failed to start desktop stream");
        } finally {
            setIsStartingStream(false);
        }
    };

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
            alert("Failed to load agents list.");
        }
    };

    const handleLinkAgent = async () => {
        if (!selectedAgentId || !asset) return;

        setIsLinking(true);
        try {
            await linkAssetToAgent(asset.id, selectedAgentId);
            alert("Agent linked successfully.");
            setIsLinkingAgent(false);
            window.location.reload(); // Reload to refresh data
        } catch (e: any) {
            console.error("Link Agent Error:", e);
            alert(`Failed to link agent: ${e.message || "Unknown error"}`);
        } finally {
            setIsLinking(false);
        }
    };

    const applicablePatches = patches.filter(p => p.affectedAssets?.includes(asset.id) && p.status === 'Pending');
    const openVulnerabilities = asset.vulnerabilities?.filter(v => v.status === 'Open').length || 0;

    const handleRunScan = async () => {
        setIsScanning(true);
        await onRunScan(asset.id);
        setIsScanning(false);
    };

    const handleRdpAction = async (action: 'enable' | 'disable') => {
        if (!confirm(`${action === 'enable' ? 'Enable' : 'Disable'} Remote Access (RDP) on ${asset.hostname}?\n\nThis will send a command to the agent.`)) {
            return;
        }
        try {
            const response = await fetch('/api/agent/deploy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agentIds: [asset.id],
                    action: `${action}_rdp`,
                    packageId: 'rdp-feature'
                })
            });
            const result = await response.json();
            if (response.ok) {
                alert(`✅ Command sent successfully.\n\nTask ID: ${result.task_id}\n\nThe agent will pick this up shortly.`);
            } else {
                alert(`❌ Error: ${result.detail || 'Failed to send command'}`);
            }
        } catch (error) {
            console.error('Error sending RDP command:', error);
            alert(`❌ Error: ${error}`);
        }
    };

    const handleApplyPatch = async (vuln: Vulnerability) => {
        if (!confirm(`Deploy patch for ${vuln.cveId || vuln.id}?\n\nThis will:\n1. Create a patch deployment job\n2. Schedule installation for the next maintenance window\n3. Notify when complete`)) {
            return;
        }

        try {
            const response = await fetch(`/api/vulnerabilities/${vuln.id}/apply-patch`, {
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
                alert(`✅ Success!\n\n${result.message}\n\nJob ID: ${result.job.id}\nScheduled for: ${new Date(result.job.scheduledFor).toLocaleString()}`);
            } else {
                alert(`❌ Error: ${result.error || 'Failed to create patch job'}`);
            }
        } catch (error) {
            console.error('Error applying patch:', error);
            alert(`❌ Failed to apply patch: ${error}`);
        }
    }

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md h-full flex flex-col">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                <div>
                    <h3 className="text-lg font-bold text-gray-800 dark:text-white">{asset.hostname}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{asset.id}</p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => setIsTerminalOpen(true)}
                        className="flex items-center px-4 py-2 text-sm font-medium text-white bg-gray-800 dark:bg-gray-700 border border-gray-600 rounded-md shadow-sm hover:bg-gray-700 dark:hover:bg-gray-600 focus:outline-none transition-colors"
                    >
                        <TerminalIcon size={16} className="mr-2 text-green-400" />
                        Remote Access
                    </button>
                    <button
                        onClick={() => setIsDeleteModalOpen(true)}
                        className="flex items-center px-3 py-2 text-sm font-medium text-red-700 bg-white dark:bg-gray-700 border border-red-300 dark:border-red-600 rounded-md shadow-sm hover:bg-red-50 dark:hover:bg-red-900/20 focus:outline-none"
                    >
                        <XCircleIcon size={16} className="mr-2" />
                        Delete Asset
                    </button>
                </div>
            </div>

            <div className="border-b border-gray-200 dark:border-gray-700">
                <nav className="-mb-px flex space-x-6 px-4 overflow-x-auto" aria-label="Tabs">
                    <button onClick={() => setActiveTab('overview')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'overview' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <CpuIcon size={16} className="mr-2" /> Overview
                    </button>
                    <button onClick={() => setActiveTab('metrics')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'metrics' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <BarChart3Icon size={16} className="mr-2" /> Metrics
                    </button>
                    <button onClick={() => setActiveTab('vulnerabilities')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'vulnerabilities' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <ShieldAlertIcon size={16} className="mr-2" /> Vulnerabilities ({openVulnerabilities})
                    </button>
                    <button onClick={() => setActiveTab('software')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'software' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <BoxIcon size={16} className="mr-2" /> Software
                    </button>
                    <button onClick={() => setActiveTab('patches')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'patches' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <ShieldAlertIcon size={16} className="mr-2" /> Patches ({applicablePatches.length})
                    </button>
                    <button onClick={() => setActiveTab('integrity')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'integrity' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <FileShieldIcon size={16} className="mr-2" /> System Integrity
                    </button>
                    <button onClick={() => setActiveTab('remote')} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'remote' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <ShieldLockIcon size={16} className="mr-2" /> RDP Config
                    </button>
                    <button onClick={() => { setActiveTab('stream'); handleStartStream(); }} className={`flex items-center whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ${activeTab === 'stream' ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}`}>
                        <MonitorIcon size={16} className="mr-2" /> Live Desktop
                    </button>
                </nav>
            </div>

            <div className="p-4 flex-1 overflow-y-auto">
                {activeTab === 'overview' && (
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <DetailCard icon={<CpuIcon size={20} />} label="CPU Model" value={asset.cpuModel} />
                            <DetailCard icon={<MemoryStickIcon size={20} />} label="RAM" value={asset.ram} />
                        </div>
                        <div>
                            <h4 className="font-semibold text-gray-700 dark:text-gray-300 mb-2">Storage Devices</h4>
                            <div className="space-y-3">
                                {(asset.disks || []).map(disk => (
                                    <div key={disk.device}>
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
                                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mb-3 overflow-hidden">
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
                                <tr className="border-b dark:border-gray-700">
                                    <td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Edition</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">{asset.osEdition || asset.osName}</td>
                                </tr>
                                <tr className="border-b dark:border-gray-700">
                                    <td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Version</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">{asset.osDisplayVersion || asset.osVersion}</td>
                                </tr>
                                <tr className="border-b dark:border-gray-700">
                                    <td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Installed on</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">{asset.osInstalledOn || 'Unknown'}</td>
                                </tr>
                                <tr className="border-b dark:border-gray-700">
                                    <td className="py-2 pr-2 text-gray-500 dark:text-gray-400">OS build</td>
                                    <td className="py-2 text-gray-800 dark:text-gray-200">{asset.osBuild || asset.kernel}</td>
                                </tr>
                                <tr className="border-b dark:border-gray-700">
                                    <td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Serial number</td>
                                    <td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">{asset.serialNumber}</td>
                                </tr>
                                {asset.osExperience && (
                                    <tr className="border-b dark:border-gray-700">
                                        <td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Experience</td>
                                        <td className="py-2 text-gray-800 dark:text-gray-200">{asset.osExperience}</td>
                                    </tr>
                                )}
                                <tr className="border-b dark:border-gray-700"><td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Kernel</td><td className="py-2 text-gray-800 dark:text-gray-200">{asset.kernel}</td></tr>
                                <tr className="border-b dark:border-gray-700"><td className="py-2 pr-2 text-gray-500 dark:text-gray-400">MAC Address</td><td className="py-2 font-mono text-xs text-gray-800 dark:text-gray-200">{asset.macAddress}</td></tr>
                                <tr><td className="py-2 pr-2 text-gray-500 dark:text-gray-400">Last Scanned</td><td className="py-2 text-gray-800 dark:text-gray-200">{new Date(asset.lastScanned).toLocaleString()}</td></tr>
                                <tr className="border-t dark:border-gray-700">
                                    <td className="py-3 pr-2 font-medium text-gray-700 dark:text-gray-300">Linked Agent</td>
                                    <td className="py-3">
                                        <div className="flex flex-col space-y-2">
                                            <div className="flex items-center space-x-2">
                                                <span className="font-mono text-sm font-semibold text-gray-900 dark:text-gray-100">
                                                    {asset.agentStatus ? `Agent Status: ${asset.agentStatus}` : 'No Agent Linked'}
                                                </span>
                                                <button
                                                    onClick={handleOpenLinkModal}
                                                    className="text-xs px-2 py-1 text-primary-600 bg-primary-50 hover:bg-primary-100 rounded dark:text-primary-400 dark:bg-gray-700 dark:hover:bg-gray-600 font-medium"
                                                >
                                                    {asset.agentStatus ? 'Change Link' : 'Link Agent'}
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
                        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                            <div>
                                <h4 className="font-semibold text-gray-800 dark:text-white">Vulnerability Scanner</h4>
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Last scanned: {new Date(asset.lastScanned).toLocaleString()}</p>
                            </div>
                            <button onClick={handleRunScan} disabled={isScanning} className="flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none disabled:bg-primary-400 disabled:cursor-wait">
                                {isScanning ? <><CogIcon size={16} className="mr-2 animate-spin" /> Scanning...</> : 'Run Vulnerability Scan'}
                            </button>
                        </div>
                        <div className="max-h-[450px] overflow-y-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400 sticky top-0">
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
                                        <tr key={vuln.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                            <td className="px-4 py-3 font-mono text-xs font-bold text-gray-900 dark:text-white">{vuln.cveId || vuln.id}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${vulnerabilitySeverityClasses[vuln.severity]}`}>{vuln.severity}</span>
                                            </td>
                                            <td className="px-4 py-3 font-mono text-xs">{vuln.affectedSoftware}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${vulnerabilityStatusClasses[vuln.status]}`}>{vuln.status}</span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
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
                                                                            const response = await fetch(`/api/vulnerabilities/${vuln.id}/resolve`, {
                                                                                method: 'POST',
                                                                                headers: { 'Content-Type': 'application/json' },
                                                                                body: JSON.stringify({ status: 'Patched' })
                                                                            });
                                                                            const result = await response.json();
                                                                            if (result.success) {
                                                                                alert(`✅ Success: ${result.message}`);
                                                                                // Ideally trigger refresh here, but for now reload
                                                                                window.location.reload();
                                                                            } else {
                                                                                alert(`❌ Error: ${result.error || 'Failed to resolve'}`);
                                                                            }
                                                                        } catch (e) {
                                                                            alert(`❌ Error: ${e}`);
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
                            <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400 sticky top-0">
                                <tr>
                                    <th scope="col" className="px-4 py-3">Package Name</th>
                                    <th scope="col" className="px-4 py-3">Version</th>
                                    <th scope="col" className="px-4 py-3">Install Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(asset.installedSoftware || []).map((pkg, index) => (
                                    <tr key={`${pkg.name}-${pkg.version}-${index}`} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
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
                            <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400 sticky top-0">
                                <tr>
                                    <th scope="col" className="px-4 py-3">CVE ID</th>
                                    <th scope="col" className="px-4 py-3">Severity</th>
                                    <th scope="col" className="px-4 py-3">Description</th>
                                    <th scope="col" className="px-4 py-3">Release Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {applicablePatches.map(patch => (
                                    <tr key={patch.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
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
                        <FimAlertsPanel changes={asset.meta?.fim?.recent_changes} />

                        {/* Existing File Table */}
                        <div className="max-h-[450px] overflow-y-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400 sticky top-0">
                                    <tr>
                                        <th scope="col" className="px-4 py-3">File Path</th>
                                        <th scope="col" className="px-4 py-3">Status</th>
                                        <th scope="col" className="px-4 py-3">Last Modified</th>
                                        <th scope="col" className="px-4 py-3">Checksum (SHA256)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(asset.criticalFiles || []).map(file => (
                                        <tr key={file.path} className={`border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 ${file.status === 'Mismatch' ? 'bg-red-50 dark:bg-red-900/20' : 'bg-white dark:bg-gray-800'}`}>
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
                {activeTab === 'remote' && (
                    <div className="space-y-6">
                        <div className="bg-gray-50 dark:bg-gray-700/50 p-6 rounded-lg text-center">
                            <ShieldLockIcon size={48} className="mx-auto text-primary-500 mb-4" />
                            <h4 className="text-xl font-bold text-gray-800 dark:text-white mb-2">Remote Access Management</h4>
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
                    agent={asset}
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
