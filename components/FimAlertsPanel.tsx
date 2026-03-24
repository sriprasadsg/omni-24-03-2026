import React, { useState } from 'react';
import { CheckIcon, XIcon, AlertTriangleIcon, FileShieldIcon, ClockIcon } from './icons';

interface FimChange {
    path: string;
    status: 'new' | 'modified' | 'deleted';
    timestamp: string;
    old_checksum?: string;
    new_checksum?: string;
}

interface FimAlertsProps {
    changes?: FimChange[];
}

export const FimAlertsPanel: React.FC<FimAlertsProps> = ({ changes }) => {
    const [showAll, setShowAll] = useState(false);

    if (!changes || changes.length === 0) {
        return (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                <div className="flex items-center">
                    <CheckIcon size={20} className="text-green-600 dark:text-green-400 mr-3" />
                    <div>
                        <h4 className="font-semibold text-green-900 dark:text-green-200">No File Changes Detected</h4>
                        <p className="text-sm text-green-700 dark:text-green-300 mt-1">All monitored files match baseline</p>
                    </div>
                </div>
            </div>
        );
    }

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'new': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300';
            case 'modified': return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300';
            case 'deleted': return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300';
            default: return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300';
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'new': return <CheckIcon size={14} />;
            case 'modified': return <AlertTriangleIcon size={14} />;
            case 'deleted': return <XIcon size={14} />;
            default: return null;
        }
    };

    const displayChanges = showAll ? changes : changes.slice(0, 5);

    return (
        <div className="space-y-3">
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                <div className="flex items-start">
                    <AlertTriangleIcon size={20} className="text-yellow-600 dark:text-yellow-400 mt-0.5 mr-3" />
                    <div className="flex-grow">
                        <h4 className="font-semibold text-yellow-900 dark:text-yellow-200">File Changes Detected</h4>
                        <p className="text-sm text-yellow-800 dark:text-yellow-300 mt-1">
                            {changes.length} file{changes.length > 1 ? 's' : ''} changed since last baseline
                        </p>
                    </div>
                </div>
            </div>

            <div className="space-y-2">
                {displayChanges.map((change, idx) => (
                    <div key={idx} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                        <div className="flex items-start justify-between">
                            <div className="flex-grow">
                                <div className="flex items-center space-x-2">
                                    <FileShieldIcon size={16} className="text-gray-500 dark:text-gray-400" />
                                    <code className="text-sm font-mono text-gray-900 dark:text-gray-200">{change.path}</code>
                                </div>
                                <div className="flex items-center space-x-3 mt-2 text-xs text-gray-500 dark:text-gray-400">
                                    <div className="flex items-center">
                                        <ClockIcon size={12} className="mr-1" />
                                        {new Date(change.timestamp).toLocaleString()}
                                    </div>
                                    {change.old_checksum && change.new_checksum && (
                                        <div className="font-mono">
                                            {change.old_checksum.substring(0, 8)}...→{change.new_checksum.substring(0, 8)}...
                                        </div>
                                    )}
                                </div>
                            </div>
                            <span className={`px-2 py-1 text-xs font-medium rounded-full flex items-center whitespace-nowrap ml-3 ${getStatusColor(change.status)}`}>
                                {getStatusIcon(change.status)}
                                <span className="ml-1">{change.status.toUpperCase()}</span>
                            </span>
                        </div>
                    </div>
                ))}
            </div>

            {changes.length > 5 && (
                <button
                    onClick={() => setShowAll(!showAll)}
                    className="w-full text-center text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium py-2"
                >
                    {showAll ? 'Show Less' : `Show All ${changes.length} Changes`}
                </button>
            )}
        </div>
    );
};
