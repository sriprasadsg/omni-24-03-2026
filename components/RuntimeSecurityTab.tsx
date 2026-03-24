import React from 'react';
import { ActivityIcon, NetworkIcon, AlertTriangleIcon, CheckIcon } from './icons';

interface Process {
    pid: number;
    name: string;
    user: string;
    cpu_percent: number;
    memory_percent: number;
    status?: string;
}

interface NetworkConnection {
    local_address: string;
    local_port: number;
    remote_address: string;
    remote_port: number;
    status: string;
    pid?: number;
}

interface SuspiciousActivity {
    type: string;
    description: string;
    severity: 'low' | 'medium' | 'high' | 'critical';
    timestamp: string;
}

interface RuntimeSecurityData {
    processes: Process[];
    connections: NetworkConnection[];
    suspicious_activities: SuspiciousActivity[];
    process_count: number;
    connection_count: number;
}

interface RuntimeSecurityTabProps {
    data?: RuntimeSecurityData;
}

export const RuntimeSecurityTab: React.FC<RuntimeSecurityTabProps> = ({ data }) => {
    if (!data || !data.processes || !data.connections) {
        return (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <ActivityIcon size={48} className="mx-auto mb-3 opacity-50" />
                <p>No runtime security data available</p>
                <p className="text-sm mt-1">Data will appear once the agent reports it</p>
            </div>
        );
    }

    const getSeverityColor = (severity: string) => {
        switch (severity) {
            case 'critical': return 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30';
            case 'high': return 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30';
            case 'medium': return 'text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30';
            case 'low': return 'text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30';
            default: return 'text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700';
        }
    };

    const topProcesses = [...data.processes]
        .sort((a, b) => b.cpu_percent - a.cpu_percent)
        .slice(0, 10);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Active Processes</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                                {data.process_count || data.processes.length}
                            </p>
                        </div>
                        <ActivityIcon size={32} className="text-primary-500 opacity-50" />
                    </div>
                </div>

                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Network Connections</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                                {data.connection_count || data.connections.length}
                            </p>
                        </div>
                        <NetworkIcon size={32} className="text-blue-500 opacity-50" />
                    </div>
                </div>

                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Suspicious Activities</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                                {data.suspicious_activities?.length || 0}
                            </p>
                        </div>
                        {(data.suspicious_activities?.length || 0) > 0 ? (
                            <AlertTriangleIcon size={32} className="text-red-500" />
                        ) : (
                            <CheckIcon size={32} className="text-green-500 opacity-50" />
                        )}
                    </div>
                </div>
            </div>

            {data.suspicious_activities && data.suspicious_activities.length > 0 && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                    <div className="flex items-start">
                        <AlertTriangleIcon size={20} className="text-red-600 dark:text-red-400 mt-0.5 mr-3 flex-shrink-0" />
                        <div className="flex-grow">
                            <h4 className="font-semibold text-red-900 dark:text-red-200 mb-2">Suspicious Activities Detected</h4>
                            <div className="space-y-2">
                                {data.suspicious_activities.map((activity, idx) => (
                                    <div key={idx} className="flex items-start justify-between text-sm">
                                        <div className="flex-grow">
                                            <span className="font-medium text-red-800 dark:text-red-300">{activity.type}:</span>
                                            <span className="text-red-700 dark:text-red-400 ml-2">{activity.description}</span>
                                        </div>
                                        <span className={`px-2 py-0.5 rounded text-xs font-medium ml-3 flex-shrink-0 ${getSeverityColor(activity.severity)}`}>
                                            {activity.severity.toUpperCase()}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center">
                    <ActivityIcon size={16} className="mr-2" />
                    Top Processes by CPU Usage
                </h4>
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                            <thead className="bg-gray-50 dark:bg-gray-700/50">
                                <tr>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">PID</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Process Name</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">User</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">CPU %</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Memory %</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                {topProcesses.map((process, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                                        <td className="px-4 py-2 text-sm font-mono text-gray-900 dark:text-gray-200">{process.pid}</td>
                                        <td className="px-4 py-2 text-sm font-medium text-gray-800 dark:text-gray-300">{process.name}</td>
                                        <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">{process.user}</td>
                                        <td className="px-4 py-2 text-sm">
                                            <div className="flex items-center">
                                                <div className="w-16 bg-gray-200 dark:bg-gray-600 rounded-full h-2 mr-2">
                                                    <div
                                                        className="bg-primary-500 h-2 rounded-full transition-all"
                                                        style={{ width: `${Math.min(process.cpu_percent, 100)}%` }}
                                                    />
                                                </div>
                                                <span className="text-gray-700 dark:text-gray-300 font-medium">
                                                    {process.cpu_percent.toFixed(1)}%
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">
                                            {process.memory_percent.toFixed(1)}%
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center">
                    <NetworkIcon size={16} className="mr-2" />
                    Active Network Connections ({data.connections.length} total)
                </h4>
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                    <div className="overflow-x-auto max-h-64 overflow-y-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                            <thead className="bg-gray-50 dark:bg-gray-700/50 sticky top-0">
                                <tr>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Local</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Remote</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">PID</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                {data.connections.slice(0, 20).map((conn, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                                        <td className="px-4 py-2 text-sm font-mono text-gray-800 dark:text-gray-300">
                                            {conn.local_address}:{conn.local_port}
                                        </td>
                                        <td className="px-4 py-2 text-sm font-mono text-gray-800 dark:text-gray-300">
                                            {conn.remote_address}:{conn.remote_port}
                                        </td>
                                        <td className="px-4 py-2 text-sm">
                                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${conn.status === 'ESTABLISHED' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' :
                                                    conn.status === 'LISTEN' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400' :
                                                        'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-400'
                                                }`}>
                                                {conn.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-2 text-sm font-mono text-gray-600 dark:text-gray-400">
                                            {conn.pid || '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {data.connections.length > 20 && (
                        <div className="bg-gray-50 dark:bg-gray-700/30 px-4 py-2 text-sm text-gray-600 dark:text-gray-400 text-center border-t border-gray-200 dark:border-gray-700">
                            Showing 20 of {data.connections.length} connections
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
