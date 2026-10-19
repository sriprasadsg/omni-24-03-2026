import React, { useState, useEffect, useMemo } from 'react';
import { Asset, Patch, Filter, VulnerabilityScanJob } from '../types';
import { AssetList } from './AssetList';
import { AssetDetail } from './AssetDetail';
import { DatabaseIcon, ShieldSearchIcon, ShieldAlertIcon, XIcon, FilterIcon, ClockIcon, ServerIcon, MonitorIcon } from './icons';
import { ScheduleScanModal } from './ScheduleScanModal';
import { VulnerabilityScanJobs } from './VulnerabilityScanJobs';
import { showToast } from '../utils/toast';

type OsFilter = 'All' | 'Linux' | 'Windows';

const TILE_TONES = {
    primary: 'text-primary-600 dark:text-primary-400 bg-primary-500/10 ring-primary-500/20',
    blue: 'text-blue-600 dark:text-blue-400 bg-blue-500/10 ring-blue-500/20',
    red: 'text-red-600 dark:text-red-400 bg-red-500/10 ring-red-500/20',
    amber: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 ring-amber-500/20',
};

// Spatial Glass stat tile, the same anatomy as the Overview KPI tiles minus the sparkline
// (there is no history behind these counts).
const StatTile: React.FC<{ icon: React.ReactNode; label: string; tone: keyof typeof TILE_TONES; footnote?: React.ReactNode; children: React.ReactNode }> = ({ icon, label, tone, footnote, children }) => (
    <div className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-5 flex flex-col">
        <div className="flex items-center gap-3 min-w-0">
            <span className={`grid place-items-center h-9 w-9 flex-shrink-0 rounded-xl ring-1 ring-inset ${TILE_TONES[tone]}`}>{icon}</span>
            <p className="text-[13px] font-medium text-gray-600 dark:text-gray-400 truncate">{label}</p>
        </div>
        <div className="mt-3">{children}</div>
        {footnote && <p className="mt-auto pt-2 text-xs text-gray-500 dark:text-gray-400">{footnote}</p>}
    </div>
);

const bigNumber = 'text-[32px] leading-none font-semibold tracking-[-0.03em] tabular-nums';

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
    const [osFilter, setOsFilter] = useState<OsFilter>('All');

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
    const assetsWithOpenVulns = filteredAssets.filter(a => a.vulnerabilities?.some(v => v.status === 'Open')).length;
    const onlineAgents = filteredAssets.filter(a => a.agentStatus === 'Online').length;
    const windowsCount = osDistribution['Windows'] || 0;
    const linuxCount = osDistribution['Linux'] || 0;
    const windowsShare = filteredAssets.length ? (windowsCount / filteredAssets.length) * 100 : 0;

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
            showToast(`Failed to schedule vulnerability scan: ${error instanceof Error ? error.message : 'Unknown error'}`, 'error');
        } finally {
            setIsScanModalOpen(false);
            setAssetsToScan([]);
        }
    };

    const handleSelectAsset = (asset: Asset) => {
        setSelectedAsset(asset);
    };


    return (
        <div className="space-y-6 fade-in">
            <div className="flex flex-col md:flex-row justify-between md:items-end gap-4">
                <header>
                    <h2 className="text-[30px] font-semibold tracking-[-0.03em] text-gray-900 dark:text-white">Assets</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Every machine your agents report, with its open vulnerabilities and scan status.
                    </p>
                </header>
                <div className="flex flex-wrap items-center gap-2">
                    {assetsNeedingScanCount > 0 && (
                        <button
                            onClick={() => handleOpenScanModal('outdated')}
                            className="flex items-center gap-2 h-10 px-4 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl transition-all hover:border-amber-500/40 active:scale-[0.98]"
                        >
                            <ClockIcon size={15} className="text-amber-500" />
                            Rescan stale ({assetsNeedingScanCount})
                        </button>
                    )}
                    <button
                        onClick={() => handleOpenScanModal('all')}
                        disabled={filteredAssets.length === 0}
                        className="flex items-center gap-2 h-10 px-5 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <ShieldSearchIcon size={15} />
                        Scan assets ({filteredAssets.length})
                    </button>
                </div>
            </div>

            {filters.length > 0 && (
                <div className="flex items-center justify-between gap-3 rounded-2xl px-4 py-3 bg-primary-500/[0.06] ring-1 ring-inset ring-primary-500/20 slide-up">
                    <div className="flex items-center gap-3 flex-wrap min-w-0">
                        <FilterIcon size={15} className="text-primary-600 dark:text-primary-400 flex-shrink-0" />
                        <span className="text-[13px] font-medium text-gray-700 dark:text-gray-300">Filtered by AI</span>
                        {filters.map((filter, index) => (
                            <span key={index} className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-white/70 dark:bg-white/[0.06] text-primary-700 dark:text-primary-300 ring-1 ring-inset ring-primary-500/25">
                                {filter.type.replace(/_/g, ' ')}: {filter.value}
                            </span>
                        ))}
                    </div>
                    <button onClick={onClearFilters} aria-label="Clear filters" className="grid place-items-center h-8 w-8 flex-shrink-0 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-900/5 dark:hover:text-white dark:hover:bg-white/10 transition-colors">
                        <XIcon size={16} />
                    </button>
                </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
                <StatTile icon={<DatabaseIcon size={18} />} label="Total assets" tone="primary" footnote={`${onlineAgents} with an online agent`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{filteredAssets.length}</p>
                </StatTile>
                <StatTile icon={<MonitorIcon size={18} />} label="Operating systems" tone="blue">
                    <div className="flex items-baseline gap-4">
                        <p><span className={`${bigNumber} text-gray-900 dark:text-white`}>{windowsCount}</span> <span className="text-xs text-gray-500 dark:text-gray-400">Windows</span></p>
                        <p><span className={`${bigNumber} text-gray-900 dark:text-white`}>{linuxCount}</span> <span className="text-xs text-gray-500 dark:text-gray-400">Linux</span></p>
                    </div>
                    <div className="mt-3 flex h-1.5 rounded-full overflow-hidden bg-gray-200 dark:bg-white/10" aria-hidden="true">
                        <div className="bg-blue-500" style={{ width: `${windowsShare}%` }} />
                        <div className="bg-primary-400" style={{ width: `${filteredAssets.length ? 100 - windowsShare : 0}%` }} />
                    </div>
                </StatTile>
                <StatTile icon={<ShieldAlertIcon size={18} />} label="Open vulnerabilities" tone="red" footnote={`on ${assetsWithOpenVulns} ${assetsWithOpenVulns === 1 ? 'asset' : 'assets'}`}>
                    <p className={`${bigNumber} ${totalVulnerabilities > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>{totalVulnerabilities}</p>
                </StatTile>
                <StatTile icon={<ClockIcon size={18} />} label="Stale scans" tone="amber" footnote="Not scanned in the last 24 hours">
                    <p className={`${bigNumber} ${assetsNeedingScanCount > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-gray-900 dark:text-white'}`}>{assetsNeedingScanCount}</p>
                </StatTile>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                <section aria-label="Asset inventory" className="lg:col-span-4 flex flex-col max-h-[520px] lg:max-h-none lg:h-[720px] rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
                    <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06] space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                                <ServerIcon size={16} className="text-primary-500" />
                                Inventory
                            </h3>
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06]">{filteredAssets.length}</span>
                        </div>
                        {osTypes.length > 0 && (
                            <div role="group" aria-label="Filter by operating system" className="inline-flex p-0.5 rounded-xl bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                                {(['All', ...osTypes] as OsFilter[]).map(os => (
                                    <button
                                        key={os}
                                        onClick={() => setOsFilter(os)}
                                        aria-pressed={osFilter === os}
                                        className={`h-7 px-3 rounded-[10px] text-xs font-medium transition-colors ${osFilter === os
                                            ? 'bg-white dark:bg-white/10 text-gray-900 dark:text-white shadow-sm'
                                            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`}
                                    >
                                        {os}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="flex-1 overflow-y-auto">
                        {filteredAssets.length > 0 ? (
                            <AssetList
                                assets={filteredAssets}
                                selectedAsset={selectedAsset}
                                onSelectAsset={handleSelectAsset}
                                onRunVulnerabilityScan={onRunVulnerabilityScan}
                            />
                        ) : (
                            <div className="h-full grid place-items-center p-8 text-center">
                                <div>
                                    <ServerIcon size={28} className="mx-auto text-gray-400" />
                                    <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                                        {deduplicatedAssets.length === 0 ? 'No assets yet' : 'No assets match these filters'}
                                    </p>
                                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                        {deduplicatedAssets.length === 0 ? 'Assets appear here once an agent reports in.' : 'Clear a filter to see more.'}
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </section>
                <div className="lg:col-span-8 lg:h-[720px] min-h-[520px] rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden flex flex-col">
                    {selectedAsset ? (
                        <AssetDetail asset={selectedAsset} patches={patches} onRunScan={onRunVulnerabilityScan} onDelete={onDeleteAsset} />
                    ) : (
                        <div className="flex-1 grid place-items-center p-12 text-center">
                            <div>
                                <DatabaseIcon size={32} className="mx-auto text-gray-400" />
                                <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">No asset selected</p>
                                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Pick one from the inventory to see its details.</p>
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
