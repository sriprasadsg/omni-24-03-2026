import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, AlertTriangleIcon, ShieldLockIcon, KeyIcon } from './icons';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface SecurityEvent {
    id: string;
    type: string;
    severity: string;
    details: any;
    timestamp: string;
}

export const SecurityAuditDashboard: React.FC = () => {
    const { timeZone } = useTimeZone();
    const [events, setEvents] = useState<SecurityEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
    const [stats, setStats] = useState({
        total: 0,
        critical: 0,
        warning: 0,
        info: 0
    });

    useEffect(() => {
        fetchAuditLog();
        const interval = setInterval(fetchAuditLog, 30000); // Refresh every 30s
        return () => clearInterval(interval);
    }, [selectedSeverity]);

    const fetchAuditLog = async () => {
        try {
            const url = `/api/security/audit-log?limit=100${selectedSeverity !== 'all' ? `&severity=${selectedSeverity}` : ''}`;
            const response = await fetch(url);
            const data = await response.json();

            setEvents(data.events || []);

            // Calculate stats
            const allEvents = data.events || [];
            setStats({
                total: allEvents.length,
                critical: allEvents.filter((e: SecurityEvent) => e.severity === 'critical').length,
                warning: allEvents.filter((e: SecurityEvent) => e.severity === 'warning').length,
                info: allEvents.filter((e: SecurityEvent) => e.severity === 'info').length
            });
        } catch (error) {
            console.error('Error fetching audit log:', error);
        } finally {
            setLoading(false);
        }
    };

    const getSeverityColor = (severity: string) => {
        switch (severity) {
            case 'critical':
                return 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300 border-red-500';
            case 'warning':
                return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300 border-yellow-500';
            case 'info':
                return 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300 border-blue-500';
            default:
                return 'bg-gray-100 text-gray-800 dark:bg-gray-900/50 dark:text-gray-300 border-gray-500';
        }
    };

    const getEventIcon = (type: string) => {
        if (type.includes('integrity') || type.includes('signature')) {
            return <ShieldCheckIcon size={18} />;
        } else if (type.includes('tampering') || type.includes('invalid')) {
            return <AlertTriangleIcon size={18} />;
        } else if (type.includes('encryption') || type.includes('key')) {
            return <KeyIcon size={18} />;
        }
        return <ShieldLockIcon size={18} />;
    };

    const getEventTypeLabel = (type: string) => {
        const labels: Record<string, string> = {
            patch_integrity_verified: 'Patch Integrity Verified',
            patch_integrity_failed: 'Patch Integrity Failed',
            signature_verified: 'Signature Verified',
            signature_invalid: 'Invalid Signature',
            agent_tampering_detected: 'Agent Tampering Detected',
            agent_self_check_failed: 'Agent Self-Check Failed',
            encryption_key_generated: 'Encryption Key Generated',
            signing_key_generated: 'Signing Key Generated'
        };
        return labels[type] || type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    };

    if (loading) {
        return <div className="p-6">Loading security audit log...</div>;
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white flex items-center">
                        <ShieldCheckIcon size={28} className="mr-3 text-primary-500" />
                        Security Audit Log
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Track integrity verification, signature validation, and security events
                    </p>
                </div>

                {/* Severity Filter */}
                <select
                    value={selectedSeverity}
                    onChange={(e) => setSelectedSeverity(e.target.value)}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-800 dark:text-white"
                >
                    <option value="all">All Severities</option>
                    <option value="critical">Critical Only</option>
                    <option value="warning">Warnings Only</option>
                    <option value="info">Info Only</option>
                </select>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Total Events</p>
                    <p className="text-3xl font-bold text-gray-800 dark:text-white">{stats.total}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 border-l-4 border-red-500">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Critical</p>
                    <p className="text-3xl font-bold text-red-600 dark:text-red-400">{stats.critical}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 border-l-4 border-yellow-500">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Warnings</p>
                    <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">{stats.warning}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 border-l-4 border-blue-500">
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Info</p>
                    <p className="text-3xl font-bold text-blue-600 dark:text-blue-400">{stats.info}</p>
                </div>
            </div>

            {/* Critical Events Alert */}
            {stats.critical > 0 && (
                <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-500 p-4 rounded-lg">
                    <div className="flex items-start">
                        <AlertTriangleIcon size={24} className="text-red-600 dark:text-red-400 mr-3 flex-shrink-0 mt-0.5" />
                        <div>
                            <h4 className="text-lg font-semibold text-red-900 dark:text-red-200">
                                {stats.critical} Critical Security Event{stats.critical !== 1 ? 's' : ''}
                            </h4>
                            <p className="text-sm text-red-800 dark:text-red-300 mt-1">
                                Immediate attention required. Review events marked as CRITICAL below.
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Events List */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-gray-50 dark:bg-gray-700">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                                    Event Type
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                                    Severity
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                                    Details
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                                    Timestamp
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {events.length === 0 ? (
                                <tr>
                                    <td colSpan={4} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                                        No security events recorded
                                    </td>
                                </tr>
                            ) : (
                                events.map(event => (
                                    <tr key={event.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                {getEventIcon(event.type)}
                                                <span className="text-sm font-medium text-gray-900 dark:text-white">
                                                    {getEventTypeLabel(event.type)}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase ${getSeverityColor(event.severity)}`}>
                                                {event.severity}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="text-sm text-gray-600 dark:text-gray-300 max-w-md">
                                                {event.details.patch_id && (
                                                    <p>Patch: <span className="font-mono text-xs">{event.details.patch_id}</span></p>
                                                )}
                                                {event.details.agent_id && (
                                                    <p>Agent: <span className="font-mono text-xs">{event.details.agent_id}</span></p>
                                                )}
                                                {event.details.valid !== undefined && (
                                                    <p>Valid: <span className={event.details.valid ? 'text-green-600' : 'text-red-600'}>
                                                        {event.details.valid ? 'Yes' : 'No'}
                                                    </span></p>
                                                )}
                                                {event.details.verified_checksums && (
                                                    <p>Verified: {event.details.verified_checksums.join(', ')}</p>
                                                )}
                                                {event.details.failed_checksums && event.details.failed_checksums.length > 0 && (
                                                    <p className="text-red-600">Failed: {event.details.failed_checksums.join(', ')}</p>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                            {new Date(event.timestamp).toLocaleString(undefined, { timeZone })}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
