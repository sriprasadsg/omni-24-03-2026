import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, AlertTriangleIcon, CheckIcon, XCircleIcon, ClockIcon, InfoIcon, SparklesIcon, GavelIcon } from './icons';
import * as api from '../services/apiService';

interface AiComplianceReportProps {
    modelId: string;
    type?: 'static' | 'expert';
    onClose: () => void;
}

export const AiComplianceReport: React.FC<AiComplianceReportProps> = ({ modelId, type = 'static', onClose }) => {
    const [report, setReport] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        evaluate();
    }, [modelId, type]);

    const evaluate = async () => {
        setLoading(true);
        try {
            const data = type === 'expert'
                ? await api.checkModelComplianceExpert(modelId)
                : await api.checkModelCompliance(modelId);
            setReport(data);
        } catch (e) {
            console.error("Evaluation failed", e);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="p-10 text-center">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600 mx-auto mb-4"></div>
                <p className="text-gray-500">{type === 'expert' ? 'SecurityExpert is performing deep-dive...' : 'Running compliance evaluation...'}</p>
            </div>
        );
    }

    if (!report) return null;

    // Handle Expert Scan Data
    if (type === 'expert' && report.result) {
        const res = report.result;
        return (
            <div className="space-y-6">
                <div className="flex justify-between items-start">
                    <div className="flex items-center">
                        <div className="p-3 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-xl mr-4">
                            <SparklesIcon size={24} />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white">AI Expert Review</h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400">Powered by SecurityExpert LLM • ISO 42001</p>
                        </div>
                    </div>
                    <div className={`px-4 py-2 rounded-full flex items-center font-bold text-sm ${res.iso42001Status === 'Compliant' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                        {res.iso42001Status === 'Compliant' ? <CheckIcon size={18} className="mr-2" /> : <AlertTriangleIcon size={18} className="mr-2" />}
                        {res.iso42001Status}
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-indigo-50 dark:bg-indigo-900/20 p-4 rounded-xl border border-indigo-100 dark:border-indigo-900/30">
                        <div className="text-[10px] text-indigo-400 uppercase font-bold mb-1 tracking-wider">Expert Score</div>
                        <div className="text-2xl font-black text-indigo-600 dark:text-indigo-300">{res.overallScore}%</div>
                    </div>
                    <div className="md:col-span-3 bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl border border-gray-100 dark:border-gray-800">
                        <div className="text-[10px] text-gray-400 uppercase font-bold mb-1 tracking-wider">Expert Opinion</div>
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 italic">"{res.expertOpinion}"</p>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-3">
                        <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center">
                            <AlertTriangleIcon size={14} className="mr-2" />
                            Identified Risks
                        </h4>
                        <div className="space-y-2">
                            {res.keyRisks.map((risk: string, i: number) => (
                                <div key={i} className="flex items-start text-sm text-gray-700 dark:text-gray-300 p-2 bg-red-100/30 dark:bg-red-900/10 rounded-lg">
                                    <div className="h-1.5 w-1.5 bg-red-500 rounded-full mt-1.5 mr-2 flex-shrink-0" />
                                    {risk}
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="space-y-3">
                        <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center">
                            <GavelIcon size={14} className="mr-2" />
                            Mitigation Roadmap
                        </h4>
                        <div className="space-y-2">
                            {res.mitigationRoadmap.map((step: string, i: number) => (
                                <div key={i} className="flex items-start text-sm text-gray-700 dark:text-gray-300 p-2 bg-green-100/30 dark:bg-green-900/10 rounded-lg">
                                    <div className="h-1.5 w-1.5 bg-green-500 rounded-full mt-1.5 mr-2 flex-shrink-0" />
                                    {step}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="pt-6 border-t border-gray-100 dark:border-gray-800 flex justify-between items-center">
                    <div className="text-xs text-gray-400">Scan ID: {report.id} • {new Date(report.timestamp).toLocaleString()}</div>
                    <button
                        onClick={onClose}
                        className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-bold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-500/20"
                    >
                        Close Review
                    </button>
                </div>
            </div>
        );
    }

    // Default Static Report View
    return (
        <div className="space-y-6">
            <div className="flex justify-between items-start">
                <div>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Compliance Report</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Model: {report.modelName} ({report.modelId})</p>
                </div>
                <div className={`px-4 py-2 rounded-full flex items-center font-bold text-sm ${report.compliant ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {report.compliant ? <CheckIcon size={18} className="mr-2" /> : <XCircleIcon size={18} className="mr-2" />}
                    {report.compliant ? 'COMPLIANT' : 'NON-COMPLIANT'}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl border border-gray-100 dark:border-gray-800">
                    <div className="text-xs text-gray-400 uppercase font-bold mb-1">Timestamp</div>
                    <div className="text-sm font-medium flex items-center">
                        <ClockIcon size={14} className="mr-2 text-gray-400" />
                        {new Date(report.timestamp).toLocaleString()}
                    </div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl border border-gray-100 dark:border-gray-800">
                    <div className="text-xs text-gray-400 uppercase font-bold mb-1">Total Violations</div>
                    <div className="text-sm font-bold text-gray-900 dark:text-white">{report.violations ? report.violations.length : 0}</div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl border border-gray-100 dark:border-gray-800">
                    <div className="text-xs text-gray-400 uppercase font-bold mb-1">Framework</div>
                    <div className="text-sm font-medium">ISO 42001 (AI Governance)</div>
                </div>
            </div>

            <div className="space-y-4">
                <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-wider">Violation Details</h4>
                {report.violations && report.violations.length > 0 ? (
                    <div className="space-y-3">
                        {report.violations.map((v: any, idx: number) => (
                            <div key={idx} className="p-4 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-xl flex items-start">
                                <AlertTriangleIcon size={20} className="text-red-500 mr-4 mt-1 flex-shrink-0" />
                                <div>
                                    <div className="flex items-center mb-1">
                                        <span className="font-bold text-red-800 dark:text-red-400 mr-2">{v.ruleName}</span>
                                        <span className="text-[10px] px-1.5 py-0.5 bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200 rounded font-bold uppercase">
                                            {v.severity}
                                        </span>
                                    </div>
                                    <p className="text-sm text-red-700 dark:text-red-300 mb-2">{v.message}</p>
                                    <div className="text-[10px] text-red-600/60 dark:text-red-400/60 font-medium">
                                        Policy: {v.policyName} ({v.policyId})
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="p-10 text-center bg-green-50 dark:bg-green-900/10 border border-green-100 dark:border-green-900/30 rounded-xl">
                        <ShieldCheckIcon size={48} className="mx-auto text-green-500 mb-4" />
                        <p className="text-green-700 dark:text-green-400 font-medium">No policy violations detected. This model is compliant with all active governance rules.</p>
                    </div>
                )}
            </div>

            <div className="pt-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
                <button
                    onClick={onClose}
                    className="px-6 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg font-bold hover:bg-gray-200 transition-colors"
                >
                    Close Report
                </button>
            </div>
        </div>
    );
};
