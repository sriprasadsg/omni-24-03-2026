import React, { useState, useEffect } from 'react';
import { Playbook, SecurityEvent, SecurityCase, PlaybookExecutionStatus, PlaybookExecutionStep } from '../types';
import { XIcon, BotIcon, ZapIcon, TerminalSquareIcon, CogIcon, CheckIcon, AlertTriangleIcon } from './icons';
import { executePlaybook } from '../services/apiService';

interface ExecutePlaybookModalProps {
  isOpen: boolean;
  onClose: () => void;
  playbook: Playbook | null;
  events: SecurityEvent[];
  cases: SecurityCase[];
}

export const ExecutePlaybookModal: React.FC<ExecutePlaybookModalProps> = ({ isOpen, onClose, playbook, events, cases }) => {
    const [targetType, setTargetType] = useState<'event' | 'case' | ''>('');
    const [targetId, setTargetId] = useState<string>('');
    const [executionStatus, setExecutionStatus] = useState<PlaybookExecutionStatus>('idle');
    const [executionLog, setExecutionLog] = useState<PlaybookExecutionStep[]>([]);
    
    useEffect(() => {
        if (isOpen) {
            // Reset state when modal opens
            setTargetType('');
            setTargetId('');
            setExecutionStatus('idle');
            setExecutionLog([]);
        }
    }, [isOpen]);

    const handleExecute = async () => {
        if (!playbook || !targetId || !targetType) return;
        
        setExecutionStatus('running');
        setExecutionLog([]);

        try {
            for await (const step of executePlaybook(playbook.id, targetId, targetType)) {
                setExecutionLog(prev => [...prev, step]);
            }
            setExecutionStatus('completed');
        } catch (error) {
            const errorStep: PlaybookExecutionStep = {
                timestamp: new Date().toISOString(),
                message: `Execution failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
                status: 'error',
            };
            setExecutionLog(prev => [...prev, errorStep]);
            setExecutionStatus('failed');
        }
    };

    if (!isOpen || !playbook) return null;
    
    const isExecutionStarted = executionStatus !== 'idle';

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center"><BotIcon className="mr-3 text-primary-500"/> Execute Playbook</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{playbook.name}</p>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>
                
                <div className="flex-grow space-y-4 overflow-y-auto pr-2">
                    {!isExecutionStarted ? (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Target Type</label>
                                <div className="mt-2 flex gap-4">
                                    <label className="flex items-center">
                                        <input type="radio" name="targetType" value="event" checked={targetType === 'event'} onChange={() => { setTargetType('event'); setTargetId(''); }} className="h-4 w-4 text-primary-600 border-gray-300 focus:ring-primary-500"/>
                                        <span className="ml-2 text-sm text-gray-600 dark:text-gray-300">Security Event</span>
                                    </label>
                                    <label className="flex items-center">
                                        <input type="radio" name="targetType" value="case" checked={targetType === 'case'} onChange={() => { setTargetType('case'); setTargetId(''); }} className="h-4 w-4 text-primary-600 border-gray-300 focus:ring-primary-500"/>
                                        <span className="ml-2 text-sm text-gray-600 dark:text-gray-300">Security Case</span>
                                    </label>
                                </div>
                            </div>
                            {targetType && (
                                <div>
                                    <label htmlFor="targetId" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Select Target</label>
                                    <select id="targetId" value={targetId} onChange={e => setTargetId(e.target.value)}
                                        className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                                    >
                                        <option value="">-- Select a {targetType} --</option>
                                        {targetType === 'event' && events.map(e => <option key={e.id} value={e.id}>{e.id} - {e.description.substring(0, 50)}...</option>)}
                                        {targetType === 'case' && cases.map(c => <option key={c.id} value={c.id}>{c.id} - {c.title}</option>)}
                                    </select>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div>
                            <div className="flex justify-between items-center mb-2">
                                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 flex items-center">
                                    <TerminalSquareIcon size={14} className="mr-1.5" />
                                    Execution Log
                                </h3>
                                {executionStatus === 'running' && <span className="flex items-center text-sm font-medium text-amber-600 dark:text-amber-400"><CogIcon size={16} className="animate-spin mr-2"/>Running...</span>}
                                {executionStatus === 'completed' && <span className="flex items-center text-sm font-medium text-green-600 dark:text-green-400"><CheckIcon size={16} className="mr-2"/>Completed</span>}
                                {executionStatus === 'failed' && <span className="flex items-center text-sm font-medium text-red-600 dark:text-red-400"><AlertTriangleIcon size={16} className="mr-2"/>Failed</span>}
                            </div>
                            <div className="p-3 bg-gray-900 dark:bg-black rounded-md max-h-64 overflow-y-auto font-mono text-xs">
                                {executionLog.map((log, index) => (
                                    <div key={index} className="flex items-start">
                                        <span className="text-gray-500 mr-3">{new Date(log.timestamp).toLocaleTimeString()}</span>
                                        {log.status === 'running' && <CogIcon size={12} className="animate-spin mr-2 mt-0.5 text-amber-400 flex-shrink-0" />}
                                        {log.status === 'success' && <CheckIcon size={12} className="mr-2 mt-0.5 text-green-400 flex-shrink-0" />}
                                        {log.status === 'error' && <AlertTriangleIcon size={12} className="mr-2 mt-0.5 text-red-400 flex-shrink-0" />}
                                        <p className={`${log.status === 'error' ? 'text-red-400' : 'text-gray-300'}`}>{log.message}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
                
                <div className="flex-shrink-0 mt-6 flex justify-end items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button type="button" onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none"
                    >
                        {isExecutionStarted ? 'Close' : 'Cancel'}
                    </button>
                    {!isExecutionStarted && (
                        <button type="button" onClick={handleExecute} disabled={!targetId}
                            className="ml-3 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none disabled:bg-primary-400 disabled:cursor-not-allowed flex items-center"
                        >
                            <ZapIcon size={16} className="mr-2" />
                            Execute
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};
