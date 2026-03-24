import React, { useState, useEffect } from 'react';
import { listPrompts, createPrompt, ingestKnowledge, queryKnowledge } from '../services/apiService';
import { SparklesIcon, UploadIcon } from './icons';
import ModelTrainingDashboard from './ModelTrainingDashboard';

const LLMOpsDashboard: React.FC = () => {
    const [activeTab, setActiveTab] = useState<'prompts' | 'knowledge' | 'training'>('prompts');

    // Prompts State
    const [prompts, setPrompts] = useState<any[]>([]);
    const [newPrompt, setNewPrompt] = useState({ name: '', template: '', input_variables: [] as string[] });

    // Knowledge State
    const [ingestText, setIngestText] = useState('');
    const [queryText, setQueryText] = useState('');
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [ingestStatus, setIngestStatus] = useState('');

    useEffect(() => {
        if (activeTab === 'prompts') {
            loadPrompts();
        }
    }, [activeTab]);

    const loadPrompts = async () => {
        const res = await listPrompts();
        if (res.prompts) setPrompts(res.prompts);
    };

    const handleCreatePrompt = async () => {
        const res = await createPrompt({
            ...newPrompt,
            version: "1.0.0",
            input_variables: newPrompt.template.match(/\{(\w+)\}/g)?.map(s => s.slice(1, -1)) || []
        });
        if (res.success) {
            alert('Prompt Created!');
            setNewPrompt({ name: '', template: '', input_variables: [] });
            loadPrompts();
        } else {
            alert('Failed: ' + res.error);
        }
    };

    const handleIngest = async () => {
        setIngestStatus('Ingesting...');
        const res = await ingestKnowledge(ingestText, 'manual_ui');
        setIngestStatus(res.success ? 'Success! ID: ' + res.id : 'Error: ' + res.error);
    };

    const handleQuery = async () => {
        const res = await queryKnowledge(queryText);
        if (res.success && res.results) setSearchResults(res.results);
    };

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-cyan-600 via-blue-600 to-indigo-600 bg-clip-text text-transparent flex items-center gap-3">
                    <SparklesIcon size={36} className="text-cyan-500" />
                    LLMOps & Knowledge Center
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Manage prompt engineering pipelines and semantic knowledge retrieval.
                </p>
            </header>

            <div className="glass-premium rounded-3xl overflow-hidden shadow-2xl">
                <div className="border-b border-white/10 dark:border-white/5 bg-black/5 dark:bg-white/5">
                    <nav className="flex space-x-2 px-6" aria-label="Tabs">
                        <button
                            onClick={() => setActiveTab('prompts')}
                            className={`flex items-center gap-2 py-5 px-4 font-bold text-sm transition-all border-b-2 ${activeTab === 'prompts' ? 'border-cyan-500 text-cyan-600 dark:text-cyan-400 bg-cyan-500/5' : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'}`}
                        >
                            Prompt Registry
                        </button>
                        <button
                            onClick={() => setActiveTab('knowledge')}
                            className={`flex items-center gap-2 py-5 px-4 font-bold text-sm transition-all border-b-2 ${activeTab === 'knowledge' ? 'border-cyan-500 text-cyan-600 dark:text-cyan-400 bg-cyan-500/5' : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'}`}
                        >
                            Knowledge Base (RAG)
                        </button>
                        <button
                            onClick={() => setActiveTab('training')}
                            className={`flex items-center gap-2 py-5 px-4 font-bold text-sm transition-all border-b-2 ${activeTab === 'training' ? 'border-blue-500 text-blue-500 dark:text-blue-400 bg-blue-500/5' : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'}`}
                        >
                            🧠 Train Custom Model
                        </button>
                    </nav>
                </div>

                <div className="p-8">
                    {activeTab === 'prompts' && (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                            <div className="glass p-6 rounded-2xl border border-white/10 space-y-4">
                                <h2 className="text-xl font-bold flex items-center gap-2">
                                    <SparklesIcon size={20} className="text-cyan-500" />
                                    Create Prompt
                                </h2>
                                <input
                                    className="w-full bg-white/5 border border-white/10 p-3 rounded-xl text-sm font-semibold focus:ring-2 focus:ring-cyan-500 outline-none"
                                    placeholder="Prompt Name (e.g., system-audit)"
                                    value={newPrompt.name}
                                    onChange={e => setNewPrompt({ ...newPrompt, name: e.target.value })}
                                />
                                <textarea
                                    className="w-full bg-white/5 border border-white/10 p-3 rounded-xl h-48 text-sm font-mono focus:ring-2 focus:ring-cyan-500 outline-none"
                                    placeholder="Template... Use {var} for variables"
                                    value={newPrompt.template}
                                    onChange={e => setNewPrompt({ ...newPrompt, template: e.target.value })}
                                />
                                <button
                                    onClick={handleCreatePrompt}
                                    className="w-full bg-gradient-to-r from-cyan-600 to-blue-600 text-white py-3 rounded-xl font-bold shadow-lg shadow-cyan-500/30 hover:scale-[1.02] transition-all"
                                >
                                    Save to Registry
                                </button>
                            </div>

                            <div className="glass p-6 rounded-2xl border border-white/10">
                                <h2 className="text-xl font-bold mb-6">Active Registry</h2>
                                <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2">
                                    {prompts.map((p, i) => (
                                        <div key={i} className="p-4 bg-white/5 rounded-xl border-l-4 border-cyan-500 hover:bg-white/10 transition-colors group">
                                            <div className="flex justify-between items-start mb-2">
                                                <h3 className="font-bold text-gray-800 dark:text-gray-200">{p.name}</h3>
                                                <span className="text-[10px] font-black bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 px-2 py-0.5 rounded uppercase tracking-widest">v{p.version}</span>
                                            </div>
                                            <pre className="text-xs text-gray-500 dark:text-gray-400 font-mono line-clamp-3 group-hover:line-clamp-none transition-all">{p.template}</pre>
                                        </div>
                                    ))}
                                    {prompts.length === 0 && (
                                        <div className="text-center py-12 text-gray-500">
                                            <p className="font-bold">No prompts registered</p>
                                            <p className="text-sm">Start by creating your first prompt template.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'knowledge' && (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                            <div className="glass p-6 rounded-2xl border border-white/10 space-y-4">
                                <h2 className="text-xl font-bold flex items-center gap-2 text-green-500">
                                    <UploadIcon size={20} />
                                    Ingest Knowledge
                                </h2>
                                <textarea
                                    className="w-full bg-white/5 border border-white/10 p-3 rounded-xl h-48 text-sm focus:ring-2 focus:ring-green-500 outline-none"
                                    placeholder="Paste documentation or text here..."
                                    value={ingestText}
                                    onChange={e => setIngestText(e.target.value)}
                                />
                                <button
                                    onClick={handleIngest}
                                    className="w-full bg-gradient-to-r from-green-600 to-emerald-600 text-white py-3 rounded-xl font-bold shadow-lg shadow-green-500/30 hover:scale-[1.02] transition-all"
                                >
                                    Ingest to Vector DB
                                </button>
                                {ingestStatus && <p className="text-center text-xs font-bold text-cyan-400 animate-pulse">{ingestStatus}</p>}
                            </div>

                            <div className="glass p-6 rounded-2xl border border-white/10 space-y-4">
                                <h2 className="text-xl font-bold mb-2 text-purple-500 italic">Semantic Search</h2>
                                <div className="flex gap-2">
                                    <input
                                        className="flex-1 bg-white/5 border border-white/10 p-3 rounded-xl text-sm font-semibold focus:ring-2 focus:ring-purple-500 outline-none"
                                        placeholder="Ask a question..."
                                        value={queryText}
                                        onChange={e => setQueryText(e.target.value)}
                                    />
                                    <button onClick={handleQuery} className="bg-purple-600 hover:bg-purple-500 px-6 rounded-xl font-bold text-white transition-colors">Search</button>
                                </div>

                                <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 mt-4">
                                    {searchResults.map((r, i) => (
                                        <div key={i} className="p-4 bg-white/5 rounded-xl border border-white/10 hover:border-purple-500/30 transition-all">
                                            <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed font-medium">{r.content}</p>
                                            <div className="flex justify-between items-center mt-3 border-t border-white/5 pt-2">
                                                <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Source: {r.source}</span>
                                                <span className="text-[10px] bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded font-black tracking-tighter uppercase font-mono">Score: {r.relevance?.toFixed(4) || 'N/A'}</span>
                                            </div>
                                        </div>
                                    ))}
                                    {searchResults.length === 0 && (
                                        <div className="text-center py-12 text-gray-500">
                                            <p className="font-bold">No results found</p>
                                            <p className="text-sm">Try asking a different question.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                    {activeTab === 'training' && (
                        <div>
                            <p className="text-gray-500 dark:text-gray-400 mb-6 text-sm">Build a custom, offline-first LLM modeled after the Llama3 architecture. All processing is local — no internet required.</p>
                            <ModelTrainingDashboard />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default LLMOpsDashboard;
