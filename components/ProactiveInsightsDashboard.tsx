import React from 'react';
import { LightbulbIcon, AlertTriangleIcon, ActivityIcon, CheckIcon, ClockIcon } from './icons';
import { ProactiveInsight } from '../types';

interface ProactiveInsightsDashboardProps {
    insights: ProactiveInsight[];
}

const severityClasses = {
    High: 'border-orange-500 bg-orange-50 dark:bg-orange-900/50 text-orange-800 dark:text-orange-300',
    Medium: 'border-amber-500 bg-amber-50 dark:bg-amber-900/50 text-amber-800 dark:text-amber-300',
    Low: 'border-blue-500 bg-blue-50 dark:bg-blue-900/50 text-blue-800 dark:text-blue-300',
};

export const ProactiveInsightsDashboard: React.FC<ProactiveInsightsDashboardProps> = ({ insights }) => {

    const insightGroups = {
        predictive: insights.filter(i => i.type === 'PREDICTIVE_ALERT'),
        anomalies: insights.filter(i => i.type === 'ANOMALY_DETECTION'),
        rca: insights.filter(i => i.type === 'ROOT_CAUSE_ANALYSIS'),
    };

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-amber-600 via-orange-600 to-red-600 bg-clip-text text-transparent flex items-center gap-3">
                    <LightbulbIcon size={36} className="text-amber-500" />
                    Proactive Insights
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    AI-driven predictions, anomaly detection, and root cause analysis to prevent issues before they impact users.
                </p>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Predictive Alerts Section */}
                <div className="glass-premium rounded-3xl p-6 flex flex-col h-full shadow-lg">
                    <h3 className="text-xl font-bold text-gray-800 dark:text-white mb-6 flex items-center gap-3">
                        <ClockIcon className="text-primary-500" />
                        Predictive Alerts
                    </h3>
                    <div className="space-y-4 flex-1">
                        {insightGroups.predictive.map(insight => (
                            <div key={insight.id} className={`p-4 rounded-2xl border border-white/10 hover:scale-[1.02] transition-all cursor-pointer ${insight.severity === 'High' ? 'bg-orange-500/10 border-orange-500/30' :
                                    insight.severity === 'Medium' ? 'bg-amber-500/10 border-amber-500/30' :
                                        'bg-blue-500/10 border-blue-500/30'
                                }`}>
                                <div className="flex justify-between items-start mb-2">
                                    <p className={`font-black text-xs uppercase tracking-widest ${insight.severity === 'High' ? 'text-red-600 dark:text-red-400' :
                                            insight.severity === 'Medium' ? 'text-orange-600 dark:text-orange-400' :
                                                'text-blue-600 dark:text-blue-400'
                                        }`}>{insight.title}</p>
                                    <span className="text-[10px] font-black opacity-50 uppercase">{insight.severity}</span>
                                </div>
                                <p className="text-sm text-gray-600 dark:text-gray-300 font-medium">{insight.summary}</p>
                                <div className="mt-3 flex items-center gap-2">
                                    <div className="h-1.5 w-1.5 rounded-full bg-primary-500 animate-pulse" />
                                    <p className="text-[10px] text-gray-400 font-mono uppercase tracking-tighter">{insight.details.entity}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Anomaly Detection Section */}
                <div className="glass-premium rounded-3xl p-6 flex flex-col h-full shadow-lg">
                    <h3 className="text-xl font-bold text-gray-800 dark:text-white mb-6 flex items-center gap-3">
                        <ActivityIcon className="text-primary-500" />
                        Anomaly Detections
                    </h3>
                    <div className="space-y-4 flex-1">
                        {insightGroups.anomalies.map(insight => (
                            <div key={insight.id} className="p-4 rounded-2xl border border-white/10 bg-white/5 hover:bg-white/10 transition-all cursor-pointer group">
                                <div className="flex justify-between items-start mb-2">
                                    <p className="font-bold text-sm text-gray-800 dark:text-gray-100 group-hover:translate-x-1 transition-transform">{insight.title}</p>
                                    <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${insight.severity === 'High' ? 'bg-red-500 text-white' : 'bg-gray-500 text-white'
                                        }`}>{insight.severity}</span>
                                </div>
                                <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{insight.summary}</p>
                                <div className="mt-3 text-[10px] font-mono text-indigo-500 opacity-70">{insight.details.entity}</div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Root Cause Analysis Section */}
                <div className="glass-premium rounded-3xl p-6 flex flex-col h-full shadow-lg border-l-4 border-primary-500">
                    <h3 className="text-xl font-bold text-gray-800 dark:text-white mb-6 flex items-center gap-3">
                        <LightbulbIcon className="text-primary-500" />
                        AI Root Cause (RCA)
                    </h3>
                    <div className="space-y-6 flex-1">
                        {insightGroups.rca.map(rca => (
                            <div key={rca.id} className="space-y-4">
                                <div className="flex justify-between items-start">
                                    <div className="space-y-1">
                                        <h4 className="font-black text-gray-800 dark:text-white uppercase tracking-tighter italic">{rca.title}</h4>
                                        <div className="flex items-center gap-1 text-[10px] text-gray-500 uppercase font-black">
                                            <ClockIcon size={10} />
                                            {new Date(rca.timestamp).toLocaleTimeString()}
                                        </div>
                                    </div>
                                    <span className="flex items-center gap-1.5 px-3 py-1 bg-green-500/10 text-green-600 dark:text-green-400 rounded-full text-[10px] font-black uppercase border border-green-500/20">
                                        {rca.details.status}
                                    </span>
                                </div>
                                <div className="glass p-4 rounded-2xl border border-primary-500/20 text-sm italic text-gray-600 dark:text-gray-300 relative overflow-hidden group">
                                    <div className="absolute top-0 left-0 w-1 h-full bg-primary-500" />
                                    {rca.summary}
                                </div>
                            </div>
                        ))}
                        {insightGroups.rca.length === 0 && (
                            <div className="flex flex-col items-center justify-center h-full text-gray-500 py-12">
                                <CheckIcon size={48} className="opacity-20 mb-4" />
                                <p className="font-bold">No RCA Tasks</p>
                                <p className="text-xs">System state is stable.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
