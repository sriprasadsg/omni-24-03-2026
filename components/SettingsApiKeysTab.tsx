import React from 'react';
import { ApiKey } from '../types';
import { PlusCircleIcon, TrashIcon, AlertTriangleIcon } from './icons';

const WARN_DAYS = 90;
const CRITICAL_DAYS = 180;

function keyAgeDays(createdAt: string): number {
    return Math.floor((Date.now() - new Date(createdAt).getTime()) / 86_400_000);
}

interface Props {
    apiKeys: ApiKey[];
    onGenerate: () => void;
    onRevoke: (keyId: string) => void;
}

export function SettingsApiKeysTab({ apiKeys, onGenerate, onRevoke }: Props) {
    const staleKeys = apiKeys.filter(k => keyAgeDays(k.createdAt) >= WARN_DAYS);

    return (
        <div>
            <div className="flex justify-between items-center mb-4">
                <div>
                    <h3 className="text-lg font-semibold">API Keys</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage API keys for programmatic access. Rotate keys every 90 days.</p>
                </div>
                <button onClick={onGenerate} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                    <PlusCircleIcon size={16} className="mr-1.5" />
                    Generate New Key
                </button>
            </div>

            {staleKeys.length > 0 && (
                <div className="mb-4 flex items-start gap-2 px-4 py-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-sm text-amber-800 dark:text-amber-300">
                    <AlertTriangleIcon size={16} className="flex-shrink-0 mt-0.5" />
                    <span>
                        {staleKeys.length} key{staleKeys.length > 1 ? 's are' : ' is'} overdue for rotation.
                        Rotate API keys every {WARN_DAYS} days to maintain security hygiene.
                    </span>
                </div>
            )}

            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-4 py-3">Name</th>
                            <th scope="col" className="px-4 py-3">Key</th>
                            <th scope="col" className="px-4 py-3">Created</th>
                            <th scope="col" className="px-4 py-3">Age</th>
                            <th scope="col" className="px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {apiKeys.map(key => {
                            const age = keyAgeDays(key.createdAt);
                            const isCritical = age >= CRITICAL_DAYS;
                            const isWarn = age >= WARN_DAYS;
                            const ageBadge = isCritical
                                ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                                : isWarn
                                ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                                : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400';
                            const ageLabel = age < 1 ? 'Today' : age === 1 ? '1 day' : `${age} days`;
                            return (
                                <tr key={key.id} className={`border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 ${isCritical ? 'bg-red-50/30 dark:bg-red-900/10' : isWarn ? 'bg-amber-50/30 dark:bg-amber-900/10' : ''}`}>
                                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{key.name}</td>
                                    <td className="px-4 py-3 font-mono text-xs">{`${key.key.substring(0, 11)}...${key.key.slice(-4)}`}</td>
                                    <td className="px-4 py-3 text-xs">{new Date(key.createdAt).toLocaleDateString()}</td>
                                    <td className="px-4 py-3">
                                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${ageBadge}`}>
                                            {(isWarn) && <AlertTriangleIcon size={11} />}
                                            {ageLabel}
                                            {isCritical && ' — rotate now'}
                                            {isWarn && !isCritical && ' — rotate soon'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <button onClick={() => onRevoke(key.id)} className="flex items-center text-xs font-medium text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300">
                                            <TrashIcon size={14} className="mr-1" /> Revoke
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
