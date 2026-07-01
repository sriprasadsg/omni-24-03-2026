import { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';
import {
    Play, Activity, Cpu, CheckCircle, AlertCircle, Loader2,
    Database, Zap, ZapOff, RefreshCw, BarChart2, Brain,
} from 'lucide-react';

interface TrainingStatus {
    is_training: boolean;
    current_job: {
        model_name: string;
        start_time: string;
        end_time?: string;
        epochs: number;
        current_epoch: number;
        step: number;
        loss: number;
        status: string;
    } | null;
    history: Array<{ epoch: number; step: number; loss: number }>;
    model_info: {
        trained: boolean;
        base_model?: string;
        lora_r?: number;
        adapter_path?: string;
    };
    dataset_stats: {
        total: number;
        by_source: Record<string, number>;
        built_at: string | null;
        path: string;
    };
}

const ModelTrainingDashboard = () => {
    const [status, setStatus] = useState<TrainingStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [isStarting, setIsStarting] = useState(false);
    const [isBuilding, setIsBuilding] = useState(false);
    const [isActivating, setIsActivating] = useState(false);
    const [activeProvider, setActiveProvider] = useState<string | null>(null);
    const [toastMsg, setToastMsg] = useState<string | null>(null);

    const toast = (msg: string) => {
        setToastMsg(msg);
        setTimeout(() => setToastMsg(null), 3500);
    };

    const fetchStatus = async () => {
        try {
            const resp = await authFetch('/api/ai/train/status');
            if (resp.ok) {
                const data = await resp.json();
                setStatus(data);
            }
        } catch (err) {
            console.error('Failed to fetch training status', err);
        } finally {
            setLoading(false);
        }
    };

    const buildDataset = async () => {
        setIsBuilding(true);
        toast('Building dataset from MongoDB...');
        try {
            const resp = await authFetch('/api/ai/train/build-dataset', { method: 'POST' });
            const data = await resp.json();
            if (data.error) { toast(`Dataset error: ${data.error}`); return; }
            toast(`Dataset ready — ${data.total} samples from ${Object.keys(data.by_source || {}).length} sources`);
            await fetchStatus();
        } catch (err) {
            toast('Failed to build dataset');
        } finally {
            setIsBuilding(false);
        }
    };

    const startTraining = async () => {
        setIsStarting(true);
        try {
            const resp = await authFetch('/api/ai/train/start', { method: 'POST' });
            const data = await resp.json();
            if (data.error) { toast(`Training error: ${data.error}`); return; }
            toast('Fine-tuning started in background...');
            await fetchStatus();
        } catch (err) {
            toast('Failed to start training');
        } finally {
            setIsStarting(false);
        }
    };

    const activateModel = async (activate: boolean) => {
        setIsActivating(true);
        try {
            const endpoint = activate ? '/api/ai/train/activate' : '/api/ai/train/deactivate';
            const resp = await authFetch(endpoint, { method: 'POST' });
            const data = await resp.json();
            if (data.error) { toast(`Error: ${data.error}`); return; }
            setActiveProvider(data.active_provider ?? null);
            toast(activate
                ? `Omni-Local activated — provider: ${data.active_provider}`
                : `Omni-Local deactivated — using: ${data.active_provider}`);
        } catch (err) {
            toast('Failed to change model activation');
        } finally {
            setIsActivating(false);
        }
    };

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 4000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return (
        <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
            <Loader2 className="animate-spin w-4 h-4" /> Initializing AI Engine...
        </div>
    );

    const currentJob = status?.current_job;
    const isTraining = status?.is_training ?? false;
    const isCompleted = currentJob?.status === 'Completed';
    const isTrained = status?.model_info?.trained ?? false;
    const datasetTotal = status?.dataset_stats?.total ?? 0;
    const datasetBuiltAt = status?.dataset_stats?.built_at;
    const bySource = status?.dataset_stats?.by_source ?? {};
    const history = status?.history ?? [];
    const maxLoss = history.length > 0 ? Math.max(...history.map(h => h.loss), 0.01) : 1;

    return (
        <div className="space-y-5">
            {/* Toast */}
            {toastMsg && (
                <div className="fixed top-4 right-4 z-50 bg-slate-800 border border-slate-600 text-white text-sm px-4 py-2.5 rounded-lg shadow-xl flex items-center gap-2 animate-fade-in">
                    <Activity className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                    {toastMsg}
                </div>
            )}

            {/* Header card */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-40 h-40 bg-blue-500/10 blur-[120px] pointer-events-none group-hover:bg-blue-400/15 transition-all duration-700" />

                <div className="flex items-start justify-between mb-5">
                    <div>
                        <h3 className="text-lg font-bold text-white flex items-center gap-2">
                            <Brain className="text-blue-400 w-5 h-5" />
                            Omni-Local LLM
                        </h3>
                        <p className="text-slate-400 text-xs mt-0.5">
                            {status?.model_info?.base_model ?? 'TinyLlama-1.1B-Chat-v1.0'} · QLoRA (r={status?.model_info?.lora_r ?? 16}) · Offline fine-tuning
                        </p>
                    </div>

                    <div className="flex items-center gap-2">
                        {isTrained && (
                            <>
                                <button
                                    onClick={() => activateModel(true)}
                                    disabled={isActivating}
                                    title="Make Omni-Local the active provider"
                                    className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded-lg font-medium transition-all disabled:opacity-50"
                                >
                                    {isActivating ? <Loader2 className="animate-spin w-3 h-3" /> : <Zap className="w-3 h-3" />}
                                    Activate
                                </button>
                                <button
                                    onClick={() => activateModel(false)}
                                    disabled={isActivating}
                                    title="Fall back to external LLM"
                                    className="flex items-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs px-3 py-1.5 rounded-lg font-medium transition-all disabled:opacity-50"
                                >
                                    <ZapOff className="w-3 h-3" />
                                    Deactivate
                                </button>
                            </>
                        )}
                        {!isTraining && (
                            <button
                                onClick={startTraining}
                                disabled={isStarting}
                                className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-4 py-1.5 rounded-lg font-medium transition-all transform hover:scale-105 flex items-center gap-1.5 shadow-lg shadow-blue-900/40 disabled:opacity-50 text-sm"
                            >
                                {isStarting ? <Loader2 className="animate-spin w-4 h-4" /> : <Play className="w-3.5 h-3.5 fill-white" />}
                                {isTrained ? 'Re-train' : 'Fine-tune'}
                            </button>
                        )}
                    </div>
                </div>

                {/* Active provider badge */}
                {activeProvider && (
                    <div className="mb-4 flex items-center gap-2 text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5">
                        <CheckCircle className="w-3.5 h-3.5" />
                        Active provider: <span className="font-semibold">{activeProvider}</span>
                    </div>
                )}

                {/* Training progress */}
                {currentJob ? (
                    <div className="space-y-4">
                        <div className="grid grid-cols-3 gap-3">
                            {[
                                { label: 'EPOCH', value: `${currentJob.current_epoch}/${currentJob.epochs}`, color: 'text-white' },
                                { label: 'STEP',  value: String(currentJob.step),                             color: 'text-sky-400' },
                                { label: 'LOSS',  value: (currentJob.loss as number).toFixed(4),              color: 'text-amber-400' },
                            ].map(m => (
                                <div key={m.label} className="bg-slate-800/60 border border-slate-700/40 p-3 rounded-lg">
                                    <span className="text-slate-500 text-[10px] font-mono block mb-1">{m.label}</span>
                                    <span className={`text-xl font-mono font-bold ${m.color}`}>{m.value}</span>
                                </div>
                            ))}
                        </div>

                        <div>
                            <div className="flex justify-between text-xs mb-1.5">
                                <span className={`flex items-center gap-1 font-medium ${isTraining ? 'text-blue-400' : 'text-emerald-400'}`}>
                                    {isTraining && <Activity className="w-3 h-3 animate-pulse" />}
                                    {currentJob.status}
                                </span>
                                <span className="text-slate-500">
                                    {currentJob.epochs > 0 ? Math.round((currentJob.current_epoch / currentJob.epochs) * 100) : 0}%
                                </span>
                            </div>
                            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-blue-500 to-indigo-400 transition-all duration-1000 ease-out rounded-full shadow-[0_0_12px_rgba(99,102,241,0.6)]"
                                    style={{ width: `${currentJob.epochs > 0 ? (currentJob.current_epoch / currentJob.epochs) * 100 : 0}%` }}
                                />
                            </div>
                        </div>

                        {/* Loss chart */}
                        {history.length > 0 && (
                            <div>
                                <p className="text-slate-500 text-[10px] font-mono mb-2 uppercase tracking-widest flex items-center gap-1">
                                    <BarChart2 className="w-3 h-3" /> Training Loss
                                </p>
                                <div className="h-20 flex items-end gap-0.5 border-b border-slate-800">
                                    {history.map((h, i) => (
                                        <div
                                            key={i}
                                            className="flex-1 bg-amber-500/30 hover:bg-amber-400/60 transition-all rounded-t-sm cursor-default"
                                            style={{ height: `${(h.loss / maxLoss) * 100}%` }}
                                            title={`Step ${h.step}: Loss=${h.loss.toFixed(4)}`}
                                        />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="bg-slate-800/30 border border-dashed border-slate-700 p-8 text-center rounded-xl">
                        <AlertCircle className="text-slate-600 w-8 h-8 mx-auto mb-3" />
                        <h4 className="text-slate-300 font-medium">Model Not Trained</h4>
                        <p className="text-slate-500 text-sm max-w-xs mx-auto mt-1.5">
                            Build the dataset then click Fine-tune to start QLoRA training on your live data.
                        </p>
                    </div>
                )}

                {isCompleted && (
                    <div className="mt-4 flex items-center gap-3 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
                        <CheckCircle className="text-emerald-400 w-5 h-5 shrink-0" />
                        <div>
                            <p className="text-emerald-200 text-sm font-bold">Fine-tuning Complete!</p>
                            <p className="text-emerald-500/70 text-xs">
                                Click Activate above to use Omni-Local as the primary AI provider.
                            </p>
                        </div>
                    </div>
                )}
            </div>

            {/* Dataset card */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                    <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                        <Database className="w-4 h-4 text-indigo-400" />
                        Training Dataset
                    </h4>
                    <button
                        onClick={buildDataset}
                        disabled={isBuilding}
                        className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3 py-1.5 rounded-lg font-medium transition-all disabled:opacity-50"
                    >
                        {isBuilding
                            ? <Loader2 className="animate-spin w-3 h-3" />
                            : <RefreshCw className="w-3 h-3" />}
                        {datasetTotal > 0 ? 'Rebuild' : 'Build Dataset'}
                    </button>
                </div>

                {datasetTotal > 0 ? (
                    <>
                        <div className="grid grid-cols-2 gap-3 mb-4">
                            <div className="bg-slate-800/50 rounded-lg p-3">
                                <p className="text-slate-500 text-[10px] font-mono mb-1">TOTAL SAMPLES</p>
                                <p className="text-2xl font-bold font-mono text-white">{datasetTotal.toLocaleString()}</p>
                            </div>
                            <div className="bg-slate-800/50 rounded-lg p-3">
                                <p className="text-slate-500 text-[10px] font-mono mb-1">LAST BUILT</p>
                                <p className="text-sm font-medium text-slate-300">
                                    {datasetBuiltAt ? new Date(datasetBuiltAt).toLocaleString() : '—'}
                                </p>
                            </div>
                        </div>

                        <div className="space-y-1.5">
                            {Object.entries(bySource).map(([src, count]) => (
                                <div key={src} className="flex items-center gap-2">
                                    <span className="text-slate-400 text-xs w-36 font-mono capitalize">{src.replace(/_/g, ' ')}</span>
                                    <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-indigo-500/60 rounded-full"
                                            style={{ width: `${Math.min((count / Math.max(datasetTotal, 1)) * 100 * 5, 100)}%` }}
                                        />
                                    </div>
                                    <span className="text-slate-500 text-xs w-10 text-right">{count}</span>
                                </div>
                            ))}
                        </div>
                    </>
                ) : (
                    <p className="text-slate-500 text-sm text-center py-4">
                        No dataset yet. Click Build Dataset to pull training data from your MongoDB collections.
                    </p>
                )}
            </div>

            {/* Model info card */}
            {isTrained && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h4 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
                        <Cpu className="w-4 h-4 text-blue-400" />
                        Saved Adapter
                    </h4>
                    <div className="text-xs text-slate-400 space-y-1 font-mono">
                        <div><span className="text-slate-500">Base model:</span> {status?.model_info?.base_model}</div>
                        <div><span className="text-slate-500">LoRA rank:</span> r={status?.model_info?.lora_r}</div>
                        <div><span className="text-slate-500">Path:</span> {status?.model_info?.adapter_path}</div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ModelTrainingDashboard;
