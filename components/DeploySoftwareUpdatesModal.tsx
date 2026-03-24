import React, { useState, useEffect } from 'react';
import { XIcon, ZapIcon, ClockIcon } from './icons';

interface SoftwareItem {
    id: string;
    name: string;
    currentVersion: string;
    latestVersion: string;
    assetId: string;
    assetName: string;
    severity?: 'Critical' | 'High' | 'Medium' | 'Low';
}

interface DeploySoftwareUpdatesModalProps {
    isOpen: boolean;
    onClose: () => void;
    softwareToUpdate: SoftwareItem[];
    onDeploy: (deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string) => void;
}

export const DeploySoftwareUpdatesModal: React.FC<DeploySoftwareUpdatesModalProps> = ({
    isOpen,
    onClose,
    softwareToUpdate,
    onDeploy
}) => {
    const [deploymentType, setDeploymentType] = useState<'Immediate' | 'Scheduled'>('Immediate');
    const [scheduleTime, setScheduleTime] = useState('');

    const affectedAssetsCount = new Set(softwareToUpdate.map(sw => sw.assetId)).size;

    const handleConfirm = () => {
        if (deploymentType === 'Scheduled' && !scheduleTime) {
            alert('Please select a date and time for the scheduled deployment.');
            return;
        }
        onDeploy(deploymentType, scheduleTime);
        onClose();
    };

    useEffect(() => {
        if (isOpen) {
            const now = new Date();
            now.setHours(now.getHours() + 1);
            now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15);
            const localISO = new Date(now.getTime() - (now.getTimezoneOffset() * 60000)).toISOString().slice(0, 16);
            setScheduleTime(localISO);
        }
    }, [isOpen]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">Confirm Software Updates Deployment</h2>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
                        <XIcon size={20} />
                    </button>
                </div>

                <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
                    You are about to deploy <strong className="text-gray-800 dark:text-white">{softwareToUpdate.length}</strong> software update(s) to <strong className="text-gray-800 dark:text-white">{affectedAssetsCount}</strong> asset(s).
                </p>

                {/* Software List */}
                <div className="mb-4 max-h-60 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-900 sticky top-0">
                            <tr>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Software</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Current</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Latest</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Asset</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {softwareToUpdate.map((sw) => (
                                <tr key={sw.id}>
                                    <td className="px-4 py-2 text-sm text-gray-900 dark:text-white">{sw.name}</td>
                                    <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">{sw.currentVersion}</td>
                                    <td className="px-4 py-2 text-sm text-green-600 dark:text-green-400 font-semibold">{sw.latestVersion}</td>
                                    <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">{sw.assetName}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Deployment Options */}
                <div className="mt-4 space-y-2">
                    <div onClick={() => setDeploymentType('Immediate')} className={`p-3 border rounded-lg cursor-pointer ${deploymentType === 'Immediate' ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/50' : 'border-gray-300 dark:border-gray-600'}`}>
                        <label className="flex items-center">
                            <input type="radio" name="deploymentType" checked={deploymentType === 'Immediate'} onChange={() => { }} className="h-4 w-4 text-primary-600 focus:ring-primary-500" />
                            <div className="ml-3">
                                <p className="font-semibold text-gray-800 dark:text-white flex items-center"><ZapIcon size={16} className="mr-2" />Deploy Immediately</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">The deployment job will start as soon as possible.</p>
                            </div>
                        </label>
                    </div>
                    <div onClick={() => setDeploymentType('Scheduled')} className={`p-3 border rounded-lg cursor-pointer ${deploymentType === 'Scheduled' ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/50' : 'border-gray-300 dark:border-gray-600'}`}>
                        <label className="flex items-center">
                            <input type="radio" name="deploymentType" checked={deploymentType === 'Scheduled'} onChange={() => { }} className="h-4 w-4 text-primary-600 focus:ring-primary-500" />
                            <div className="ml-3">
                                <p className="font-semibold text-gray-800 dark:text-white flex items-center"><ClockIcon size={16} className="mr-2" />Schedule for Later</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">Choose a specific time for the deployment to start.</p>
                            </div>
                        </label>
                        {deploymentType === 'Scheduled' && (
                            <input
                                type="datetime-local"
                                value={scheduleTime}
                                onChange={e => setScheduleTime(e.target.value)}
                                className="mt-2 w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm text-gray-900 dark:text-white"
                            />
                        )}
                    </div>
                </div>

                <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium border rounded-md text-gray-700 bg-white dark:text-gray-300 dark:bg-gray-700 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600">Cancel</button>
                    <button onClick={handleConfirm} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Confirm Deployment</button>
                </div>
            </div>
        </div>
    );
};
