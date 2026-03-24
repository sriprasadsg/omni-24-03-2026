import React from 'react';
import { GitMergeIcon, ClockIcon, AlertTriangleIcon } from './icons';
import { Trace, ServiceMap } from '../types';

interface DistributedTracingDashboardProps {
    traces: Trace[];
    serviceMap: ServiceMap | null;
}

export const DistributedTracingDashboard: React.FC<DistributedTracingDashboardProps> = ({ traces, serviceMap }) => {

    if (!serviceMap) {
        return (
            <div className="container mx-auto text-center p-8">
                <p className="text-gray-500 dark:text-gray-400">Loading tracing data...</p>
            </div>
        )
    }

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-primary-600 via-indigo-600 to-accent-600 bg-clip-text text-transparent flex items-center gap-3">
                    <GitMergeIcon size={36} className="text-primary-500" />
                    Distributed Tracing
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Visualize request flows and identify performance bottlenecks in your microservices architecture.
                </p>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Service Map */}
                <div className="glass-premium rounded-3xl overflow-hidden">
                    <div className="p-6 border-b border-white/10 dark:border-white/5 bg-gradient-to-r from-primary-500/5 to-transparent">
                        <h3 className="text-xl font-bold flex items-center gap-3">
                            <GitMergeIcon className="text-primary-500" />
                            Live Service Map
                        </h3>
                    </div>
                    <div className="p-8 h-96 relative overflow-hidden">
                        {/* Simplified visualization with glass blocks */}
                        <div className="absolute top-1/2 left-12 w-40 h-24 glass dark:glass border border-primary-500/30 rounded-2xl p-4 text-center shadow-lg transform hover:scale-105 transition-all">
                            <strong className="text-primary-600 dark:text-primary-400 block mb-1">{serviceMap.nodes[0].id}</strong>
                            <div className="text-sm font-semibold">{serviceMap.nodes[0].requestCount} reqs</div>
                            <div className="text-xs text-gray-500">{serviceMap.nodes[0].avgLatency}ms avg</div>
                        </div>
                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-40 h-24 glass dark:glass border border-indigo-500/30 rounded-2xl p-4 text-center shadow-lg transform hover:scale-105 transition-all">
                            <strong className="text-indigo-600 dark:text-indigo-400 block mb-1">{serviceMap.nodes[1].id}</strong>
                            <div className="text-sm font-semibold">{serviceMap.nodes[1].requestCount} reqs</div>
                            <div className="text-xs text-gray-500">{serviceMap.nodes[1].avgLatency}ms avg</div>
                        </div>
                        <div className="absolute top-1/2 right-12 -translate-y-full w-40 h-24 glass dark:glass border border-accent-500/30 rounded-2xl p-4 text-center shadow-lg transform hover:scale-105 transition-all">
                            <strong className="text-accent-600 dark:text-accent-400 block mb-1">{serviceMap.nodes[2].id}</strong>
                            <div className="text-sm font-semibold">{serviceMap.nodes[2].requestCount} reqs</div>
                            <div className="text-xs text-gray-500">{serviceMap.nodes[2].avgLatency}ms avg</div>
                        </div>
                        {/* Connectors with gradient anim */}
                        <svg className="absolute inset-0 w-full h-full -z-10 opacity-30">
                            <defs>
                                <linearGradient id="trace-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                                    <stop offset="0%" stopColor="#4f46e5" />
                                    <stop offset="100%" stopColor="#818cf8" />
                                </linearGradient>
                            </defs>
                            <line x1="200" y1="192" x2="320" y2="192" stroke="url(#trace-grad)" strokeWidth="3" strokeDasharray="5,5" />
                            <line x1="430" y1="192" x2="520" y2="100" stroke="url(#trace-grad)" strokeWidth="3" strokeDasharray="5,5" />
                        </svg>
                    </div>
                </div>

                {/* Trace Explorer */}
                <div className="glass-premium rounded-3xl overflow-hidden">
                    <div className="p-6 border-b border-white/10 dark:border-white/5 bg-gradient-to-r from-indigo-500/5 to-transparent">
                        <h3 className="text-xl font-bold">Trace Explorer</h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-gray-400 uppercase bg-black/5 dark:bg-white/5 font-bold">
                                <tr>
                                    <th className="px-6 py-4">Root Span</th>
                                    <th className="px-6 py-4">Duration</th>
                                    <th className="px-6 py-4 text-center">Services</th>
                                    <th className="px-6 py-4">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {traces.map(trace => (
                                    <tr key={trace.id} className="hover:bg-primary-500/5 transition-colors cursor-pointer group">
                                        <td className="px-6 py-5">
                                            <div className="font-mono text-xs font-bold text-primary-600 dark:text-primary-400 group-hover:translate-x-1 transition-transform">{trace.rootSpan.name}</div>
                                            <div className="text-[10px] text-gray-400 mt-1 uppercase tracking-tighter">{trace.id.substring(0, 12)}...</div>
                                        </td>
                                        <td className="px-6 py-5">
                                            <div className="flex items-center gap-2 font-semibold">
                                                <ClockIcon size={14} className="text-indigo-500" />
                                                {trace.totalDuration}ms
                                            </div>
                                        </td>
                                        <td className="px-6 py-5 text-center font-bold">
                                            <span className="px-2 py-1 bg-white/10 rounded-lg">{trace.serviceCount}</span>
                                        </td>
                                        <td className="px-6 py-5">
                                            {trace.errorCount > 0 ?
                                                <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full font-bold text-xs uppercase animate-pulse">
                                                    <AlertTriangleIcon size={12} /> {trace.errorCount} Errors
                                                </span>
                                                : <span className="inline-flex items-center px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full font-bold text-xs uppercase">Healthy</span>
                                            }
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
};
