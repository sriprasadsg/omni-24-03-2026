import React from 'react';
import { ApiDocEndpoint } from '../types';
import { BookKeyIcon, CogIcon } from './icons';

interface DeveloperHubDashboardProps {
    endpoints: ApiDocEndpoint[];
}

const MethodBadge: React.FC<{ method: ApiDocEndpoint['method'] }> = ({ method }) => {
    const colors: Record<ApiDocEndpoint['method'], string> = {
        GET: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
        POST: 'bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/30',
        PUT: 'bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30',
        DELETE: 'bg-rose-500/20 text-rose-600 dark:text-rose-400 border-rose-500/30',
    };
    return (
        <span className={`px-3 py-1 text-[10px] font-black rounded-lg border uppercase tracking-widest ${colors[method]}`}>
            {method}
        </span>
    );
};

export const DeveloperHubDashboard: React.FC<DeveloperHubDashboardProps> = ({ endpoints }) => {
    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 bg-clip-text text-transparent flex items-center gap-3">
                    <BookKeyIcon size={36} className="text-emerald-500" />
                    Developer Hub
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg font-medium">
                    Explore the Omni-Agent AI Platform API to build custom integrations and automations.
                </p>
            </header>

            <div className="glass-premium rounded-3xl shadow-2xl overflow-hidden border border-white/10">
                <div className="p-6 border-b border-white/10 flex justify-between items-center bg-black/5 dark:bg-white/5">
                    <h3 className="text-xl font-bold flex items-center gap-2 italic uppercase tracking-tighter">
                        <CogIcon size={24} className="text-emerald-500" />
                        API Reference
                    </h3>
                    <div className="flex gap-2">
                        <span className="px-3 py-1 bg-green-500/10 text-green-500 rounded-lg text-[10px] font-black uppercase tracking-widest border border-green-500/20">v2.0 Stable</span>
                        <span className="px-3 py-1 bg-blue-500/10 text-blue-500 rounded-lg text-[10px] font-black uppercase tracking-widest border border-blue-500/20">REST API</span>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-[10px] font-black uppercase tracking-widest bg-black/20 dark:bg-white/5 text-gray-500">
                            <tr>
                                <th scope="col" className="px-8 py-5 w-32">Method</th>
                                <th scope="col" className="px-6 py-5">Endpoint Path</th>
                                <th scope="col" className="px-8 py-5">Functionality & Scope</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {endpoints.map(endpoint => (
                                <tr key={endpoint.id} className="hover:bg-white/5 transition-colors group">
                                    <td className="px-8 py-6">
                                        <MethodBadge method={endpoint.method} />
                                    </td>
                                    <td className="px-6 py-6 transition-all group-hover:translate-x-1">
                                        <code className="px-3 py-1.5 rounded-lg bg-black/10 dark:bg-white/5 border border-white/5 text-gray-800 dark:text-gray-200 font-mono text-[11px] font-bold">
                                            {endpoint.path}
                                        </code>
                                    </td>
                                    <td className="px-8 py-6 text-gray-600 dark:text-gray-400 font-medium text-sm">
                                        {endpoint.description}
                                    </td>
                                </tr>
                            ))}
                            {endpoints.length === 0 && (
                                <tr>
                                    <td colSpan={3} className="py-24 text-center">
                                        <BookKeyIcon size={48} className="mx-auto text-gray-400 opacity-20 mb-4" />
                                        <p className="font-black text-gray-500 uppercase tracking-widest text-lg">Documentation Depleted</p>
                                        <p className="text-xs text-gray-400 mt-1 uppercase font-bold">Synchronizing with gateway records...</p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
