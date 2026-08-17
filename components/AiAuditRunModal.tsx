import React, { useState } from 'react';
import { Modal } from './Modal';

interface AiAuditRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRunAudit: (frameworkId: string) => void;
}

const AiAuditRunModal: React.FC<AiAuditRunModalProps> = ({ isOpen, onClose, onRunAudit }) => {
  const [frameworkId, setFrameworkId] = useState('');

  const handleSubmit = () => {
    if (frameworkId) {
      onRunAudit(frameworkId);
      onClose();
    }
  };

  const footer = (
    <>
      <button
        type="button"
        onClick={onClose}
        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={handleSubmit}
        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
        disabled={!frameworkId}
      >
        Run Audit
      </button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Run AI Audit" size="sm" footer={footer}>
      <div>
        <label htmlFor="frameworkId" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Framework ID
        </label>
        <input
          type="text"
          id="frameworkId"
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
          value={frameworkId}
          onChange={(e) => setFrameworkId(e.target.value)}
          placeholder="e.g., cis_v8"
        />
      </div>
    </Modal>
  );
};

export default AiAuditRunModal;
