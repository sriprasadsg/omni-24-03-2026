

import React, { useState } from 'react';
import { Alert, AlertSeverity } from '../types';
import { AlertTriangleIcon, ChevronDownIcon } from './icons';

interface AlertsPanelProps {
  alerts: Alert[];
}

const severityClasses: Record<AlertSeverity, { bg: string, text: string, icon: string, border: string }> = {
  Critical: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400', icon: 'text-red-500', border: 'border-red-500/30' },
  High: { bg: 'bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400', icon: 'text-orange-500', border: 'border-orange-500/30' },
  Medium: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', icon: 'text-amber-500', border: 'border-amber-500/30' },
  Low: { bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', icon: 'text-blue-500', border: 'border-blue-500/30' },
};

import { useTimeZone } from '../contexts/TimeZoneContext';

// ... interface ...

// ... severityClasses ...

export const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts }) => {
  const { timeZone } = useTimeZone();
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  const handleToggleExpand = (alertId: string) => {
    setExpandedAlertId(prevId => (prevId === alertId ? null : alertId));
  };

  return (
    <div className="glass-premium rounded-3xl border border-white/10 dark:border-white/5 h-full flex flex-col shadow-2xl overflow-hidden">
      {/* ... header ... */}
      <div className="p-6 border-b border-white/10 dark:border-white/5 bg-gradient-to-r from-primary-500/5 to-transparent flex-shrink-0">
        <h3 className="text-xl font-bold flex items-center gap-3 tracking-tight text-gray-800 dark:text-white">
          <div className="p-2 bg-primary-500/10 rounded-xl">
            <AlertTriangleIcon className="text-primary-600 dark:text-primary-400" size={24} />
          </div>
          Recent Signals
        </h3>
      </div>
      <div className="p-6 space-y-3 flex-grow overflow-y-auto">
        {alerts.map(alert => {
          const classes = severityClasses[alert.severity];
          const isExpanded = expandedAlertId === alert.id;
          return (
            <div key={alert.id} className={`rounded-2xl transition-all duration-200 border ${classes.border} ${classes.bg} hover:scale-[1.02] cursor-pointer`}>
              <button
                onClick={() => handleToggleExpand(alert.id)}
                className="w-full text-left p-4"
                aria-expanded={isExpanded}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-2 h-2 mt-2 rounded-full ${classes.icon.replace('text-', 'bg-')} flex-shrink-0`}></div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start gap-2">
                      <div className="flex items-center gap-3 flex-wrap">
                        <p className={`text-xs font-black uppercase tracking-widest ${classes.text}`}>{alert.severity}</p>
                        <p className="text-[10px] text-gray-500 dark:text-gray-400 font-mono">{new Date(alert.timestamp).toLocaleString(undefined, { timeZone })}</p>
                      </div>
                      <ChevronDownIcon size={18} className={`transform transition-transform duration-200 flex-shrink-0 text-gray-400 ${isExpanded ? 'rotate-180' : ''}`} />
                    </div>
                    <p className={`mt-2 text-sm font-semibold ${classes.text} ${isExpanded ? '' : 'truncate'}`}>{alert.message}</p>
                  </div>
                </div>
              </button>
              {isExpanded && (
                <div className={`px-4 pb-4 border-t pt-4 ${classes.border}`}>
                  <div className="space-y-2 text-xs">
                    <h4 className="font-black text-gray-700 dark:text-gray-300 uppercase tracking-wider text-[10px]">Details</h4>
                    <p className={`whitespace-pre-wrap break-words text-sm leading-relaxed ${classes.text}`}>
                      {alert.message}
                    </p>
                    <p className="text-gray-500 dark:text-gray-400 pt-2 flex items-center gap-2">
                      <span className="font-bold text-[10px] uppercase tracking-wider">Source:</span>
                      <span className="font-mono text-xs bg-white/5 px-2 py-0.5 rounded border border-white/10">{alert.source}</span>
                    </p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {alerts.length === 0 && (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <AlertTriangleIcon size={48} className="mx-auto mb-4 opacity-20" />
            <p className="font-bold text-sm uppercase tracking-wider">No Recent Alerts</p>
            <p className="text-xs mt-1">All systems operational.</p>
          </div>
        )}
      </div>
    </div>
  );
};
