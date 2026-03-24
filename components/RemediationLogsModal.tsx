import React from 'react';
import { Agent } from '../types';
import { XIcon, HistoryIcon, CheckIcon, XCircleIcon } from './icons';

interface RemediationLogsModalProps {
  isOpen: boolean;
  onClose: () => void;
  agent: Agent | null;
}

export const RemediationLogsModal: React.FC<RemediationLogsModalProps> = ({ isOpen, onClose, agent }) => {
  if (!isOpen || !agent) return null;

  // Simulate a log for each attempt
  const getSimulatedLogForAttempt = (timestamp: string, index: number) => {
    const isSuccess = (index + agent.hostname.length) % 3 !== 0; // Pseudo-random success/failure
    return {
        timestamp,
        isSuccess,
        log: [
            `[INFO] Autonomous remediation attempt #${index + 1} initiated.`,
            `[ACTION] Checking agent service status...`,
            `[OBSERVATION] Service 'omni-agent' is in 'error' state.`,
            `[THOUGHT] Log indicates a permissions issue. Attempting to fix.`,
            `[ACTION] Executing: 'sudo chown -R omni-agent:omni-agent /var/log/omni-agent/'`,
            `[OBSERVATION] Command executed successfully.`,
            `[ACTION] Restarting agent service...`,
            `[OBSERVATION] ${isSuccess ? "Agent status changed to 'Online'." : "Agent failed to restart. Timeout reached."}`,
            `[INFO] Remediation attempt ${isSuccess ? 'succeeded' : 'failed'}.`
        ]
    };
  };

  const attemptLogs = (agent.remediationAttempts || []).map((attempt, index) => getSimulatedLogForAttempt(attempt.timestamp, index)).reverse();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex-shrink-0 flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
              <HistoryIcon className="mr-3 text-primary-500" />
              Remediation History
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{agent.hostname}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        
        <div className="flex-grow space-y-4 overflow-y-auto pr-2">
          {attemptLogs.length > 0 ? (
            attemptLogs.map((attemptLog, index) => (
              <div key={index} className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
                <div className="flex justify-between items-center mb-2">
                  <p className="font-semibold text-gray-700 dark:text-gray-300">Attempt #{attemptLogs.length - index} - {new Date(attemptLog.timestamp).toLocaleString()}</p>
                  {attemptLog.isSuccess ? (
                    <span className="flex items-center text-xs font-medium text-green-700 bg-green-100 dark:text-green-200 dark:bg-green-900/50 px-2 py-1 rounded-full">
                      <CheckIcon size={14} className="mr-1.5" /> Success
                    </span>
                  ) : (
                    <span className="flex items-center text-xs font-medium text-red-700 bg-red-100 dark:text-red-200 dark:bg-red-900/50 px-2 py-1 rounded-full">
                      <XCircleIcon size={14} className="mr-1.5" /> Failed
                    </span>
                  )}
                </div>
                <div className="p-3 bg-gray-900 dark:bg-black rounded-md font-mono text-xs text-gray-300 max-h-40 overflow-y-auto">
                  {attemptLog.log.map((line, lineIndex) => (
                    <p key={lineIndex} className="whitespace-pre-wrap">{line}</p>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-8">No remediation attempts have been recorded for this agent.</p>
          )}
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
