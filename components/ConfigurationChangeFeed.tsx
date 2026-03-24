import React from 'react';
import { NetworkDevice } from '../types';
import { HistoryIcon } from './icons';

interface ConfigurationChangeFeedProps {
    devices: NetworkDevice[];
}

export const ConfigurationChangeFeed: React.FC<ConfigurationChangeFeedProps> = ({ devices }) => {
    const changes = (devices || [])
        .flatMap(d => (d.configBackups || []).filter(b => b.diff !== null).map(b => ({ ...b, deviceName: d.hostname })))
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, 5);

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold flex items-center">
                    <HistoryIcon className="mr-2" />
                    Config Changes
                </h3>
            </div>
            <div className="p-4 space-y-3 max-h-48 overflow-y-auto">
                {changes.map(change => (
                    <div key={change.id}>
                        <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">{change.deviceName}</p>
                        <p className="font-mono text-xs bg-gray-100 dark:bg-gray-900 rounded p-1 mt-1 whitespace-pre-wrap">{change.diff}</p>
                        <p className="text-xs text-gray-400 text-right">{new Date(change.timestamp).toLocaleString()}</p>
                    </div>
                ))}
                {changes.length === 0 && <p className="text-xs text-center text-gray-500">No recent config changes.</p>}
            </div>
        </div>
    );
};
