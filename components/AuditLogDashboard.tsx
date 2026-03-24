import React, { useState, useMemo } from 'react';
import { AuditLog } from '../types';
import { ClipboardListIcon, FilterIcon } from './icons';

interface AuditLogDashboardProps {
    logs: AuditLog[];
}

import { AuditLog as AuditLogTimeline } from './AuditLog';
import { useTimeZone } from '../contexts/TimeZoneContext';

export const AuditLogDashboard: React.FC<AuditLogDashboardProps> = ({ logs }) => {
    const { timeZone } = useTimeZone();
    const [activeTab, setActiveTab] = useState<'table' | 'timeline'>('timeline'); // Default to new Time Machine view
    const [userFilter, setUserFilter] = useState<string>('');
    const [actionFilter, setActionFilter] = useState<string>('');
    const [startDate, setStartDate] = useState<string>('');
    const [endDate, setEndDate] = useState<string>('');
    const [searchTerm, setSearchTerm] = useState<string>('');

    const uniqueUsers = useMemo(() => [...new Set(logs.map(log => log.userName))].sort(), [logs]);
    const uniqueActionTypes = useMemo(() => [...new Set(logs.map(log => log.action.split('.')[0]))].sort(), [logs]);

    const filteredLogs = useMemo(() => {
        return logs.filter(log => {
            const logDate = new Date(log.timestamp);
            const start = startDate ? new Date(startDate) : null;
            const end = endDate ? new Date(endDate) : null;
            if (start) start.setHours(0, 0, 0, 0);
            if (end) end.setHours(23, 59, 59, 999);

            const userMatch = !userFilter || log.userName === userFilter;
            const actionMatch = !actionFilter || log.action.startsWith(actionFilter);
            const dateMatch = (!start || logDate >= start) && (!end || logDate <= end);
            const searchMatch = !searchTerm ||
                log.details.toLowerCase().includes(searchTerm.toLowerCase()) ||
                log.resourceId.toLowerCase().includes(searchTerm.toLowerCase()) ||
                log.action.toLowerCase().includes(searchTerm.toLowerCase());

            return userMatch && actionMatch && dateMatch && searchMatch;
        });
    }, [logs, userFilter, actionFilter, startDate, endDate, searchTerm]);

    const clearFilters = () => {
        setUserFilter('');
        setActionFilter('');
        setStartDate('');
        setEndDate('');
        setSearchTerm('');
    };

    return (
        <div className="container mx-auto space-y-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Audit Log</h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Review user actions and system events.</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-1 rounded-lg border border-gray-200 dark:border-gray-700 flex">
                    <button
                        onClick={() => setActiveTab('timeline')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === 'timeline' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                    >
                        🕒 Time Machine
                    </button>
                    <button
                        onClick={() => setActiveTab('table')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === 'table' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
                    >
                        📋 Data Table
                    </button>
                </div>
            </div>

            {activeTab === 'timeline' ? (
                <AuditLogTimeline />
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md animate-in fade-in slide-in-from-bottom-2">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h3 className="text-lg font-semibold flex items-center mb-4">
                            <FilterIcon className="mr-2 text-primary-500" />
                            Filter Logs
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <input
                                type="text"
                                placeholder="Search details, resource..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                            />
                            <select value={userFilter} onChange={(e) => setUserFilter(e.target.value)} className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md sm:text-sm">
                                <option value="">All Users</option>
                                {uniqueUsers.map(user => <option key={user} value={user}>{user}</option>)}
                            </select>
                            <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md sm:text-sm">
                                <option value="">All Action Types</option>
                                {uniqueActionTypes.map(type => <option key={type} value={type}>{type}</option>)}
                            </select>
                            <div className="flex items-center gap-2">
                                <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md sm:text-sm" />
                                <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md sm:text-sm" />
                            </div>
                        </div>
                        <div className="mt-4">
                            <button onClick={clearFilters} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">Clear Filters</button>
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                            <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                                <tr>
                                    <th scope="col" className="px-6 py-3">Timestamp</th>
                                    <th scope="col" className="px-6 py-3">User</th>
                                    <th scope="col" className="px-6 py-3">Action</th>
                                    <th scope="col" className="px-6 py-3">Resource</th>
                                    <th scope="col" className="px-6 py-3">Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredLogs.map(log => (
                                    <tr key={log.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                        <td className="px-6 py-4 whitespace-nowrap">{new Date(log.timestamp).toLocaleString(undefined, { timeZone })}</td>
                                        <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{log.userName}</td>
                                        <td className="px-6 py-4"><span className="px-2 py-1 font-mono text-xs bg-gray-100 dark:bg-gray-900 rounded-md">{log.action}</span></td>
                                        <td className="px-6 py-4"><span className="font-mono text-xs">{log.resourceType}: {log.resourceId}</span></td>
                                        <td className="px-6 py-4">{log.details}</td>
                                    </tr>
                                ))}
                                {filteredLogs.length === 0 && (
                                    <tr>
                                        <td colSpan={5} className="text-center py-8 text-gray-500 dark:text-gray-400">
                                            No audit logs match the current filters.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};
