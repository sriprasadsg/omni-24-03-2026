import React from 'react';
import { Agent } from '../types';
import { XIcon, AlertTriangleIcon, ZapIcon } from './icons';

interface RemediationConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  agentsToRemediate: Agent[];
}

export const RemediationConfirmationModal: React.FC<RemediationConfirmationModalProps> = ({ isOpen, onClose, onConfirm, agentsToRemediate }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
            <AlertTriangleIcon className="mr-3 text-amber-500" />
            Confirm Autonomous Remediation
          </h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        
        <div className="text-sm text-gray-600 dark:text-gray-300 space-y-4">
            <p>You are about to authorize the Omni-Agent AI to attempt autonomous remediation on the following {agentsToRemediate.length} agent(s) in an error state:</p>
            <ul className="list-disc list-inside bg-gray-100 dark:bg-gray-700/50 p-3 rounded-md max-h-32 overflow-y-auto">
                {agentsToRemediate.map(agent => (
                    <li key={agent.id} className="font-mono text-xs">{agent.hostname}</li>
                ))}
            </ul>
             <p className="font-semibold text-amber-700 dark:text-amber-300">
                The AI will execute commands on these systems to resolve the issue. This action cannot be undone. Are you sure you want to proceed?
            </p>
        </div>

        <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
          >
            Cancel
          </button>
          <button type="button" onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none flex items-center"
          >
            <ZapIcon size={16} className="mr-2" />
            Confirm & Authorize
          </button>
        </div>
      </div>
    </div>
  );
};
