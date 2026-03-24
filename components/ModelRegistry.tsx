
import React from 'react';
import { RegisteredModel, ModelStage } from '../types';
import { useUser } from '../contexts/UserContext';
// FIX: Added missing PackageCheckIcon and RocketIcon.
import { GitMergeIcon, ChevronDownIcon, PackageCheckIcon, RocketIcon } from './icons';

interface ModelRegistryProps {
    models: RegisteredModel[];
    onPromoteModel: (modelId: string, toStage: ModelStage) => void;
}

const stageInfo: Record<ModelStage, { icon: React.ReactNode; classes: string; }> = {
    Development: { icon: <PackageCheckIcon size={14} />, classes: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300' },
    Staging: { icon: <GitMergeIcon size={14} />, classes: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300' },
    Production: { icon: <RocketIcon size={14} />, classes: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' },
    Archived: { icon: <PackageCheckIcon size={14} />, classes: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500' },
};


export const ModelRegistry: React.FC<ModelRegistryProps> = ({ models, onPromoteModel }) => {
    const { hasPermission } = useUser();
    const canManage = hasPermission('manage:ai_risks');

    const handlePromote = (e: React.MouseEvent, modelId: string, toStage: ModelStage) => {
        e.stopPropagation();
        if(window.confirm(`Are you sure you want to promote this model to ${toStage}?`)) {
            onPromoteModel(modelId, toStage);
        }
    };
    
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold">Registered Models</h3>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-6 py-3">Model Name</th>
                            <th scope="col" className="px-6 py-3">Stage</th>
                            <th scope="col" className="px-6 py-3">Latest Version</th>
                            <th scope="col" className="px-6 py-3">Last Promoted</th>
                            <th scope="col" className="px-6 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {models.map(model => {
                            const currentVersionInfo = model.versions.find(v => v.version === model.latestVersion);
                            return (
                                <tr key={model.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                    <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{model.name}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${stageInfo[model.stage].classes}`}>
                                            {stageInfo[model.stage].icon} <span className="ml-1.5">{model.stage}</span>
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 font-mono text-xs">{model.latestVersion}</td>
                                    <td className="px-6 py-4">{currentVersionInfo ? new Date(currentVersionInfo.promotedAt).toLocaleDateString() : 'N/A'}</td>
                                    <td className="px-6 py-4">
                                        {canManage && model.stage === 'Development' && (
                                            <button onClick={(e) => handlePromote(e, model.id, 'Staging')} className="px-2.5 py-1 text-xs font-medium text-blue-700 bg-blue-100 rounded-md hover:bg-blue-200">Promote to Staging</button>
                                        )}
                                        {canManage && model.stage === 'Staging' && (
                                            <button onClick={(e) => handlePromote(e, model.id, 'Production')} className="px-2.5 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-md hover:bg-green-200">Promote to Production</button>
                                        )}
                                    </td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
