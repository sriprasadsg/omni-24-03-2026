import React, { useState } from 'react';
import { XIcon, BotIcon, SparklesIcon, CogIcon } from './icons';

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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
            <SparklesIcon className="mr-3 text-primary-500" />
            AI-Generate SOAR Playbook
          </h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
            <XIcon size={20} />
          </button>
        </div>
        
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

        <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
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
        </div>
      </div>
    </div>
  );
};
