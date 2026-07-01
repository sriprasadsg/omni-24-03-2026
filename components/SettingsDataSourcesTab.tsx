import React from 'react';
import { DataSource, DataSourceStatus } from '../types';
import { PlusCircleIcon, PencilIcon, TrashIcon, CogIcon, CheckIcon, AlertTriangleIcon } from './icons';

const statusInfo: Record<DataSourceStatus, { icon: React.ReactNode; classes: string }> = {
    Connected: { icon: <CheckIcon size={14} />, classes: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' },
    Error: { icon: <AlertTriangleIcon size={14} />, classes: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' },
    Pending: { icon: <CogIcon size={14} className="animate-spin" />, classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' },
};

interface Props {
    dataSources: DataSource[];
    testingState: Record<string, { status: 'testing' | 'error'; message?: string }>;
    onNew: () => void;
    onEdit: (source: DataSource) => void;
    onDelete: (sourceId: string) => void;
    onTest: (sourceId: string) => void;
}

export function SettingsDataSourcesTab({ dataSources, testingState, onNew, onEdit, onDelete, onTest }: Props) {
    return (
        <div>
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">Data Sources</h3>
                <button onClick={onNew} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                    <PlusCircleIcon size={16} className="mr-1.5" />
                    New Data Source
                </button>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-4 py-3">Name</th>
                            <th scope="col" className="px-4 py-3">Type</th>
                            <th scope="col" className="px-4 py-3">Status</th>
                            <th scope="col" className="px-4 py-3">Last Tested</th>
                            <th scope="col" className="px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {dataSources.map(source => (
                            <tr key={source.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{source.name}</td>
                                <td className="px-4 py-3">{source.type}</td>
                                <td className="px-4 py-3">
                                    <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${statusInfo[source.status].classes}`}>
                                        {statusInfo[source.status].icon}
                                        <span className="ml-1.5">{source.status}</span>
                                    </span>
                                </td>
                                <td className="px-4 py-3">{source.lastTested ? new Date(source.lastTested).toLocaleString() : 'Never'}</td>
                                <td className="px-4 py-3">
                                    <div className="flex items-center space-x-2">
                                        <button onClick={() => onTest(source.id)} disabled={testingState[source.id]?.status === 'testing'} className="px-2.5 py-1 text-xs font-medium text-primary-700 bg-primary-100 rounded-md hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-wait">
                                            {testingState[source.id]?.status === 'testing' ? 'Testing...' : 'Test'}
                                        </button>
                                        <button onClick={() => onEdit(source)} className="p-1.5 text-gray-500 hover:text-primary-600"><PencilIcon size={14} /></button>
                                        <button onClick={() => onDelete(source.id)} className="p-1.5 text-gray-500 hover:text-red-600"><TrashIcon size={14} /></button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
