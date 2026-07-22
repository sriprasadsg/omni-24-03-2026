import React, { useState, useMemo, useEffect } from 'react';
import { Patch, Asset } from '../types';
import { ZapIcon, ClockIcon } from './icons';
import { showToast } from '../utils/toast';
import { Modal } from './Modal';

interface DeployPatchesModalProps {
  isOpen: boolean;
  onClose: () => void;
  patchesToDeploy: Patch[];
  assets: Asset[];
  onDeploy: (deploymentType: 'Immediate' | 'Scheduled', scheduleTime?: string) => void;
}

export const DeployPatchesModal: React.FC<DeployPatchesModalProps> = ({ isOpen, onClose, patchesToDeploy, assets, onDeploy }) => {
    const [deploymentType, setDeploymentType] = useState<'Immediate' | 'Scheduled'>('Immediate');
    const [scheduleTime, setScheduleTime] = useState('');

    const affectedAssets = useMemo(() => {
        const assetIds = new Set(patchesToDeploy.flatMap(p => p.affectedAssets));
        return assets.filter(a => assetIds.has(a.id));
    }, [patchesToDeploy, assets]);

    const handleConfirm = () => {
        if (deploymentType === 'Scheduled' && !scheduleTime) {
            showToast('Please select a date and time for the scheduled deployment.', 'error');
            return;
        }
        onDeploy(deploymentType, scheduleTime);
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

    const footer = (
        <>
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium border rounded-md text-gray-700 bg-white dark:text-gray-300 dark:bg-gray-700 dark:border-gray-600">Cancel</button>
            <button onClick={handleConfirm} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Confirm Deployment</button>
        </>
    );

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Confirm Patch Deployment" size="lg" footer={footer}>
            <p className="text-sm text-gray-600 dark:text-gray-300">You are about to deploy <strong className="text-gray-800 dark:text-white">{patchesToDeploy.length}</strong> patch(es) to <strong className="text-gray-800 dark:text-white">{affectedAssets.length}</strong> affected asset(s).</p>

            <div className="mt-4 space-y-2">
                <div onClick={() => setDeploymentType('Immediate')} className={`p-3 border rounded-lg cursor-pointer ${deploymentType === 'Immediate' ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/50' : 'border-gray-300 dark:border-gray-600'}`}>
                    <label className="flex items-center">
                        <input type="radio" name="deploymentType" checked={deploymentType === 'Immediate'} onChange={() => {}} className="h-4 w-4 text-primary-600 focus:ring-primary-500" />
                        <div className="ml-3">
                            <p className="font-semibold text-gray-800 dark:text-white flex items-center"><ZapIcon size={16} className="mr-2" />Deploy Immediately</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">The deployment job will start as soon as possible.</p>
                        </div>
                    </label>
                </div>
                 <div onClick={() => setDeploymentType('Scheduled')} className={`p-3 border rounded-lg cursor-pointer ${deploymentType === 'Scheduled' ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/50' : 'border-gray-300 dark:border-gray-600'}`}>
                    <label className="flex items-center">
                        <input type="radio" name="deploymentType" checked={deploymentType === 'Scheduled'} onChange={() => {}} className="h-4 w-4 text-primary-600 focus:ring-primary-500" />
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
                            className="mt-2 w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm"
                        />
                    )}
                </div>
            </div>
        </Modal>
    );
};
