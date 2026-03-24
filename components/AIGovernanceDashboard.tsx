import React, { useState } from 'react';
import { AiModelRegistry } from './AiModelRegistry';
import { AiPolicyEngine } from './AiPolicyEngine';
import { AiComplianceReport } from './AiComplianceReport';
import { AIGuardrails } from './AIGuardrails';
import { ShadowAI } from './ShadowAI';
import { LayersIcon, ShieldCheckIcon, AlertTriangleIcon, SearchIcon, XIcon } from './icons';

export const AIGovernanceDashboard: React.FC<any> = (props) => {
    const [activeTab, setActiveTab] = useState<'registry' | 'policies' | 'compliance' | 'guardrails' | 'shadow_ai'>('registry');
    const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
    const [showReport, setShowReport] = useState(false);
    const [reviewType, setReviewType] = useState<'static' | 'expert'>('static');

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Governance (ISO 42001)</h1>
                {activeTab === 'registry' && (
                    <div className="flex space-x-2">
                        <div className="relative">
                            <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search models..."
                                className="pl-10 pr-4 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
                            />
                        </div>
                    </div>
                )}
            </div>

            {/* Tab Navigation */}
            <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg w-fit mb-8">
                <button
                    onClick={() => setActiveTab('registry')}
                    className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'registry'
                        ? 'bg-white dark:bg-gray-700 text-primary-600 dark:text-primary-400 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                        }`}
                >
                    <LayersIcon size={16} className="mr-2" />
                    Model Registry
                </button>
                <button
                    onClick={() => setActiveTab('policies')}
                    className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'policies'
                        ? 'bg-white dark:bg-gray-700 text-primary-600 dark:text-primary-400 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                        }`}
                >
                    <ShieldCheckIcon size={16} className="mr-2" />
                    Policy Engine
                </button>
                <button
                    onClick={() => setActiveTab('guardrails')}
                    className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'guardrails'
                        ? 'bg-white dark:bg-gray-700 text-primary-600 dark:text-primary-400 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                        }`}
                >
                    <ShieldCheckIcon size={16} className="mr-2" />
                    LLM Firewall
                </button>
                <button
                    onClick={() => setActiveTab('compliance')}
                    className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'compliance'
                        ? 'bg-white dark:bg-gray-700 text-primary-600 dark:text-primary-400 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                        }`}
                >
                    <AlertTriangleIcon size={16} className="mr-2" />
                    Risks & Incidents
                </button>
                <button
                    onClick={() => setActiveTab('shadow_ai')}
                    className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === 'shadow_ai'
                        ? 'bg-white dark:bg-gray-700 text-primary-600 dark:text-primary-400 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700 dark:text-gray-400'
                        }`}
                >
                    <SearchIcon size={16} className="mr-2" />
                    Shadow AI
                </button>
            </div>

            {/* Content Area */}
            <div>
                {activeTab === 'registry' && (
                    <div className="space-y-6">
                        <AiModelRegistry
                            onEvaluate={(id: string) => {
                                setSelectedModelId(id);
                                setReviewType('static');
                                setShowReport(true);
                            }}
                            onExpertEvaluate={(id: string) => {
                                setSelectedModelId(id);
                                setReviewType('expert');
                                setShowReport(true);
                            }}
                        />

                        {showReport && selectedModelId && (
                            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                                <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-4xl shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto p-8 relative">
                                    <button
                                        onClick={() => setShowReport(false)}
                                        className="absolute top-4 right-4 p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                                    >
                                        <XIcon size={24} />
                                    </button>
                                    <AiComplianceReport
                                        modelId={selectedModelId}
                                        type={reviewType}
                                        onClose={() => setShowReport(false)}
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                )}
                {activeTab === 'policies' && <AiPolicyEngine />}
                {activeTab === 'guardrails' && <AIGuardrails />}
                {activeTab === 'shadow_ai' && <ShadowAI />}
                {activeTab === 'compliance' && (
                    <div className="text-center py-20 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-dashed border-gray-300 dark:border-gray-700">
                        <AlertTriangleIcon size={48} className="mx-auto text-gray-400 mb-4" />
                        <h3 className="text-lg font-medium text-gray-900 dark:text-white">Risk Assessment</h3>
                        <p className="text-gray-500 dark:text-gray-400 mt-1">View AI risk register and incident reports.</p>
                    </div>
                )}
            </div>
        </div>
    );
};
