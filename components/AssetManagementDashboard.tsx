import React, { useState, useEffect, useMemo } from 'react';
import { Asset, Patch, Filter, VulnerabilityScanJob } from '../types';
import { AssetList } from './AssetList';
import { AssetDetail } from './AssetDetail';
import { DatabaseIcon, ShieldSearchIcon, XCircleIcon, FilterIcon, ClockIcon } from './icons';
import { ScheduleScanModal } from './ScheduleScanModal';
import { VulnerabilityScanJobs } from './VulnerabilityScanJobs';

interface AssetManagementDashboardProps {
    assets: Asset[];
    patches: Patch[];
    onRunVulnerabilityScan: (assetId: string) => Promise<void>;
    filters: Filter[];
    onClearFilters: () => void;
    vulnerabilityScanJobs: VulnerabilityScanJob[];
    onScheduleVulnerabilityScan: (assetIds: string[], scanType: 'Immediate' | 'Scheduled', scheduleTime?: string) => Promise<void>;
    onDeleteAsset: (asset: Asset) => void;
}

export const AssetManagementDashboard: React.FC<AssetManagementDashboardProps> = ({
    assets,
    patches,
    onRunVulnerabilityScan,
    filters,
    onClearFilters,
    vulnerabilityScanJobs,
    onScheduleVulnerabilityScan,
    onDeleteAsset
}) => {
    const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
    const [osFilter, setOsFilter] = useState<'All' | 'Linux' | 'Windows'>('All');

    // Scheduling state
    const [isScanModalOpen, setIsScanModalOpen] = useState(false);
    const [assetsToScan, setAssetsToScan] = useState<string[]>([]);

    const osTypes = useMemo(() => {
        const types = new Set(assets.map(a => (a.osName || '').includes('Windows') ? 'Windows' : 'Linux'));
        return Array.from(types);
    }, [assets]);

    // Deduplicate assets by ID (keep most recent based on lastScanned)
    const deduplicatedAssets = useMemo(() => {
        const assetMap = new Map<string, Asset>();
        assets.forEach(asset => {
            const existing = assetMap.get(asset.id);
            if (!existing) {
                assetMap.set(asset.id, asset);
            } else {
                // Keep the one with the most recent lastScanned timestamp
                const existingDate = new Date(existing.lastScanned || 0).getTime();
                const currentDate = new Date(asset.lastScanned || 0).getTime();
                if (currentDate > existingDate) {
                    assetMap.set(asset.id, asset);
                }
            }
        });
        return Array.from(assetMap.values());
    }, [assets]);

    const filteredAssets = useMemo(() => {
        let tempAssets = [...deduplicatedAssets];

        // Apply local OS filter
        if (osFilter !== 'All') {
            tempAssets = tempAssets.filter(asset => {
                const os = (asset.osName || '').includes('Windows') ? 'Windows' : 'Linux';
                return os === osFilter;
            });
        }

        // Apply AI-driven filters from props
        if (filters.length === 0) {
            return tempAssets;
        }

        return tempAssets.filter(asset => {
            return filters.every(filter => {
                if (filter.type === 'vulnerability_severity') {
                    return asset.vulnerabilities?.some(v => v.severity === filter.value && v.status === 'Open') ?? false;
                }
                return true;
            });
        });
    }, [deduplicatedAssets, filters, osFilter]);

    useEffect(() => {
        if (selectedAsset) {
            // Check if the currently selected asset has been updated in the new list
            const updatedAsset = filteredAssets.find(a => a.id === selectedAsset.id);
            if (updatedAsset && updatedAsset !== selectedAsset) {
                setSelectedAsset(updatedAsset);
            } else if (!updatedAsset) {
                // Selected asset no longer exists in filter
                setSelectedAsset(filteredAssets[0] || null);
            }
        } else if (filteredAssets.length > 0) {
            // Initial selection
            setSelectedAsset(filteredAssets[0] || null);
        }
    }, [filteredAssets, selectedAsset]);

    const osDistribution = filteredAssets.reduce((acc, asset) => {
        const os = (asset.osName || '').includes('Windows') ? 'Windows' : 'Linux';
        acc[os] = (acc[os] || 0) + 1;
        return acc;
    }, {} as Record<string, number>);

    const outdatedAssets = filteredAssets.filter(a => {
        if (!a.lastScanned) return true; // Never scanned is outdated
        const lastScanned = new Date(a.lastScanned);
        if (isNaN(lastScanned.getTime())) return true; // Invalid date is outdated

        const hoursSinceScan = (new Date().getTime() - lastScanned.getTime()) / (1000 * 60 * 60);
        return hoursSinceScan > 24;
    });
    const assetsNeedingScanCount = outdatedAssets.length;

    const totalVulnerabilities = filteredAssets.reduce((sum, asset) => sum + (asset.vulnerabilities?.filter(v => v.status === 'Open').length || 0), 0);

    const handleOpenScanModal = (target: 'all' | 'outdated') => {
        if (target === 'outdated') {
            setAssetsToScan(outdatedAssets.map(a => a.id));
        } else {
            setAssetsToScan(filteredAssets.map(a => a.id));
        }
        setIsScanModalOpen(true);
    };

    const handleScheduleScan = async (scanType: 'Immediate' | 'Scheduled', scheduleTime?: string) => {
        try {
            await onScheduleVulnerabilityScan(assetsToScan, scanType, scheduleTime);
        } catch (error) {
            console.error('Failed to schedule scan:', error);
            alert(`Failed to schedule vulnerability scan: ${error instanceof Error ? error.message : 'Unknown error'}`);
        } finally {
            setIsScanModalOpen(false);
            setAssetsToScan([]);
        }
    };

    const handleSelectAsset = (asset: Asset) => {
        setSelectedAsset(asset);
    };


    return (
        <div className="space-y-8 animate-fade-in p-2">
            <div className="flex flex-col lg:flex-row justify-between lg:items-center gap-6">
                <header>
                    <h2 className="text-4xl font-black bg-gradient-to-r from-blue-600 via-indigo-600 to-violet-600 bg-clip-text text-transparent flex items-center gap-3 italic uppercase tracking-tighter">
                        <DatabaseIcon size={36} className="text-blue-500" />
                        Asset Management
                    </h2>
                    <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg font-medium">
                        Complete enterprise inventory of hardware and virtualized infrastructure.
                    </p>
                </header>
                <div className="flex flex-wrap gap-3">
                    {assetsNeedingScanCount > 0 && (
                        <button
                            onClick={() => handleOpenScanModal('outdated')}
                            className="flex items-center justify-center px-6 py-3 text-sm font-black uppercase tracking-widest text-white bg-gradient-to-r from-amber-500 to-orange-600 rounded-xl hover:scale-105 transition-all shadow-lg shadow-amber-500/20"
                        >
                            <ClockIcon size={18} className="mr-2" />
                            Schedule Audit ({assetsNeedingScanCount})
                        </button>
                    )}
                    <button
                        onClick={() => handleOpenScanModal('all')}
                        className="flex items-center justify-center px-6 py-3 text-sm font-black uppercase tracking-widest text-white bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl hover:scale-105 transition-all shadow-lg shadow-blue-500/20"
                    >
                        <ShieldSearchIcon size={18} className="mr-2" />
                        Scan Network
                    </button>
                </div>
            </div>

            {filters.length > 0 && (
                <div className="glass-premium p-4 rounded-2xl flex items-center justify-between border-l-4 border-primary-500 animate-slide-in">
                    <div className="flex items-center space-x-3">
                        <div className="bg-primary-500/10 p-2 rounded-lg">
                            <FilterIcon size={16} className="text-primary-500" />
                        </div>
                        <span className="font-black text-[10px] text-gray-400 uppercase tracking-widest">Active Neural Filters</span>
                        <div className="flex gap-2">
                            {filters.map((filter, index) => (
                                <span key={index} className="px-3 py-1 text-[10px] font-black rounded-lg bg-primary-500/10 text-primary-600 dark:text-primary-400 uppercase tracking-widest border border-primary-500/20">
                                    {filter.type}: {filter.value}
                                </span>
                            ))}
                        </div>
                    </div>
                    <button onClick={onClearFilters} className="p-2 hover:bg-red-500/10 text-gray-400 hover:text-red-500 rounded-lg transition-colors">
                        <XCircleIcon size={20} />
                    </button>
                </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="glass-premium p-6 rounded-3xl group hover:scale-105 transition-all border-l-4 border-blue-500">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Total Assets</p>
                    <p className="text-3xl font-black text-gray-800 dark:text-gray-100 italic tracking-tighter">{filteredAssets.length}</p>
                </div>
                <div className="glass-premium p-6 rounded-3xl group hover:scale-105 transition-all border-l-4 border-indigo-500">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">OS Distribution</p>
                    <p className="text-lg font-black text-gray-800 dark:text-gray-100 uppercase tracking-tighter italic">
                        <span className="text-blue-500">{osDistribution['Linux'] || 0}L</span> / <span className="text-indigo-500">{osDistribution['Windows'] || 0}W</span>
                    </p>
                </div>
                <div className="glass-premium p-6 rounded-3xl group hover:scale-105 transition-all border-l-4 border-rose-500">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Open Vulnerabilities</p>
                    <p className="text-3xl font-black text-rose-500 italic tracking-tighter">{totalVulnerabilities}</p>
                </div>
                <div className="glass-premium p-6 rounded-3xl group hover:scale-105 transition-all border-l-4 border-amber-500">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Stale Scans</p>
                    <p className="text-3xl font-black text-amber-500 italic tracking-tighter">{assetsNeedingScanCount}</p>
                </div>
            </div>

            <div className="glass-premium rounded-3xl p-6 flex flex-col md:flex-row items-center gap-6 border border-white/10">
                <div className="flex items-center gap-3">
                    <div className="bg-white/5 p-3 rounded-xl border border-white/10">
                        <FilterIcon size={20} className="text-blue-500" />
                    </div>
                    <label htmlFor="os-filter" className="text-sm font-black uppercase tracking-widest text-gray-500 italic">
                        OS Filter
                    </label>
                </div>
                <select
                    id="os-filter"
                    value={osFilter}
                    onChange={(e) => setOsFilter(e.target.value as 'All' | 'Linux' | 'Windows')}
                    className="flex-1 lg:max-w-xs px-6 py-3 bg-black/5 dark:bg-white/5 border border-white/10 rounded-xl text-sm font-bold focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                >
                    <option value="All">All Biological/Virtual Targets</option>
                    {osTypes.map(os => (
                        <option key={os} value={os}>{os}</option>
                    ))}
                </select>
            </div>


            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-1">
                    <div className="glass-premium rounded-3xl shadow-2xl border border-white/10 overflow-hidden flex flex-col h-[700px]">
                        <div className="p-6 border-b border-white/10 bg-black/5 dark:bg-white/5 flex items-center justify-between">
                            <h3 className="text-xl font-black flex items-center gap-2 italic uppercase tracking-tighter">
                                <DatabaseIcon size={22} className="text-blue-500" />
                                Asset Registry
                            </h3>
                            <span className="px-3 py-1 bg-blue-500/10 text-blue-500 rounded-lg text-[10px] font-black uppercase tracking-widest border border-blue-500/20">{filteredAssets.length}</span>
                        </div>
                        <div className="flex-1 overflow-y-auto">
                            <AssetList
                                assets={filteredAssets}
                                selectedAsset={selectedAsset}
                                onSelectAsset={handleSelectAsset}
                                onRunVulnerabilityScan={onRunVulnerabilityScan}
                            />
                        </div>
                    </div>
                </div>
                <div className="lg:col-span-2">
                    {selectedAsset ? (
                        <div className="glass-premium rounded-3xl shadow-2xl border border-white/10 overflow-hidden h-[700px] flex flex-col">
                            <AssetDetail asset={selectedAsset} patches={patches} onRunScan={onRunVulnerabilityScan} onDelete={onDeleteAsset} />
                        </div>
                    ) : (
                        <div className="glass-premium rounded-3xl shadow-2xl border border-white/10 h-[700px] flex items-center justify-center">
                            <div className="text-center p-12 space-y-4">
                                <DatabaseIcon size={64} className="mx-auto text-gray-400 opacity-20" />
                                <p className="font-black text-gray-500 uppercase tracking-widest text-lg italic">No Target Selected</p>
                                <p className="text-xs text-gray-400 font-bold uppercase">Select an asset from the registry to engage.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <VulnerabilityScanJobs jobs={vulnerabilityScanJobs} />

            <ScheduleScanModal
                isOpen={isScanModalOpen}
                onClose={() => setIsScanModalOpen(false)}
                onSchedule={handleScheduleScan}
                assetCount={assetsToScan.length}
            />
        </div>
    );
};
