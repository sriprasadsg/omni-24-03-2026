
import React from 'react';
import { RiskHistoryLog } from '../types';
import { HistoryIcon, UserIcon } from './icons';

interface RiskHistoryProps {
  logs: RiskHistoryLog[];
}

export const RiskHistory: React.FC<RiskHistoryProps> = ({ logs }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
          <HistoryIcon className="mr-2 text-primary-500" />
          Risk History
        </h3>
      </div>
      <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
        {logs.length > 0 ? (
          logs.map(log => (
            <div key={log.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
              <div className="flex justify-between items-center text-xs text-gray-500 dark:text-gray-400">
                <span className="flex items-center font-medium">
                  <UserIcon size={12} className="mr-1.5" /> {log.user}
                </span>
                <span>{new Date(log.timestamp).toLocaleString()}</span>
              </div>
              <p className="mt-1.5 text-sm text-gray-800 dark:text-gray-200">
                <span className="font-semibold">{log.action}:</span> {log.details}
              </p>
            </div>
          ))
        ) : (
          <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-4">
            No risk history available for this system.
          </p>
        )}
      </div>
    </div>
  );
};
