import React, { useState, useEffect } from 'react';
import { DataSource, DataSourceType } from '../types';
import { XIcon, CogIcon, CheckIcon, AlertTriangleIcon } from './icons';
import { testDataSourceConnection } from '../services/apiService';

interface DataSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (source: DataSource) => void;
  dataSource: DataSource | null;
}

const defaultSource: Omit<DataSource, 'id' | 'tenantId' | 'lastTested'> = {
  name: '',
  type: 'PostgreSQL',
  status: 'Pending',
  config: {},
};

const typeOptions: DataSourceType[] = ['PostgreSQL', 'AWS S3', 'MongoDB'];

export const DataSourceModal: React.FC<DataSourceModalProps> = ({ isOpen, onClose, onSave, dataSource }) => {
  const [formData, setFormData] = useState<Omit<DataSource, 'id' | 'tenantId' | 'lastTested'>>(defaultSource);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle');
  const [testMessage, setTestMessage] = useState('');

  useEffect(() => {
    if (isOpen) {
      if (dataSource) {
        setFormData({ name: dataSource.name, type: dataSource.type, status: dataSource.status, config: dataSource.config });
      } else {
        setFormData(defaultSource);
      }
      setTestStatus('idle');
      setTestMessage('');
    }
  }, [dataSource, isOpen]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setTestStatus('idle');
  };
  
  const handleConfigChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    const finalValue = e.target.type === 'number' ? parseInt(value, 10) || 0 : value;
    setFormData(prev => ({ ...prev, config: { ...prev.config, [name]: finalValue } }));
    setTestStatus('idle');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const sourceToSave: DataSource = {
      id: dataSource?.id || `ds-${Date.now()}`,
      tenantId: dataSource?.tenantId || '', // tenantId will be set in App.tsx
      ...formData,
      lastTested: dataSource?.lastTested || null,
    };
    onSave(sourceToSave);
  };

  const handleTestConnection = async () => {
    setTestStatus('testing');
    setTestMessage('');
    try {
      const tempSource: DataSource = { id: 'test', tenantId: '', ...formData, lastTested: null };
      const result = await testDataSourceConnection(tempSource);
      setTestStatus('success');
      setTestMessage(result.message);
    } catch (error) {
      setTestStatus('failed');
      setTestMessage(error instanceof Error ? error.message : 'An unknown error occurred.');
    }
  };

  const renderConfigFields = () => {
    switch (formData.type) {
      case 'PostgreSQL':
        return (
          <>
            <input name="host" value={formData.config.host || ''} onChange={handleConfigChange} placeholder="Host (e.g., my-db.db.internal)" className="mt-1 block w-full input-style" />
            <input name="port" type="number" value={formData.config.port || ''} onChange={handleConfigChange} placeholder="Port (e.g., 5432)" className="mt-1 block w-full input-style" />
            <input name="username" value={formData.config.username || ''} onChange={handleConfigChange} placeholder="Username" className="mt-1 block w-full input-style" />
            <input name="databaseName" value={formData.config.databaseName || ''} onChange={handleConfigChange} placeholder="Database Name" className="mt-1 block w-full input-style" />
          </>
        );
      case 'AWS S3':
        return (
          <>
            <input name="bucketName" value={formData.config.bucketName || ''} onChange={handleConfigChange} placeholder="Bucket Name" className="mt-1 block w-full input-style" />
            <input name="region" value={formData.config.region || ''} onChange={handleConfigChange} placeholder="Region (e.g., us-east-1)" className="mt-1 block w-full input-style" />
          </>
        );
      case 'MongoDB':
        return (
          <>
            <input name="connectionString" value={formData.config.connectionString || ''} onChange={handleConfigChange} placeholder="Connection String (mongodb+srv://...)" className="mt-1 block w-full input-style" />
          </>
        );
      default:
        return null;
    }
  };
  
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">{dataSource ? 'Edit Data Source' : 'Add New Data Source'}</h2>
            <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"><XIcon size={20} /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
            <style>{`.input-style { padding: 0.5rem 0.75rem; background-color: white; border: 1px solid #d1d5db; border-radius: 0.375rem; } .dark .input-style { background-color: #374151; border-color: #4b5563; }`}</style>
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Data Source Name</label>
              <input type="text" name="name" id="name" value={formData.name} onChange={handleChange} required className="mt-1 block w-full input-style" />
            </div>
            <div>
              <label htmlFor="type" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Type</label>
              <select name="type" id="type" value={formData.type} onChange={handleChange} className="mt-1 block w-full input-style">
                {typeOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            </div>
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Configuration</label>
                <div className="mt-1 space-y-2 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-md border border-gray-200 dark:border-gray-600">
                    {renderConfigFields()}
                </div>
            </div>
             
            {testStatus !== 'idle' && (
                <div className={`p-3 rounded-md text-sm flex items-start ${
                    testStatus === 'success' ? 'bg-green-50 dark:bg-green-900/50' :
                    testStatus === 'failed' ? 'bg-red-50 dark:bg-red-900/50' :
                    'bg-gray-100 dark:bg-gray-700/50'
                }`}>
                    {testStatus === 'testing' && <CogIcon size={18} className="animate-spin mr-2 mt-0.5 text-gray-500" />}
                    {testStatus === 'success' && <CheckIcon size={18} className="mr-2 mt-0.5 text-green-500" />}
                    {testStatus === 'failed' && <AlertTriangleIcon size={18} className="mr-2 mt-0.5 text-red-500" />}
                    <p className={
                        testStatus === 'success' ? 'text-green-700 dark:text-green-300' :
                        testStatus === 'failed' ? 'text-red-700 dark:text-red-300' :
                        'text-gray-500 dark:text-gray-400'
                    }>
                        {testStatus === 'testing' ? 'Testing connection...' : testMessage}
                    </p>
                </div>
            )}

            <div className="mt-6 flex justify-between items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                <button type="button" onClick={handleTestConnection} disabled={testStatus === 'testing'}
                    className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 dark:bg-primary-900/50 dark:text-primary-300 rounded-lg hover:bg-primary-200 dark:hover:bg-primary-900 disabled:opacity-50"
                >
                    Test Connection
                </button>
                <div className="flex space-x-3">
                    <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                    <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Save</button>
                </div>
            </div>
        </form>
      </div>
    </div>
  );
};
