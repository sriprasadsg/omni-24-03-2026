
import React, { useState } from 'react';
import { CopyIcon, CheckIcon, AlertTriangleIcon } from './icons';

interface ShowNewKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: { name: string; key: string } | null;
}

export const ShowNewKeyModal: React.FC<ShowNewKeyModalProps> = ({ isOpen, onClose, apiKey }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (apiKey) {
      navigator.clipboard.writeText(apiKey.key).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  };

  if (!isOpen || !apiKey) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">API Key Generated Successfully</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Key Name: <span className="font-semibold">{apiKey.name}</span></p>
        
        <div className="p-4 bg-amber-50 dark:bg-amber-900/50 rounded-lg flex items-start text-sm text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800 mb-4">
            <AlertTriangleIcon size={20} className="mr-3 mt-0.5 flex-shrink-0 text-amber-500" />
            <div>
                <span className="font-semibold">Important:</span> This is the only time you will see this key. Copy it and store it in a secure location. You will not be able to retrieve it again.
            </div>
        </div>
        
        <div className="relative bg-gray-900 dark:bg-black rounded-md p-4 font-mono text-sm text-gray-200">
            <pre className="whitespace-pre-wrap break-all"><code>{apiKey.key}</code></pre>
            <button
                onClick={handleCopy}
                className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-700 hover:bg-gray-600 text-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500"
                aria-label="Copy API Key"
            >
                {copied ? <CheckIcon size={16} className="text-green-400" /> : <CopyIcon size={16} />}
            </button>
        </div>

        <div className="mt-6 flex justify-end">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
