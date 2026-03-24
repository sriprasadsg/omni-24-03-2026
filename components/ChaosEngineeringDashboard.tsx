import React, { useState } from 'react';
import { ChaosExperiment } from '../types';
import { BombIcon, TestTubeIcon, ZapIcon, CheckIcon, XCircleIcon, CogIcon, ClockIcon } from './icons';

interface ChaosEngineeringDashboardProps {
    experiments: ChaosExperiment[];
}

const statusInfo: Record<ChaosExperiment['status'], { icon: React.ReactNode; classes: string; }> = {
    Scheduled: { icon: <ClockIcon size={14} />, classes: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300' },
    Running: { icon: <CogIcon size={14} className="animate-spin" />, classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' },
    Completed: { icon: <CheckIcon size={14} />, classes: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' },
    Failed: { icon: <XCircleIcon size={14} />, classes: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' },
};


export const ChaosEngineeringDashboard: React.FC<ChaosEngineeringDashboardProps> = ({ experiments }) => {

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-red-600 via-orange-600 to-amber-600 bg-clip-text text-transparent flex items-center gap-3">
                    <BombIcon size={36} className="text-red-500" />
                    Chaos Engineering
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Proactively test system resilience by injecting controlled failures.
                </p>
            </header>

            <div className="glass-premium rounded-3xl shadow-2xl overflow-hidden border border-white/10">
                <div className="p-6 border-b border-white/10 flex justify-between items-center bg-black/5 dark:bg-white/5">
                    <h3 className="text-xl font-bold flex items-center gap-2 italic uppercase tracking-tighter">
                        <TestTubeIcon size={24} className="text-red-500" />
                        Experiment Registry
                    </h3>
                    <button className="bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-red-500/30 transition-all hover:scale-105">
                        New Chaos Hunt
                    </button>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-[10px] font-black uppercase tracking-widest bg-black/20 dark:bg-white/5 text-gray-500">
                            <tr>
                                <th scope="col" className="px-8 py-5">Experiment</th>
                                <th scope="col" className="px-6 py-5">Type</th>
                                <th scope="col" className="px-6 py-5">Blast Radius</th>
                                <th scope="col" className="px-6 py-5 text-center">Execution State</th>
                                <th scope="col" className="px-6 py-5 text-right">Last Payload</th>
                                <th scope="col" className="px-8 py-5 text-right">Ops</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {experiments.map(exp => (
                                <tr key={exp.id} className="hover:bg-white/5 transition-colors group">
                                    <td className="px-8 py-6">
                                        <div className="flex flex-col">
                                            <span className="font-black text-gray-800 dark:text-gray-100 uppercase tracking-tighter italic">{exp.name}</span>
                                            <span className="text-[10px] text-gray-400 uppercase font-bold tracking-widest mt-1">ID: {exp.id.slice(0, 8)}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-6 font-mono text-[10px] uppercase font-black text-red-500/80">{exp.type}</td>
                                    <td className="px-6 py-6">
                                        <code className="bg-white/5 px-2 py-1 rounded text-[10px] font-mono border border-white/5 text-gray-400">{exp.target}</code>
                                    </td>
                                    <td className="px-6 py-6 text-center">
                                        <span className={`inline-flex items-center gap-1.5 px-3 py-1 text-[10px] font-black rounded-full uppercase border ${exp.status === 'Running' ? 'bg-amber-500/10 text-amber-500 border-amber-500/30 animate-pulse' :
                                                exp.status === 'Completed' ? 'bg-green-500/10 text-green-500 border-green-500/30' :
                                                    exp.status === 'Failed' ? 'bg-red-500/10 text-red-500 border-red-500/30' :
                                                        'bg-blue-500/10 text-blue-500 border-blue-500/30'
                                            }`}>
                                            {statusInfo[exp.status].icon} {exp.status}
                                        </span>
                                    </td>
                                    <td className="px-6 py-6 text-right font-mono text-[10px] text-gray-500">
                                        {new Date(exp.lastRun).toLocaleString()}
                                    </td>
                                    <td className="px-8 py-6 text-right">
                                        <button className="inline-flex items-center gap-2 p-2 rounded-lg bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-500 transition-all border border-white/5">
                                            <ZapIcon size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                            {experiments.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="py-24 text-center">
                                        <BombIcon size={48} className="mx-auto text-gray-400 opacity-20 mb-4" />
                                        <p className="font-black text-gray-500 uppercase tracking-widest text-lg">No Active Experiments</p>
                                        <p className="text-xs text-gray-400 mt-1 uppercase font-bold">Safe harbor protocols engaged.</p>
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
