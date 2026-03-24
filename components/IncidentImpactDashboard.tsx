import React, { useState } from 'react';
import { IncidentImpactGraph, Alert, SecurityCase } from '../types';
import { analyzeIncident } from '../services/apiService';
import { Share2Icon, AlertTriangleIcon, BoxIcon, ShieldCheckIcon, ServerIcon, ArrowLeftIcon, CpuIcon, LoaderIcon } from './icons';


interface IncidentImpactDashboardProps {
    graph: IncidentImpactGraph;
    context: { type: 'alert' | 'case', id: string } | null;
    alerts: Alert[];
    cases: SecurityCase[];
    onAnalyze?: (type: 'alert' | 'case', id: string) => void;
}

const NodeCard: React.FC<{ node: IncidentImpactGraph['nodes'][0] }> = ({ node }) => {
    const icons: any = {
        'Alert': <AlertTriangleIcon className="text-red-500" size={20} />,
        'Service': <BoxIcon className="text-blue-500" size={20} />,
        'KPI': <Share2Icon className="text-purple-500" size={20} />,
        'Case': <ShieldCheckIcon className="text-green-500" size={20} />,
        'Asset': <ServerIcon className="text-gray-500" size={20} />,
    };

    return (
        <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 flex items-center">
            <div className="mr-3">{icons[node.type] || <BoxIcon size={20} />}</div>
            <div>
                <p className="font-semibold text-sm text-gray-800 dark:text-gray-200">{node.label}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{node.type}</p>
            </div>
        </div>
    );
};


export const IncidentImpactDashboard: React.FC<IncidentImpactDashboardProps> = ({ graph, context, alerts, cases, onAnalyze }) => {

    // Selection Mode
    if (!context || context.id === 'dummy-id') {
        return (
            <div className="container mx-auto p-6">
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6 flex items-center">
                    <Share2Icon size={24} className="mr-3 text-primary-500" />
                    Incident Impact Analysis
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <h3 className="text-lg font-bold mb-4 flex items-center"><AlertTriangleIcon className="mr-2 text-red-500" /> Select an Alert</h3>
                        <ul className="space-y-2 max-h-96 overflow-y-auto">
                            {alerts.map(alert => (
                                <li key={alert.id}
                                    onClick={() => onAnalyze && onAnalyze('alert', alert.id)}
                                    className="p-3 border rounded hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors"
                                >
                                    <div className="font-medium text-sm">{alert.message}</div>
                                    <div className="text-xs text-gray-500">{alert.severity} - {new Date(alert.timestamp).toLocaleDateString()}</div>
                                </li>
                            ))}
                        </ul>
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <h3 className="text-lg font-bold mb-4 flex items-center"><ShieldCheckIcon className="mr-2 text-green-500" /> Select a Case</h3>
                        <ul className="space-y-2 max-h-96 overflow-y-auto">
                            {cases.map(c => (
                                <li key={c.id}
                                    onClick={() => onAnalyze && onAnalyze('case', c.id)}
                                    className="p-3 border rounded hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors"
                                >
                                    <div className="font-medium text-sm">{c.title}</div>
                                    <div className="text-xs text-gray-500">{c.status} - {c.severity}</div>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>
        );
    }

    const sourceEntity = context.type === 'case'
        ? cases.find(c => c.id === context.id)
        : alerts.find(a => a.id === context.id);

    const sourceTitle = context.type === 'case' ? (sourceEntity as SecurityCase)?.title : (sourceEntity as Alert)?.message;

    const [aiAnalysis, setAiAnalysis] = useState<any>(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);

    const handleRunAiAnalysis = async () => {
        setIsAnalyzing(true);
        try {
            const result = await analyzeIncident(context.type, context.id);
            setAiAnalysis(result);
        } catch (e) {
            alert("AI Analysis failed. Check console or API Key settings.");
        } finally {
            setIsAnalyzing(false);
        }
    };

    return (
        <div className="container mx-auto p-4">
            <button onClick={() => onAnalyze && onAnalyze('alert', 'dummy-id')} className="mb-4 text-sm text-primary-600 hover:text-primary-800 flex items-center">
                <ArrowLeftIcon size={16} className="mr-1" /> Back to Selection
            </button>
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2 flex items-center">
                <Share2Icon size={24} className="mr-3 text-primary-500" />
                Incident Impact Analysis
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                Analyzing the blast radius for {context.type}: <span className="font-semibold text-gray-700 dark:text-gray-300">{sourceTitle || context.id}</span>
            </p>

            <div className="mb-6">
                <button
                    onClick={handleRunAiAnalysis}
                    disabled={isAnalyzing}
                    className="flex items-center px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-lg hover:from-purple-700 hover:to-indigo-700 transition-all shadow-md disabled:opacity-50"
                >
                    {isAnalyzing ? <LoaderIcon className="animate-spin mr-2" /> : <CpuIcon className="mr-2" />}
                    {isAnalyzing ? 'Analyzing with Gemini...' : 'Analyze with Agentic AI'}
                </button>
            </div>

            {aiAnalysis && (
                <div className="mb-6 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-lg p-6">
                    <h3 className="text-lg font-bold text-indigo-900 dark:text-indigo-100 mb-3 flex items-center">
                        <CpuIcon className="mr-2" /> AI Assessment: {aiAnalysis.severityAssessment || 'Analysis Complete'}
                    </h3>
                    <p className="mb-4 text-gray-700 dark:text-gray-300 italic">"{aiAnalysis.summary}"</p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-white dark:bg-gray-800 p-4 rounded border dark:border-gray-700">
                            <h4 className="font-semibold mb-2 text-red-600">Root Cause</h4>
                            <p className="text-sm">{aiAnalysis.rootCauseAnalysis}</p>
                        </div>
                        <div className="bg-white dark:bg-gray-800 p-4 rounded border dark:border-gray-700">
                            <h4 className="font-semibold mb-2 text-green-600">Mitigation Steps</h4>
                            <ul className="list-disc pl-5 text-sm space-y-1">
                                {aiAnalysis.mitigationSteps?.map((step: string, i: number) => <li key={i}>{step}</li>)}
                            </ul>
                        </div>
                    </div>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold mb-4">Impact Graph</h3>
                    <div className="relative h-96 border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-900/50 overflow-auto flex items-center justify-center">
                        {/* Simplified graph visualization */}
                        <div className="flex flex-col items-center space-y-6 w-full">
                            {!graph || graph.nodes.length === 0 ? <p>No impact data found.</p> : (
                                <>
                                    {/* Root */}
                                    {graph.nodes.filter(n => n.id === 'root').map(n => <NodeCard key={n.id} node={n} />)}
                                    {graph.nodes.length > 1 && <div className="h-8 w-px bg-gray-400"></div>}
                                    {/* Level 1 */}
                                    <div className="flex flex-wrap justify-center gap-4">
                                        {graph.nodes.filter(n => n.id !== 'root').map(n => <NodeCard key={n.id} node={n} />)}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>

                <div className="lg:col-span-1 bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold mb-4">Impacted Entities</h3>
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                        {graph.nodes.filter(n => n.id !== 'root').map(node => (
                            <NodeCard key={node.id} node={node} />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};
