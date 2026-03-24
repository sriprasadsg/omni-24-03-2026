import React, { useState, useEffect } from 'react';
import { CloudShieldIcon, ActivityIcon, ShieldIcon, DatabaseIcon, NetworkIcon } from './icons';

const UnifiedFutureOpsDashboard: React.FC = () => {
    const [aiopsData, setAiopsData] = useState<any>(null);
    const [streaming, setStreaming] = useState<any>(null);
    const [multicloud, setMulticloud] = useState<any>(null);
    const [privacy, setPrivacy] = useState<any>(null);
    const [blockchain, setBlockchain] = useState<any>(null);
    const [xdr, setXdr] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchAllData();
        const interval = setInterval(fetchAllData, 5000); // Refresh every 5s
        return () => clearInterval(interval);
    }, []);

    const fetchAllData = async () => {
        try {
            const [aiopsRes, streamingRes, multicloudRes, privacyRes, blockchainRes, xdrRes] = await Promise.all([
                fetch('/api/aiops/capacity-predictions'),
                fetch('/api/streaming/live-events'),
                fetch('/api/multicloud/cost-optimization'),
                fetch('/api/privacy/consent-tracking'),
                fetch('/api/blockchain/audit-chain'),
                fetch('/api/xdr/automated-hunts')
            ]);

            setAiopsData(await aiopsRes.json());
            setStreaming(await streamingRes.json());
            setMulticloud(await multicloudRes.json());
            setPrivacy(await privacyRes.json());
            setBlockchain(await blockchainRes.json());
            setXdr(await xdrRes.json());
            setLoading(false);
        } catch (error) {
            console.error('Error fetching 2030 features data:', error);
            setLoading(false);
        }
    };

    if (loading) {
        return <div className="p-6">Loading advanced features...</div>;
    }

    const totalSavings = multicloud?.recommendations?.reduce((sum: number, r: any) => sum + r.savings, 0) || 0;

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                    2030 Advanced Operations Dashboard
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    AIOps, Real-Time Analytics, Multi-Cloud, Privacy, Blockchain & XDR
                </p>
            </div>

            {/* Real-Time Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg shadow-md p-4 text-white">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm opacity-90">Live Events/Sec</p>
                            <p className="text-3xl font-bold mt-1">{streaming?.eventsPerSecond || 0}</p>
                        </div>
                        <ActivityIcon size={36} className="opacity-80" />
                    </div>
                    <p className="text-xs mt-2 opacity-75">Avg Latency: {streaming?.avgLatencyMs}ms</p>
                </div>

                <div className="bg-gradient-to-br from-green-500 to-green-600 rounded-lg shadow-md p-4 text-white">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm opacity-90">Cost Savings</p>
                            <p className="text-3xl font-bold mt-1">${totalSavings}</p>
                        </div>
                        <CloudShieldIcon size={36} className="opacity-80" />
                    </div>
                    <p className="text-xs mt-2 opacity-75">Multi-Cloud Optimization</p>
                </div>

                <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-lg shadow-md p-4 text-white">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm opacity-90">Blockchain Blocks</p>
                            <p className="text-3xl font-bold mt-1">{Array.isArray(blockchain) && blockchain.length > 0 ? blockchain[0]?.blockNumber : 0}</p>
                        </div>
                        <NetworkIcon size={36} className="opacity-80" />
                    </div>
                    <p className="text-xs mt-2 opacity-75">Immutable Audit Trail</p>
                </div>

                <div className="bg-gradient-to-br from-red-500 to-red-600 rounded-lg shadow-md p-4 text-white">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm opacity-90">Active Threat Hunts</p>
                            <p className="text-3xl font-bold mt-1">{xdr?.activeHunts || 0}</p>
                        </div>
                        <ShieldIcon size={36} className="opacity-80" />
                    </div>
                    <p className="text-xs mt-2 opacity-75">Automated XDR</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* AIOps Predictions */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                        AI-Driven Capacity Predictions
                    </h2>
                    <div className="space-y-4">
                        {aiopsData?.predictions?.map((pred: any, idx: number) => (
                            <div key={idx} className="space-y-2">
                                <div className="flex justify-between text-sm">
                                    <span className="font-medium text-gray-700 dark:text-gray-300">{pred.resource}</span>
                                    <span className="text-gray-600 dark:text-gray-400">
                                        {pred.currentUsage}% → {pred.predicted7Days}%
                                    </span>
                                </div>
                                <div className="relative w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                                    <div
                                        className={`absolute top-0 left-0 h-3 rounded-full ${pred.predicted7Days >= pred.threshold ? 'bg-red-500' : 'bg-green-500'
                                            }`}
                                        style={{ width: `${pred.predicted7Days}%` }}
                                    />
                                    <div
                                        className="absolute top-0 h-3 w-0.5 bg-yellow-500"
                                        style={{ left: `${pred.threshold}%` }}
                                        title={`Threshold: ${pred.threshold}%`}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Multi-Cloud Optimization */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                        Cost Optimization Recommendations
                    </h2>
                    <div className="space-y-3">
                        {multicloud?.recommendations?.map((rec: any, idx: number) => (
                            <div key={idx} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                                <div className="flex justify-between items-start mb-2">
                                    <div>
                                        <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded">
                                            {rec.type}
                                        </span>
                                        <p className="text-sm font-mono text-gray-700 dark:text-gray-300 mt-1">
                                            {rec.resource}
                                        </p>
                                    </div>
                                    <span className="text-lg font-bold text-green-600">${rec.savings}</span>
                                </div>
                                <div className="flex justify-between text-xs text-gray-500">
                                    <span>Current: ${rec.currentCost}/mo</span>
                                    <span>Confidence: {(rec.confidence * 100).toFixed(0)}%</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Data Privacy */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                        Privacy & Consent Management
                    </h2>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="text-center">
                                <p className="text-3xl font-bold text-green-600">{privacy?.withConsent}</p>
                                <p className="text-xs text-gray-500 mt-1">With Consent</p>
                            </div>
                            <div className="text-center">
                                <p className="text-3xl font-bold text-gray-900 dark:text-white">{privacy?.complianceRate}%</p>
                                <p className="text-xs text-gray-500 mt-1">Compliance Rate</p>
                            </div>
                        </div>
                        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                            <div className="flex justify-between text-sm mb-1">
                                <span className="text-gray-600 dark:text-gray-400">Pending: {privacy?.pending}</span>
                                <span className="text-gray-600 dark:text-gray-400">Revoked: {privacy?.revoked}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Blockchain Audit */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                        Blockchain Audit Trail
                    </h2>
                    <div className="space-y-3">
                        {Array.isArray(blockchain) && blockchain.slice(0, 5).map((block: any, idx: number) => (
                            <div key={idx} className="border-l-4 border-purple-500 pl-3">
                                <div className="flex justify-between items-start">
                                    <div>
                                        <p className="font-mono text-sm text-gray-900 dark:text-white">
                                            Block #{block.blockNumber}
                                        </p>
                                        <p className="font-mono text-xs text-gray-500 mt-1">
                                            {block.hash?.substring(0, 20)}...
                                        </p>
                                    </div>
                                    {block.verified && (
                                        <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded">
                                            ✓ Verified
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-gray-500 mt-1">{block.events} events</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* XDR Threat Intelligence */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                    Extended Detection & Response (XDR)
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                        <p className="text-sm text-gray-600 dark:text-gray-400">Findings (24h)</p>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                            {xdr?.findingsLast24h}
                        </p>
                        <p className="text-xs text-red-600 mt-2">
                            {xdr?.confirmedThreats} confirmed threats
                        </p>
                    </div>
                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                        <p className="text-sm text-gray-600 dark:text-gray-400">Active Hunts</p>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                            {xdr?.activeHunts}
                        </p>
                        <p className="text-xs text-gray-500 mt-2">Automated detection running</p>
                    </div>
                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                        <p className="text-sm text-gray-600 dark:text-gray-400">False Positives</p>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                            {xdr?.falsePositives}
                        </p>
                        <p className="text-xs text-green-600 mt-2">Low false positive rate</p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default UnifiedFutureOpsDashboard;
