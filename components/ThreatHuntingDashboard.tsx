import React, { useState, useMemo } from 'react';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { UebaFinding, AuditLog, User } from '../types';
import { UsersIcon, AlertTriangleIcon, CheckIcon } from './icons';
import { UebaFindingDetailModal } from './UebaFindingDetailModal';
import { ThreatHunting } from './ThreatHunting';

interface ThreatHuntingDashboardProps {
    findings: UebaFinding[];
    auditLogs: AuditLog[];
    users: User[];
}

const getRiskInfo = (score: number): { color: string; label: string; bg: string; } => {
    if (score > 75) return { color: 'text-red-500', label: 'High', bg: 'bg-red-500' };
    if (score > 40) return { color: 'text-orange-500', label: 'Medium', bg: 'bg-orange-500' };
    return { color: 'text-amber-500', label: 'Low', bg: 'bg-amber-500' };
};


export const ThreatHuntingDashboard: React.FC<ThreatHuntingDashboardProps> = ({ findings, auditLogs, users }) => {
    const { timeZone } = useTimeZone();
    const [viewingFinding, setViewingFinding] = useState<UebaFinding | null>(null);
    const [activeTab, setActiveTab] = useState<'ueba' | 'ai'>('ai');

    const sortedFindings = useMemo(() => {
        return [...findings].sort((a, b) => b.riskScore - a.riskScore);
    }, [findings]);

    const relatedLogs = useMemo(() => {
        if (!viewingFinding) return [];
        return auditLogs.filter(log => viewingFinding.relatedLogIds.includes(log.id));
    }, [viewingFinding, auditLogs]);

    const findingUser = useMemo(() => {
        if (!viewingFinding) return undefined;
        return users.find(u => u.id === viewingFinding.userId);
    }, [viewingFinding, users]);

    return (
        <div className="container mx-auto space-y-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Threat Hunting Center</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Proactively identify threats using AI or behavioral analytics.</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-1 rounded-lg border border-gray-200 dark:border-gray-700 flex">
                    <button
                        onClick={() => setActiveTab('ai')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === 'ai' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                    >
                        ⚡ Active AI Hunt
                    </button>
                    <button
                        onClick={() => setActiveTab('ueba')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === 'ueba' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                    >
                        🛡️ UEBA Findings
                    </button>
                </div>
            </div>

            {activeTab === 'ai' ? (
                <ThreatHunting />
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md animate-in fade-in slide-in-from-bottom-2">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h3 className="text-lg font-semibold flex items-center text-gray-800 dark:text-white">
                            <UsersIcon className="mr-2 text-primary-500" />
                            Anomalous Activity Findings
                        </h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                            <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                <tr>
                                    <th scope="col" className="px-6 py-3">User</th>
                                    <th scope="col" className="px-6 py-3">Summary</th>
                                    <th scope="col" className="px-6 py-3">Risk Score</th>
                                    <th scope="col" className="px-6 py-3">Time</th>
                                    <th scope="col" className="px-6 py-3">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedFindings.map(finding => {
                                    const user = users.find(u => u.id === finding.userId);
                                    const riskInfo = getRiskInfo(finding.riskScore);
                                    return (
                                        <tr key={finding.id} onClick={() => setViewingFinding(finding)} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 cursor-pointer">
                                            <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                                                <div className="flex items-center">
                                                    {user && <img src={user.avatar} alt={user.name} className="h-8 w-8 rounded-full object-cover mr-3" />}
                                                    <span>{user?.name || finding.userId}</span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">{finding.summary}</td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center">
                                                    <span className={`font-bold text-lg ${riskInfo.color}`}>{finding.riskScore}</span>
                                                    <div className="w-16 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 ml-3">
                                                        <div className={`${riskInfo.bg} h-1.5 rounded-full`} style={{ width: `${finding.riskScore}%` }}></div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">{new Date(finding.timestamp).toLocaleString(undefined, { timeZone })}</td>
                                            <td className="px-6 py-4">
                                                <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${finding.status === 'Open' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' : 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300'}`}>
                                                    {finding.status === 'Open' ? <AlertTriangleIcon size={12} className="mr-1.5" /> : <CheckIcon size={12} className="mr-1.5" />}
                                                    {finding.status}
                                                </span>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <UebaFindingDetailModal
                isOpen={!!viewingFinding}
                onClose={() => setViewingFinding(null)}
                finding={viewingFinding}
                relatedLogs={relatedLogs}
                user={findingUser}
            />
        </div>
    );
};
