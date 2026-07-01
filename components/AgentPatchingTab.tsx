import React from 'react';
import { Agent } from '../types';
import { ServerIcon, HistoryIcon } from './icons';

interface Props {
    agent: Agent;
}

export const AgentPatchingTab: React.FC<Props> = ({ agent }) => {
    const patching = (agent.meta as any)?.system_patching;
    const pendingUpdates: any[] = patching?.pending_updates || [];

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-3 flex items-center">
                    <ServerIcon size={20} className="mr-2" />System Information
                </h3>
                <dl className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
                    <div className="sm:col-span-1">
                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">BIOS Version</dt>
                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{patching?.bios_info?.version || 'Unknown'}</dd>
                    </div>
                    <div className="sm:col-span-1">
                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Manufacturer</dt>
                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{patching?.bios_info?.manufacturer || 'Unknown'}</dd>
                    </div>
                    <div className="sm:col-span-1">
                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Release Date</dt>
                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{patching?.bios_info?.release_date || 'Unknown'}</dd>
                    </div>
                    <div className="sm:col-span-1">
                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Boot Time</dt>
                        <dd className="mt-1 text-sm text-gray-900 dark:text-gray-200">{patching?.uptime?.boot_time || 'Unknown'}</dd>
                    </div>
                </dl>
            </div>

            <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-3 flex items-center">
                    <HistoryIcon size={20} className="mr-2" />Pending Updates ({pendingUpdates.length})
                </h3>
                {pendingUpdates.length > 0 ? (
                    <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg max-h-60">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                            <thead className="bg-gray-50 dark:bg-gray-800 sticky top-0">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Update Title</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Severity</th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Mandatory</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                {pendingUpdates.map((update: any, idx: number) => (
                                    <tr key={idx}>
                                        <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-200">{update.title}</td>
                                        <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">{update.severity}</td>
                                        <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">{update.mandatory ? 'Yes' : 'No'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p className="text-sm text-gray-400 italic">No pending updates found.</p>
                )}
            </div>
        </div>
    );
};
