import React, { useState, useEffect } from 'react';
import { CheckCircle2, Circle } from 'lucide-react';
import { ShieldCheckIcon, InfoIcon, ChevronDownIcon, XCircleIcon, AlertTriangleIcon, ShieldIcon } from './icons';
import { fetchComplianceScore } from '../services/apiService';
import { ComplianceScorePayload, FrameworkScore } from '../types';

function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  return new Date(iso).toLocaleString();
}
function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 50) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}
function barColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 50) return 'bg-amber-500';
  return 'bg-red-500';
}

interface TooltipProps {
  visible: boolean; onMouseEnter: () => void; onMouseLeave: () => void;
  onFocus: () => void; onBlur: () => void;
}

const SeverityWeightTooltip: React.FC<TooltipProps> = ({
  visible, onMouseEnter, onMouseLeave, onFocus, onBlur,
}) => (
  <span className="relative inline-flex items-center">
    <span
      role="button"
      tabIndex={0}
      aria-label="Severity weight explanation"
      className="cursor-pointer"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onFocus(); }}
    >
      <InfoIcon size={16} className="ml-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" />
    </span>
    {visible && (
      <div className="absolute z-10 w-64 p-3 bg-gray-900 dark:bg-gray-700 text-white rounded-lg shadow-xl text-sm bottom-full left-1/2 -translate-x-1/2 mb-2">
        <p className="text-xs font-semibold mb-2">Severity-Weighted Score</p>
        <div className="space-y-1">
          {([
            ['Critical', 'bg-red-600', '×4'],
            ['High', 'bg-orange-500', '×3'],
            ['Medium', 'bg-yellow-500 text-gray-900', '×2'],
            ['Low', 'bg-blue-500', '×1'],
          ] as [string, string, string][]).map(([label, bg, weight]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-xs text-gray-300 w-20">{label}</span>
              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${bg}`}>{weight}</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-2 border-t border-gray-600 pt-2">
          Score = sum of passing weights ÷ sum of all weights × 100.
        </p>
        <p className="text-xs text-gray-400 mt-1">
          Controls with no monitored asset evidence are excluded.
        </p>
      </div>
    )}
  </span>
);

export const ComplianceScorePanel: React.FC = () => {
  const [data, setData] = useState<ComplianceScorePayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<boolean>(false);
  const [expandedFramework, setExpandedFramework] = useState<string | null>(null);
  const [tooltipVisible, setTooltipVisible] = useState<boolean>(false);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchComplianceScore().then(result => {
      if (cancelled) return;
      if (result === null) setError(true);
      else setData(result);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const totalPassing = data ? data.frameworks.reduce((s, f) => s + f.passing, 0) : 0;
  const totalFailing = data ? data.frameworks.reduce((s, f) => s + f.failing, 0) : 0;
  const totalPartial = data ? data.frameworks.reduce((s, f) => s + f.partial, 0) : 0;
  const totalEvaluated = data ? data.frameworks.reduce((s, f) => s + f.total_controls, 0) : 0;

  const panelHeader = (
    <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center">
      <ShieldCheckIcon size={20} className="text-indigo-500 mr-2" aria-hidden="true" />
      <span className="text-lg font-semibold">Compliance Score</span>
      <SeverityWeightTooltip
        visible={tooltipVisible}
        onMouseEnter={() => setTooltipVisible(true)}
        onMouseLeave={() => setTooltipVisible(false)}
        onFocus={() => setTooltipVisible(true)}
        onBlur={() => setTooltipVisible(false)}
      />
    </div>
  );

  if (loading) {
    return (
      <div
        className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700"
        aria-busy="true"
      >
        {panelHeader}
        <div className="p-4">
          <span className="sr-only">Loading compliance score</span>
          <div className="animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg h-20 w-full mb-4" aria-hidden="true" />
          {[1, 2, 3].map(i => (
            <div key={i} className="animate-pulse h-10 bg-gray-100 dark:bg-gray-700/50 rounded mb-2" aria-hidden="true" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        {panelHeader}
        <div className="p-4" role="alert">
          <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-900/20">
            <div className="flex items-center">
              <AlertTriangleIcon size={20} className="text-amber-500 mr-2" aria-hidden="true" />
              <span className="text-sm font-semibold text-amber-700 dark:text-amber-400">Score unavailable</span>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              The compliance score could not be loaded. Refresh the page to try again.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (data && totalEvaluated === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        {panelHeader}
        <div className="flex flex-col items-center justify-center py-8 px-4">
          <ShieldIcon size={32} className="text-gray-300 dark:text-gray-600" aria-hidden="true" />
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mt-2">No monitored controls yet</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
            Upload evidence or configure asset compliance to see your score here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      {panelHeader}
      <div className="p-4">
        <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg mb-4">
          <div>
            <p className={`text-3xl font-bold ${data ? scoreColor(data.overall_score) : ''}`}>
              {data ? `${data.overall_score}%` : '—'}
            </p>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">Severity-weighted score</p>
          </div>
          <div className="text-right space-y-1">
            <p className="text-sm text-green-600 dark:text-green-400">
              <span className="inline-block w-2 h-2 rounded-full mr-1 bg-green-500" />
              {totalPassing} Passing
            </p>
            <p className="text-sm text-red-600 dark:text-red-400">
              <span className="inline-block w-2 h-2 rounded-full mr-1 bg-red-500" />
              {totalFailing} Failing
            </p>
            <p className="text-sm text-amber-600 dark:text-amber-400">
              <span className="inline-block w-2 h-2 rounded-full mr-1 bg-amber-500" />
              {totalPartial} Partial
            </p>
          </div>
        </div>

        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {data && data.frameworks.map((fw: FrameworkScore) => {
            const expanded = expandedFramework === fw.framework_id;
            return (
              <div key={fw.framework_id}>
                <button
                  className="w-full flex items-center p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors duration-150 border-t border-gray-100 dark:border-gray-700 min-h-[44px]"
                  aria-expanded={expanded}
                  aria-controls={`${fw.framework_id}-detail`}
                  aria-label={expanded ? `Collapse ${fw.framework_name} breakdown` : `Expand ${fw.framework_name} breakdown`}
                  onClick={() => setExpandedFramework(expanded ? null : fw.framework_id)}
                >
                  <span className="w-24 text-sm font-medium text-gray-800 dark:text-white text-left">
                    {fw.short_name}
                  </span>
                  <span className="flex-1 mx-4 h-1.5 rounded-full bg-gray-200 dark:bg-gray-700">
                    <span
                      className={`block h-full rounded-full ${barColor(fw.score)}`}
                      style={{ width: `${fw.score}%` }}
                    />
                  </span>
                  <span className={`w-12 text-right text-sm font-medium ${scoreColor(fw.score)}`}>
                    {fw.score}%
                  </span>
                  <ChevronDownIcon
                    size={16}
                    className={`text-gray-400 ml-2 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
                    aria-hidden="true"
                  />
                </button>
                {expanded && (
                  <div
                    id={`${fw.framework_id}-detail`}
                    className="bg-gray-50 dark:bg-gray-700/30 px-4 py-3 space-y-1"
                  >
                    <p className="flex items-center text-sm">
                      <CheckCircle2 size={16} className="mr-2 text-green-500" aria-hidden="true" />
                      <span className="font-medium">{fw.passing}</span>&nbsp;controls passing
                    </p>
                    <p className="flex items-center text-sm">
                      <XCircleIcon size={16} className="mr-2 text-red-500" aria-hidden="true" />
                      <span className="font-medium">{fw.failing}</span>&nbsp;controls failing
                    </p>
                    <p className="flex items-center text-sm">
                      <Circle size={16} className="mr-2 text-amber-500" aria-hidden="true" />
                      <span className="font-medium">{fw.partial}</span>&nbsp;controls partial
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      {data && (
        <p className="p-4 pt-2 text-xs text-gray-400 dark:text-gray-500">
          Score last computed: {relativeTime(data.computed_at)}
        </p>
      )}
    </div>
  );
};
