

import React, { useState } from 'react';
import { Alert, AlertSeverity } from '../types';
import { AlertTriangleIcon, ChevronDownIcon } from './icons';

interface AlertsPanelProps {
  alerts: Alert[];
}

const severityClasses: Record<AlertSeverity, { bg: string, text: string, icon: string, border: string }> = {
  Critical: { bg: 'bg-red-100 dark:bg-red-900/50', text: 'text-red-800 dark:text-red-300', icon: 'text-red-500', border: 'border-red-200 dark:border-red-800' },
  High: { bg: 'bg-orange-100 dark:bg-orange-900/50', text: 'text-orange-800 dark:text-orange-300', icon: 'text-orange-500', border: 'border-orange-200 dark:border-orange-800' },
  Medium: { bg: 'bg-amber-100 dark:bg-amber-900/50', text: 'text-amber-800 dark:text-amber-300', icon: 'text-amber-500', border: 'border-amber-200 dark:border-amber-800' },
  Low: { bg: 'bg-blue-100 dark:bg-blue-900/50', text: 'text-blue-800 dark:text-blue-300', icon: 'text-blue-500', border: 'border-blue-200 dark:border-blue-800' },
};

export const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts }) => {
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  const handleToggleExpand = (alertId: string) => {
    setExpandedAlertId(prevId => (prevId === alertId ? null : alertId));
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 h-full flex flex-col">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <h3 className="text-lg font-semibold flex items-center">
          <AlertTriangleIcon className="mr-2 text-primary-500" />
          Recent Alerts
        </h3>
      </div>
      <div className="p-4 space-y-3 flex-grow overflow-y-auto">
        {alerts.map(alert => {
          const classes = severityClasses[alert.severity];
          const isExpanded = expandedAlertId === alert.id;
          return (
            <div key={alert.id} className={`rounded-lg transition-all duration-200 ${classes.bg}`}>
              <button
                onClick={() => handleToggleExpand(alert.id)}
                className="w-full text-left p-3"
                aria-expanded={isExpanded}
              >
                <div className="flex items-start">
                  <div className={`w-1.5 h-1.5 mt-1.5 mr-3 rounded-full ${classes.icon.replace('text-', 'bg-')}`}></div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center">
                        <p className={`text-sm font-bold ${classes.text}`}>{alert.severity}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 ml-3">{alert.timestamp}</p>
                      </div>
                      <ChevronDownIcon size={20} className={`transform transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                    </div>
                    <p className={`mt-1 text-sm ${classes.text} truncate`}>{alert.message}</p>
                  </div>
                </div>
              </button>
              {isExpanded && (
                <div className={`px-3 pb-3 border-t pt-3 ${classes.border}`}>
                  <div className="space-y-1 text-xs">
                    <h4 className="font-semibold text-gray-700 dark:text-gray-300 mb-1">Details</h4>
                    <p className={`whitespace-pre-wrap break-words text-sm ${classes.text}`}>
                      {alert.message}
                    </p>
                    <p className="text-gray-500 dark:text-gray-400 pt-1">
                      <span className="font-medium">Source:</span> <span className="font-mono text-xs">{alert.source}</span>
                    </p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {alerts.length === 0 && (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>No recent alerts.</p>
          </div>
        )}
      </div>
    </div>
  );
};