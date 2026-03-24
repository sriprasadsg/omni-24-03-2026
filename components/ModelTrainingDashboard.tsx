import React, { useState, useEffect } from 'react';
import { Play, Activity, Cpu, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

const ModelTrainingDashboard = () => {
    const [status, setStatus] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [isStarting, setIsStarting] = useState(false);

    const fetchStatus = async () => {
        try {
            const token = localStorage.getItem('token');
            const resp = await fetch('http://localhost:5000/api/ai/train/status', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (resp.ok) {
                const data = await resp.json();
                setStatus(data);
            }
            setLoading(false);
        } catch (err) {
            console.error("Failed to fetch training status", err);
            setLoading(false);
        }
    };

    const startTraining = async () => {
        setIsStarting(true);
        try {
            const token = localStorage.getItem('token');
            await fetch('http://localhost:5000/api/ai/train/start', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            await fetchStatus();
        } catch (err) {
            console.error("Failed to start training", err);
        } finally {
            setIsStarting(false);
        }
    };

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 3000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return (
        <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
            <Loader2 className="animate-spin w-4 h-4" /> Initializing AI Engine...
        </div>
    );

    const currentJob = status?.current_job;
    const isTraining = status?.is_training;
    const isCompleted = currentJob?.status === "Completed";

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl relative overflow-hidden group">
            {/* Background glow effect */}
            <div className="absolute top-0 right-0 w-40 h-40 bg-blue-500/10 blur-[120px] pointer-events-none group-hover:bg-blue-400/15 transition-all duration-700"></div>
            
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <Cpu className="text-blue-400 w-5 h-5" />
                        Omni-LLM: Build From Scratch
                    </h3>
                    <p className="text-slate-400 text-xs mt-0.5">Transformer Architecture · Offline-only · Llama3 Replica</p>
                </div>
                {!isTraining && !isCompleted && (
                    <button
                        onClick={startTraining}
                        disabled={isStarting}
                        className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-5 py-2 rounded-lg font-medium transition-all transform hover:scale-105 flex items-center gap-2 shadow-lg shadow-blue-900/40 disabled:opacity-50 text-sm"
                    >
                        {isStarting ? <Loader2 className="animate-spin w-4 h-4" /> : <Play className="w-4 h-4 fill-white" />}
                        Begin Training
                    </button>
                )}
            </div>

            {currentJob ? (
                <div className="space-y-5">
                    {/* Metrics Grid */}
                    <div className="grid grid-cols-3 gap-3">
                        {[
                            { label: "EPOCH", value: `${currentJob.current_epoch}/${currentJob.epochs}`, color: "text-white" },
                            { label: "LOSS", value: (currentJob.loss as number).toFixed(4), color: "text-amber-400" },
                            { label: "ACCURACY", value: `${((currentJob.accuracy as number) * 100).toFixed(1)}%`, color: "text-emerald-400" },
                        ].map((m) => (
                            <div key={m.label} className="bg-slate-800/60 border border-slate-700/40 p-3 rounded-lg">
                                <span className="text-slate-500 text-[10px] font-mono block mb-1">{m.label}</span>
                                <span className={`text-xl font-mono font-bold ${m.color}`}>{m.value}</span>
                            </div>
                        ))}
                    </div>

                    {/* Progress Bar */}
                    <div>
                        <div className="flex justify-between text-xs mb-1.5">
                            <span className={`flex items-center gap-1 font-medium ${isTraining ? 'text-blue-400' : 'text-emerald-400'}`}>
                                {isTraining && <Activity className="w-3 h-3 animate-pulse" />}
                                {currentJob.status}
                            </span>
                            <span className="text-slate-500">{Math.round(((currentJob.current_epoch as number) / (currentJob.epochs as number)) * 100)}%</span>
                        </div>
                        <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-gradient-to-r from-blue-500 to-indigo-400 transition-all duration-1000 ease-out rounded-full shadow-[0_0_12px_rgba(99,102,241,0.6)]"
                                style={{ width: `${((currentJob.current_epoch as number) / (currentJob.epochs as number)) * 100}%` }}
                            />
                        </div>
                    </div>

                    {/* History Graph */}
                    {status.history && status.history.length > 0 && (
                        <div>
                            <p className="text-slate-500 text-[10px] font-mono mb-2 uppercase tracking-widest">Accuracy History</p>
                            <div className="h-20 flex items-end gap-0.5 border-b border-slate-800">
                                {status.history.map((h: any, i: number) => (
                                    <div
                                        key={i}
                                        className="flex-1 bg-indigo-500/30 hover:bg-indigo-400/60 transition-all rounded-t-sm cursor-default"
                                        style={{ height: `${(h.accuracy as number) * 100}%` }}
                                        title={`Ep ${h.epoch}: Loss=${(h.loss as number).toFixed(3)}, Acc=${(h.accuracy as number).toFixed(3)}`}
                                    />
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            ) : (
                <div className="bg-slate-800/30 border border-dashed border-slate-700 p-10 text-center rounded-xl">
                    <AlertCircle className="text-slate-600 w-10 h-10 mx-auto mb-3" />
                    <h4 className="text-slate-300 font-medium">Model Not Initialized</h4>
                    <p className="text-slate-500 text-sm max-w-xs mx-auto mt-1.5">
                        Click 'Begin Training' to build your custom Transformer LLM from scratch. All training is 100% offline.
                    </p>
                </div>
            )}

            {/* Completed state - model selection prompt */}
            {isCompleted && (
                <div className="mt-5 flex items-center gap-3 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
                    <CheckCircle className="text-emerald-400 w-6 h-6 flex-shrink-0" />
                    <div className="flex-1">
                        <p className="text-emerald-200 text-sm font-bold">Omni-LLM Training Complete!</p>
                        <p className="text-emerald-500/70 text-xs">Select "Omni-LLM-Scratch" as your provider in LLM Settings to activate it.</p>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ModelTrainingDashboard;
