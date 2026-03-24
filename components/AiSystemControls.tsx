import React, { useState } from 'react';
import { AiSystem } from '../types';
import { SlidersHorizontalIcon, PowerIcon, BrainCircuitIcon, AlertTriangleIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface AiSystemControlsProps {
  system: AiSystem;
  onControlsChange: (systemId: string, updatedControls: AiSystem['controls']) => void;
}

export const AiSystemControls: React.FC<AiSystemControlsProps> = ({ system, onControlsChange }) => {
    const { hasPermission } = useUser();
    const canManage = hasPermission('manage:ai_risks');

    const isEnabled = system.controls.isEnabled;
    const [isRetraining, setIsRetraining] = useState(false);

    const handleToggle = () => {
        if (!canManage) return;
        onControlsChange(system.id, { ...system.controls, isEnabled: !isEnabled });
    };

    const handleThresholdChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!canManage) return;
        onControlsChange(system.id, { ...system.controls, confidenceThreshold: parseInt(e.target.value, 10) });
    };

    const handleRetraining = () => {
        if (!canManage) return;
        if (window.confirm('Are you sure you want to trigger a manual model retraining? This may impact system performance.')) {
            setIsRetraining(true);
            onControlsChange(system.id, { ...system.controls, lastRetrainingTriggered: new Date().toISOString() });
            setTimeout(() => {
                setIsRetraining(false);
            }, 3000); // Simulate a 3-second retraining process
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold flex items-center">
                    <SlidersHorizontalIcon className="mr-2 text-primary-500" />
                    AI System Controls
                </h3>
            </div>
            <div className="p-4 space-y-4">
                {/* Enable/Disable Toggle */}
                <div className="flex items-center justify-between" title="Activates or deactivates the AI model's real-time processing and alert generation.">
                    <div className="flex items-center">
                        <PowerIcon size={20} className={`mr-2 ${isEnabled ? 'text-green-500' : 'text-red-500'}`} />
                        <label htmlFor="system-enabled" className="font-medium text-gray-700 dark:text-gray-300">
                            System Status
                        </label>
                    </div>
                    <div className="flex items-center">
                        <span className={`mr-3 text-sm font-semibold ${isEnabled ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                            {isEnabled ? 'Enabled' : 'Disabled'}
                        </span>
                        <button
                            type="button"
                            className={`${isEnabled ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-600'} ${!canManage ? 'cursor-not-allowed opacity-50' : ''} relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:ring-offset-gray-800`}
                            role="switch"
                            aria-checked={isEnabled}
                            onClick={handleToggle}
                            disabled={!canManage}
                            title={!canManage ? "Permission Denied" : "Toggle System Status"}
                        >
                            <span
                                aria-hidden="true"
                                className={`${isEnabled ? 'translate-x-5' : 'translate-x-0'} pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out`}
                            />
                        </button>
                    </div>
                </div>
                
                {!isEnabled && (
                    <div className="p-3 bg-amber-50 dark:bg-amber-900/50 rounded-lg flex items-start text-sm text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                        <AlertTriangleIcon size={18} className="mr-2.5 mt-0.5 flex-shrink-0 text-amber-500" />
                        <div>
                            <span className="font-semibold">System Disabled</span>
                            <p className="text-amber-700 dark:text-amber-400">All operational controls are inactive until the system is re-enabled.</p>
                        </div>
                    </div>
                )}

                {/* Confidence Threshold Slider */}
                <div className={`space-y-2 transition-opacity ${!isEnabled || !canManage ? 'opacity-50 pointer-events-none' : ''}`} title="Sets the minimum confidence score the model must have to generate an alert. Helps manage alert volume and sensitivity.">
                    <label
                        htmlFor="confidence-threshold"
                        className={`font-medium text-gray-700 dark:text-gray-300 transition-colors ${!isEnabled || !canManage ? 'text-gray-400 dark:text-gray-500' : ''}`}
                    >
                        Confidence Threshold
                    </label>
                    <div className="flex items-center space-x-4">
                        <input
                            id="confidence-threshold"
                            type="range"
                            min="0"
                            max="100"
                            value={system.controls.confidenceThreshold}
                            onChange={handleThresholdChange}
                            disabled={!isEnabled || !canManage}
                            className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:cursor-not-allowed"
                        />
                        <span className="font-bold text-primary-600 dark:text-primary-400 w-12 text-center">{system.controls.confidenceThreshold}%</span>
                    </div>
                </div>

                {/* Manual Retraining */}
                <div className={`transition-opacity ${!isEnabled || !canManage ? 'opacity-50' : ''}`} title="Initiates a manual retraining job using the latest available data to improve model accuracy.">
                    <h4 className={`font-medium text-gray-700 dark:text-gray-300 transition-colors ${!isEnabled || !canManage ? 'text-gray-400 dark:text-gray-500' : ''}`}>Model Retraining</h4>
                    <div className="flex items-center justify-between mt-2">
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                            Last triggered: {system.controls.lastRetrainingTriggered ? new Date(system.controls.lastRetrainingTriggered).toLocaleString() : 'Never'}
                        </p>
                        <button
                            onClick={handleRetraining}
                            disabled={!isEnabled || isRetraining || !canManage}
                            className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
                        >
                            <BrainCircuitIcon size={16} className="mr-1.5" />
                            {isRetraining ? 'Retraining...' : 'Trigger Retraining'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
