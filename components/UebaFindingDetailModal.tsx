import React from 'react';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { UebaFinding, AuditLog, User } from '../types';
import { AlertTriangleIcon } from './icons';
import { Modal } from './Modal';

interface UebaFindingDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  finding: UebaFinding | null;
  relatedLogs: AuditLog[];
  user: User | undefined;
}

export const UebaFindingDetailModal: React.FC<UebaFindingDetailModalProps> = ({ isOpen, onClose, finding, relatedLogs, user }) => {
  const { timeZone } = useTimeZone();
  if (!finding) return null;

  const riskColor = finding.riskScore > 75 ? 'text-red-500' : finding.riskScore > 50 ? 'text-orange-500' : 'text-amber-500';

  const footer = (
    <button type="button" onClick={onClose}
      className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
    >
      Close
    </button>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      icon={<AlertTriangleIcon className={riskColor} />}
      title={
        <div>
          <span className="text-xl font-bold text-gray-900 dark:text-white">Anomalous Activity Detected</span>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{finding.id}</p>
        </div>
      }
      size="2xl"
      footer={footer}
    >
        <div className="space-y-4">
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
    </Modal>
  );
};
