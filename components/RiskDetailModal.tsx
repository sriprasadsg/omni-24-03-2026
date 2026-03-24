
import React from 'react';
import { AiRisk, AiRiskSeverity, AiRiskStatus, MitigationTask, MitigationTaskStatus, TaskPriority } from '../types';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { XIcon, UserIcon, CalendarIcon, AlertTriangleIcon, InfoIcon, HistoryIcon } from './icons';

interface RiskDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  risk: AiRisk | null;
}

const severityClasses: Record<AiRiskSeverity, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
};

const statusClasses: Record<AiRiskStatus, string> = {
  Open: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  Mitigated: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  Accepted: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  Closed: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
};

const taskStatusClasses: Record<MitigationTaskStatus, string> = {
  'To Do': 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  'In Progress': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  'Done': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
};

const priorityClasses: Record<TaskPriority, string> = {
  High: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
};

export const RiskDetailModal: React.FC<RiskDetailModalProps> = ({ isOpen, onClose, risk }) => {
  const { timeZone } = useTimeZone();
  if (!isOpen || !risk) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex-shrink-0 flex justify-between items-start mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Risk Details</h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        <div className="flex-grow space-y-4 overflow-y-auto pr-2">
          <div>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Title</h3>
            <p className="mt-1 text-gray-900 dark:text-white">{risk.title}</p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Details</h3>
            <p className="mt-1 text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{risk.detail}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 flex items-center">
                <AlertTriangleIcon size={14} className="mr-1.5" />
                Severity
              </h3>
              <p className="mt-1">
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[risk.severity]}`}>{risk.severity}</span>
              </p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 flex items-center">
                <InfoIcon size={14} className="mr-1.5" />
                Status
              </h3>
              <p className="mt-1">
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusClasses[risk.status]}`}>{risk.status}</span>
              </p>
            </div>
          </div>

          {/* Mitigation Plan Section */}
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700 mt-4">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 mt-4">Mitigation Plan</h3>
            {risk.mitigationTasks && risk.mitigationTasks.length > 0 ? (
              <div className="space-y-3">
                {risk.mitigationTasks.map(task => (
                  <div key={task.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                    <div className="flex justify-between items-start">
                      <p className="flex-1 text-sm text-gray-800 dark:text-gray-200">{task.description}</p>
                      <div className="ml-4 flex-shrink-0 flex items-center space-x-2">
                        {task.priority && <span className={`px-2 py-1 text-xs font-medium rounded-full ${priorityClasses[task.priority]}`}>{task.priority}</span>}
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${taskStatusClasses[task.status]}`}>{task.status}</span>
                      </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span className="flex items-center">
                        <UserIcon size={12} className="mr-1.5" /> {task.owner}
                      </span>
                      <span className="flex items-center">
                        <CalendarIcon size={12} className="mr-1.5" /> Due: {task.dueDate}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-3">No specific mitigation tasks have been defined.</p>
            )}
          </div>

          {/* Audit Trail Section */}
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700 mt-4">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 mt-4 flex items-center">
              <HistoryIcon size={14} className="mr-1.5" />
              Audit Trail
            </h3>
            {risk.history && risk.history.length > 0 ? (
              <div className="space-y-3">
                {risk.history.map(log => (
                  <div key={log.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                    <div className="flex justify-between items-center text-xs text-gray-500 dark:text-gray-400">
                      <span className="flex items-center font-medium">
                        <UserIcon size={12} className="mr-1.5" /> {log.user}
                      </span>
                      <span>{new Date(log.timestamp).toLocaleString(undefined, { timeZone })}</span>
                    </div>
                    <p className="mt-1.5 text-sm text-gray-800 dark:text-gray-200">
                      <span className="font-semibold">{log.action}:</span> {log.details}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-3">No history has been recorded for this risk.</p>
            )}
          </div>

        </div>
        <div className="flex-shrink-0 mt-6 flex justify-end items-center pt-4 border-t border-gray-200 dark:border-gray-700">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
