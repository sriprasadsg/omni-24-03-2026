import React from 'react';
import { Agent, Asset } from '../types';
import { ComponentIcon } from './icons';

interface Props {
    agent: Agent;
    asset?: Asset;
}

type SoftwareItem = {
    name: string;
    version: string;
    installDate?: string;
    updateAvailable?: boolean;
    latestVersion?: string;
};

export const AgentSoftwareTab: React.FC<Props> = ({ agent, asset }) => {
    const softwareList: SoftwareItem[] = (asset?.installedSoftware as SoftwareItem[] | undefined) || (agent?.meta as any)?.installed_software || [];

    return (
        <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center">
                <ComponentIcon size={20} className="mr-2" />
                Installed Software ({softwareList.length})
            </h3>
            {softwareList.length > 0 ? (
                <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-lg">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-800">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Name</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Version</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Install Date</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {softwareList.map((sw, idx) => (
                                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-200 font-medium">
                                        <div className="flex items-center">
                                            {sw.name}
                                            {sw.updateAvailable && (
                                                <span title="Update Available" className="ml-2 w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 font-mono text-xs">
                                        {sw.version}
                                        {sw.latestVersion && (
                                            <div className="text-red-500 dark:text-red-400 font-bold mt-1">Latest: {sw.latestVersion}</div>
                                        )}
                                    </td>
                                    <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">{sw.installDate || 'Unknown'}</td>
                                    <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                                        {sw.updateAvailable ? (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                                                Update Available
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                                                Up to date
                                            </span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <p className="text-gray-500 dark:text-gray-400 italic">No installed software detected.</p>
            )}
        </div>
    );
};
