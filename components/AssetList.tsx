
import React, { useState } from 'react';
import { Asset } from '../types';
import { CogIcon, ShieldSearchIcon } from './icons';

interface AssetListProps {
  assets: Asset[];
  selectedAsset: Asset | null;
  onSelectAsset: (asset: Asset) => void;
  onRunVulnerabilityScan: (assetId: string) => Promise<void>;
  /** Bulk selection (checkboxes) — rendered only when both are given. */
  checkedIds?: Set<string>;
  onToggleChecked?: (assetId: string) => void;
}

export const AssetList: React.FC<AssetListProps> = ({ assets, selectedAsset, onSelectAsset, onRunVulnerabilityScan, checkedIds, onToggleChecked }) => {
  const selectable = !!checkedIds && !!onToggleChecked;
  const [scanningAssetIds, setScanningAssetIds] = useState<Set<string>>(new Set());

  const handleScanClick = async (e: React.MouseEvent, assetId: string) => {
    e.stopPropagation();
    setScanningAssetIds(prev => new Set(prev).add(assetId));
    try {
      await onRunVulnerabilityScan(assetId);
    } finally {
      setScanningAssetIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(assetId);
        return newSet;
      });
    }
  };

  return (
    <ul className="p-2 space-y-1">
      {assets.map(asset => {
        const criticalPatches = asset.patchStatus?.critical || 0;
        const highPatches = asset.patchStatus?.high || 0;
        const isScanning = scanningAssetIds.has(asset.id);
        const isSelected = selectedAsset?.id === asset.id;

        // The scan control sits beside the row button, not inside it: a button nested in a button
        // is invalid and screen readers announce only the outer one.
        return (
          <li key={asset.id} className="relative">
            {selectable && (
              <label className="absolute left-1 top-1.5 z-[1] grid place-items-center h-9 w-9 rounded-lg cursor-pointer hover:bg-gray-900/[0.04] dark:hover:bg-white/[0.05]">
                <input
                  type="checkbox"
                  checked={checkedIds!.has(asset.id)}
                  onChange={() => onToggleChecked!(asset.id)}
                  aria-label={`Select ${asset.hostname}`}
                  className="h-4 w-4 rounded accent-cyan-600 cursor-pointer"
                />
              </label>
            )}
            <button
              onClick={() => onSelectAsset(asset)}
              aria-current={isSelected ? 'true' : undefined}
              className={`w-full text-left ${selectable ? 'pl-11' : 'pl-3.5'} pr-12 py-3 rounded-xl transition-colors duration-150 ${isSelected
                ? 'bg-primary-500/[0.08] ring-1 ring-inset ring-primary-500/30 dark:bg-primary-400/10'
                : 'hover:bg-gray-100/80 dark:hover:bg-white/[0.04]'
                }`}
            >
              {isSelected && <span className="absolute left-0 top-3 bottom-3 w-[3px] rounded-full bg-primary-500 dark:bg-primary-400" aria-hidden="true" />}
              <div className="flex items-center gap-2 min-w-0">
                <p className="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">{asset.hostname}</p>
                {criticalPatches > 0 && (
                  <span title={`${criticalPatches} critical patches pending`} className="flex-shrink-0 px-1.5 py-px rounded-full text-[11px] font-semibold tabular-nums text-red-700 dark:text-red-300 bg-red-500/10 ring-1 ring-inset ring-red-500/20">
                    {criticalPatches}C
                  </span>
                )}
                {highPatches > 0 && (
                  <span title={`${highPatches} high patches pending`} className="flex-shrink-0 px-1.5 py-px rounded-full text-[11px] font-semibold tabular-nums text-orange-700 dark:text-orange-300 bg-orange-500/10 ring-1 ring-inset ring-orange-500/20">
                    {highPatches}H
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center min-w-0">
                <span className="truncate">{asset.osName} {asset.osVersion}</span>
                <span className="mx-1.5 text-gray-300 dark:text-gray-600">·</span>
                <span className="font-mono flex-shrink-0">{asset.ipAddress}</span>
              </p>
              {asset.agentStatus && (
                <div className="mt-1.5 flex items-center text-xs">
                  <span className={`h-1.5 w-1.5 rounded-full mr-1.5 ${asset.agentStatus === 'Online' ? 'bg-emerald-500' : asset.agentStatus === 'Error' ? 'bg-red-500' : 'bg-gray-400'}`} aria-hidden="true" />
                  <span className={`font-medium ${asset.agentStatus === 'Online' ? 'text-emerald-700 dark:text-emerald-400' :
                    asset.agentStatus === 'Error' ? 'text-red-600 dark:text-red-400' :
                      'text-gray-500 dark:text-gray-400'
                    }`}>
                    Agent {asset.agentStatus.toLowerCase()}{asset.agentVersion && <span className="font-normal text-gray-500 dark:text-gray-400"> · v{asset.agentVersion}</span>}
                  </span>
                  {asset.agentCapabilities && asset.agentCapabilities.length > 0 && (
                    <span className="ml-2 px-1.5 py-px rounded-md text-[10px] font-mono text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06] cursor-help" title={`Capabilities: ${asset.agentCapabilities.join(', ')}`}>
                      {asset.agentCapabilities.length} caps
                    </span>
                  )}
                </div>
              )}
            </button>
            <button
              onClick={(e) => handleScanClick(e, asset.id)}
              disabled={isScanning}
              aria-label={`Scan ${asset.hostname} for vulnerabilities`}
              title="Run vulnerability scan"
              className="absolute top-2 right-2 grid place-items-center h-8 w-8 rounded-lg text-gray-500 hover:text-primary-600 hover:bg-primary-500/10 dark:text-gray-400 dark:hover:text-primary-400 transition-colors disabled:cursor-wait disabled:opacity-60"
            >
              {isScanning ? <CogIcon size={15} className="animate-spin" /> : <ShieldSearchIcon size={15} />}
            </button>
          </li>
        );
      })}
    </ul>
  );
};
