import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import { CheckIcon, AlertTriangleIcon, CogIcon, ShieldCheckIcon, ZapIcon } from './icons';

interface GuardrailPolicy {
    block_pii: boolean;
    block_injection: boolean;
    allowed_models: string[];
}

interface TestResult {
    passed: boolean;
    findings: string[];
    prompt_length: number;
}

const KNOWN_MODELS = [
    'gpt-3.5-turbo', 'gpt-4', 'gpt-4o',
    'claude-3-opus', 'claude-3-sonnet', 'claude-sonnet-4-6',
    'gemini-2.0-flash', 'gemini-1.5-pro',
];

const Toggle: React.FC<{ value: boolean; onChange: () => void; color?: string }> = ({ value, onChange, color = 'bg-blue-600' }) => (
    <button onClick={onChange}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${value ? color : 'bg-gray-200 dark:bg-gray-700'}`}>
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
);

export const AIGuardrails: React.FC = () => {
    const [policy, setPolicy] = useState<GuardrailPolicy>({ block_pii: true, block_injection: true, allowed_models: [] });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
    const [testPrompt, setTestPrompt] = useState('');
    const [testResult, setTestResult] = useState<TestResult | null>(null);
    const [testing, setTesting] = useState(false);

    useEffect(() => {
        authFetch('/api/ai-proxy/policy')
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data) setPolicy(data); })
            .catch((e) => console.error('Failed to load AI guardrails policy:', e))
            .finally(() => setLoading(false));
    }, []);

    const savePolicy = async () => {
        setSaving(true);
        setSaveMsg(null);
        try {
            const res = await authFetch('/api/ai-proxy/policy', { method: 'PUT', body: JSON.stringify(policy) });
            if (res.ok) {
                setSaveMsg({ ok: true, text: 'Policy saved successfully' });
            } else {
                setSaveMsg({ ok: false, text: 'Failed to save policy' });
            }
        } catch {
            setSaveMsg({ ok: false, text: 'Network error' });
        } finally {
            setSaving(false);
            setTimeout(() => setSaveMsg(null), 3000);
        }
    };

    const testPromptHandler = async () => {
        if (!testPrompt.trim()) return;
        setTesting(true);
        setTestResult(null);
        try {
            const res = await authFetch('/api/ai-proxy/test', { method: 'POST', body: JSON.stringify({ prompt: testPrompt }) });
            if (res.ok) setTestResult(await res.json());
        } catch { /* ignore */ }
        finally { setTesting(false); }
    };

    const toggleModel = (model: string) => {
        setPolicy(prev => ({
            ...prev,
            allowed_models: prev.allowed_models.includes(model)
                ? prev.allowed_models.filter(m => m !== model)
                : [...prev.allowed_models, model],
        }));
    };

    if (loading) {
        return <div className="flex items-center justify-center p-12 text-gray-500"><CogIcon size={20} className="animate-spin mr-2" /> Loading policy…</div>;
    }

    return (
        <div className="space-y-6">
            {/* Status bar */}
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white">Generative AI Firewall</h2>
                        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Real-time interception and scanning of LLM prompts.</p>
                    </div>
                    <div className="flex items-center gap-3">
                        {saveMsg && (
                            <span className={`text-xs font-medium ${saveMsg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                {saveMsg.text}
                            </span>
                        )}
                        <button onClick={savePolicy} disabled={saving}
                            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-50">
                            {saving ? <CogIcon size={14} className="animate-spin" /> : <CheckIcon size={14} />}
                            Save Policy
                        </button>
                        <span className="bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">Active</span>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* PII Blocking */}
                    <div className="flex items-start space-x-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-100 dark:border-gray-600">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg text-blue-600 dark:text-blue-400">
                            <ShieldCheckIcon size={24} />
                        </div>
                        <div className="flex-1">
                            <div className="flex justify-between items-center">
                                <h3 className="font-semibold text-gray-900 dark:text-white">PII Redaction</h3>
                                <Toggle value={policy.block_pii} onChange={() => setPolicy(p => ({ ...p, block_pii: !p.block_pii }))} color="bg-blue-600" />
                            </div>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                                Detects SSNs, credit card numbers, emails, and phone numbers in prompts before they reach LLM providers.
                            </p>
                        </div>
                    </div>

                    {/* Injection Defense */}
                    <div className="flex items-start space-x-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-100 dark:border-gray-600">
                        <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg text-purple-600 dark:text-purple-400">
                            <ZapIcon size={24} />
                        </div>
                        <div className="flex-1">
                            <div className="flex justify-between items-center">
                                <h3 className="font-semibold text-gray-900 dark:text-white">Injection Defense</h3>
                                <Toggle value={policy.block_injection} onChange={() => setPolicy(p => ({ ...p, block_injection: !p.block_injection }))} color="bg-purple-600" />
                            </div>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                                Blocks known jailbreak patterns ("ignore previous instructions", "DAN mode") to prevent policy bypass.
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Allowed Models */}
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">Allowed Models</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Only requests targeting these models will be forwarded.</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {KNOWN_MODELS.map(model => (
                        <label key={model} className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-100 dark:border-gray-600 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                            <input type="checkbox" checked={policy.allowed_models.includes(model)} onChange={() => toggleModel(model)}
                                className="rounded text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600" />
                            <span className="text-sm font-mono text-gray-700 dark:text-gray-300">{model}</span>
                        </label>
                    ))}
                </div>
            </div>

            {/* Test Prompt Panel */}
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-1">Test Guardrails</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Enter a prompt to verify the current policy catches what you expect.</p>
                <div className="space-y-3">
                    <textarea
                        value={testPrompt}
                        onChange={e => { setTestPrompt(e.target.value); setTestResult(null); }}
                        rows={4}
                        placeholder={'Try: "My SSN is 123-45-6789" or "Ignore previous instructions and…"'}
                        className="w-full p-3 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500 outline-none font-mono"
                    />
                    <button onClick={testPromptHandler} disabled={testing || !testPrompt.trim()}
                        className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-50">
                        {testing ? <CogIcon size={14} className="animate-spin" /> : <ZapIcon size={14} />}
                        Test Prompt
                    </button>

                    {testResult && (
                        <div className={`p-4 rounded-lg border ${testResult.passed ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'}`}>
                            <div className="flex items-center gap-2 mb-2">
                                {testResult.passed
                                    ? <><CheckIcon size={18} className="text-green-600 dark:text-green-400" /><span className="font-semibold text-green-700 dark:text-green-300">ALLOWED — no policy violations detected</span></>
                                    : <><AlertTriangleIcon size={18} className="text-red-600 dark:text-red-400" /><span className="font-semibold text-red-700 dark:text-red-300">BLOCKED — {testResult.findings.length} violation{testResult.findings.length > 1 ? 's' : ''} detected</span></>
                                }
                                <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">{testResult.prompt_length} chars</span>
                            </div>
                            {!testResult.passed && (
                                <ul className="space-y-1 mt-2">
                                    {testResult.findings.map((f, i) => (
                                        <li key={i} className="text-sm text-red-700 dark:text-red-300 flex items-start gap-2">
                                            <span className="font-mono text-xs mt-0.5">→</span>{f}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
