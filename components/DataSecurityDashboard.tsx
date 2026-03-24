import React, { useMemo, useState } from 'react';
import { SensitiveDataFinding, DataClassification } from '../types';
import { DnaIcon } from './icons';

interface DataSecurityDashboardProps {
    findings: SensitiveDataFinding[];
}

const classificationClasses: Record<DataClassification, string> = {
    PII: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    Financial: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
    IP: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300',
    Public: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};


export const DataSecurityDashboard: React.FC<DataSecurityDashboardProps> = ({ findings }) => {
    const [classificationFilter, setClassificationFilter] = useState<'All' | DataClassification>('All');

    const filteredFindings = useMemo(() => {
        if (classificationFilter === 'All') return findings;
        return findings.filter(f => f.classification === classificationFilter);
    }, [findings, classificationFilter]);

    const classificationCounts = useMemo(() => {
        return findings.reduce((acc, finding) => {
            acc[finding.classification] = (acc[finding.classification] || 0) + 1;
            return acc;
        }, {} as Record<DataClassification, number>);
    }, [findings]);


    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-primary-600 via-indigo-600 to-accent-600 bg-clip-text text-transparent flex items-center gap-3">
                    <DnaIcon size={36} className="text-primary-500" />
                    Data Security Posture Management (DSPM)
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Discover, classify, and protect sensitive data across your enterprise assets.
                </p>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="glass-premium p-6 rounded-3xl transform hover:scale-105 transition-all">
                    <p className="text-sm text-gray-400 font-bold uppercase tracking-wider mb-2">Total Findings</p>
                    <p className="text-4xl font-black text-gray-800 dark:text-gray-100">{findings.length}</p>
                </div>
                <div className="glass-premium p-6 rounded-3xl border-l-4 border-red-500 transform hover:scale-105 transition-all">
                    <p className="text-sm text-red-500 font-bold uppercase tracking-wider mb-2">PII Exposures</p>
                    <p className="text-4xl font-black text-red-600 dark:text-red-400">{classificationCounts.PII || 0}</p>
                </div>
                <div className="glass-premium p-6 rounded-3xl border-l-4 border-orange-500 transform hover:scale-105 transition-all">
                    <p className="text-sm text-orange-500 font-bold uppercase tracking-wider mb-2">Financial Data</p>
                    <p className="text-4xl font-black text-orange-600 dark:text-orange-400">{classificationCounts.Financial || 0}</p>
                </div>
                <div className="glass-premium p-6 rounded-3xl border-l-4 border-purple-500 transform hover:scale-105 transition-all">
                    <p className="text-sm text-purple-500 font-bold uppercase tracking-wider mb-2">Intellectual Property</p>
                    <p className="text-4xl font-black text-purple-600 dark:text-purple-400">{classificationCounts.IP || 0}</p>
                </div>
            </div>

            <div className="glass-premium rounded-3xl overflow-hidden shadow-2xl">
                <div className="p-6 border-b border-white/10 dark:border-white/5 bg-gradient-to-r from-primary-500/5 to-transparent flex items-center justify-between">
                    <h3 className="text-xl font-bold flex items-center gap-3">
                        <DnaIcon size={24} className="text-primary-500" />
                        Sensitive Data Findings
                    </h3>
                    <div className="flex gap-2">
                        {['All', 'PII', 'Financial', 'IP'].map(type => (
                            <button
                                key={type}
                                onClick={() => setClassificationFilter(type as any)}
                                className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${classificationFilter === type ? 'bg-primary-600 text-white shadow-lg shadow-primary-500/30' : 'bg-white/10 text-gray-400 hover:bg-white/20'}`}
                            >
                                {type}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-gray-400 uppercase bg-black/5 dark:bg-white/5 font-black">
                            <tr>
                                <th scope="col" className="px-6 py-4">Finding & Resource</th>
                                <th scope="col" className="px-6 py-4">Asset</th>
                                <th scope="col" className="px-6 py-4">Classification</th>
                                <th scope="col" className="px-6 py-4">Severity</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {filteredFindings.map(finding => (
                                <tr key={finding.id} className="hover:bg-primary-500/5 transition-colors group">
                                    <td className="px-6 py-5">
                                        <div className="font-bold text-gray-800 dark:text-gray-100 group-hover:translate-x-1 transition-transform">{finding.finding}</div>
                                        <div className="font-mono text-[10px] text-gray-500 dark:text-gray-400 mt-1 uppercase tracking-tighter bg-white/5 inline-block px-1 rounded">{finding.resource}</div>
                                    </td>
                                    <td className="px-6 py-5">
                                        <span className="font-mono text-xs bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 px-2 py-0.5 rounded-lg border border-indigo-500/20">{finding.assetName}</span>
                                    </td>
                                    <td className="px-6 py-5">
                                        <span className={`px-3 py-1 text-[10px] font-black rounded-full uppercase tracking-widest ${classificationClasses[finding.classification]}`}>
                                            {finding.classification}
                                        </span>
                                    </td>
                                    <td className="px-6 py-5">
                                        <span className={`px-3 py-1 text-[10px] font-black rounded-full uppercase tracking-widest ${finding.severity === 'Critical' ? 'bg-red-500 text-white animate-pulse' :
                                                finding.severity === 'High' ? 'bg-orange-500 text-white' :
                                                    'bg-amber-500 text-white'
                                            }`}>
                                            {finding.severity}
                                        </span>
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
