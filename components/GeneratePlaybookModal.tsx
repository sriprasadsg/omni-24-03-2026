import React, { useState } from 'react';
import { SparklesIcon, CogIcon } from './icons';
import { Modal } from './Modal';

interface GeneratePlaybookModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGenerate: (prompt: string) => Promise<void>;
}

export const GeneratePlaybookModal: React.FC<GeneratePlaybookModalProps> = ({ isOpen, onClose, onGenerate }) => {
  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setIsLoading(true);
    try {
      await onGenerate(prompt.trim());
      onClose(); // Close on success
    } catch (error) {
      // Error is handled by an alert in App.tsx
    } finally {
      setIsLoading(false);
    }
  };

  const footer = (
    <>
      <button type="button" onClick={onClose} disabled={isLoading} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">
        Cancel
      </button>
      <button
        type="button"
        onClick={handleGenerate}
        disabled={isLoading || !prompt.trim()}
        className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-primary-400/50 disabled:cursor-wait flex items-center"
      >
        {isLoading ? (
          <><CogIcon size={16} className="animate-spin mr-2" /> Generating...</>
        ) : (
          'Generate Playbook'
        )}
      </button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="AI-Generate SOAR Playbook"
      icon={<SparklesIcon className="text-primary-500" />}
      size="lg"
      footer={footer}
    >
      <div className="space-y-4">
        <div>
          <label htmlFor="playbook-prompt" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Describe the threat or scenario
          </label>
          <textarea
            id="playbook-prompt"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            rows={4}
            placeholder="e.g., A user reported a phishing email with a malicious attachment that attempts to establish persistence."
            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            The AI will generate a multi-step playbook based on your description.
          </p>
        </div>
      </div>
    </Modal>
  );
};
