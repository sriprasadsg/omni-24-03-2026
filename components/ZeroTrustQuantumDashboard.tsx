import React, { useState, useEffect } from 'react';
import { DeviceTrustScore, UserSessionRisk, CryptographicInventory } from '../types';
import { ShieldCheckIcon, ShieldAlertIcon, KeyIcon, AlertTriangleIcon } from './icons';
import * as api from '../services/apiService';

const ZeroTrustQuantumDashboard: React.FC = () => {
    const [deviceScores, setDeviceScores] = useState<DeviceTrustScore[]>([]);
    const [sessionRisks, setSessionRisks] = useState<UserSessionRisk[]>([]);
    const [cryptoInventory, setCryptoInventory] = useState<CryptographicInventory[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const [devices, sessions, crypto] = await Promise.all([
                api.fetchDeviceTrustScores(),
                api.fetchSessionRisks(),
                api.fetchCryptoInventory()
            ]);

            if (devices) setDeviceScores(devices);
            if (sessions) setSessionRisks(sessions);
            if (crypto) setCryptoInventory(crypto);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching security data:', error);
            setLoading(false);
        }
    };


    const avgDeviceScore = deviceScores.reduce((sum, d) => sum + d.score, 0) / (deviceScores.length || 1);
    const quantumVulnerableCount = cryptoInventory.filter(c => c.quantumVulnerable).length;

    if (loading) {
        return <div className="p-6">Loading security metrics...</div>;
    }

    return (
        <div className="p-6 space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center">
                    <ShieldCheckIcon size={28} className="mr-3 text-blue-600" />
                    Zero Trust & Quantum-Ready Security
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    Continuous authentication, device trust, and post-quantum cryptography readiness
                </p>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Avg Device Trust</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white mt-1">
                                {avgDeviceScore.toFixed(0)}%
                            </p>
                        </div>
                        <ShieldCheckIcon size={40} className="text-green-600" />
                    </div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">High-Risk Sessions</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white mt-1">
                                {sessionRisks.filter(s => s.riskScore > 70).length}
                            </p>
                        </div>
                        <ShieldAlertIcon size={40} className="text-red-600" />
                    </div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">Quantum Vulnerable</p>
                            <p className="text-3xl font-bold text-gray-900 dark:text-white mt-1">
                                {quantumVulnerableCount}/{cryptoInventory.length}
                            </p>
                        </div>
                        <KeyIcon size={40} className="text-orange-600" />
                    </div>
                </div>
            </div>

            {/* Zero Trust Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Device Trust Scores */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Device Trust Scores</h2>
                    </div>
                    <div className="divide-y divide-gray-200 dark:divide-gray-700">
                        {deviceScores.map(device => (
                            <div key={device.deviceId} className="p-4">
                                <div className="flex justify-between items-center mb-2">
                                    <span className="font-mono text-sm text-gray-900 dark:text-white">{device.deviceId}</span>
                                    <div className="flex items-center gap-2">
                                        <div className={`text-lg font-bold ${device.score >= 90 ? 'text-green-600' :
                                            device.score >= 70 ? 'text-yellow-600' :
                                                'text-red-600'
                                            }`}>
                                            {device.score}%
                                        </div>
                                    </div>
                                </div>
                                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-3">
                                    <div
                                        className={`h-2 rounded-full ${device.score >= 90 ? 'bg-green-600' :
                                            device.score >= 70 ? 'bg-yellow-600' :
                                                'bg-red-600'
                                            }`}
                                        style={{ width: `${device.score}%` }}
                                    />
                                </div>
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                    <div className={`flex items-center ${device.factors.osPatched ? 'text-green-600' : 'text-red-600'}`}>
                                        {device.factors.osPatched ? '✓' : '✗'} OS Patched
                                    </div>
                                    <div className={`flex items-center ${device.factors.antivirusActive ? 'text-green-600' : 'text-red-600'}`}>
                                        {device.factors.antivirusActive ? '✓' : '✗'} Antivirus
                                    </div>
                                    <div className={`flex items-center ${device.factors.diskEncrypted ? 'text-green-600' : 'text-red-600'}`}>
                                        {device.factors.diskEncrypted ? '✓' : '✗'} Encrypted
                                    </div>
                                    <div className={`flex items-center ${device.factors.compliantLocation ? 'text-green-600' : 'text-red-600'}`}>
                                        {device.factors.compliantLocation ? '✓' : '✗'} Location
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Session Risks */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Active Session Risks</h2>
                    </div>
                    <div className="divide-y divide-gray-200 dark:divide-gray-700">
                        {sessionRisks.map(session => (
                            <div key={session.sessionId} className="p-4">
                                <div className="flex justify-between items-center mb-2">
                                    <div>
                                        <span className="font-mono text-sm text-gray-900 dark:text-white">{session.userId}</span>
                                        <span className="ml-2 text-xs px-2 py-1 rounded-full bg-gray-100 dark:bg-gray-700">
                                            {session.authLevel}
                                        </span>
                                    </div>
                                    <span className={`text-lg font-bold ${session.riskScore < 30 ? 'text-green-600' :
                                        session.riskScore < 60 ? 'text-yellow-600' :
                                            'text-red-600'
                                        }`}>
                                        {session.riskScore}
                                    </span>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                    {session.factors.unusualLocation && (
                                        <span className="text-xs px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded">
                                            Unusual Location
                                        </span>
                                    )}
                                    {session.factors.unusualTime && (
                                        <span className="text-xs px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded">
                                            Unusual Time
                                        </span>
                                    )}
                                    {session.factors.newDevice && (
                                        <span className="text-xs px-2 py-1 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded">
                                            New Device
                                        </span>
                                    )}
                                    {session.factors.suspiciousActivity && (
                                        <span className="text-xs px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded">
                                            Suspicious Activity
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Quantum-Ready Cryptography */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Cryptographic Inventory</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Post-quantum migration readiness</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <AlertTriangleIcon size={20} className="text-orange-600" />
                        <span className="text-sm text-orange-600 font-semibold">
                            {quantumVulnerableCount} algorithms vulnerable to quantum attacks
                        </span>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-50 dark:bg-gray-700 text-xs uppercase text-gray-700 dark:text-gray-400">
                            <tr>
                                <th className="px-4 py-3 text-left">Algorithm</th>
                                <th className="px-4 py-3 text-left">Usage</th>
                                <th className="px-4 py-3 text-center">Quantum Vulnerable</th>
                                <th className="px-4 py-3 text-center">Priority</th>
                                <th className="px-4 py-3 text-left">Replacement</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {cryptoInventory.map(item => (
                                <tr key={item.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="px-4 py-3 font-mono text-gray-900 dark:text-white">{item.algorithm}</td>
                                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{item.usage}</td>
                                    <td className="px-4 py-3 text-center">
                                        {item.quantumVulnerable ? (
                                            <span className="px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded text-xs">
                                                Yes
                                            </span>
                                        ) : (
                                            <span className="px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded text-xs">
                                                No
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-center">
                                        <span className={`px-2 py-1 rounded text-xs ${item.migrationPriority === 'High' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400' :
                                            item.migrationPriority === 'Medium' ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400' :
                                                'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-400'
                                            }`}>
                                            {item.migrationPriority}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-400">
                                        {item.replacementAlgorithm || 'N/A'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default ZeroTrustQuantumDashboard;
