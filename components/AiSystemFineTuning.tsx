import React, { useState, useEffect } from 'react';
import { AiSystem } from '../types';
import { BrainCircuitIcon, CogIcon, UploadCloudIcon, CheckIcon, TerminalSquareIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface AiSystemFineTuningProps {
  system: AiSystem;
  onFineTuneComplete: (systemId: string, newVersion: string) => void;
}

const mockDatasets = [
    { id: 'ds-001', name: 'Q3_SRE_Incidents.json', size: '15.2 MB', records: 12053 },
    { id: 'ds-002', name: 'user_feedback_batch_004.csv', size: '2.1 MB', records: 5000 },
    { id: 'ds-003', name: 'synthetic_failure_patterns_v2.json', size: '8.7 MB', records: 45000 },
];

const getNextVersion = (currentVersion: string): string => {
    const parts = currentVersion.split('.');
    if (parts.length === 3) {
        const patch = parseInt(parts[2], 10);
        if (!isNaN(patch)) {
            return `${parts[0]}.${parts[1]}.${patch + 1}`;
        }
    }
    return `${currentVersion}-tuned`;
};

export const AiSystemFineTuning: React.FC<AiSystemFineTuningProps> = ({ system, onFineTuneComplete }) => {
    const { hasPermission } = useUser();
    const canManageAIs = hasPermission('manage:ai_risks');

    const [jobStatus, setJobStatus] = useState<'idle' | 'running' | 'completed'>('idle');
    const [logs, setLogs] = useState<string[]>([]);
    
    useEffect(() => {
        // Reset the component state when the selected system changes
        setJobStatus('idle');
        setLogs([]);
    }, [system]);

    const handleStartJob = () => {
        if (!canManageAIs) return;
        setJobStatus('running');
        setLogs([]);

        const newVersion = getNextVersion(system.version);
        const steps = [
            { msg: '✅ Job Queued. Waiting for available resources...', delay: 500 },
            { msg: '🔧 Provisioning training environment (gpu-a100-large)...', delay: 1500 },
            { msg: '🔍 Validating datasets...', delay: 1000 },
            { msg: '📊 Preprocessing 62,053 new records...', delay: 2000 },
            { msg: '🧠 Starting fine-tuning on base model...', delay: 500 },
            { msg: '... Epoch 1/5, Loss: 0.234', delay: 1500 },
            { msg: '... Epoch 2/5, Loss: 0.187', delay: 1500 },
            { msg: '... Epoch 3/5, Loss: 0.155', delay: 1500 },
            { msg: '... Epoch 4/5, Loss: 0.121', delay: 1500 },
            { msg: '... Epoch 5/5, Loss: 0.098', delay: 1500 },
            { msg: '📈 Running evaluation against holdout set...', delay: 2000 },
            { msg: '👍 Accuracy improved by 4.7%.', delay: 500 },
            { msg: `🚀 Deploying new model version: ${newVersion}`, delay: 1500 },
            { msg: `🎉 Fine-tuning complete. System version updated.`, delay: 500 },
        ];
        
        let cumulativeDelay = 0;
        steps.forEach(step => {
            cumulativeDelay += step.delay;
            setTimeout(() => {
                setLogs(prev => [...prev, step.msg]);
            }, cumulativeDelay);
        });

        setTimeout(() => {
            setJobStatus('completed');
            onFineTuneComplete(system.id, newVersion);
        }, cumulativeDelay + 500);
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold flex items-center">
                    <BrainCircuitIcon className="mr-2 text-primary-500" />
                    Model Fine-Tuning & Continuous Improvement
                </h3>
            </div>
            <div className="p-4 space-y-4">
                <div>
                    <h4 className="font-medium text-gray-700 dark:text-gray-300 mb-2">Available Datasets for Training</h4>
                    <div className="space-y-2">
                        {mockDatasets.map(ds => (
                            <div key={ds.id} className="flex items-center p-2 bg-gray-50 dark:bg-gray-700/50 rounded-md text-sm">
                                <UploadCloudIcon size={16} className="mr-3 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                                <span className="font-mono text-xs text-gray-800 dark:text-gray-200 flex-grow">{ds.name}</span>
                                <span className="text-gray-500 dark:text-gray-400 text-xs mx-4">{ds.size}</span>
                                <span className="text-gray-500 dark:text-gray-400 text-xs hidden sm:block">{ds.records.toLocaleString()} records</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                    {jobStatus === 'idle' && (
                        <button
                            onClick={handleStartJob}
                            disabled={!canManageAIs}
                            title={canManageAIs ? "Start a new fine-tuning job" : "You do not have permission to manage AI systems"}
                            className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
                        >
                            Start Fine-Tuning Job
                        </button>
                    )}

                    {jobStatus === 'running' && (
                        <div>
                             <div className="flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg cursor-wait">
                                <CogIcon size={16} className="mr-2 animate-spin" />
                                Fine-Tuning Job in Progress...
                            </div>
                        </div>
                    )}
                    
                    {jobStatus === 'completed' && (
                        <div className="text-center">
                            <div className="flex items-center justify-center p-3 text-sm font-medium text-green-800 bg-green-100 dark:text-green-200 dark:bg-green-900/50 rounded-lg">
                                <CheckIcon size={16} className="mr-2" />
                                Model successfully updated to version {system.version}
                            </div>
                             <button
                                onClick={() => { setJobStatus('idle'); setLogs([]); }}
                                disabled={!canManageAIs}
                                title={canManageAIs ? "Start a new fine-tuning job" : "You do not have permission to manage AI systems"}
                                className="mt-4 px-4 py-2 text-sm font-medium text-primary-700 dark:text-primary-300 bg-primary-100 dark:bg-primary-900/50 rounded-lg hover:bg-primary-200 dark:hover:bg-primary-900 disabled:bg-gray-400 disabled:cursor-not-allowed"
                            >
                                Start New Job
                            </button>
                        </div>
                    )}

                    {logs.length > 0 && (
                        <div className="mt-4 p-3 bg-gray-900 dark:bg-black rounded-md max-h-48 overflow-y-auto">
                            <div className="flex items-center text-gray-400 text-xs mb-2">
                                <TerminalSquareIcon size={14} className="mr-2"/> Job Logs
                            </div>
                            <div className="font-mono text-xs text-green-400 space-y-1">
                                {logs.map((log, index) => (
                                    <p key={index} className="whitespace-pre-wrap">{`[${new Date().toLocaleTimeString()}] ${log}`}</p>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
