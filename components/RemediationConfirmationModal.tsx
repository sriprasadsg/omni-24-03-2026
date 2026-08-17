import React from 'react';
import { Agent } from '../types';
import { AlertTriangleIcon, ZapIcon } from './icons';
import { Modal } from './Modal';

interface RemediationConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  agentsToRemediate: Agent[];
}

export const RemediationConfirmationModal: React.FC<RemediationConfirmationModalProps> = ({ isOpen, onClose, onConfirm, agentsToRemediate }) => {
  const footer = (
    <>
      <button type="button" onClick={onClose}
        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none">
        Cancel
      </button>
      <button type="button" onClick={onConfirm}
        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none flex items-center">
        <ZapIcon size={16} className="mr-2" />
        Confirm &amp; Authorize
      </button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Confirm Autonomous Remediation"
      icon={<AlertTriangleIcon className="text-amber-500" />}
      size="lg"
      footer={footer}
    >
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
    </Modal>
  );
};
