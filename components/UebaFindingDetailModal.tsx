import React from 'react';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { UebaFinding, AuditLog, User } from '../types';
import { XIcon, UsersIcon, AlertTriangleIcon, ClockIcon, UserIcon } from './icons';

interface UebaFindingDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  finding: UebaFinding | null;
  relatedLogs: AuditLog[];
  user: User | undefined;
}

export const UebaFindingDetailModal: React.FC<UebaFindingDetailModalProps> = ({ isOpen, onClose, finding, relatedLogs, user }) => {
  const { timeZone } = useTimeZone();
  if (!isOpen || !finding) return null;

  const riskColor = finding.riskScore > 75 ? 'text-red-500' : finding.riskScore > 50 ? 'text-orange-500' : 'text-amber-500';

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex-shrink-0 flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
              <AlertTriangleIcon className={`mr-3 ${riskColor}`} />
              Anomalous Activity Detected
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{finding.id}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        <div className="flex-grow space-y-4 overflow-y-auto pr-2">
          <div className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
              <div>
                <strong className="block text-gray-500 dark:text-gray-400">User</strong>
                <div className="flex items-center mt-1">
                  {user && <img src={user.avatar} alt={user.name} className="h-6 w-6 rounded-full mr-2" />}
                  <span>{user?.name || finding.userId}</span>
                </div>
              </div>
              <div>
                <strong className="block text-gray-500 dark:text-gray-400">Risk Score</strong>
                <p className={`font-bold text-lg ${riskColor}`}>{finding.riskScore} / 100</p>
              </div>
              <div>
                <strong className="block text-gray-500 dark:text-gray-400">Time Detected</strong>
                <p>{new Date(finding.timestamp).toLocaleString(undefined, { timeZone })}</p>
              </div>
            </div>
            <div className="mt-4">
              <strong className="block text-gray-500 dark:text-gray-400 text-sm">Summary</strong>
              <p className="mt-1 text-gray-800 dark:text-gray-200">{finding.summary}</p>
            </div>
            <div className="mt-4">
              <strong className="block text-gray-500 dark:text-gray-400 text-sm">AI-Powered Details</strong>
              <p className="mt-1 text-gray-600 dark:text-gray-300 text-sm">{finding.details}</p>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Correlated Audit Log Events</h3>
            <div className="space-y-2 max-h-64 overflow-y-auto p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
              {relatedLogs.map(log => (
                <div key={log.id} className="p-2 bg-white dark:bg-gray-800 rounded-md text-xs">
                  <div className="flex justify-between items-center text-gray-500 dark:text-gray-400">
                    <span>{new Date(log.timestamp).toLocaleString(undefined, { timeZone })}</span>
                    <span className="font-mono">{log.action}</span>
                  </div>
                  <p className="mt-1 text-gray-700 dark:text-gray-300">{log.details}</p>
                </div>
              ))}
            </div>
          </div>

        </div>
        <div className="flex-shrink-0 mt-6 flex justify-end items-center pt-4 border-t border-gray-200 dark:border-gray-700">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
