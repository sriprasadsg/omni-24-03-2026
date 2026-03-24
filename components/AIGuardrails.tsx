import React, { useState, useEffect } from 'react';

interface GuardrailPolicy {
    block_pii: boolean;
    block_injection: boolean;
    allowed_models: string[];
}

export const AIGuardrails: React.FC = () => {
    const [policy, setPolicy] = useState<GuardrailPolicy>({
        block_pii: true,
        block_injection: true,
        allowed_models: ["gpt-3.5-turbo", "gpt-4", "claude-3-opus"]
    });

    // In real app, fetch from backend:
    // useEffect(() => fetch('/api/ai-proxy/policy')..., [])

    const togglePolicy = (key: keyof GuardrailPolicy) => {
        // @ts-ignore
        setPolicy({ ...policy, [key]: !policy[key] });
    };

    return (
        <div className="space-y-8">
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white">Generative AI Firewall</h2>
                        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Configure real-time interception and scanning of LLM prompts.</p>
                    </div>
                    <div className="bg-green-100 text-green-800 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">
                        Active
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* PII Blocking */}
                    <div className="flex items-start space-x-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-100 dark:border-gray-600">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg text-blue-600 dark:text-blue-400">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                        </div>
                        <div className="flex-1">
                            <div className="flex justify-between items-center">
                                <h3 className="font-semibold text-gray-900 dark:text-white">PII Redaction</h3>
                                <button
                                    onClick={() => togglePolicy('block_pii')}
                                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${policy.block_pii ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}
                                >
                                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${policy.block_pii ? 'translate-x-6' : 'translate-x-1'}`} />
                                </button>
                            </div>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                                Automatically detects and blocks sensitive data (SSNs, Credit Cards, Emails) from being sent to external LLM providers.
                            </p>
                        </div>
                    </div>

                    {/* Prompt Injection */}
                    <div className="flex items-start space-x-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-100 dark:border-gray-600">
                        <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg text-purple-600 dark:text-purple-400">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                        </div>
                        <div className="flex-1">
                            <div className="flex justify-between items-center">
                                <h3 className="font-semibold text-gray-900 dark:text-white">Injection Defense</h3>
                                <button
                                    onClick={() => togglePolicy('block_injection')}
                                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${policy.block_injection ? 'bg-purple-600' : 'bg-gray-200 dark:bg-gray-700'}`}
                                >
                                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${policy.block_injection ? 'translate-x-6' : 'translate-x-1'}`} />
                                </button>
                            </div>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                                Blocks known "jailbreak" attempts (e.g., "Ignore previous instructions", "DAN mode") to maintain system integrity.
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Allowed Models</h2>
                <div className="space-y-2">
                    {["gpt-3.5-turbo", "gpt-4", "claude-3-opus", "claude-3-sonnet", "gemini-pro"].map(model => (
                        <label key={model} className="flex items-center space-x-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-lg cursor-pointer">
                            <input
                                type="checkbox"
                                checked={policy.allowed_models.includes(model)}
                                onChange={(e) => {
                                    if (e.target.checked) setPolicy({ ...policy, allowed_models: [...policy.allowed_models, model] });
                                    else setPolicy({ ...policy, allowed_models: policy.allowed_models.filter(m => m !== model) });
                                }}
                                className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                            />
                            <span className="text-gray-700 dark:text-gray-200 font-mono text-sm">{model}</span>
                        </label>
                    ))}
                </div>
            </div>
        </div>
    );
};
