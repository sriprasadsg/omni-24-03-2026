import React, { useState } from 'react';

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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white p-6 rounded-lg shadow-xl dark:bg-gray-800 w-96">
        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-gray-100">Run AI Audit</h2>
        <div className="mb-4">
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
        <div className="flex justify-end space-x-2">
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
        </div>
      </div>
    </div>
  );
};

export default AiAuditRunModal;