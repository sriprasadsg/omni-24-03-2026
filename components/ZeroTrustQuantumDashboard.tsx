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


    const [activeTab, setActiveTab] = useState<'metrics' | 'planner'>('metrics');

    const avgDeviceScore = deviceScores.reduce((sum, d) => sum + d.score, 0) / (deviceScores.length || 1);
    const quantumVulnerableCount = cryptoInventory.filter(c => c.quantumVulnerable).length;

    if (loading) {
        return <div className="p-6">Loading security metrics...</div>;
    }

    const renderMigrationPlanner = () => (
        <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-500">
            <div className="bg-gradient-to-br from-indigo-900 to-slate-900 p-8 rounded-2xl border border-indigo-500/30 text-white relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-10">
                    <KeyIcon size={120} />
                </div>
                <div className="relative z-10">
                    <h2 className="text-3xl font-bold mb-2">PQC Migration Roadmap</h2>
                    <p className="text-indigo-200 max-w-2xl">
                        Based on your cryptographic inventory, we've generated a multi-phase migration plan to transition your classical asymmetric algorithms to NIST-standard Post-Quantum Cryptography (PQC).
                    </p>
                    <div className="mt-8 grid grid-cols-1 md:grid-cols-4 gap-4">
                        {[
                            { label: 'Discovery', status: 'Complete', date: 'Q1 2026', color: 'bg-emerald-500' },
                            { label: 'Pilot (Kyber)', status: 'In Progress', date: 'Q2 2026', color: 'bg-indigo-500' },
                            { label: 'Scale Deployment', status: 'Pending', date: 'Q3 2026', color: 'bg-slate-700' },
                            { label: 'Classical Deprecation', status: 'Pending', date: 'Q4 2026', color: 'bg-slate-700' }
                        ].map((step, idx) => (
                            <div key={idx} className="bg-white/10 backdrop-blur-md p-4 rounded-xl border border-white/10">
                                <div className={`w-2 h-2 rounded-full ${step.color} mb-3 shadow-[0_0_8px_rgba(255,255,255,0.5)]`}></div>
                                <div className="text-sm font-bold">{step.label}</div>
                                <div className="text-[10px] text-white/60 uppercase tracking-tighter mt-1">{step.status} • {step.date}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-100 dark:border-gray-700 overflow-hidden">
                    <div className="p-6 border-b border-gray-100 dark:border-gray-700">
                        <h3 className="font-bold text-gray-900 dark:text-white">Migration Strategy & Mapping</h3>
                    </div>
                    <div className="p-0">
                        <table className="w-full text-left">
                            <thead className="bg-gray-50 dark:bg-gray-900/50 text-[10px] uppercase font-bold text-gray-500">
                                <tr>
                                    <th className="px-6 py-4">Legacy Algorithm</th>
                                    <th className="px-6 py-4">PQC Replacement (NIST)</th>
                                    <th className="px-6 py-4">Complexity</th>
                                    <th className="px-6 py-4">Priority</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                {[
                                    { legacy: 'RSA-2048 / 4096', pqc: 'CRYSTALS-Kyber (ML-KEM)', complexity: 'High', priority: 'Critical' },
                                    { legacy: 'ECDSA (P-256 / P-384)', pqc: 'CRYSTALS-Dilithium (ML-DSA)', complexity: 'Medium', priority: 'High' },
                                    { legacy: 'Diffie-Hellman', pqc: 'Falcon / SPHINCS+', complexity: 'High', priority: 'Medium' }
                                ].map((row, i) => (
                                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors">
                                        <td className="px-6 py-4 font-mono text-sm text-gray-900 dark:text-white">{row.legacy}</td>
                                        <td className="px-6 py-4 font-bold text-indigo-600 dark:text-indigo-400">{row.pqc}</td>
                                        <td className="px-6 py-4 text-sm text-gray-500">{row.complexity}</td>
                                        <td className="px-6 py-4">
                                            <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase ${
                                                row.priority === 'Critical' ? 'bg-red-100 text-red-600' : 'bg-orange-100 text-orange-600'
                                            }`}>{row.priority}</span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-100 dark:border-gray-700">
                    <h3 className="font-bold text-gray-900 dark:text-white mb-4">Migration Insights</h3>
                    <div className="space-y-4">
                        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border-l-4 border-blue-500">
                            <p className="text-xs font-bold text-blue-800 dark:text-blue-300 mb-1 uppercase">Recommendation</p>
                            <p className="text-sm text-blue-700 dark:text-blue-400">
                                Your VPN gateways are currently using RSA-2048. We recommend prioritizing Kyber-768 encapsulation for these tunnels.
                            </p>
                        </div>
                        <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg border-l-4 border-purple-500">
                            <p className="text-xs font-bold text-purple-800 dark:text-purple-300 mb-1 uppercase">Performance Impact</p>
                            <p className="text-sm text-purple-700 dark:text-purple-400">
                                Switching to Dilithium signatures will increase certificate size by ~1.2KB. Ensure MTU sizing is adjusted.
                            </p>
                        </div>
                        <button className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold transition-all shadow-lg shadow-indigo-500/30">
                            Generate NIST Audit Package
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );

    return (
        <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-900 min-h-screen">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-black text-slate-900 dark:text-white flex items-center tracking-tight">
                        <ShieldCheckIcon size={28} className="mr-3 text-indigo-600" />
                        Zero Trust & Quantum-Ready Security
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Continuous authentication, device trust, and post-quantum cryptography readiness
                    </p>
                </div>
                <div className="flex bg-white dark:bg-slate-800 p-1 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700">
                    <button 
                        onClick={() => setActiveTab('metrics')}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeTab === 'metrics' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20' : 'text-slate-500 hover:text-slate-900'}`}
                    >
                        Security Metrics
                    </button>
                    <button 
                        onClick={() => setActiveTab('planner')}
                        className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${activeTab === 'planner' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20' : 'text-slate-500 hover:text-slate-900'}`}
                    >
                        Migration Planner
                    </button>
                </div>
            </div>

            {activeTab === 'planner' ? renderMigrationPlanner() : (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-6 hover:shadow-xl transition-all group">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Avg Device Trust</p>
                                    <p className="text-4xl font-black text-slate-900 dark:text-white mt-1">
                                        {avgDeviceScore.toFixed(0)}%
                                    </p>
                                </div>
                                <div className="w-12 h-12 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center text-emerald-600 group-hover:scale-110 transition-transform">
                                    <ShieldCheckIcon size={28} />
                                </div>
                            </div>
                        </div>
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-6 hover:shadow-xl transition-all group">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">High-Risk Sessions</p>
                                    <p className="text-4xl font-black text-slate-900 dark:text-white mt-1">
                                        {sessionRisks.filter(s => s.riskScore > 70).length}
                                    </p>
                                </div>
                                <div className="w-12 h-12 rounded-xl bg-red-50 dark:bg-red-900/20 flex items-center justify-center text-red-600 group-hover:scale-110 transition-transform">
                                    <ShieldAlertIcon size={28} />
                                </div>
                            </div>
                        </div>
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 p-6 hover:shadow-xl transition-all group">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Quantum Vulnerable</p>
                                    <p className="text-4xl font-black text-slate-900 dark:text-white mt-1">
                                        {quantumVulnerableCount}
                                    </p>
                                </div>
                                <div className="w-12 h-12 rounded-xl bg-orange-50 dark:bg-orange-900/20 flex items-center justify-center text-orange-600 group-hover:scale-110 transition-transform">
                                    <KeyIcon size={28} />
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Zero Trust Section */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Device Trust Scores */}
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center">
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">Device Trust Scores</h2>
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Live Monitoring</span>
                            </div>
                            <div className="divide-y divide-slate-100 dark:divide-slate-700">
                                {deviceScores.map(device => (
                                    <div key={device.deviceId} className="p-6 hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors">
                                        <div className="flex justify-between items-center mb-3">
                                            <div>
                                                <span className="font-bold text-sm text-slate-900 dark:text-white">{device.deviceId}</span>
                                                <p className="text-[10px] text-slate-500 uppercase font-bold tracking-tighter">Endpoint Identity Verified</p>
                                            </div>
                                            <div className={`text-2xl font-black ${device.score >= 90 ? 'text-emerald-500' :
                                                device.score >= 70 ? 'text-amber-500' :
                                                    'text-red-500'
                                                }`}>
                                                {device.score}%
                                            </div>
                                        </div>
                                        <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5 mb-4">
                                            <div
                                                className={`h-1.5 rounded-full transition-all duration-1000 ${device.score >= 90 ? 'bg-emerald-500' :
                                                    device.score >= 70 ? 'bg-amber-500' :
                                                        'bg-red-500'
                                                    }`}
                                                style={{ width: `${device.score}%` }}
                                            />
                                        </div>
                                        <div className="grid grid-cols-2 gap-3 text-[11px] font-bold">
                                            <div className={`flex items-center ${device.factors.osPatched ? 'text-emerald-600' : 'text-red-500'}`}>
                                                <span className="w-4 h-4 rounded-full flex items-center justify-center bg-current/10 mr-2">{device.factors.osPatched ? '✓' : '✗'}</span>
                                                OS PATCHED
                                            </div>
                                            <div className={`flex items-center ${device.factors.antivirusActive ? 'text-emerald-600' : 'text-red-500'}`}>
                                                <span className="w-4 h-4 rounded-full flex items-center justify-center bg-current/10 mr-2">{device.factors.antivirusActive ? '✓' : '✗'}</span>
                                                ANTIVIRUS ACTIVE
                                            </div>
                                            <div className={`flex items-center ${device.factors.diskEncrypted ? 'text-emerald-600' : 'text-red-500'}`}>
                                                <span className="w-4 h-4 rounded-full flex items-center justify-center bg-current/10 mr-2">{device.factors.diskEncrypted ? '✓' : '✗'}</span>
                                                DISK ENCRYPTED
                                            </div>
                                            <div className={`flex items-center ${device.factors.compliantLocation ? 'text-emerald-600' : 'text-red-500'}`}>
                                                <span className="w-4 h-4 rounded-full flex items-center justify-center bg-current/10 mr-2">{device.factors.compliantLocation ? '✓' : '✗'}</span>
                                                COMPLIANT GEO
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Session Risks */}
                        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center">
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">Active Session Risks</h2>
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Real-time UEBA</span>
                            </div>
                            <div className="divide-y divide-slate-100 dark:divide-slate-700">
                                {sessionRisks.map(session => (
                                    <div key={session.sessionId} className="p-6 hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors">
                                        <div className="flex justify-between items-center mb-4">
                                            <div>
                                                <span className="font-bold text-sm text-slate-900 dark:text-white">{session.userId}</span>
                                                <div className="flex items-center mt-1">
                                                    <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-bold uppercase">
                                                        {session.authLevel}
                                                    </span>
                                                    <span className="text-[10px] text-slate-400 ml-2 font-mono">{session.sessionId.substring(0, 8)}...</span>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-[10px] font-bold text-slate-400 uppercase mb-1">Risk Score</p>
                                                <span className={`text-2xl font-black ${session.riskScore < 30 ? 'text-emerald-500' :
                                                    session.riskScore < 60 ? 'text-amber-500' :
                                                        'text-red-500'
                                                    }`}>
                                                    {session.riskScore}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            {session.factors.unusualLocation && (
                                                <span className="text-[10px] font-bold px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 rounded-lg flex items-center border border-red-100 dark:border-red-900/30">
                                                    <AlertTriangleIcon size={10} className="mr-1" /> UNUSUAL LOCATION
                                                </span>
                                            )}
                                            {session.factors.unusualTime && (
                                                <span className="text-[10px] font-bold px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 rounded-lg flex items-center border border-red-100 dark:border-red-900/30">
                                                    <AlertTriangleIcon size={10} className="mr-1" /> ANOMALOUS TIME
                                                </span>
                                            )}
                                            {session.factors.newDevice && (
                                                <span className="text-[10px] font-bold px-2 py-1 bg-amber-50 dark:bg-amber-900/20 text-amber-600 rounded-lg flex items-center border border-amber-100 dark:border-amber-900/30">
                                                    <AlertTriangleIcon size={10} className="mr-1" /> NEW DEVICE
                                                </span>
                                            )}
                                            {session.factors.suspiciousActivity && (
                                                <span className="text-[10px] font-bold px-2 py-1 bg-red-50 dark:bg-red-900/20 text-red-600 rounded-lg flex items-center border border-red-100 dark:border-red-900/30">
                                                    <AlertTriangleIcon size={10} className="mr-1" /> SUSPICIOUS ACTIVITY
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Cryptographic Inventory */}
                    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
                        <div className="p-6 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">Cryptographic Inventory</h2>
                                <p className="text-xs text-slate-500 font-medium">Post-quantum migration readiness audit</p>
                            </div>
                            <div className="flex items-center gap-3 bg-orange-50 dark:bg-orange-900/20 px-4 py-2 rounded-xl border border-orange-100 dark:border-orange-900/30">
                                <AlertTriangleIcon size={18} className="text-orange-600" />
                                <span className="text-xs text-orange-700 dark:text-orange-400 font-bold">
                                    {quantumVulnerableCount} VULNERABLE ALGORITHMS
                                </span>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left">
                                <thead className="bg-slate-50 dark:bg-slate-900/50 text-[10px] uppercase font-black text-slate-400 tracking-widest">
                                    <tr>
                                        <th className="px-6 py-4">Algorithm</th>
                                        <th className="px-6 py-4">Usage Context</th>
                                        <th className="px-6 py-4">Vulnerability</th>
                                        <th className="px-6 py-4">Priority</th>
                                        <th className="px-6 py-4">NIST Replacement</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                                    {cryptoInventory.map(item => (
                                        <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors">
                                            <td className="px-6 py-4 font-black text-slate-900 dark:text-white font-mono">{item.algorithm}</td>
                                            <td className="px-6 py-4 text-slate-500 font-medium">{item.usage}</td>
                                            <td className="px-6 py-4">
                                                {item.quantumVulnerable ? (
                                                    <span className="px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg text-[10px] font-bold border border-red-200 dark:border-red-900/50">
                                                        VULNERABLE
                                                    </span>
                                                ) : (
                                                    <span className="px-2 py-1 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 rounded-lg text-[10px] font-bold border border-emerald-200 dark:border-emerald-900/50">
                                                        QUANTUM-SAFE
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className={`px-2 py-1 rounded-lg text-[10px] font-bold ${item.migrationPriority === 'High' ? 'bg-red-600 text-white shadow-lg shadow-red-500/20' :
                                                    item.migrationPriority === 'Medium' ? 'bg-amber-500 text-white shadow-lg shadow-amber-500/20' :
                                                        'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300'
                                                    }`}>
                                                    {item.migrationPriority.toUpperCase()}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 font-bold text-indigo-600 dark:text-indigo-400 text-sm">
                                                {item.replacementAlgorithm || 'N/A'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default ZeroTrustQuantumDashboard;
