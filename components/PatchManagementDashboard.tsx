import React, { useMemo, useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, Legend } from 'recharts';
import { Patch, PatchSeverity, Asset, PatchDeploymentJob, VulnerabilityScanJob } from '../types';
import { PatchList } from './PatchList';
import { ShieldAlertIcon, ShieldSearchIcon } from './icons';
import { DeployPatchesModal } from './DeployPatchesModal';
import { PatchDeploymentJobs } from './PatchDeploymentJobs';
import { AssetPatchStatusList } from './AssetPatchStatusList';
import { ScheduleScanModal } from './ScheduleScanModal';
import { VulnerabilityScanJobs } from './VulnerabilityScanJobs';
import AgentApprovalDashboard from './AgentApprovalDashboard';
import { ErrorBoundary } from './ErrorBoundary';
import { authFetch } from '../services/apiService';
import { LocalRepoManager } from './LocalRepoManager';
import { PatchSoftwareUpdatesTab, OutdatedPackage } from './PatchSoftwareUpdatesTab';
import { OsPatchesTab, OsAssetPatch } from './OsPatchesTab';
import { showToast } from '../utils/toast';

interface PatchManagementDashboardProps {
    patches: Patch[];
    assets: Asset[];
    patchDeploymentJobs: PatchDeploymentJob[];
    onSchedulePatchDeployment: (patchIds: string[], assetIds: string[], deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string) => Promise<void>;
    vulnerabilityScanJobs: VulnerabilityScanJob[];
    onScheduleVulnerabilityScan: (assetIds: string[], scanType: 'Immediate' | 'Scheduled', scheduleTime?: string) => Promise<void>;
}

export const PatchManagementDashboard: React.FC<PatchManagementDashboardProps> = ({
    patches, assets, patchDeploymentJobs, onSchedulePatchDeployment, vulnerabilityScanJobs, onScheduleVulnerabilityScan
}) => {
    const [selectedPatchIds, setSelectedPatchIds] = useState<Set<string>>(new Set());
    const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
    const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(new Set());
    const [isScanModalOpen, setIsScanModalOpen] = useState(false);
    const [scanScope, setScanScope] = useState<'selected' | 'all'>('selected');
    const [activeTab, setActiveTab] = useState<'patches' | 'approvals' | 'software-updates' | 'os-patches'>('patches');

    // Software Updates state
    const [outdatedPackages, setOutdatedPackages] = useState<OutdatedPackage[]>([]);
    const [outdatedMeta, setOutdatedMeta] = useState<{ total_checked: number; scanned_at: string } | null>(null);
    const [outdatedLoading, setOutdatedLoading] = useState(false);
    const [scanLoading, setScanLoading] = useState(false);
    const [scanMessage, setScanMessage] = useState('');
    const [pkgTypeFilter, setPkgTypeFilter] = useState<string>('all');
    const [updatingPkgs, setUpdatingPkgs] = useState<Set<string>>(new Set());
    const [bulkUpdating, setBulkUpdating] = useState(false);

    // Velocity chart state
    const [velocityData, setVelocityData] = useState<{ date: string; deployed: number; failed: number }[]>([]);
    useEffect(() => {
        authFetch('/api/patches/velocity?days=30')
            .then(r => r.ok ? r.json() : [])
            .then(data => setVelocityData(Array.isArray(data) ? data : []))
            .catch((e) => console.error('Failed to load patch velocity data:', e));
    }, []);

    // OS Patches state
    const [osPatches, setOsPatches] = useState<OsAssetPatch[]>([]);
    const [osPatchesMeta, setOsPatchesMeta] = useState<{ total_pending_os_patches: number; scanned_at: string } | null>(null);
    const [osPatchesLoading, setOsPatchesLoading] = useState(false);
    const [deployingAssetPatches, setDeployingAssetPatches] = useState<Set<string>>(new Set());

    const pendingPatches = patches.filter(p => p.status === 'Pending');
    const severityCounts = useMemo(() => {
        const counts: Record<string, number> = { Critical: 0, High: 0, Medium: 0, Low: 0 };
        pendingPatches.forEach(patch => {
            const sev = patch.severity as string;
            if (counts.hasOwnProperty(sev)) counts[sev]++;
            else counts['Medium']++;
        });
        return counts;
    }, [pendingPatches]);

    const chartData = [
        { name: 'Critical', count: severityCounts.Critical, fill: '#ef4444' },
        { name: 'High', count: severityCounts.High, fill: '#f97316' },
        { name: 'Medium', count: severityCounts.Medium, fill: '#f59e0b' },
        { name: 'Low', count: severityCounts.Low, fill: '#3b82f6' },
    ];
    const affectedAssetsCount = new Set(pendingPatches.flatMap(p => p.affectedAssets || [])).size;
    const selectedPatches = useMemo(() => patches.filter(p => selectedPatchIds.has(p.id)), [patches, selectedPatchIds]);

    const fetchOutdatedPackages = useCallback(async (type?: string) => {
        setOutdatedLoading(true);
        try {
            const qs = type && type !== 'all' ? `?pkg_type=${type}` : '';
            const res = await authFetch(`/api/patches/outdated${qs}`);
            if (res.ok) {
                const data = await res.json();
                setOutdatedPackages(data.packages ?? []);
                setOutdatedMeta({ total_checked: data.total_checked, scanned_at: data.scanned_at });
            }
        } catch (e) {
            console.error('Error fetching outdated packages', e);
        } finally {
            setOutdatedLoading(false);
        }
    }, []);

    const fetchOsPatches = useCallback(async () => {
        setOsPatchesLoading(true);
        try {
            const res = await authFetch('/api/patches/os');
            if (res.ok) {
                const data = await res.json();
                setOsPatches(data.assets ?? []);
                setOsPatchesMeta({ total_pending_os_patches: data.total_pending_os_patches, scanned_at: data.scanned_at });
            }
        } catch (e) {
            console.error('Error fetching OS patches', e);
        } finally {
            setOsPatchesLoading(false);
        }
    }, []);

    const handleUpdateSoftware = async (pkgName: string, pkgType: string) => {
        const updateKey = `${pkgName}-${pkgType}`;
        setUpdatingPkgs(prev => new Set(prev).add(updateKey));
        try {
            const onlineAgent = osPatches.find(a => a.status === 'online')?.agent_id;
            if (!onlineAgent) { showToast("No online agent found to perform update.", 'error'); return; }
            const res = await authFetch('/api/patches/apply-software-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: onlineAgent, package_name: pkgName, pkg_type: pkgType })
            });
            if (res.ok) {
                setScanMessage(`Upgrade instruction sent for ${pkgName}. Result will appear in next scan.`);
            } else {
                const error = await res.json();
                showToast(`Error: ${error.detail || 'Failed to trigger update'}`, 'error');
            }
        } catch (e) {
            console.error('Error triggering update', e);
        } finally {
            setUpdatingPkgs(prev => { const next = new Set(prev); next.delete(updateKey); return next; });
        }
    };

    const handleBulkUpdate = async () => {
        if (outdatedPackages.length === 0) return;
        const updates = outdatedPackages.filter(pkg => pkg.is_outdated && pkg.agent_id)
            .map(pkg => ({ agent_id: pkg.agent_id, package_name: pkg.name, pkg_type: pkg.pkg_type }));
        if (updates.length === 0) { showToast("No packages with valid agent IDs found for update.", 'error'); return; }
        setBulkUpdating(true);
        try {
            const res = await authFetch('/api/patches/bulk-apply-software-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ updates })
            });
            if (res.ok) {
                const data = await res.json();
                setScanMessage(`Bulk updates triggered! ${data.count} instructions queued.`);
            } else {
                const error = await res.json();
                showToast(`Error: ${error.detail || 'Failed to trigger bulk update'}`, 'error');
            }
        } catch (e) {
            console.error('Error triggering bulk update', e);
        } finally {
            setBulkUpdating(false);
        }
    };

    const handleApplyOsPatches = async (agentId: string, patches: string[]) => {
        setDeployingAssetPatches(prev => new Set(prev).add(agentId));
        try {
            const res = await authFetch('/api/patches/apply-os-patches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: agentId, patch_ids: patches })
            });
            if (res.ok) {
                const data = await res.json();
                setScanMessage(`OS patch deployment queued. Job ID: ${data.job_id}`);
            } else {
                const error = await res.json();
                showToast(`Error: ${error.detail || 'Failed to trigger patches'}`, 'error');
            }
        } catch (e) {
            console.error('Error triggering OS patches', e);
        } finally {
            setDeployingAssetPatches(prev => { const next = new Set(prev); next.delete(agentId); return next; });
        }
    };

    const handleTriggerScan = async () => {
        setScanLoading(true);
        setScanMessage('');
        try {
            const res = await authFetch('/api/patches/scan', { method: 'POST' });
            const data = await res.json();
            setScanMessage(data.message ?? `Scan triggered for ${data.triggered} agent(s). Refreshing in 15 seconds...`);
            setTimeout(() => fetchOutdatedPackages(pkgTypeFilter), 15000);
        } catch (e) {
            setScanMessage('Failed to trigger scan. Check that agents are online.');
        } finally {
            setScanLoading(false);
        }
    };

    useEffect(() => {
        if (activeTab === 'software-updates') fetchOutdatedPackages(pkgTypeFilter);
        if (activeTab === 'os-patches') fetchOsPatches();
    }, [activeTab]);

    useEffect(() => {
        if (activeTab === 'software-updates') fetchOutdatedPackages(pkgTypeFilter);
    }, [pkgTypeFilter]);

    const handleDeploy = (deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string) => {
        const assetIdsToPatch = new Set<string>();
        selectedPatches.forEach(patch => patch.affectedAssets.forEach(id => assetIdsToPatch.add(id)));
        onSchedulePatchDeployment(Array.from(selectedPatchIds), Array.from(assetIdsToPatch), deploymentType, scheduleTime);
        setIsDeployModalOpen(false);
        setSelectedPatchIds(new Set());
    };
    const handleToggleAssetSelection = (assetId: string) => {
        setSelectedAssetIds(prev => { const s = new Set(prev); s.has(assetId) ? s.delete(assetId) : s.add(assetId); return s; });
    };
    const handleToggleAllAssets = (assetIds: string[]) => {
        setSelectedAssetIds(assetIds.every(id => selectedAssetIds.has(id)) && assetIds.length > 0 ? new Set() : new Set(assetIds));
    };
    const openScanModal = (scope: 'selected' | 'all') => { setScanScope(scope); setIsScanModalOpen(true); };
    const handleScheduleScan = (scanType: 'Immediate' | 'Scheduled', scheduleTime?: string) => {
        const assetIdsToScan = scanScope === 'all' ? assets.map(a => a.id) : Array.from(selectedAssetIds);
        onScheduleVulnerabilityScan(assetIdsToScan, scanType, scheduleTime);
        setIsScanModalOpen(false);
        setSelectedAssetIds(new Set());
    };
    const scanAssetCount = scanScope === 'all' ? assets.length : selectedAssetIds.size;

    const tabs: { id: 'patches' | 'approvals' | 'software-updates' | 'os-patches'; label: string; badge?: string }[] = [
        { id: 'patches', label: 'Patches & Deployment' },
        { id: 'software-updates', label: '🔄 Software Updates', badge: outdatedPackages.length > 0 ? String(outdatedPackages.length) : undefined },
        { id: 'os-patches', label: '🖥️ OS Patches', badge: osPatchesMeta?.total_pending_os_patches ? String(osPatchesMeta.total_pending_os_patches) : undefined },
        { id: 'approvals', label: 'Agent Approvals', badge: 'Agentic' },
    ];

    return (
        <div className="container mx-auto space-y-6">
            <div>
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Patch Management</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Monitor, approve, and deploy security patches. Now with real-time software version validation.</p>
            </div>

            <div className="flex space-x-1 border-b border-gray-200 dark:border-gray-700">
                {tabs.map(tab => (
                    <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                        className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-2 ${activeTab === tab.id
                            ? 'bg-white dark:bg-gray-800 text-primary-600 dark:text-primary-400 border-t border-l border-r border-gray-200 dark:border-gray-700'
                            : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
                        {tab.label}
                        {tab.badge && (
                            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${tab.id === 'approvals' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-400' : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}`}>
                                {tab.badge}
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {activeTab === 'patches' && (
                <div className="space-y-6">
                    <ErrorBoundary fallback={<div className="p-4 bg-red-50 text-red-800 rounded">Error loading charts</div>}>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                                <h3 className="text-lg font-semibold flex items-center mb-4">Pending Patches by Severity</h3>
                                <div className="h-64 w-full">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.1} />
                                            <XAxis type="number" hide />
                                            <YAxis type="category" dataKey="name" stroke="#9ca3af" fontSize={12} width={80} tick={{ fill: '#9ca3af' }} />
                                            <Tooltip cursor={{ fill: 'rgba(128,128,128,0.1)' }} contentStyle={{ backgroundColor: 'rgba(31,41,55,0.9)', border: 'none', borderRadius: '0.5rem', color: '#fff' }} />
                                            <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={20} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-6">
                                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Total Pending Patches</p>
                                    <p className="text-3xl font-bold">{pendingPatches.length}</p>
                                </div>
                                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Assets Affected</p>
                                    <p className="text-3xl font-bold">{affectedAssetsCount} / {assets.length}</p>
                                </div>
                                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md col-span-2">
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Pending Critical Patches</p>
                                    <p className="text-3xl font-bold text-red-500">{severityCounts.Critical}</p>
                                </div>
                            </div>
                        </div>
                    </ErrorBoundary>

                    {/* Remediation Velocity Chart */}
                    {velocityData.length > 0 && (
                        <ErrorBoundary fallback={<div />}>
                            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                                    30-Day Remediation Velocity
                                    <span className="ml-2 text-xs text-gray-400 font-normal">patches deployed/failed per day</span>
                                </h3>
                                <div className="h-40">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={velocityData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                                            <defs>
                                                <linearGradient id="velDeployed" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                                                </linearGradient>
                                                <linearGradient id="velFailed" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
                                            <XAxis dataKey="date" fontSize={10} stroke="#9ca3af"
                                                tickFormatter={v => v.slice(5)} interval={6} />
                                            <YAxis fontSize={10} stroke="#9ca3af" allowDecimals={false} />
                                            <Tooltip contentStyle={{ fontSize: 12, backgroundColor: 'rgba(31,41,55,0.9)', border: 'none', borderRadius: '0.5rem', color: '#fff' }} />
                                            <Legend wrapperStyle={{ fontSize: 11 }} />
                                            <Area type="monotone" dataKey="deployed" stroke="#22c55e" strokeWidth={2} fill="url(#velDeployed)" />
                                            <Area type="monotone" dataKey="failed" stroke="#ef4444" strokeWidth={2} fill="url(#velFailed)" />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                        </ErrorBoundary>
                    )}

                    <ErrorBoundary fallback={<div className="p-4 bg-red-50 text-red-800 rounded">Error loading patch inventory</div>}>
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                                <h3 className="text-lg font-semibold flex items-center"><ShieldAlertIcon className="mr-2 text-primary-500" />Patch Inventory</h3>
                                <button onClick={() => setIsDeployModalOpen(true)} disabled={selectedPatchIds.size === 0}
                                    className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed">
                                    Deploy {selectedPatchIds.size > 0 ? `(${selectedPatchIds.size})` : ''} Selected
                                </button>
                            </div>
                            <PatchList patches={patches} selectedPatchIds={selectedPatchIds} onSetSelectedPatchIds={setSelectedPatchIds} />
                        </div>
                    </ErrorBoundary>
                    <ErrorBoundary fallback={<div className="p-4 bg-red-50 text-red-800 rounded">Error loading deployment jobs</div>}>
                        <PatchDeploymentJobs jobs={patchDeploymentJobs} />
                    </ErrorBoundary>
                    <ErrorBoundary fallback={<div className="p-4 bg-red-50 text-red-800 rounded">Error loading asset status</div>}>
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                                <h3 className="text-lg font-semibold flex items-center"><ShieldSearchIcon className="mr-2 text-primary-500" />Asset Patch Status &amp; Vulnerability Scanning</h3>
                                <div className="flex items-center space-x-2">
                                    <button onClick={() => openScanModal('selected')} disabled={selectedAssetIds.size === 0}
                                        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed">
                                        Scan Selected ({selectedAssetIds.size})
                                    </button>
                                    <button onClick={() => openScanModal('all')}
                                        className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 rounded-lg hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300">
                                        Scan All Assets
                                    </button>
                                </div>
                            </div>
                            <AssetPatchStatusList assets={assets} selectedAssetIds={selectedAssetIds} onToggleSelection={handleToggleAssetSelection} onToggleAll={handleToggleAllAssets} />
                        </div>
                    </ErrorBoundary>
                    <ErrorBoundary fallback={<div className="p-4 bg-red-50 text-red-800 rounded">Error loading scan jobs</div>}>
                        <VulnerabilityScanJobs jobs={vulnerabilityScanJobs} />
                    </ErrorBoundary>
                    <DeployPatchesModal isOpen={isDeployModalOpen} onClose={() => setIsDeployModalOpen(false)} patchesToDeploy={selectedPatches} assets={assets} onDeploy={handleDeploy} />
                    <ScheduleScanModal isOpen={isScanModalOpen} onClose={() => setIsScanModalOpen(false)} onSchedule={handleScheduleScan} assetCount={scanAssetCount} />
                </div>
            )}

            {activeTab === 'software-updates' && (
                <PatchSoftwareUpdatesTab
                    outdatedPackages={outdatedPackages}
                    outdatedMeta={outdatedMeta}
                    outdatedLoading={outdatedLoading}
                    scanLoading={scanLoading}
                    scanMessage={scanMessage}
                    pkgTypeFilter={pkgTypeFilter}
                    updatingPkgs={updatingPkgs}
                    bulkUpdating={bulkUpdating}
                    onFilterChange={setPkgTypeFilter}
                    onTriggerScan={handleTriggerScan}
                    onBulkUpdate={handleBulkUpdate}
                    onUpdateSoftware={handleUpdateSoftware}
                    onRefresh={() => fetchOutdatedPackages(pkgTypeFilter)}
                />
            )}

            {activeTab === 'os-patches' && (
                <OsPatchesTab
                    osPatches={osPatches}
                    osPatchesMeta={osPatchesMeta}
                    osPatchesLoading={osPatchesLoading}
                    deployingAssetPatches={deployingAssetPatches}
                    onRefresh={fetchOsPatches}
                    onApplyOsPatches={handleApplyOsPatches}
                />
            )}

            {activeTab === 'approvals' && (
                <ErrorBoundary fallback={<div className="p-4 bg-red-50 text-red-800 rounded">Error loading approvals</div>}>
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                        <AgentApprovalDashboard />
                    </div>
                </ErrorBoundary>
            )}
        </div>
    );
};

export default PatchManagementDashboard;
