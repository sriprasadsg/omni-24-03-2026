import React from 'react';

export interface OutdatedPackage {
    name: string;
    current_version: string;
    latest_version: string;
    update_status: 'major' | 'minor' | 'patch' | 'up-to-date' | 'unknown';
    pkg_type: string;
    is_outdated: boolean;
    agent_id?: string;
}

const versionBadgeStyles: Record<string, string> = {
    major: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    minor: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
    patch: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    'up-to-date': 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
    unknown: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const pkgTypeStyles: Record<string, string> = {
    pip: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
    npm: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    apt: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
    winget: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
    windows_update: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300',
};

const severityBorderColor: Record<string, string> = {
    major: 'border-l-red-500', minor: 'border-l-amber-500', patch: 'border-l-blue-500',
};

interface Props {
    outdatedPackages: OutdatedPackage[];
    outdatedMeta: { total_checked: number; scanned_at: string } | null;
    outdatedLoading: boolean;
    scanLoading: boolean;
    scanMessage: string;
    pkgTypeFilter: string;
    updatingPkgs: Set<string>;
    bulkUpdating: boolean;
    onFilterChange: (type: string) => void;
    onTriggerScan: () => void;
    onBulkUpdate: () => void;
    onUpdateSoftware: (pkgName: string, pkgType: string) => void;
    onRefresh: () => void;
}

export function PatchSoftwareUpdatesTab({
    outdatedPackages, outdatedMeta, outdatedLoading, scanLoading, scanMessage,
    pkgTypeFilter, updatingPkgs, bulkUpdating,
    onFilterChange, onTriggerScan, onBulkUpdate, onUpdateSoftware, onRefresh,
}: Props) {
    return (
        <div className="space-y-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 flex flex-wrap gap-3 items-center justify-between">
                <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Filter by type:</span>
                    {['all', 'pip', 'npm', 'apt', 'winget'].map(type => (
                        <button key={type} onClick={() => onFilterChange(type)}
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
                    <button onClick={onTriggerScan} disabled={scanLoading}
                        className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2">
                        {scanLoading ? (
                            <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Scanning...</>
                        ) : '🔍 Trigger Live Scan'}
                    </button>
                    <button onClick={onBulkUpdate} disabled={bulkUpdating || outdatedPackages.length === 0}
                        className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2">
                        {bulkUpdating ? (
                            <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Queuing...</>
                        ) : '🚀 Bulk Update All'}
                    </button>
                    <button onClick={onRefresh} disabled={outdatedLoading}
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
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${pkgTypeStyles[pkg.pkg_type] ?? 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'}`}>{pkg.pkg_type}</span>
                                    </td>
                                    <td className="px-4 py-3 font-mono text-sm text-gray-500 dark:text-gray-400">{pkg.current_version}</td>
                                    <td className="px-4 py-3 font-mono text-sm text-emerald-600 dark:text-emerald-400 font-semibold">{pkg.latest_version}</td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${versionBadgeStyles[pkg.update_status] ?? versionBadgeStyles.unknown}`}>
                                            {pkg.update_status.charAt(0).toUpperCase() + pkg.update_status.slice(1)}
                                        </span>
                                    </td>
                                    <td className="px-6 py-3 text-right whitespace-nowrap">
                                        <button onClick={() => onUpdateSoftware(pkg.name, pkg.pkg_type)}
                                            disabled={updatingPkgs.has(`${pkg.name}-${pkg.pkg_type}`)}
                                            className="inline-flex items-center px-3 py-1 text-xs font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors">
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
    );
}
