import React from 'react';
import { AiSystem, AiRiskSeverity } from '../types';
import { BotIcon, ActivityIcon, AlertTriangleIcon } from './icons';

interface AIGovernanceSummaryProps {
    aiSystems: AiSystem[];
}

const StatCard: React.FC<{ title: string; value: string | number; icon: React.ReactNode; className?: string }> = ({ title, value, icon, className = '' }) => (
    <div className={`bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex items-center ${className}`}>
        <div className="p-3 bg-primary-100 dark:bg-primary-900/50 rounded-full mr-4 text-primary-500 dark:text-primary-400">
            {icon}
        </div>
        <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
        </div>
    </div>
);

const severityClasses: Record<AiRiskSeverity, string> = {
  Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
};


export const AIGovernanceSummary: React.FC<AIGovernanceSummaryProps> = ({ aiSystems }) => {
    const totalSystems = aiSystems.length;

    const statusCounts = aiSystems.reduce((acc, system) => {
        acc[system.status] = (acc[system.status] || 0) + 1;
        return acc;
    }, {} as Record<AiSystem['status'], number>);

    const highPriorityRisks = aiSystems.flatMap(system => 
        system.risks
            .filter(risk => risk.status === 'Open' && (risk.severity === 'Critical' || risk.severity === 'High'))
            .map(risk => ({ ...risk, systemName: system.name }))
    ).sort((a, b) => (a.severity === 'Critical' ? -1 : 1) - (b.severity === 'Critical' ? -1 : 1));

    const highPriorityRiskCount = highPriorityRisks.length;
    const topRisks = highPriorityRisks.slice(0, 5);

    return (
        <div className="mb-6 space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
                <StatCard title="Total AI Systems" value={totalSystems} icon={<BotIcon />} />
                
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                     <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Systems by Status</p>
                     <div className="flex justify-around items-center h-full">
                        <div className="text-center">
                            <p className="text-2xl font-bold text-green-500">{statusCounts['Active'] || 0}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Active</p>
                        </div>
                         <div className="text-center">
                            <p className="text-2xl font-bold text-blue-500">{statusCounts['In Development'] || 0}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">In Dev</p>
                        </div>
                         <div className="text-center">
                            <p className="text-2xl font-bold text-gray-500">{statusCounts['Sunset'] || 0}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Sunset</p>
                        </div>
                     </div>
                </div>
                
                <StatCard title="Open High-Priority Risks" value={highPriorityRiskCount} icon={<AlertTriangleIcon />} />
            </div>

            {topRisks.length > 0 && (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h3 className="text-lg font-semibold flex items-center">
                            <ActivityIcon className="mr-2 text-red-500" />
                            High-Priority Risk Overview
                        </h3>
                    </div>
                    <div className="p-4">
                         <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                                <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                    <tr>
                                        <th scope="col" className="px-4 py-3">Risk</th>
                                        <th scope="col" className="px-4 py-3">AI System</th>
                                        <th scope="col" className="px-4 py-3">Severity</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {topRisks.map(risk => (
                                        <tr key={risk.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                            <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{risk.title}</td>
                                            <td className="px-4 py-3">{risk.systemName}</td>
                                            <td className="px-4 py-3">
                                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[risk.severity]}`}>{risk.severity}</span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
