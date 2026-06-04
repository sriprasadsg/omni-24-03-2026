import React from 'react';
import { CheckIcon, AlertTriangleIcon } from './icons';

interface DeployResult {
    success: boolean;
    message: string;
    taskIds?: string[];
}

interface Props {
    isOpen: boolean;
    result: DeployResult | null;
    onClose: () => void;
    onViewHistory: () => void;
}

export function SoftwareDeployModal({ isOpen, result, onClose, onViewHistory }: Props) {
    if (!isOpen || !result) return null;
    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className={`bg-slate-900 border rounded-xl p-8 max-w-md w-full max-h-[90vh] overflow-y-auto shadow-2xl ${result.success ? 'border-green-500/50' : 'border-red-500/50'}`}>
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center space-x-3">
                        {result.success ? (
                            <div className="w-12 h-12 bg-green-500/20 rounded-xl flex items-center justify-center">
                                <CheckIcon className="w-6 h-6 text-green-400" />
                            </div>
                        ) : (
                            <div className="w-12 h-12 bg-red-500/20 rounded-xl flex items-center justify-center">
                                <AlertTriangleIcon className="w-6 h-6 text-red-400" />
                            </div>
                        )}
                        <div>
                            <h3 className="text-xl font-bold text-slate-100">
                                {result.success ? 'Deployment Dispatched!' : 'Deployment Failed'}
                            </h3>
                            <p className="text-slate-400 text-sm">{result.taskIds?.length || 0} Agent(s) Targeted</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-lg transition-colors">
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                        </svg>
                    </button>
                </div>
                <div className="space-y-4 mb-6">
                    <div className="bg-slate-800/50 p-4 rounded-lg">
                        <p className={`font-semibold ${result.success ? 'text-green-400' : 'text-red-400'}`}>{result.message}</p>
                    </div>
                    {result.taskIds && result.taskIds.length > 0 && (
                        <div>
                            <p className="text-sm text-slate-400 mb-2">Task ID{result.taskIds.length > 1 ? 's' : ''}:</p>
                            <div className="flex flex-wrap gap-2">
                                {result.taskIds.map(id => (
                                    <span key={id} className="bg-blue-500/20 text-blue-300 px-3 py-1 rounded-full text-xs font-mono">
                                        {id.substring(0, 8)}…
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
                <div className="flex gap-3 pt-4 border-t border-slate-700">
                    <button
                        onClick={onClose}
                        className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 py-2 px-4 rounded-lg transition-colors font-medium"
                    >
                        Close
                    </button>
                    {result.success && (
                        <button
                            onClick={() => { onClose(); onViewHistory(); }}
                            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg transition-colors font-medium"
                        >
                            View in History
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
