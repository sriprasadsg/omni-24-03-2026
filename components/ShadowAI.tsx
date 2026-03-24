import React, { useState, useEffect } from 'react';

const API_BASE_URL = 'http://localhost:5000';

interface ShadowAIEvent {
    id: string;
    agent_id: string;
    process: string;
    remote_ip: string;
    remote_host: string;
    timestamp: string;
}

interface UEBAStats {
    shadow_ai_detections: number;
    login_anomalies: number;
}

export const ShadowAI: React.FC = () => {
    const [events, setEvents] = useState<ShadowAIEvent[]>([]);
    const [stats, setStats] = useState<UEBAStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [eventsRes, statsRes] = await Promise.all([
                    fetch(`${API_BASE_URL}/api/ueba/shadow-ai/events`),
                    fetch(`${API_BASE_URL}/api/ueba/stats`)
                ]);

                if (eventsRes.ok && statsRes.ok) {
                    const eventsData = await eventsRes.json();
                    const statsData = await statsRes.json();
                    setEvents(eventsData);
                    setStats(statsData);
                }
            } catch (error) {
                console.error("Failed to fetch Shadow AI data", error);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        // Poll every 10 seconds
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div>Loading Shadow AI Insights...</div>;

    return (
        <div className="space-y-6">
            <div className="bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-900/20 dark:to-orange-900/20 p-6 rounded-xl border border-red-100 dark:border-red-900/50">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-xl font-bold text-red-900 dark:text-red-100">Shadow AI & Risk Monitoring</h2>
                        <p className="text-red-700 dark:text-red-300 mt-1">Real-time detection of unauthorized AI usage and anomalous behaviors.</p>
                    </div>
                    <div className="text-right">
                        <div className="text-3xl font-bold text-red-600 dark:text-red-400">{stats?.shadow_ai_detections || 0}</div>
                        <div className="text-sm font-medium text-red-800 dark:text-red-200">Unauthorized AI Connections</div>
                    </div>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                    <h3 className="font-semibold text-gray-900 dark:text-white">Recent Detections</h3>
                    <span className="text-xs text-gray-500">Live Stream (Polling)</span>
                </div>
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-900/50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Timestamp</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Agent</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Process</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Destination</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Risk</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {events.map((event) => (
                                <tr key={event.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                        {new Date(event.timestamp).toLocaleTimeString()}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                                        {event.agent_id}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                                        <span className="font-mono bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded text-xs">{event.process}</span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-red-600 dark:text-red-400 font-medium">
                                        {event.remote_host} ({event.remote_ip})
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                                            High
                                        </span>
                                    </td>
                                </tr>
                            ))}
                            {events.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                                        No unauthorized AI usage detected yet.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};
