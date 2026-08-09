import React, { useState } from 'react';
import { Modal } from './Modal';

interface GenerateApiKeyNameModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGenerate: (name: string) => void;
}

export const GenerateApiKeyNameModal: React.FC<GenerateApiKeyNameModalProps> = ({ isOpen, onClose, onGenerate }) => {
  const [name, setName] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      onGenerate(name.trim());
    }
  };

  const footer = (
    <>
      <button type="button" onClick={onClose}
        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none">
        Cancel
      </button>
      <button type="submit" form="gen-api-key-form"
        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none">
        Generate Key
      </button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Generate New API Key" size="md" footer={footer}>
      <form id="gen-api-key-form" onSubmit={handleSubmit}>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          Give your new API key a descriptive name to help you identify it later.
        </p>
        <div>
          <label htmlFor="keyName" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Key Name</label>
          <input
            type="text"
            id="keyName"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
            placeholder="e.g., CI/CD Pipeline Key"
          />
        </div>
      </form>
    </Modal>
  );
};
