import React, { useState, useEffect, useMemo } from 'react';
import { Agent } from '../types';
import { authFetch, runAgentComplianceScan } from '../services/apiService';
import { ShieldCheckIcon, CogIcon, CheckIcon, AlertTriangleIcon, XCircleIcon, RefreshCwIcon } from './icons';

interface EvidenceRecord {
    _id?: string;
    assetId?: string;
    hostname?: string;
    framework?: string;
    controlId?: string;
    status?: string;
    lastUpdated?: string;
    evidence?: any[];
}

interface AgentScanStatus {
    agentId: string;
    hostname: string;
    hasCapability: boolean;
    scanning: boolean;
    lastScan?: string;
    passCount: number;
    failCount: number;
    pendingCount: number;
}

interface Props {
    agents: Agent[];
}

export const ComplianceEvidenceStatusDashboard: React.FC<Props> = ({ agents }) => {
    const [records, setRecords] = useState<EvidenceRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [scanStatuses, setScanStatuses] = useState<Record<string, boolean>>({});
    const [toast, setToast] = useState<string | null>(null);

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(null), 3500);
    };

    useEffect(() => {
        setLoading(true);
        authFetch('/api/compliance/evidence')
            .then(r => r.ok ? r.json() : [])
            .then(data => setRecords(Array.isArray(data) ? data : []))
            .catch(() => setRecords([]))
            .finally(() => setLoading(false));
    }, []);

    // Build per-agent summary from evidence records
    const agentSummaries = useMemo((): AgentScanStatus[] => {
        return agents.map(agent => {
            const caps = (agent.capabilities || []) as Array<string | { id?: string }>;
            const hasCapability = caps.some(c =>
                (typeof c === 'string' ? c : c?.id) === 'compliance_enforcement'
            );
            const agentRecords = records.filter(r =>
                r.assetId === agent.assetId || r.hostname === agent.hostname
            );
            const passCount = agentRecords.filter(r => r.status === 'Compliant').length;
            const failCount = agentRecords.filter(r => r.status === 'Non-Compliant').length;
            const pendingCount = agentRecords.filter(r => r.status === 'Pending_Evidence').length;
            const lastScan = agentRecords.reduce((latest, r) => {
                if (!r.lastUpdated) return latest;
                return !latest || r.lastUpdated > latest ? r.lastUpdated : latest;
            }, '');
            return {
                agentId: agent.id,
                hostname: agent.hostname,
                hasCapability,
                scanning: scanStatuses[agent.id] ?? false,
                lastScan: lastScan || undefined,
                passCount,
                failCount,
                pendingCount,
            };
        });
    }, [agents, records, scanStatuses]);

    const handleScan = async (agentId: string, hostname: string) => {
        setScanStatuses(prev => ({ ...prev, [agentId]: true }));
        try {
            await runAgentComplianceScan(agentId);
            showToast(`Compliance scan queued for ${hostname}`);
        } catch {
            showToast(`Failed to start scan for ${hostname}`);
        } finally {
            setScanStatuses(prev => ({ ...prev, [agentId]: false }));
        }
    };

    const total = agentSummaries.length;
    const withCapability = agentSummaries.filter(a => a.hasCapability).length;
    const totalPass = agentSummaries.reduce((s, a) => s + a.passCount, 0);
    const totalFail = agentSummaries.reduce((s, a) => s + a.failCount, 0);

    return (
        <div className="container mx-auto space-y-5">
            <div>
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-1">Compliance Evidence Collector</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                    Automated evidence collection status per agent. Agents with the
                    <span className="font-medium text-primary-600 dark:text-primary-400"> compliance_enforcement</span> capability
                    collect evidence on each heartbeat.
                </p>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { label: 'Total Agents', value: total, color: 'text-gray-800 dark:text-white' },
                    { label: 'Collector Enabled', value: withCapability, color: 'text-primary-600 dark:text-primary-400' },
                    { label: 'Controls Passed', value: totalPass, color: 'text-green-600 dark:text-green-400' },
                    { label: 'Controls Failed', value: totalFail, color: 'text-red-600 dark:text-red-400' },
                ].map(({ label, value, color }) => (
                    <div key={label} className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                        <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">{label}</p>
                        <p className={`text-3xl font-bold ${color}`}>{value}</p>
                    </div>
                ))}
            </div>

            {/* Agent table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center gap-2">
                    <ShieldCheckIcon size={18} className="text-primary-500" />
                    <h3 className="text-sm font-semibold text-gray-800 dark:text-white">Per-Agent Collection Status</h3>
                </div>
                {loading ? (
                    <div className="flex items-center justify-center p-12 text-gray-500">
                        <CogIcon size={20} className="animate-spin mr-2" /> Loading evidence records…
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs uppercase bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                                <tr>
                                    <th className="px-4 py-3">Agent</th>
                                    <th className="px-4 py-3">Collector</th>
                                    <th className="px-4 py-3">Last Collected</th>
                                    <th className="px-4 py-3">Pass</th>
                                    <th className="px-4 py-3">Fail</th>
                                    <th className="px-4 py-3">Pending</th>
                                    <th className="px-4 py-3">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {agentSummaries.length === 0 && (
                                    <tr>
                                        <td colSpan={7} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                                            No agents found
                                        </td>
                                    </tr>
                                )}
                                {agentSummaries.map(agent => (
                                    <tr key={agent.agentId} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white font-mono text-xs">
                                            {agent.hostname}
                                        </td>
                                        <td className="px-4 py-3">
                                            {agent.hasCapability ? (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">
                                                    <CheckIcon size={11} /> Enabled
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                                                    <XCircleIcon size={11} /> Disabled
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                                            {agent.lastScan ? new Date(agent.lastScan).toLocaleString() : '—'}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`font-semibold text-sm ${agent.passCount > 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                                                {agent.passCount}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            {agent.failCount > 0 ? (
                                                <span className="inline-flex items-center gap-1 font-semibold text-sm text-red-600 dark:text-red-400">
                                                    <AlertTriangleIcon size={13} /> {agent.failCount}
                                                </span>
                                            ) : (
                                                <span className="text-gray-400 text-sm">0</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-amber-600 dark:text-amber-400">
                                            {agent.pendingCount || '—'}
                                        </td>
                                        <td className="px-4 py-3">
                                            <button
                                                onClick={() => handleScan(agent.agentId, agent.hostname)}
                                                disabled={agent.scanning}
                                                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-primary-600 dark:text-primary-400 border border-primary-300 dark:border-primary-700 rounded-md hover:bg-primary-50 dark:hover:bg-primary-900/30 disabled:opacity-50"
                                            >
                                                {agent.scanning
                                                    ? <CogIcon size={12} className="animate-spin" />
                                                    : <RefreshCwIcon size={12} />}
                                                Scan
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {toast && (
                <div className="fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white bg-primary-600 z-50">
                    {toast}
                </div>
            )}
        </div>
    );
};
