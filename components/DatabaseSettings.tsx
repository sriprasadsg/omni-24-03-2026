import React, { useState, useEffect, useMemo } from 'react';
import { DatabaseSettings as DatabaseSettingsType } from '../types';
import { DatabaseIcon, XIcon, CogIcon, CheckIcon, AlertTriangleIcon } from './icons';
import { testDatabaseConnection } from '../services/apiService';

interface DatabaseSettingsProps {
    isOpen: boolean;
    onClose: () => void;
    settings: DatabaseSettingsType;
    onSave: (settings: DatabaseSettingsType) => void;
}

export const DatabaseSettings: React.FC<DatabaseSettingsProps> = ({ isOpen, onClose, settings, onSave }) => {
    const [formData, setFormData] = useState(settings);
    const [password, setPassword] = useState('••••••••');
    const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle');
    const [testMessage, setTestMessage] = useState('');
    const [errors, setErrors] = useState<Record<string, string>>({});

    useEffect(() => {
        if (isOpen) {
            setFormData(settings);
            setPassword('••••••••');
            setTestStatus('idle');
            setTestMessage('');
            setErrors({});
        }
    }, [settings, isOpen]);

    const validate = (data: DatabaseSettingsType): Record<string, string> => {
        const newErrors: Record<string, string> = {};
        if (!data.host) newErrors.host = "Host cannot be empty.";
        if (data.port <= 0 || data.port > 65535) newErrors.port = "Port must be between 1 and 65535.";
        if (!data.username) newErrors.username = "Username cannot be empty.";
        if (!data.databaseName) newErrors.databaseName = "Database name cannot be empty.";
        return newErrors;
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value } = e.target;
        const finalValue = name === 'port' ? parseInt(value, 10) || 0 : value;
        setFormData(prev => ({ ...prev, [name]: finalValue }));
        setTestStatus('idle');
        if (errors[name]) {
            setErrors(prev => {
                const newErrors = { ...prev };
                delete newErrors[name];
                return newErrors;
            });
        }
    };
    
    const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name } = e.target;
        const validationErrors = validate(formData);
        if (validationErrors[name]) {
            setErrors(prev => ({ ...prev, [name]: validationErrors[name] }));
        }
    };

    const handleSave = () => {
        const validationErrors = validate(formData);
        if (Object.keys(validationErrors).length > 0) {
            setErrors(validationErrors);
            return;
        }
        onSave(formData);
    };

    const handleTestConnection = async () => {
        const validationErrors = validate(formData);
        if (Object.keys(validationErrors).length > 0) {
            setErrors(validationErrors);
            setTestStatus('failed');
            setTestMessage('Please fix the validation errors before testing.');
            return;
        }

        setTestStatus('testing');
        setTestMessage('');
        try {
            const result = await testDatabaseConnection(formData);
            setTestStatus('success');
            setTestMessage(result.message);
        } catch (error) {
            setTestStatus('failed');
            setTestMessage(error instanceof Error ? error.message : 'An unknown error occurred.');
        }
    };
    
    const generatedConnectionString = useMemo(() => {
        if (formData.type === 'MongoDB') {
            return `mongodb://${formData.username}:${password}@${formData.host}:${formData.port}/${formData.databaseName}`;
        }
        if (formData.type === 'PostgreSQL') {
            return `postgresql://${formData.username}:${password}@${formData.host}:${formData.port}/${formData.databaseName}`;
        }
         if (formData.type === 'MySQL') {
            return `mysql://${formData.username}:${password}@${formData.host}:${formData.port}/${formData.databaseName}`;
        }
        return '';
    }, [formData, password]);

    const renderField = (label: string, name: keyof DatabaseSettingsType, type: string = 'text', options?: string[]) => (
        <div>
            <label htmlFor={name} className="block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
            {options ? (
                <select id={name} name={name} value={String(formData[name])} onChange={handleChange}
                    className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                >
                    {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
            ) : (
                <input type={type} id={name} name={name} value={String(formData[name])} onChange={handleChange} onBlur={handleBlur}
                    className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors[name] ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
                />
            )}
            {errors[name] && <p className="mt-1 text-xs text-red-500">{errors[name]}</p>}
        </div>
    );

    if (!isOpen) return null;
    
    const hasErrors = Object.keys(errors).length > 0;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center"><DatabaseIcon className="mr-3"/> Database Connection</h2>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>
                <div className="space-y-4">
                    {renderField('Database Type', 'type', 'select', ['MongoDB', 'PostgreSQL', 'MySQL'])}
                    {renderField('Host', 'host')}
                    <div className="grid grid-cols-2 gap-4">
                        {renderField('Port', 'port', 'number')}
                        {renderField('Username', 'username')}
                    </div>
                    {renderField('Database Name', 'databaseName')}
                    <div>
                         <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
                         <input type="password" id="password" name="password" value={password} onChange={e => setPassword(e.target.value)}
                           className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm" />
                    </div>
                     {generatedConnectionString && (
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Connection String</label>
                            <div className="mt-1 p-2 bg-gray-100 dark:bg-gray-900 rounded-md font-mono text-xs text-gray-500 dark:text-gray-400 break-all">
                                {generatedConnectionString}
                            </div>
                        </div>
                     )}
                </div>

                {testStatus !== 'idle' && (
                    <div className={`mt-4 p-3 rounded-md text-sm flex items-start ${
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
                     <button
                        type="button"
                        onClick={handleTestConnection}
                        disabled={testStatus === 'testing'}
                        className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 dark:bg-primary-900/50 dark:text-primary-300 rounded-lg hover:bg-primary-200 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Test Connection
                    </button>
                    <div className="flex space-x-3">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                        <button type="button" onClick={handleSave} disabled={hasErrors} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-primary-400/50 disabled:cursor-not-allowed">Save Changes</button>
                    </div>
                </div>
            </div>
        </div>
    );
};
