import React, { useEffect, useState } from 'react';
import { fetchAgentUptime, AgentUptimeTimelineBucket } from '../services/apiService';
import { ActivityIcon } from './icons';

interface AgentUptimeTimelineProps {
    agentId: string;
    hours: 1 | 6 | 24 | 48;
}

// FOBS-02: per-agent heartbeat-presence uptime % + bucketed timeline strip.
// Reacts to the same `hours` range selector AgentMetricsTab owns.
export const AgentUptimeTimeline: React.FC<AgentUptimeTimelineProps> = ({ agentId, hours }) => {
    const [timeline, setTimeline] = useState<AgentUptimeTimelineBucket[]>([]);
    const [uptimePercent, setUptimePercent] = useState<number>(0);
    const [expectedBuckets, setExpectedBuckets] = useState<number>(0);
    const [receivedBuckets, setReceivedBuckets] = useState<number>(0);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        if (!agentId) return;
        let mounted = true;
        setIsLoading(true);
        fetchAgentUptime(agentId, hours).then(res => {
            if (!mounted) return;
            setUptimePercent(res.uptime_percent ?? 0);
            setExpectedBuckets(res.expected_buckets ?? 0);
            setReceivedBuckets(res.received_buckets ?? 0);
            setTimeline(res.timeline || []);
        }).catch(() => {
            if (!mounted) return;
            setUptimePercent(0);
            setExpectedBuckets(0);
            setReceivedBuckets(0);
            setTimeline([]);
        }).finally(() => {
            if (mounted) setIsLoading(false);
        });
        return () => { mounted = false; };
    }, [agentId, hours]);

    const uptimeColorClass = uptimePercent >= 99
        ? 'text-green-600 dark:text-green-400'
        : uptimePercent >= 90
            ? 'text-amber-600 dark:text-amber-400'
            : 'text-red-600 dark:text-red-400';

    return (
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center">
                    <ActivityIcon size={20} className="text-teal-500 mr-2" />
                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Uptime</h4>
                </div>
                <div className="text-right">
                    <span className={`text-2xl font-bold ${uptimeColorClass}`}>{uptimePercent.toFixed(1)}%</span>
                </div>
            </div>

            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Heartbeat-presence estimate ({receivedBuckets}/{expectedBuckets} expected 30s heartbeats received) — assumes a fixed 30s cadence, not a measured per-agent interval.
            </p>

            {isLoading ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">Loading uptime…</p>
            ) : timeline.length === 0 ? (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                    <p className="text-sm text-blue-700 dark:text-blue-300">No uptime data available for this range yet.</p>
                </div>
            ) : (
                <div className="flex w-full h-6 rounded overflow-hidden border border-gray-200 dark:border-gray-700" role="img" aria-label={`Uptime timeline: ${uptimePercent.toFixed(1)}% over the last ${hours}h`}>
                    {timeline.map((bucket, idx) => (
                        <div
                            key={idx}
                            className={bucket.up ? 'bg-green-500' : 'bg-red-400'}
                            style={{ flex: '1 1 0%' }}
                            title={`${new Date(bucket.start).toLocaleString()}: ${bucket.up ? 'Up' : 'Down'}`}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};
