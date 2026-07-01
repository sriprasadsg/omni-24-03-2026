
import React, { useState } from 'react';
import { Asset } from '../types';
import { CogIcon, ShieldSearchIcon, ServerIcon } from './icons';

interface AssetListProps {
  assets: Asset[];
  selectedAsset: Asset | null;
  onSelectAsset: (asset: Asset) => void;
  onRunVulnerabilityScan: (assetId: string) => Promise<void>;
}

export const AssetList: React.FC<AssetListProps> = ({ assets, selectedAsset, onSelectAsset, onRunVulnerabilityScan }) => {
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
    <div className="p-2 space-y-2 max-h-[600px] overflow-y-auto">
      {assets.map(asset => {
        const criticalPatches = asset.patchStatus?.critical || 0;
        const highPatches = asset.patchStatus?.high || 0;
        const isScanning = scanningAssetIds.has(asset.id);

        return (
          <button
            key={asset.id}
            onClick={() => onSelectAsset(asset)}
            className={`w-full text-left p-3 rounded-lg transition-colors duration-150 ${selectedAsset?.id === asset.id
              ? 'bg-primary-100 dark:bg-primary-900/50 ring-2 ring-primary-500'
              : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
              }`}
          >
            <div className="flex justify-between items-start">
              <p className="font-semibold text-gray-800 dark:text-gray-100 truncate">{asset.hostname}</p>
              <div className="flex items-center space-x-1.5 flex-shrink-0 ml-2">
                {criticalPatches > 0 && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300">
                    {criticalPatches}C
                  </span>
                )}
                {highPatches > 0 && (
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300">
                    {highPatches}H
                  </span>
                )}
                <div
                  onClick={(e) => handleScanClick(e, asset.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleScanClick(e as any, asset.id);
                    }
                  }}
                  className={`p-1.5 text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400 cursor-pointer ${isScanning ? 'cursor-wait opacity-50 pointer-events-none' : ''}`}
                  title="Run Vulnerability Scan"
                >
                  {isScanning ? <CogIcon size={14} className="animate-spin" /> : <ShieldSearchIcon size={14} />}
                </div>
              </div>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 flex items-center">
              <span>{asset.osName} {asset.osVersion}</span>
              <span className="mx-2">•</span>
              <span className="font-mono text-xs">{asset.ipAddress}</span>
            </p>
            {asset.agentStatus && (
              <div className="mt-2 flex items-center text-xs">
                <ServerIcon size={12} className="mr-1 text-gray-400" />
                <span className={`font-medium ${asset.agentStatus === 'Online' ? 'text-green-600 dark:text-green-400' :
                  asset.agentStatus === 'Error' ? 'text-red-600 dark:text-red-400' :
                    'text-gray-500'
                  }`}>
                  Agent: {asset.agentStatus} {asset.agentVersion && `(v${asset.agentVersion})`}
                </span>
                {asset.agentCapabilities && asset.agentCapabilities.length > 0 && (
                  <span className="ml-2 px-1.5 py-0.5 bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded text-[10px] font-mono cursor-help" title={`Capabilities: ${asset.agentCapabilities.join(', ')}`}>
                    {asset.agentCapabilities.length} caps
                  </span>
                )}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
};
