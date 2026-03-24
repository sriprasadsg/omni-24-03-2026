import React, { useState, useEffect } from 'react';
import {
    AlertTriangle, Shield, CheckCircle, TrendingUp, Plus, Search, Filter,
    MoreHorizontal, Edit2, Trash2, Zap, Cloud, Users, FileText
} from 'lucide-react';
import * as api from '../services/apiService';
import { RiskFormModal } from './RiskFormModal';

// Types (should eventually be moved to types.ts)
interface Risk {
    id: string;
    title: string;
    description: string;
    category: 'Enterprise' | 'AI' | 'Compliance' | 'Third-Party' | 'Cyber';
    status: 'Open' | 'Mitigated' | 'Accepted' | 'Transferred' | 'Avoided';
    likelihood: number;
    impact: number;
    risk_score: number;
    owner: string;
    mitigation_plan?: string;
    created_at: string;
    updated_at: string;
}

export default function RiskRegister() {
    const [risks, setRisks] = useState<Risk[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [filterCategory, setFilterCategory] = useState<string>('All');
    const [showAddModal, setShowAddModal] = useState(false);
    const [selectedRisk, setSelectedRisk] = useState<Risk | null>(null);

    useEffect(() => {
        fetchRisks();
    }, []);

    const fetchRisks = async () => {
        try {
            const data = await api.fetchRisks();
            setRisks(data);
        } catch (error) {
            console.error('Error fetching risks:', error);
        } finally {
            setLoading(false);
        }
    };

    const getRiskLevel = (score: number) => {
        if (score >= 20) return { label: 'Critical', color: 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30' };
        if (score >= 12) return { label: 'High', color: 'text-orange-600 bg-orange-100 dark:text-orange-400 dark:bg-orange-900/30' };
        if (score >= 6) return { label: 'Medium', color: 'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900/30' };
        return { label: 'Low', color: 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30' };
    };

    const getCategoryIcon = (category: string) => {
        switch (category) {
            case 'AI': return <Zap className="w-4 h-4" />;
            case 'Cyber': return <Shield className="w-4 h-4" />;
            case 'Compliance': return <FileText className="w-4 h-4" />;
            case 'Third-Party': return <Users className="w-4 h-4" />;
            default: return <AlertTriangle className="w-4 h-4" />;
        }
    };

    const filteredRisks = risks.filter(risk =>
        (filterCategory === 'All' || risk.category === filterCategory) &&
        (risk.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
            risk.description.toLowerCase().includes(searchTerm.toLowerCase()))
    );

    // Heatmap Calculation
    const heatmapData = Array(5).fill(0).map(() => Array(5).fill(0));
    risks.forEach(risk => {
        // Likelihood (y) vs Impact (x). Arrays are 0-indexed.
        if (risk.likelihood > 0 && risk.likelihood <= 5 && risk.impact > 0 && risk.impact <= 5) {
            heatmapData[5 - risk.likelihood][risk.impact - 1]++;
            // 5-likelihood inverts Y axis so 5 is at top
        }
    });

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">
                        Enterprise Risk Register
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400">
                        Centralized view of all organizational risks across AI, Cyber, and Compliance.
                    </p>
                </div>
                <button
                    onClick={() => setShowAddModal(true)}
                    className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg flex items-center gap-2 transition-colors shadow-sm"
                >
                    <Plus className="w-4 h-4" />
                    New Risk
                </button>
            </div>

            {/* Risk Heatmap & Stats */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1 bg-white dark:bg-[#0f1115] p-5 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4" /> Risk Heatmap
                    </h3>
                    <div className="aspect-square relative flex flex-col justify-between">
                        {heatmapData.map((row, y) => (
                            <div key={y} className="flex flex-1 gap-1">
                                {row.map((count, x) => {
                                    const likelihood = 5 - y;
                                    const impact = x + 1;
                                    const score = likelihood * impact;
                                    let bg = 'bg-gray-100 dark:bg-gray-800';
                                    if (score >= 20) bg = 'bg-red-200 dark:bg-red-900/50';
                                    else if (score >= 12) bg = 'bg-orange-200 dark:bg-orange-900/50';
                                    else if (score >= 6) bg = 'bg-yellow-200 dark:bg-yellow-900/50';
                                    else if (score >= 1) bg = 'bg-green-200 dark:bg-green-900/50';

                                    return (
                                        <div key={x} className={`flex-1 rounded flex items-center justify-center text-xs font-bold ${bg} ${count > 0 ? 'border border-white/20' : ''}`}>
                                            {count > 0 ? count : ''}
                                        </div>
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="lg:col-span-2 grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {[
                        { label: 'Total Risks', value: risks.length, color: 'text-blue-600' },
                        { label: 'Critical', value: risks.filter(r => r.risk_score >= 20).length, color: 'text-red-600' },
                        { label: 'High Priority', value: risks.filter(r => r.risk_score >= 12 && r.risk_score < 20).length, color: 'text-orange-600' },
                        { label: 'Mitigated', value: risks.filter(r => r.status === 'Mitigated').length, color: 'text-green-600' },
                    ].map((stat, i) => (
                        <div key={i} className="bg-white dark:bg-[#0f1115] p-5 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm flex flex-col items-center justify-center">
                            <span className={`text-3xl font-bold ${stat.color}`}>{stat.value}</span>
                            <span className="text-sm text-gray-500 dark:text-gray-400 mt-1">{stat.label}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Risk Table */}
            <div className="bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex flex-col sm:flex-row gap-4 justify-between">
                    <div className="relative max-w-sm w-full">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                            type="text"
                            placeholder="Search risks..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-[#0b0c0e] border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                    <div className="flex gap-2">
                        {['All', 'Enterprise', 'Cyber', 'AI', 'Third-Party'].map(cat => (
                            <button
                                key={cat}
                                onClick={() => setFilterCategory(cat)}
                                className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${filterCategory === cat
                                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                                    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                                    }`}
                            >
                                {cat}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-gray-50 dark:bg-[#0b0c0e] text-gray-500 dark:text-gray-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-3 font-medium">Risk Title</th>
                                <th className="px-6 py-3 font-medium">Category</th>
                                <th className="px-6 py-3 font-medium">Score</th>
                                <th className="px-6 py-3 font-medium">Status</th>
                                <th className="px-6 py-3 font-medium">Owner</th>
                                <th className="px-6 py-3 font-medium text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                            {filteredRisks.map(risk => {
                                const level = getRiskLevel(risk.risk_score);
                                return (
                                    <tr key={risk.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="font-medium text-gray-900 dark:text-gray-100">{risk.title}</div>
                                            <div className="text-xs text-gray-500 truncate max-w-xs">{risk.description}</div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                                                {getCategoryIcon(risk.category)}
                                                {risk.category}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`px-2 py-1 rounded-md text-xs font-semibold ${level.color}`}>
                                                {risk.risk_score} ({level.label})
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${risk.status === 'Open' ? 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/10 dark:text-red-400 dark:border-red-900/30' :
                                                risk.status === 'Mitigated' ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-900/10 dark:text-green-400 dark:border-green-900/30' :
                                                    'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
                                                }`}>
                                                {risk.status === 'Mitigated' && <CheckCircle className="w-3 h-3" />}
                                                {risk.status}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                                            {risk.owner}
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="flex justify-end gap-2">
                                                <button className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors">
                                                    <Edit2 className="w-4 h-4" />
                                                </button>
                                                <button className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors">
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
            <RiskFormModal
                isOpen={showAddModal}
                onClose={() => setShowAddModal(false)}
                onSubmit={async (data) => {
                    await api.createRisk(data);
                    fetchRisks();
                }}
            />
        </div >
    );
}
