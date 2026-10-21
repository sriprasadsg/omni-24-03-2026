import React from 'react';
import { ThreatIntelResult } from '../types';
import { ShieldSearchIcon } from './icons';

interface ThreatIntelFeedProps {
  feed: ThreatIntelResult[];
  onViewReport: (result: ThreatIntelResult) => void;
}

const verdictPills: Record<string, string> = {
  Malicious: 'text-red-700 dark:text-red-300 bg-red-500/10 ring-red-500/20',
  Suspicious: 'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-amber-500/20',
  Harmless: 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 ring-emerald-500/20',
};
const unknownPill = 'text-gray-700 dark:text-gray-300 bg-gray-500/10 ring-gray-500/20';

const scannedAt = (iso: string) => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export const ThreatIntelFeed: React.FC<ThreatIntelFeedProps> = ({ feed, onViewReport }) => {
  return (
    <section aria-label="Threat intelligence" className="h-full flex flex-col rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
      <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06]">
        <div className="flex items-center justify-between">
          <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <ShieldSearchIcon size={16} className="text-primary-500" />
            Threat intelligence
          </h3>
          <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06]">{feed.length}</span>
        </div>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">VirusTotal lookups</p>
      </div>
      {feed.length === 0 ? (
        <div className="flex-1 grid place-items-center p-8 text-center">
          <div>
            <ShieldSearchIcon size={28} className="mx-auto text-gray-400" />
            <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">No lookups yet</p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Scan an IP or file hash from an event to check it with VirusTotal.</p>
          </div>
        </div>
      ) : (
        <ul className="flex-1 min-h-0 overflow-y-auto max-h-[360px] lg:max-h-none divide-y divide-gray-100 dark:divide-white/[0.06]">
          {feed.map(item => {
            const when = scannedAt(item.scanDate);
            return (
              <li key={item.id} className="px-5 py-3 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[13px] text-gray-900 dark:text-gray-100 truncate" title={item.artifact}>{item.artifact}</p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5 min-w-0">
                    <span className={`flex-shrink-0 px-1.5 py-px rounded-full text-[11px] font-semibold ring-1 ring-inset ${verdictPills[item.verdict] || unknownPill}`}>{item.verdict}</span>
                    <span className="tabular-nums">{item.detectionRatio}</span>
                    {when && (
                      <>
                        <span className="text-gray-300 dark:text-gray-600">·</span>
                        <span className="truncate tabular-nums">{when}</span>
                      </>
                    )}
                  </p>
                </div>
                <button
                  onClick={() => onViewReport(item)}
                  aria-label={`Report for ${item.artifact}`}
                  className="flex-shrink-0 h-8 px-2.5 rounded-lg text-xs font-medium text-primary-700 dark:text-primary-300 hover:bg-primary-500/10 transition-colors"
                >
                  Report
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
