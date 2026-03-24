
import React, { useState } from 'react';
import { CloudAccount, CloudProvider } from '../types';
import { XIcon, InfoIcon } from './icons';

interface AddCloudAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: Omit<CloudAccount, 'id' | 'tenantId' | 'status'>) => void;
}

const providerOptions: CloudProvider[] = ['AWS', 'GCP', 'Azure'];

export const AddCloudAccountModal: React.FC<AddCloudAccountModalProps> = ({ isOpen, onClose, onSave }) => {
  const [provider, setProvider] = useState<CloudProvider>('AWS');
  const [name, setName] = useState('');
  const [accountId, setAccountId] = useState('');
  const [accessKey, setAccessKey] = useState('');
  const [secretKey, setSecretKey] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !accountId.trim()) {
        alert("Please fill all required fields.");
        return;
    }
    onSave({ provider, name, accountId });
  };
  
  const getAccountIdLabel = () => {
      switch (provider) {
          case 'AWS': return 'Account ID';
          case 'GCP': return 'Project ID';
          case 'Azure': return 'Subscription ID';
      }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Add Cloud Account</h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
            <XIcon size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <style>{`.input-style { padding: 0.5rem 0.75rem; background-color: white; border: 1px solid #d1d5db; border-radius: 0.375rem; } .dark .input-style { background-color: #374151; border-color: #4b5563; }`}</style>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="provider" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Cloud Provider</label>
              <select id="provider" value={provider} onChange={e => setProvider(e.target.value as CloudProvider)} className="mt-1 block w-full input-style">
                {providerOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Account Name</label>
              <input id="name" value={name} onChange={e => setName(e.target.value)} required placeholder="e.g., Production AWS" className="mt-1 block w-full input-style" />
            </div>
          </div>
          
          <div>
            <label htmlFor="accountId" className="block text-sm font-medium text-gray-700 dark:text-gray-300">{getAccountIdLabel()}</label>
            <input id="accountId" value={accountId} onChange={e => setAccountId(e.target.value)} required placeholder="e.g., 123456789012" className="w-full input-style mt-1" />
          </div>

          <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Simulated Credentials</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <input value={accessKey} onChange={e => setAccessKey(e.target.value)} placeholder="Access Key ID" className="w-full input-style" />
              <input type="password" value={secretKey} onChange={e => setSecretKey(e.target.value)} placeholder="Secret Access Key" className="w-full input-style" />
            </div>
            <div className="mt-3 p-2 bg-blue-50 dark:bg-blue-900/50 rounded-lg flex items-start text-xs text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                <InfoIcon size={16} className="mr-2 mt-0.5 flex-shrink-0 text-blue-500" />
                <p>For this simulation, API keys are not required. In a real-world scenario, you would connect via a secure, role-based integration.</p>
            </div>
          </div>

          <div className="mt-6 flex justify-end space-x-3">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium border rounded-md">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add and Connect</button>
          </div>
        </form>
      </div>
    </div>
  );
};
