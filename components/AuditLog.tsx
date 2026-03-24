import React, { useState, useEffect } from 'react';
import { fetchAuditLogs, rollbackChange } from '../services/apiService';
import { ClockIcon, ShieldIcon, SettingsIcon, AlertTriangleIcon, FileTextIcon, HistoryIcon, CheckIcon, XCircleIcon } from './icons';

interface AuditLogEntry {
    id: string;
    timestamp: string;
    actor: string;
    action: string;
    status: string;
    details: any;
}

import { useTimeZone } from '../contexts/TimeZoneContext';
import { useUser } from '../contexts/UserContext';

export function AuditLog() {
    const { timeZone } = useTimeZone();
    const [logs, setLogs] = useState<AuditLogEntry[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [rollbackStatus, setRollbackStatus] = useState<{ id: string; message: string; type: 'success' | 'error' } | null>(null);
    const fetchLogs = async () => {
        setIsLoading(true);
        try {
            const data = await fetchAuditLogs();
            setLogs(data);
        } catch (error) {
            console.error("Failed to fetch audit logs", error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
    }, []);

    const handleRollback = async (logId: string) => {
        setRollbackStatus(null);
        try {
            const data = await rollbackChange(logId);
            setRollbackStatus({ id: logId, message: data.message || "Rollback successful", type: 'success' });
            // Refresh logs
            setTimeout(fetchLogs, 1000);
        } catch (error: any) {
            setRollbackStatus({ id: logId, message: error.message || "Rollback failed", type: 'error' });
        }
    };


    const getIcon = (action: string) => {
        if (action.includes('patch')) return <ShieldIcon className="h-5 w-5 text-blue-500" />;
        if (action.includes('config')) return <SettingsIcon className="h-5 w-5 text-orange-500" />;
        if (action.includes('error') || action.includes('fail')) return <AlertTriangleIcon className="h-5 w-5 text-red-500" />;
        return <FileTextIcon className="h-5 w-5 text-gray-400" />;
    };

    const isReversible = (action: string) => {
        return action === 'system_patch' || action === 'config_change';
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            <div className="flex flex-col gap-2">
                <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white">Time Machine Audit</h1>
                <p className="text-gray-500 dark:text-gray-400">
                    Visualize system events and rollback unintended changes.
                </p>
            </div>

            <div className="relative border-l-2 border-gray-200 dark:border-gray-700 ml-4 space-y-8 pb-10">
                {isLoading ? (
                    <div className="pl-6 text-gray-500">Loading timeline...</div>
                ) : logs.map((log) => (
                    <div key={log.id} className="relative pl-6 group">
                        <span className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 border-white dark:border-gray-900 ${log.status === 'SUCCESS' ? 'bg-green-500' : 'bg-red-500'}`}></span>

                        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 p-4 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm transition-all hover:shadow-md">

                            <div className="flex gap-4">
                                <div className="mt-1 bg-gray-50 dark:bg-gray-700 p-2 rounded-full h-fit">
                                    {getIcon(log.action)}
                                </div>
                                <div>
                                    <div className="flex items-center gap-2">
                                        <h3 className="font-semibold text-gray-900 dark:text-white text-lg capitalize">
                                            {log.action.replace(/_/g, ' ')}
                                        </h3>
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500">{log.actor}</span>
                                    </div>
                                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-2">
                                        <ClockIcon className="h-3 w-3" />
                                        {new Date(log.timestamp).toLocaleString(undefined, { timeZone })}
                                    </p>

                                    <div className="mt-2 text-sm text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-900/50 p-2 rounded border border-gray-100 dark:border-gray-700 font-mono">
                                        {JSON.stringify(log.details).substring(0, 100)}
                                        {JSON.stringify(log.details).length > 100 && '...'}
                                    </div>

                                    {rollbackStatus && rollbackStatus.id === log.id && (
                                        <div className={`mt-2 text-sm flex items-center gap-2 ${rollbackStatus.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                                            {rollbackStatus.type === 'success' ? <CheckIcon className="h-4 w-4" /> : <XCircleIcon className="h-4 w-4" />}
                                            {rollbackStatus.message}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {isReversible(log.action) && log.status === 'SUCCESS' && (
                                <button
                                    onClick={() => handleRollback(log.id)}
                                    className="whitespace-nowrap flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30 rounded-md transition-colors"
                                >
                                    <HistoryIcon className="h-4 w-4" />
                                    Rollback
                                </button>
                            )}
                        </div>
                    </div>
                ))}

                {!isLoading && logs.length === 0 && (
                    <div className="pl-6 text-gray-500">No audit logs found.</div>
                )}
            </div>
        </div>
    );
}
