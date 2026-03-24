import React from 'react';
import { Agent, LogEntry, LogSeverity } from '../types';
import { XIcon, InfoIcon, AlertCircleIcon, XCircleIcon } from './icons';

interface AgentLogsModalProps {
  isOpen: boolean;
  onClose: () => void;
  agent: Agent | null;
  logs: LogEntry[];
}

const severityStyles: Record<LogSeverity, { icon: React.ReactNode; color: string }> = {
  INFO: { icon: <InfoIcon size={14} />, color: 'text-blue-500 dark:text-blue-400' },
  WARN: { icon: <AlertCircleIcon size={14} />, color: 'text-amber-500 dark:text-amber-400' },
  ERROR: { icon: <XCircleIcon size={14} />, color: 'text-red-500 dark:text-red-400' },
  DEBUG: { icon: <InfoIcon size={14} />, color: 'text-gray-500 dark:text-gray-400' },
};

export const AgentLogsModal: React.FC<AgentLogsModalProps> = ({ isOpen, onClose, agent, logs }) => {
  if (!isOpen || !agent) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl h-[80vh] flex flex-col p-0 m-4" onClick={e => e.stopPropagation()}>
        <header className="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Logs for <span className="text-primary-600 dark:text-primary-400">{agent.hostname}</span>
          </h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </header>

        <main className="flex-grow p-4 bg-gray-50 dark:bg-gray-900 overflow-y-auto">
            <div className="font-mono text-xs text-gray-700 dark:text-gray-300 space-y-2">
                {logs.map((log, index) => {
                    const style = severityStyles[log.severity];
                    return (
                        <div key={index} className="flex items-start">
                            <span className="text-gray-400 dark:text-gray-500 mr-4">{log.timestamp}</span>
                            <span className={`flex-shrink-0 w-16 flex items-center font-bold ${style.color}`}>
                                {style.icon}
                                <span className="ml-1.5">{log.severity}</span>
                            </span>
                            <p className="flex-1 break-words whitespace-pre-wrap">{log.message}</p>
                        </div>
                    )
                })}
            </div>
        </main>

        <footer className="flex-shrink-0 p-4 border-t border-gray-200 dark:border-gray-700 flex justify-end">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
          >
            Close
          </button>
        </footer>
      </div>
    </div>
  );
};
