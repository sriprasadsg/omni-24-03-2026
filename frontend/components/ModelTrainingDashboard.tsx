import React, { useState, useEffect } from 'react';
import { Play, Activity, Cpu, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

const ModelTrainingDashboard = () => {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isStarting, setIsStarting] = useState(false);

    const fetchStatus = async () => {
        try {
            const token = localStorage.getItem('token');
            const resp = await fetch('http://localhost:5000/api/ai/train/status', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await resp.json();
            setStatus(data);
            setLoading(false);
        } catch (err) {
            console.error("Failed to fetch training status", err);
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

    if (loading) return <div className="p-4 text-center">Initializing AI Engine...</div>;

    const currentJob = status?.current_job;
    const isTraining = status?.is_training;

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl relative overflow-hidden group">
            {/* Background Glow */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 blur-[100px] pointer-events-none group-hover:bg-blue-400/20 transition-all duration-500"></div>
            
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h3 className="text-xl font-bold text-white flex items-center gap-2">
                        <Cpu className="text-blue-400 w-5 h-5" />
                        Omni-LLM Scratch Training
                    </h3>
                    <p className="text-slate-400 text-sm">Real-time Model Evolution Dashboard</p>
                </div>
                {!isTraining && currentJob?.status !== "Completed" && (
                    <button 
                        onClick={startTraining}
                        disabled={isStarting}
                        className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-medium transition-all transform hover:scale-105 flex items-center gap-2 shadow-lg shadow-blue-900/40 disabled:opacity-50"
                    >
                        {isStarting ? <Loader2 className="animate-spin w-4 h-4" /> : <Play className="w-4 h-4" />}
                        Initiate Training Process
                    </button>
                )}
            </div>

            {currentJob ? (
                <div className="space-y-6">
                    {/* Status Overview */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-slate-800/50 border border-slate-700/50 p-4 rounded-lg">
                            <span className="text-slate-400 text-xs block mb-1">CURRENT EPOCH</span>
                            <span className="text-2xl font-mono text-white tracking-widest">
                                {currentJob.current_epoch} <span className="text-slate-500 text-sm">/ {currentJob.epochs}</span>
                            </span>
                        </div>
                        <div className="bg-slate-800/50 border border-slate-700/50 p-4 rounded-lg">
                            <span className="text-slate-400 text-xs block mb-1">LOSS METRIC</span>
                            <span className="text-2xl font-mono text-amber-400 leading-none">
                                {currentJob.loss.toFixed(4)}
                            </span>
                        </div>
                        <div className="bg-slate-800/50 border border-slate-700/50 p-4 rounded-lg">
                            <span className="text-slate-400 text-xs block mb-1">ACCURACY</span>
                            <span className="text-2xl font-mono text-emerald-400">
                                {(currentJob.accuracy * 100).toFixed(1)}%
                            </span>
                        </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="space-y-2">
                        <div className="flex justify-between text-xs font-medium uppercase tracking-tighter">
                            <span className={isTraining ? "text-blue-400" : "text-emerald-400 flex items-center gap-1"}>
                                {isTraining && <Activity className="w-3 h-3 animate-pulse inline mr-1" />}
                                {currentJob.status}
                            </span>
                            <span className="text-slate-500">{Math.round((currentJob.current_epoch / currentJob.epochs) * 100)}%</span>
                        </div>
                        <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                            <div 
                                className="h-full bg-blue-500 transition-all duration-1000 ease-out shadow-[0_0_15px_rgba(59,130,246,0.5)]"
                                style={{ width: `${(currentJob.current_epoch / currentJob.epochs) * 100}%` }}
                            ></div>
                        </div>
                    </div>

                    {/* History Graph Silhouette (Simplest Mock) */}
                    <div className="h-32 flex items-end gap-1 px-1 border-b border-slate-800">
                        {status.history?.map((h, i) => (
                            <div 
                                key={i}
                                className="flex-1 bg-blue-500/30 hover:bg-blue-400 transition-all group"
                                style={{ height: `${h.accuracy * 100}%` }}
                                title={`Epoch ${h.epoch}: ${h.accuracy.toFixed(3)}`}
                            >
                                <div className="opacity-0 group-hover:opacity-100 absolute bottom-full mb-2 p-1 bg-slate-800 text-[10px] rounded border border-slate-700 pointer-events-none whitespace-nowrap">
                                    L: {h.loss.toFixed(2)} | A: {h.accuracy.toFixed(2)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ) : (
                <div className="bg-slate-800/30 border border-dashed border-slate-700 p-12 text-center rounded-xl">
                    <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-4">
                        <AlertCircle className="text-slate-600 w-8 h-8" />
                    </div>
                    <h4 className="text-slate-300 font-medium text-lg">Model Inactive</h4>
                    <p className="text-slate-500 text-sm max-w-xs mx-auto mt-2">
                        Initialize the training pipeline to build your custom Transformer model from scratch.
                    </p>
                </div>
            )}
            
            {/* Model Ready Alert */}
            {currentJob?.status === "Completed" && (
                <div className="mt-6 flex items-center gap-4 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
                    <CheckCircle className="text-emerald-500 w-6 h-6 flex-shrink-0" />
                    <div className="flex-1">
                        <p className="text-emerald-200 text-sm font-semibold">Omni-LLM Trained Successfully</p>
                        <p className="text-emerald-500/70 text-xs">Model is now persistent and selectable for Agentic Core.</p>
                    </div>
                    <button className="text-emerald-400 font-bold text-xs uppercase hover:underline">Select Now</button>
                </div>
            )}
        </div>
    );
};

export default ModelTrainingDashboard;
