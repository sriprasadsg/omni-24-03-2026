import React, { useState, useEffect, useCallback } from 'react';
import { ChaosExperiment } from '../types';
import { fetchChaosExperiments, createChaosExperiment, runChaosExperiment } from '../services/apiService';
import { BombIcon, TestTubeIcon, ZapIcon, CheckIcon, XCircleIcon, CogIcon, ClockIcon, PlusIcon } from './icons';

const STATUS_CLASSES: Record<ChaosExperiment['status'], string> = {
    Scheduled: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
    Running: 'bg-amber-500/10 text-amber-500 border-amber-500/30 animate-pulse',
    Completed: 'bg-green-500/10 text-green-500 border-green-500/30',
    Failed: 'bg-red-500/10 text-red-500 border-red-500/30',
};

const STATUS_ICONS: Record<ChaosExperiment['status'], React.ReactNode> = {
    Scheduled: <ClockIcon size={14} />,
    Running: <CogIcon size={14} className="animate-spin" />,
    Completed: <CheckIcon size={14} />,
    Failed: <XCircleIcon size={14} />,
};

const EXPERIMENT_TYPES: ChaosExperiment['type'][] = ['CPU Hog', 'Latency Injection', 'Pod Failure'];

interface CreateForm { name: string; type: ChaosExperiment['type']; target: string }

export const ChaosEngineeringDashboard: React.FC = () => {
    const [experiments, setExperiments] = useState<ChaosExperiment[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showCreate, setShowCreate] = useState(false);
    const [form, setForm] = useState<CreateForm>({ name: '', type: 'CPU Hog', target: '' });
    const [creating, setCreating] = useState(false);
    const [runningId, setRunningId] = useState<string | null>(null);
    const [runResult, setRunResult] = useState<{ id: string; message: string; ok: boolean } | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchChaosExperiments();
            setExperiments(data);
        } catch {
            setError('Failed to load experiments.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!form.name.trim() || !form.target.trim()) return;
        setCreating(true);
        const result = await createChaosExperiment(form);
        setCreating(false);
        if (result.status === 403) {
            setError('Tenant context required. Please ensure you are logged in with a valid tenant.');
            setShowCreate(false);
            return;
        }
        if (!result.ok) {
            setError('Failed to create experiment.');
            return;
        }
        setShowCreate(false);
        setForm({ name: '', type: 'CPU Hog', target: '' });
        load();
    };

    const handleRun = async (id: string) => {
        setRunningId(id);
        setRunResult(null);
        const result = await runChaosExperiment(id);
        setRunningId(null);
        if (result.status === 403) {
            setRunResult({ id, message: 'Tenant context required.', ok: false });
        } else if (!result.ok) {
            setRunResult({ id, message: result.data?.detail || 'Run failed.', ok: false });
        } else {
            setRunResult({ id, message: result.data?.message || 'Experiment dispatched.', ok: true });
            load();
        }
    };

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-red-600 via-orange-600 to-amber-600 bg-clip-text text-transparent flex items-center gap-3">
                    <BombIcon size={36} className="text-red-500" />
                    Chaos Engineering
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Proactively test system resilience by injecting controlled failures.
                </p>
            </header>

            {error && (
                <div className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-medium">
                    <XCircleIcon size={16} className="shrink-0" />
                    {error}
                    <button onClick={() => setError(null)} className="ml-auto text-red-400/60 hover:text-red-400">✕</button>
                </div>
            )}

            {runResult && (
                <div className={`flex items-center gap-3 p-4 rounded-xl text-sm font-medium border ${runResult.ok ? 'bg-green-500/10 border-green-500/30 text-green-400' : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
                    {runResult.ok ? <CheckIcon size={16} className="shrink-0" /> : <XCircleIcon size={16} className="shrink-0" />}
                    {runResult.message}
                    <button onClick={() => setRunResult(null)} className="ml-auto opacity-60 hover:opacity-100">✕</button>
                </div>
            )}

            <div className="glass-premium rounded-3xl shadow-2xl overflow-hidden border border-white/10">
                <div className="p-6 border-b border-white/10 flex justify-between items-center bg-black/5 dark:bg-white/5">
                    <h3 className="text-xl font-bold flex items-center gap-2 italic uppercase tracking-tighter">
                        <TestTubeIcon size={24} className="text-red-500" />
                        Experiment Registry
                    </h3>
                    <button
                        onClick={() => setShowCreate(true)}
                        className="flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-red-500/30 transition-all hover:scale-105"
                    >
                        <PlusIcon size={14} /> New Chaos Hunt
                    </button>
                </div>
                <div className="overflow-x-auto">
                    {loading ? (
                        <div className="py-16 text-center text-gray-500 text-sm">Loading experiments…</div>
                    ) : (
                        <table className="w-full text-sm text-left">
                            <thead className="text-[10px] font-black uppercase tracking-widest bg-black/20 dark:bg-white/5 text-gray-500">
                                <tr>
                                    <th className="px-8 py-5">Experiment</th>
                                    <th className="px-6 py-5">Type</th>
                                    <th className="px-6 py-5">Blast Radius</th>
                                    <th className="px-6 py-5 text-center">Execution State</th>
                                    <th className="px-6 py-5 text-right">Last Payload</th>
                                    <th className="px-8 py-5 text-right">Ops</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {experiments.map(exp => (
                                    <tr key={exp.id} className="hover:bg-white/5 transition-colors group">
                                        <td className="px-8 py-6">
                                            <div className="flex flex-col">
                                                <span className="font-black text-gray-800 dark:text-gray-100 uppercase tracking-tighter italic">{exp.name}</span>
                                                <span className="text-[10px] text-gray-400 uppercase font-bold tracking-widest mt-1">ID: {exp.id.slice(0, 8)}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-6 font-mono text-[10px] uppercase font-black text-red-500/80">{exp.type}</td>
                                        <td className="px-6 py-6">
                                            <code className="bg-white/5 px-2 py-1 rounded text-[10px] font-mono border border-white/5 text-gray-400">{exp.target}</code>
                                        </td>
                                        <td className="px-6 py-6 text-center">
                                            <span className={`inline-flex items-center gap-1.5 px-3 py-1 text-[10px] font-black rounded-full uppercase border ${STATUS_CLASSES[exp.status]}`}>
                                                {STATUS_ICONS[exp.status]} {exp.status}
                                            </span>
                                        </td>
                                        <td className="px-6 py-6 text-right font-mono text-[10px] text-gray-500">
                                            {new Date(exp.lastRun).toLocaleString()}
                                        </td>
                                        <td className="px-8 py-6 text-right">
                                            <button
                                                onClick={() => handleRun(exp.id)}
                                                disabled={runningId === exp.id || exp.status === 'Running'}
                                                title="Run experiment"
                                                className="inline-flex items-center gap-2 p-2 rounded-lg bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-500 transition-all border border-white/5 disabled:opacity-40 disabled:cursor-not-allowed"
                                            >
                                                {runningId === exp.id
                                                    ? <CogIcon size={16} className="animate-spin" />
                                                    : <ZapIcon size={16} />}
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                                {experiments.length === 0 && (
                                    <tr>
                                        <td colSpan={6} className="py-24 text-center">
                                            <BombIcon size={48} className="mx-auto text-gray-400 opacity-20 mb-4" />
                                            <p className="font-black text-gray-500 uppercase tracking-widest text-lg">No Active Experiments</p>
                                            <p className="text-xs text-gray-400 mt-1 uppercase font-bold">Safe harbor protocols engaged.</p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            {/* Create Experiment Modal */}
            {showCreate && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                    <div className="glass-premium rounded-3xl shadow-2xl border border-white/10 w-full max-w-md p-8">
                        <h3 className="text-xl font-black uppercase tracking-tighter italic mb-6 flex items-center gap-2">
                            <BombIcon size={20} className="text-red-500" /> New Chaos Experiment
                        </h3>
                        <form onSubmit={handleCreate} className="space-y-5">
                            <div>
                                <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2">Experiment Name</label>
                                <input
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-gray-200 focus:outline-none focus:border-red-500/50"
                                    placeholder="e.g. DB Failover Drill"
                                    value={form.name}
                                    onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2">Type</label>
                                <select
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-gray-200 focus:outline-none focus:border-red-500/50"
                                    value={form.type}
                                    onChange={e => setForm(f => ({ ...f, type: e.target.value as ChaosExperiment['type'] }))}
                                >
                                    {EXPERIMENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2">Target / Blast Radius</label>
                                <input
                                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-gray-200 focus:outline-none focus:border-red-500/50"
                                    placeholder="e.g. db-prod-01"
                                    value={form.target}
                                    onChange={e => setForm(f => ({ ...f, target: e.target.value }))}
                                    required
                                />
                            </div>
                            <div className="flex gap-3 pt-2">
                                <button
                                    type="submit"
                                    disabled={creating}
                                    className="flex-1 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all"
                                >
                                    {creating ? 'Creating…' : 'Deploy Experiment'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setShowCreate(false)}
                                    className="flex-1 bg-white/5 hover:bg-white/10 text-gray-400 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all"
                                >
                                    Cancel
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
