import React, { useState, useMemo, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { BoxIcon, DownloadIcon, RefreshCwIcon, AlertCircleIcon, CheckIcon, SearchIcon } from './icons';
import { Asset } from '../types';
import { DeploySoftwareUpdatesModal } from './DeploySoftwareUpdatesModal';
import { showToast } from '../utils/toast';

interface SoftwareItem {
    id: string;
    name: string;
    currentVersion: string;
    latestVersion: string;
    updateAvailable: boolean;
    publisher: string;
    installDate?: string;
    assetId: string;
    assetName: string;
    severity?: 'Critical' | 'High' | 'Medium' | 'Low';
}

interface SoftwareUpdateManagementProps {
    assets: Asset[];
}

export const SoftwareUpdateManagement: React.FC<SoftwareUpdateManagementProps> = ({ assets }) => {
    const [selectedSoftwareIds, setSelectedSoftwareIds] = useState<Set<string>>(new Set());
    const [filterStatus, setFilterStatus] = useState<'all' | 'updates' | 'uptodate'>('all');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedAssetFilter, setSelectedAssetFilter] = useState<string>('all');
    const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
    const [inventory, setInventory] = useState<any[] | null>(null);

    // Load the installed-software inventory (has real current/latest versions and
    // is_outdated flags — unlike asset.installedSoftware, which is name/version only).
    useEffect(() => {
        let cancelled = false;
        authFetch('/api/software/inventory')
            .then(r => (r.ok ? r.json() : []))
            .then(data => { if (!cancelled) setInventory(Array.isArray(data) ? data : []); })
            .catch(() => { if (!cancelled) setInventory([]); });
        return () => { cancelled = true; };
    }, []);

    const _severityFor = (name: string, publisher: string, updateAvailable: boolean) => {
        if (!updateAvailable) return undefined;
        if (name?.toLowerCase().includes('security') || name?.toLowerCase().includes('defender')) return 'Critical' as const;
        if (publisher?.toLowerCase().includes('microsoft') || publisher?.toLowerCase().includes('google')) return 'High' as const;
        return 'Medium' as const;
    };

    // Build the software list from the inventory when available, flattening each
    // package's per-agent rows and mapping agents back to assets by hostname so
    // the asset filter keeps working. Falls back to asset.installedSoftware.
    const softwareList: SoftwareItem[] = useMemo(() => {
        const assetByHost = new Map(assets.map(a => [a.hostname, a]));

        if (inventory && inventory.length > 0) {
            const items: SoftwareItem[] = [];
            inventory.forEach(pkg => {
                (pkg.agents || []).forEach((ag: any, idx: number) => {
                    const asset = assetByHost.get(ag.agent_name);
                    const updateAvailable = !!ag.is_outdated;
                    const publisher = pkg.pkg_type || 'Unknown';
                    items.push({
                        id: `${pkg.name}-${ag.agent_id || idx}`,
                        name: pkg.name || 'Unknown Software',
                        currentVersion: ag.version || 'N/A',
                        latestVersion: ag.latest_version || ag.version || 'N/A',
                        updateAvailable,
                        publisher,
                        installDate: ag.last_scanned,
                        assetId: asset?.id || ag.agent_id || '',
                        assetName: ag.agent_name || asset?.hostname || '',
                        severity: _severityFor(pkg.name, publisher, updateAvailable),
                    });
                });
            });
            return items;
        }

        // Fallback: derive from assets' embedded installedSoftware (name/version only).
        const items: SoftwareItem[] = [];
        assets.forEach(asset => {
            (asset.installedSoftware || []).forEach((sw: any, index: number) => {
                const updateAvailable = sw.updateAvailable || false;
                items.push({
                    id: `${asset.id}-${index}`,
                    name: sw.name || sw.displayName || 'Unknown Software',
                    currentVersion: sw.version || sw.displayVersion || 'N/A',
                    latestVersion: sw.latestVersion || sw.version || 'N/A',
                    updateAvailable,
                    publisher: sw.publisher || 'Unknown',
                    installDate: sw.installDate,
                    assetId: asset.id,
                    assetName: asset.hostname,
                    severity: _severityFor(sw.name, sw.publisher, updateAvailable),
                });
            });
        });
        return items;
    }, [assets, inventory]);

    // Filter software
    const filteredSoftware = useMemo(() => {
        return softwareList.filter(sw => {
            // Status filter
            if (filterStatus === 'updates' && !sw.updateAvailable) return false;
            if (filterStatus === 'uptodate' && sw.updateAvailable) return false;

            // Search filter
            if (searchTerm && !sw.name.toLowerCase().includes(searchTerm.toLowerCase())) return false;

            // Asset filter
            if (selectedAssetFilter !== 'all' && sw.assetId !== selectedAssetFilter) return false;

            return true;
        });
    }, [softwareList, filterStatus, searchTerm, selectedAssetFilter]);

    // Statistics
    const stats = useMemo(() => {
        const total = softwareList.length;
        const updatesAvailable = softwareList.filter(sw => sw.updateAvailable).length;
        const criticalUpdates = softwareList.filter(sw => sw.updateAvailable && sw.severity === 'Critical').length;
        const highUpdates = softwareList.filter(sw => sw.updateAvailable && sw.severity === 'High').length;

        return { total, updatesAvailable, criticalUpdates, highUpdates };
    }, [softwareList]);

    const handleToggleSelection = (id: string) => {
        setSelectedSoftwareIds(prev => {
            const newSet = new Set(prev);
            if (newSet.has(id)) {
                newSet.delete(id);
            } else {
                newSet.add(id);
            }
            return newSet;
        });
    };

    const handleSelectAll = () => {
        if (selectedSoftwareIds.size === filteredSoftware.length && filteredSoftware.length > 0) {
            setSelectedSoftwareIds(new Set());
        } else {
            setSelectedSoftwareIds(new Set(filteredSoftware.map(sw => sw.id)));
        }
    };

    const handleDeployUpdates = () => {
        setIsDeployModalOpen(true);
    };

    const handleConfirmDeployment = async (deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string) => {
        const selectedItems = filteredSoftware.filter(sw => selectedSoftwareIds.has(sw.id));

        try {
            const response = await authFetch('/api/software/updates/deploy', {
                method: 'POST',
                body: JSON.stringify({
                    softwareUpdates: selectedItems,
                    deploymentType,
                    scheduleTime
                })
            });

            const data = await response.json();

            if (data.success) {
                setSelectedSoftwareIds(new Set());
                showToast(`Deployment ${deploymentType === 'Immediate' ? 'started' : 'scheduled'}. Job ID: ${data.job.id}`, 'success');
            } else {
                showToast(`Deployment failed: ${data.error || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            console.error('Deployment error:', error);
            showToast(`Failed to start deployment: ${error instanceof Error ? error.message : 'Network error'}`, 'error');
        }
    };

    const getSeverityBadge = (severity?: 'Critical' | 'High' | 'Medium' | 'Low') => {
        if (!severity) return null;

        const colors = {
            Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
            High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
            Medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
            Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300'
        };

        return (
            <span className={`px-2 py-1 rounded-full text-xs font-semibold ${colors[severity]}`}>
                {severity}
            </span>
        );
    };

    return (
        <div className="container mx-auto space-y-6 p-6">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2 flex items-center">
                    <BoxIcon className="mr-3 text-primary-500" size={28} />
                    Software Update Management
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                    Track installed software versions, identify available updates, and deploy updates across your fleet.
                </p>
            </div>

            {/* Statistics Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Total Software</p>
                    <p className="text-3xl font-bold">{stats.total}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Updates Available</p>
                    <p className="text-3xl font-bold text-blue-500">{stats.updatesAvailable}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Critical Updates</p>
                    <p className="text-3xl font-bold text-red-500">{stats.criticalUpdates}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">High Priority Updates</p>
                    <p className="text-3xl font-bold text-orange-500">{stats.highUpdates}</p>
                </div>
            </div>

            {/* Filters and Actions */}
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
                    <div className="flex flex-wrap gap-4 flex-1">
                        {/* Search */}
                        <div className="relative">
                            <SearchIcon size={18} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search software..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                            />
                        </div>

                        {/* Status Filter */}
                        <select
                            value={filterStatus}
                            onChange={(e) => setFilterStatus(e.target.value as any)}
                            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                        >
                            <option value="all">All Software</option>
                            <option value="updates">Updates Available</option>
                            <option value="uptodate">Up-to-date</option>
                        </select>

                        {/* Asset Filter */}
                        <select
                            value={selectedAssetFilter}
                            onChange={(e) => setSelectedAssetFilter(e.target.value)}
                            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                        >
                            <option value="all">All Assets</option>
                            {assets.map(asset => (
                                <option key={asset.id} value={asset.id}>{asset.hostname}</option>
                            ))}
                        </select>
                    </div>

                    {/* Deploy Button */}
                    <button
                        onClick={handleDeployUpdates}
                        disabled={selectedSoftwareIds.size === 0}
                        className="flex items-center px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                    >
                        <DownloadIcon size={18} className="mr-2" />
                        Deploy Updates ({selectedSoftwareIds.size})
                    </button>
                </div>
            </div>

            {/* Software Table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-900">
                            <tr>
                                <th className="px-6 py-3 text-left">
                                    <input
                                        type="checkbox"
                                        checked={selectedSoftwareIds.size === filteredSoftware.length && filteredSoftware.length > 0}
                                        onChange={handleSelectAll}
                                        className="rounded"
                                    />
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Software Name
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Current Version
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Latest Version
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Asset
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Publisher
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {filteredSoftware.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                                        <BoxIcon size={48} className="mx-auto mb-4 text-gray-400" />
                                        <p className="text-lg font-semibold">No software found</p>
                                        <p className="text-sm">Try adjusting your filters</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredSoftware.map((sw) => (
                                    <tr
                                        key={sw.id}
                                        className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 ${selectedSoftwareIds.has(sw.id) ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                                    >
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <input
                                                type="checkbox"
                                                checked={selectedSoftwareIds.has(sw.id)}
                                                onChange={() => handleToggleSelection(sw.id)}
                                                className="rounded"
                                            />
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="text-sm font-medium text-gray-900 dark:text-white">
                                                {sw.name}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm text-gray-900 dark:text-gray-300">
                                                {sw.currentVersion}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm font-semibold text-gray-900 dark:text-white">
                                                {sw.latestVersion}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="flex items-center gap-2">
                                                {sw.updateAvailable ? (
                                                    <>
                                                        <AlertCircleIcon size={16} className="text-orange-500" />
                                                        <span className="text-sm text-orange-600 dark:text-orange-400 font-medium">
                                                            Update Available
                                                        </span>
                                                        {getSeverityBadge(sw.severity)}
                                                    </>
                                                ) : (
                                                    <>
                                                        <CheckIcon size={16} className="text-green-500" />
                                                        <span className="text-sm text-green-600 dark:text-green-400">
                                                            Up-to-date
                                                        </span>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm text-gray-600 dark:text-gray-400">
                                                {sw.assetName}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm text-gray-600 dark:text-gray-400">
                                                {sw.publisher}
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Summary */}
            <div className="text-sm text-gray-500 dark:text-gray-400 text-center">
                Showing {filteredSoftware.length} of {softwareList.length} installed software packages
            </div>

            {/* Deployment Modal */}
            <DeploySoftwareUpdatesModal
                isOpen={isDeployModalOpen}
                onClose={() => setIsDeployModalOpen(false)}
                softwareToUpdate={filteredSoftware.filter(sw => selectedSoftwareIds.has(sw.id))}
                onDeploy={handleConfirmDeployment}
            />
        </div>
    );
};
