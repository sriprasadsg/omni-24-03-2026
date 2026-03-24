import React, { useState } from 'react';
import { FileText, Shield, Code, CheckCircle, Upload, ArrowRight, Zap } from 'lucide-react';

interface TechnicalRule {
    policy_id: string;
    rule_name: string;
    technical_implementation: string;
    severity: string;
}

interface AnalysisResult {
    summary: string;
    extracted_policies: string[];
    generated_rules: TechnicalRule[];
    confidence_score: number;
}

const ComplianceOracleDashboard: React.FC = () => {
    const [policyText, setPolicyText] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);

    const handleAnalyze = async () => {
        if (!policyText.trim()) return;
        setLoading(true);
        try {
            const res = await fetch('/api/compliance_oracle/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ policy_text: policyText })
            });
            const data = await res.json();
            setResult(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6 space-y-6 bg-slate-50 min-h-screen">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Generative Compliance Oracle</h1>
                    <p className="text-slate-500">Transform natural language policies into executable technical rules using AI</p>
                </div>
                <div className="flex items-center gap-2 bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full text-sm font-medium border border-indigo-100">
                    <Zap size={16} /> Beta Feature
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Input Section */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100 flex flex-col h-full">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                        <Upload size={20} className="text-blue-600" /> Policy Input
                    </h2>
                    <p className="text-sm text-slate-600 mb-4">
                        Paste your compliance policy text (e.g., from PDF or Wiki) below. The Oracle will parse it and generate Rego/Terraform constraints.
                    </p>
                    <textarea
                        className="flex-1 w-full p-4 border border-slate-200 rounded-lg text-sm bg-slate-50 focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none resize-none font-mono mb-4"
                        placeholder="e.g. 'All data stored in cloud storage must be encrypted using AES-256. Access logs must be retained for at least 90 days.'"
                        value={policyText}
                        onChange={(e) => setPolicyText(e.target.value)}
                    />
                    <div className="flex justify-end">
                        <button
                            onClick={handleAnalyze}
                            disabled={loading || !policyText}
                            className={`px-6 py-2.5 rounded-lg font-medium text-white flex items-center gap-2 transition-colors ${loading ? 'bg-slate-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
                                }`}
                        >
                            {loading ? 'Analyzing with AI...' : <><Zap size={18} /> Analyze & Generate Rules</>}
                        </button>
                    </div>
                </div>

                {/* Output Section */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-100 min-h-[500px] overflow-y-auto">
                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                        <Code size={20} className="text-purple-600" /> Generated Constraints
                    </h2>

                    {!result ? (
                        <div className="h-64 flex flex-col items-center justify-center text-slate-400">
                            <Shield size={48} className="mb-2 opacity-20" />
                            <p>Generated rules will appear here</p>
                        </div>
                    ) : (
                        <div className="space-y-6 animate-in fade-in duration-500">
                            {/* Summary Card */}
                            <div className="p-4 bg-slate-50 rounded-lg border border-slate-100">
                                <div className="flex justify-between items-start mb-2">
                                    <h3 className="font-semibold text-slate-800">Analysis Summary</h3>
                                    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">Confidence: {(result.confidence_score * 100).toFixed(1)}%</span>
                                </div>
                                <p className="text-sm text-slate-600">{result.summary}</p>
                                <div className="mt-3 flex flex-wrap gap-2">
                                    {result.extracted_policies.map((p, i) => (
                                        <span key={i} className="text-xs bg-white border border-slate-200 px-2 py-1 rounded text-slate-600 flex items-center gap-1">
                                            <CheckCircle size={10} className="text-green-500" /> {p}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            {/* Rules List */}
                            <div className="space-y-4">
                                {result.generated_rules.map((rule, idx) => (
                                    <div key={idx} className="border border-slate-200 rounded-lg overflow-hidden">
                                        <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex justify-between items-center">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-mono font-bold text-slate-500">{rule.policy_id}</span>
                                                <span className="text-sm font-semibold text-slate-800">{rule.rule_name}</span>
                                            </div>
                                            <span className={`text-[10px] px-2 py-0.5 rounded uppercase font-bold tracking-wider ${rule.severity === 'Critical' ? 'bg-red-100 text-red-700' :
                                                    rule.severity === 'High' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'
                                                }`}>
                                                {rule.severity}
                                            </span>
                                        </div>
                                        <div className="p-4 bg-slate-900 group relative">
                                            <code className="text-xs font-mono text-green-400 block break-all whitespace-pre-wrap">
                                                {rule.technical_implementation}
                                            </code>
                                            <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                                <button className="bg-white/10 hover:bg-white/20 text-white text-xs px-2 py-1 rounded">Copy</button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ComplianceOracleDashboard;
