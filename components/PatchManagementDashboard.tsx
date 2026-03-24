import React, { useMemo, useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
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

// ── Types for Phase 11 ────────────────────────────────────────────────────────
interface OutdatedPackage {
    name: string;
    current_version: string;
    latest_version: string;
    update_status: 'major' | 'minor' | 'patch' | 'up-to-date' | 'unknown';
    pkg_type: string;
    is_outdated: boolean;
    agent_id?: string;
}

interface OsAssetPatch {
    agent_id: string;
    hostname: string;
    os: string;
    os_version: string;
    status: string;
    pending_count: number;
    last_checked: string;
    pending_updates: string[];
}

// ── Version badge helper ──────────────────────────────────────────────────────
const VersionBadge: React.FC<{ status: string }> = ({ status }) => {
    const styles: Record<string, string> = {
        major: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        minor: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
        patch: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
        'up-to-date': 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
        unknown: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
    };
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${styles[status] ?? styles.unknown}`}>
            {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
    );
};

const PkgTypeBadge: React.FC<{ type: string }> = ({ type }) => {
    const styles: Record<string, string> = {
        pip: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
        npm: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
        apt: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
        winget: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
        windows_update: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300',
    };
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[type] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>
            {type}
        </span>
    );
};


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

    // Tab state — now includes software-updates and os-patches
    const [activeTab, setActiveTab] = useState<'patches' | 'approvals' | 'software-updates' | 'os-patches'>('patches');

    // Phase 11: Software Updates & OS Patches state
    const [outdatedPackages, setOutdatedPackages] = useState<OutdatedPackage[]>([]);
    const [outdatedMeta, setOutdatedMeta] = useState<{ total_checked: number; scanned_at: string } | null>(null);
    const [outdatedLoading, setOutdatedLoading] = useState(false);
    const [scanLoading, setScanLoading] = useState(false);
    const [scanMessage, setScanMessage] = useState('');
    const [osPatches, setOsPatches] = useState<OsAssetPatch[]>([]);
    const [osPatchesMeta, setOsPatchesMeta] = useState<{ total_pending_os_patches: number; scanned_at: string } | null>(null);
    const [osPatchesLoading, setOsPatchesLoading] = useState(false);
    const [pkgTypeFilter, setPkgTypeFilter] = useState<string>('all');
    const [updatingPkgs, setUpdatingPkgs] = useState<Set<string>>(new Set());
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

    // ── Fetch outdated packages ────────────────────────────────────────────────
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

    // ── Fetch OS patches ──────────────────────────────────────────────────────
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

    // ── Apply Software Update ─────────────────────────────────────────────────
    const handleUpdateSoftware = async (pkgName: string, pkgType: string) => {
        const updateKey = `${pkgName}-${pkgType}`;
        setUpdatingPkgs(prev => new Set(prev).add(updateKey));
        try {
            // In this project, we assume the first online agent for simplicity if no specific agent selected
            const onlineAgent = osPatches.find(a => a.status === 'online')?.agent_id;
            if (!onlineAgent) {
                alert("No online agent found to perform update.");
                return;
            }

            const res = await authFetch('/api/patches/apply-software-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent_id: onlineAgent,
                    package_name: pkgName,
                    pkg_type: pkgType
                })
            });
            if (res.ok) {
                setScanMessage(`Upgrade instruction sent for ${pkgName}. Result will appear in next scan.`);
            } else {
                const error = await res.json();
                alert(`Error: ${error.detail || 'Failed to trigger update'}`);
            }
        } catch (e) {
            console.error('Error triggering update', e);
        } finally {
            setUpdatingPkgs(prev => {
                const next = new Set(prev);
                next.delete(updateKey);
                return next;
            });
        }
    };

    // ── Apply Bulk Software Updates ───────────────────────────────────────────
    const [bulkUpdating, setBulkUpdating] = useState(false);
    const handleBulkUpdate = async () => {
        if (outdatedPackages.length === 0) return;

        const updates = outdatedPackages
            .filter(pkg => pkg.is_outdated && pkg.agent_id)
            .map(pkg => ({
                agent_id: pkg.agent_id,
                package_name: pkg.name,
                pkg_type: pkg.pkg_type
            }));

        if (updates.length === 0) {
            alert("No packages with valid agent IDs found for update.");
            return;
        }

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
                alert(`Error: ${error.detail || 'Failed to trigger bulk update'}`);
            }
        } catch (e) {
            console.error('Error triggering bulk update', e);
        } finally {
            setBulkUpdating(false);
        }
    };

    // ── Apply OS Patches ──────────────────────────────────────────────────────
    const handleApplyOsPatches = async (agentId: string, patches: string[]) => {
        setDeployingAssetPatches(prev => new Set(prev).add(agentId));
        try {
            const res = await authFetch('/api/patches/apply-os-patches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    agent_id: agentId,
                    patch_ids: patches
                })
            });
            if (res.ok) {
                const data = await res.json();
                setScanMessage(`OS patch deployment queued. Job ID: ${data.job_id}`);
            } else {
                const error = await res.json();
                alert(`Error: ${error.detail || 'Failed to trigger patches'}`);
            }
        } catch (e) {
            console.error('Error triggering OS patches', e);
        } finally {
            setDeployingAssetPatches(prev => {
                const next = new Set(prev);
                next.delete(agentId);
                return next;
            });
        }
    };

    // Fetch data when tab becomes active
    useEffect(() => {
        if (activeTab === 'software-updates') fetchOutdatedPackages(pkgTypeFilter);
        if (activeTab === 'os-patches') fetchOsPatches();
    }, [activeTab]);

    // Re-fetch when pkg type filter changes
    useEffect(() => {
        if (activeTab === 'software-updates') fetchOutdatedPackages(pkgTypeFilter);
    }, [pkgTypeFilter]);

    // ── Trigger Live Scan ─────────────────────────────────────────────────────
    const handleTriggerScan = async () => {
        setScanLoading(true);
        setScanMessage('');
        try {
            const res = await authFetch('/api/patches/scan', { method: 'POST' });
            const data = await res.json();
            setScanMessage(data.message ?? `Scan triggered for ${data.triggered} agent(s). Refreshing in 15 seconds...`);
            // Auto-refresh after 15 seconds
            setTimeout(() => fetchOutdatedPackages(pkgTypeFilter), 15000);
        } catch (e) {
            setScanMessage('Failed to trigger scan. Check that agents are online.');
        } finally {
            setScanLoading(false);
        }
    };

    // ── Existing handlers ─────────────────────────────────────────────────────
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

    // Colour strip for update severity
    const severityBorderColor: Record<string, string> = {
        major: 'border-l-red-500', minor: 'border-l-amber-500', patch: 'border-l-blue-500',
    };

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

            {/* Tab Navigation */}
            <div className="flex space-x-1 border-b border-gray-200 dark:border-gray-700">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-2 ${activeTab === tab.id
                            ? 'bg-white dark:bg-gray-800 text-primary-600 dark:text-primary-400 border-t border-l border-r border-gray-200 dark:border-gray-700'
                            : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700'
                            }`}
                    >
                        {tab.label}
                        {tab.badge && (
                            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${tab.id === 'approvals' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-400' : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'}`}>
                                {tab.badge}
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {/* ── TAB: Patches & Deployment ─────────────────────────────────────── */}
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

            {/* ── TAB: Software Updates (Phase 11) ─────────────────────────────── */}
            {activeTab === 'software-updates' && (
                <div className="space-y-4">
                    {/* Toolbar */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-wrap gap-3 items-center justify-between">
                        <div className="flex items-center gap-3">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Filter by type:</span>
                            {['all', 'pip', 'npm', 'apt', 'winget'].map(type => (
                                <button key={type} onClick={() => setPkgTypeFilter(type)}
                                    className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors ${pkgTypeFilter === type ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
                                    {type}
                                </button>
                            ))}
                        </div>
                        <div className="flex items-center gap-3">
                            {outdatedMeta && (
                                <span className="text-xs text-gray-400 dark:text-gray-500">
                                    {outdatedMeta.total_checked} packages checked · {outdatedPackages.length} outdated · last scan: {new Date(outdatedMeta.scanned_at).toLocaleTimeString()}
                                </span>
                            )}
                            <button onClick={handleTriggerScan} disabled={scanLoading}
                                className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2">
                                {scanLoading ? (
                                    <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Scanning...</>
                                ) : '🔍 Trigger Live Scan'}
                            </button>
                            <button onClick={handleBulkUpdate} disabled={bulkUpdating || outdatedPackages.length === 0}
                                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2">
                                {bulkUpdating ? (
                                    <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Queuing...</>
                                ) : '🚀 Bulk Update All'}
                            </button>
                            <button onClick={() => fetchOutdatedPackages(pkgTypeFilter)} disabled={outdatedLoading}
                                className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 rounded-lg hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300">
                                ↻ Refresh
                            </button>
                        </div>
                    </div>

                    {scanMessage && (
                        <div className="bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-700 rounded-lg p-3 text-sm text-emerald-800 dark:text-emerald-300">
                            ✅ {scanMessage}
                        </div>
                    )}

                    {/* Table */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                            <h3 className="text-lg font-semibold">Outdated Software Packages</h3>
                            <span className="text-sm text-gray-500">
                                {outdatedLoading ? 'Loading...' : `${outdatedPackages.length} packages need updates`}
                            </span>
                        </div>

                        {outdatedLoading ? (
                            <div className="flex justify-center items-center py-16 text-gray-400">
                                <span className="animate-spin inline-block w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full mr-3" />
                                Fetching latest versions from PyPI, npm &amp; Ubuntu Packages...
                            </div>
                        ) : outdatedPackages.length === 0 ? (
                            <div className="text-center py-16 text-gray-400 dark:text-gray-500">
                                <p className="text-4xl mb-3">✅</p>
                                <p className="text-lg font-medium">All packages are up to date!</p>
                                <p className="text-sm mt-1">Click "Trigger Live Scan" to collect fresh data from agents.</p>
                            </div>
                        ) : (
                            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                <thead className="bg-gray-50 dark:bg-gray-700/50">
                                    <tr>
                                        <th className="pl-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Package</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Latest</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Gap</th>
                                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                    {outdatedPackages.map((pkg, idx) => (
                                        <tr key={`${pkg.name}-${idx}`}
                                            className={`border-l-4 ${severityBorderColor[pkg.update_status] ?? 'border-l-gray-200'} hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors`}>
                                            <td className="pl-6 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{pkg.name}</td>
                                            <td className="px-4 py-3"><PkgTypeBadge type={pkg.pkg_type} /></td>
                                            <td className="px-4 py-3 font-mono text-sm text-gray-500 dark:text-gray-400">{pkg.current_version}</td>
                                            <td className="px-4 py-3 font-mono text-sm text-emerald-600 dark:text-emerald-400 font-semibold">{pkg.latest_version}</td>
                                            <td className="px-4 py-3"><VersionBadge status={pkg.update_status} /></td>
                                            <td className="px-6 py-3 text-right whitespace-nowrap">
                                                <button
                                                    onClick={() => handleUpdateSoftware(pkg.name, pkg.pkg_type)}
                                                    disabled={updatingPkgs.has(`${pkg.name}-${pkg.pkg_type}`)}
                                                    className="inline-flex items-center px-3 py-1 text-xs font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                                                >
                                                    {updatingPkgs.has(`${pkg.name}-${pkg.pkg_type}`) ? (
                                                        <><span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full mr-1" />Updating</>
                                                    ) : 'Update'}
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            )}

            {/* ── TAB: OS Patches (Phase 11) ────────────────────────────────────── */}
            {activeTab === 'os-patches' && (
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
                        <button onClick={fetchOsPatches} disabled={osPatchesLoading}
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
                                                <button
                                                    onClick={() => handleApplyOsPatches(asset.agent_id, asset.pending_updates)}
                                                    disabled={deployingAssetPatches.has(asset.agent_id)}
                                                    className="ml-2 px-3 py-1 text-xs font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:bg-gray-400 transition-colors"
                                                >
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
            )}

            {/* ── TAB: Agent Approvals ─────────────────────────────────────────── */}
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
