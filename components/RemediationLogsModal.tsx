import React from 'react';
import { Agent } from '../types';
import { HistoryIcon, CheckIcon, XCircleIcon } from './icons';
import { Modal } from './Modal';

interface RemediationLogsModalProps {
  isOpen: boolean;
  onClose: () => void;
  agent: Agent | null;
}

export const RemediationLogsModal: React.FC<RemediationLogsModalProps> = ({ isOpen, onClose, agent }) => {
  if (!agent) return null;

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
      icon={<HistoryIcon className="text-primary-500" />}
      title={
        <div>
          <span className="text-xl font-bold text-gray-900 dark:text-white">Remediation History</span>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{agent.hostname}</p>
        </div>
      }
      size="2xl"
      footer={footer}
    >
        <div className="space-y-4">
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
    </Modal>
  );
};
