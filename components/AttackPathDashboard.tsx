import React from 'react';
import { AttackPath } from '../types';
import { NetworkIcon, ShieldAlertIcon, BoxIcon } from './icons';

interface AttackPathDashboardProps {
    attackPaths: AttackPath[];
}

const NodeCard: React.FC<{ node: AttackPath['nodes'][0] }> = ({ node }) => {
    const icons = {
        'Public Asset': <ShieldAlertIcon className="text-red-500" size={24} />,
        'Internal Service': <BoxIcon className="text-indigo-500" size={24} />,
        'Database': <BoxIcon className="text-purple-500" size={24} />,
        'Crown Jewel': <ShieldAlertIcon className="text-amber-500 animate-pulse" size={24} />,
    };

    return (
        <div className="glass-premium p-4 rounded-2xl hover:scale-105 transition-all cursor-pointer group">
            <div className="flex items-center gap-4">
                <div className="p-2 bg-white/5 rounded-xl group-hover:bg-primary-500/10 transition-colors">
                    {icons[node.type] || <BoxIcon size={24} />}
                </div>
                <div>
                    <p className="font-bold text-gray-800 dark:text-gray-100 uppercase tracking-tight">{node.label}</p>
                    <p className="text-[10px] font-black text-gray-500 dark:text-gray-400 uppercase tracking-widest">{node.type}</p>
                </div>
            </div>
        </div>
    );
};


export const AttackPathDashboard: React.FC<AttackPathDashboardProps> = ({ attackPaths }) => {

    // For simplicity, we'll just show the first attack path
    const displayPath = attackPaths[0];
    if (!displayPath) return (
        <div className="flex flex-col items-center justify-center p-12 glass-premium rounded-3xl text-gray-500">
            <NetworkIcon size={48} className="mb-4 opacity-20" />
            <p className="text-xl font-bold">No High-Risk Attack Paths Identified</p>
            <p className="text-sm">Your infrastructure perimeter remains secure.</p>
        </div>
    );

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-primary-600 via-indigo-600 to-accent-600 bg-clip-text text-transparent flex items-center gap-3">
                    <NetworkIcon size={36} className="text-primary-500" />
                    Attack Path Analysis
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Strategic visualization of potential adversary paths to your crown jewel assets.
                </p>
            </header>

            <div className="glass-premium rounded-3xl p-8 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8">
                    <div className="px-4 py-1.5 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full text-xs font-black uppercase tracking-widest animate-pulse border border-red-500/20">
                        High Priority Scenario
                    </div>
                </div>

                <div className="mb-12">
                    <h3 className="text-2xl font-black text-gray-800 dark:text-white uppercase tracking-tighter italic">
                        Scenario: <span className="text-primary-600">{displayPath.name}</span>
                    </h3>
                </div>

                <div className="relative border-t border-white/5 pt-12">
                    <div className="flex flex-col items-center space-y-6">
                        {/* Debug logging */}
                        {console.log('AttackPathDashboard render:', displayPath)}
                        {(displayPath.nodes || []).map((node, index) => (
                            <React.Fragment key={node.id}>
                                <div className="w-80">
                                    <NodeCard node={node} />
                                </div>
                                {index < displayPath.nodes.length - 1 && (
                                    <div className="flex flex-col items-center py-2">
                                        <div className="h-16 w-1 bg-gradient-to-b from-primary-500 to-indigo-500 rounded-full relative shadow-[0_0_15px_rgba(79,70,229,0.5)]">
                                            <div className="absolute top-1/2 left-4 whitespace-nowrap">
                                                <div className="bg-white/5 dark:bg-black/20 backdrop-blur-md px-3 py-1 rounded-full border border-white/10 text-[10px] font-black text-indigo-500 uppercase tracking-widest">
                                                    {(displayPath.edges || []).find(e => e.from === node.id)?.label}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </React.Fragment>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};
