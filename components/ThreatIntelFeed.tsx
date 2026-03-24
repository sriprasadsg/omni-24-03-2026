
import React from 'react';
import { ThreatIntelResult } from '../types';
import { ShieldSearchIcon } from './icons';

interface ThreatIntelFeedProps {
  feed: ThreatIntelResult[];
  onViewReport: (result: ThreatIntelResult) => void;
}

const VerdictIndicator: React.FC<{ verdict: ThreatIntelResult['verdict'] }> = ({ verdict }) => {
    const classes = {
        Malicious: 'bg-red-500',
        Suspicious: 'bg-amber-500',
        Harmless: 'bg-green-500',
    };
    return <span className={`inline-block h-2 w-2 rounded-full ${classes[verdict] || 'bg-gray-400'}`} title={verdict}></span>;
};

export const ThreatIntelFeed: React.FC<ThreatIntelFeedProps> = ({ feed, onViewReport }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 h-full flex flex-col">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <h3 className="text-lg font-semibold flex items-center">
          <ShieldSearchIcon className="mr-2 text-primary-500" />
          Live Threat Intelligence Feed
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">Powered by VirusTotal</p>
      </div>
      <div className="p-4 space-y-3 flex-grow overflow-y-auto max-h-[350px]">
        {feed.length === 0 && (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>No threat intelligence lookups yet. Live feed will populate automatically.</p>
          </div>
        )}
        {feed.map(item => (
          <div key={item.id} className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded-md">
            <div className="flex justify-between items-center">
                <div className="flex items-center space-x-2 overflow-hidden">
                    <VerdictIndicator verdict={item.verdict} />
                    <p className="font-mono text-xs text-gray-800 dark:text-gray-200 truncate">{item.artifact}</p>
                </div>
                <button 
                    onClick={() => onViewReport(item)}
                    className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline flex-shrink-0 ml-2"
                >
                    Details
                </button>
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex justify-between">
                <span>{item.verdict} ({item.detectionRatio})</span>
                <span>{new Date(item.scanDate).toLocaleTimeString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
