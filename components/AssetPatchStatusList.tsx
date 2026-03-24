import React from 'react';
// Asset Patch Status List Component
import { Asset } from '../types';

interface AssetPatchStatusListProps {
    assets: Asset[];
    selectedAssetIds: Set<string>;
    onToggleSelection: (assetId: string) => void;
    onToggleAll: (assetIds: string[]) => void;
}

export const AssetPatchStatusList: React.FC<AssetPatchStatusListProps> = ({ assets, selectedAssetIds, onToggleSelection, onToggleAll }) => {
    const allSelected = assets.length > 0 && assets.every(a => selectedAssetIds.has(a.id));

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                    <tr>
                        <th scope="col" className="p-4">
                            <div className="flex items-center">
                                <input id="checkbox-all-assets" type="checkbox" checked={allSelected} onChange={() => onToggleAll(assets.map(a => a.id))} className="w-4 h-4 text-primary-600 bg-gray-100 border-gray-300 rounded focus:ring-primary-500" />
                                <label htmlFor="checkbox-all-assets" className="sr-only">checkbox</label>
                            </div>
                        </th>
                        <th scope="col" className="px-6 py-3">Hostname</th>
                        <th scope="col" className="px-6 py-3">OS</th>
                        <th scope="col" className="px-6 py-3">Pending Patches</th>
                        <th scope="col" className="px-6 py-3">Last Scanned</th>
                    </tr>
                </thead>
                <tbody>
                    {assets.map(asset => (
                        <tr key={asset.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                            <td className="w-4 p-4">
                                <div className="flex items-center">
                                    <input id={`checkbox-asset-${asset.id}`} type="checkbox" checked={selectedAssetIds.has(asset.id)} onChange={() => onToggleSelection(asset.id)} className="w-4 h-4 text-primary-600 bg-gray-100 border-gray-300 rounded focus:ring-primary-500" />
                                    <label htmlFor={`checkbox-asset-${asset.id}`} className="sr-only">checkbox</label>
                                </div>
                            </td>
                            <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{asset.hostname}</td>
                            <td className="px-6 py-4">{asset.osName}</td>
                            <td className="px-6 py-4 text-center">
                                {asset.patchStatus ? (
                                    (asset.patchStatus.critical || 0) +
                                    (asset.patchStatus.high || 0) +
                                    (asset.patchStatus.medium || 0) +
                                    (asset.patchStatus.low || 0)
                                ) : 0}
                            </td>
                            <td className="px-6 py-4">
                                {asset.lastScanned ? new Date(asset.lastScanned).toLocaleString() : 'Never'}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};
