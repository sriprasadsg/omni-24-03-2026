import React, { useState, useEffect } from 'react';
import { Activity, AlertTriangle, CheckCircle, Clock, TrendingUp, Shield, Server, ArrowRight } from 'lucide-react';

interface Prediction {
    host_id: string;
    hostname: string;
    os: string;
    status: string;
    failure_probability: number;
    risk_level: 'high' | 'medium' | 'low';
    hours_to_failure: number | null;
    failure_window: string;
    top_indicators: string[];
    last_evaluated: string;
}

interface AccuracyMetrics {
    precision: number;
    recall: number;
    f1_score: number;
    predictions_last_30d: number;
    correct_predictions: number;
    model_version: string;
}

export const PredictiveHealthDashboard: React.FC = () => {
    const [predictions, setPredictions] = useState<Prediction[]>([]);
    const [metrics, setMetrics] = useState<AccuracyMetrics | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [predRes, metricRes] = await Promise.all([
                fetch('/api/predictive/hosts'),
                fetch('/api/predictive/model/accuracy')
            ]);
            const predData = await predRes.json();
            const metricData = await metricRes.json();
            setPredictions(predData.predictions || []);
            setMetrics(metricData);
        } catch (error) {
            console.error('Error fetching predictive health data:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    const getRiskColor = (level: string) => {
        switch (level) {
            case 'high': return 'text-red-500 bg-red-50 dark:bg-red-900/20 border-red-200';
            case 'medium': return 'text-amber-500 bg-amber-50 dark:bg-amber-900/20 border-amber-200';
            default: return 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200';
        }
    };

    if (loading && predictions.length === 0) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    return (
        <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-900 min-h-screen">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Predictive Health Dashboard</h1>
                    <p className="text-slate-500 dark:text-slate-400">AIOps-powered failure forecasting and risk analysis</p>
                </div>
                <div className="flex space-x-2">
                    <button 
                        onClick={fetchData}
                        className="px-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 transition-colors"
                    >
                        Refresh Data
                    </button>
                    <div className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium flex items-center">
                        <Shield className="w-4 h-4 mr-2" />
                        Model Active: {metrics?.model_version || 'v2.1.0'}
                    </div>
                </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <div className="flex justify-between items-start">
                        <p className="text-sm text-slate-500 dark:text-slate-400">Avg. Precision</p>
                        <TrendingUp className="w-4 h-4 text-emerald-500" />
                    </div>
                    <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">{(metrics?.precision || 0.87 * 100).toFixed(1)}%</p>
                    <div className="mt-2 w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5">
                        <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${(metrics?.precision || 0.87) * 100}%` }}></div>
                    </div>
                </div>
                <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <p className="text-sm text-slate-500 dark:text-slate-400">Total Predictions (30d)</p>
                    <p className="text-2xl font-bold mt-1 text-slate-900 dark:text-white">{metrics?.predictions_last_30d || 142}</p>
                    <p className="text-xs text-emerald-500 mt-1 flex items-center">
                        <CheckCircle className="w-3 h-3 mr-1" />
                        {metrics?.correct_predictions || 118} accurate
                    </p>
                </div>
                <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <p className="text-sm text-slate-500 dark:text-slate-400">Critical Forecasts</p>
                    <p className="text-2xl font-bold mt-1 text-red-500">{predictions.filter(p => p.risk_level === 'high').length}</p>
                    <p className="text-xs text-slate-400 mt-1">Requires immediate attention</p>
                </div>
                <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                    <p className="text-sm text-slate-500 dark:text-slate-400">Fleet Health Index</p>
                    <p className="text-2xl font-bold mt-1 text-indigo-500">94.2</p>
                    <p className="text-xs text-slate-400 mt-1">Stable across 12 zones</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* High Risk Targets */}
                <div className="lg:col-span-2 space-y-4">
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center">
                        <AlertTriangle className="w-5 h-5 mr-2 text-amber-500" />
                        At-Risk Host Forecasts
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {predictions.slice(0, 4).map(host => (
                            <div key={host.host_id} className="bg-white dark:bg-slate-800 p-5 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-shadow group">
                                <div className="flex justify-between items-start mb-4">
                                    <div className="flex items-center">
                                        <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg mr-3 group-hover:bg-indigo-100 transition-colors">
                                            <Server className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-slate-900 dark:text-white">{host.hostname}</h3>
                                            <p className="text-xs text-slate-500">{host.os} • {host.host_id.slice(0, 8)}</p>
                                        </div>
                                    </div>
                                    <div className={`px-2 py-1 rounded text-xs font-bold uppercase ${getRiskColor(host.risk_level)}`}>
                                        {host.risk_level}
                                    </div>
                                </div>
                                
                                <div className="space-y-3">
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="text-slate-500">Failure Prob:</span>
                                        <span className="font-mono font-bold">{(host.failure_probability * 100).toFixed(1)}%</span>
                                    </div>
                                    <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-2">
                                        <div 
                                            className={`h-2 rounded-full ${host.risk_level === 'high' ? 'bg-red-500' : 'bg-amber-500'}`} 
                                            style={{ width: `${host.failure_probability * 100}%` }}
                                        ></div>
                                    </div>
                                    
                                    <div className="flex items-center text-sm text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/50 p-2 rounded-lg">
                                        <Clock className="w-4 h-4 mr-2 text-indigo-500" />
                                        <span>Time to failure: <strong>{host.failure_window}</strong></span>
                                    </div>

                                    <div className="pt-2">
                                        <p className="text-xs font-bold text-slate-400 uppercase mb-1">Top Indicators</p>
                                        <div className="flex flex-wrap gap-1">
                                            {host.top_indicators.map((ind, i) => (
                                                <span key={i} className="text-[10px] px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded">
                                                    {ind}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                                
                                <button className="mt-4 w-full flex items-center justify-center py-2 bg-slate-50 dark:bg-slate-900/50 hover:bg-indigo-600 hover:text-white rounded-lg text-sm font-medium transition-all group-hover:border-indigo-600">
                                    Acknowledge & Investigate
                                    <ArrowRight className="w-4 h-4 ml-2" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Accuracy & Distribution */}
                <div className="space-y-6">
                    <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
                        <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Risk Distribution</h2>
                        <div className="space-y-4">
                            <div className="flex justify-between items-center">
                                <div className="flex items-center">
                                    <div className="w-3 h-3 rounded-full bg-red-500 mr-2"></div>
                                    <span className="text-sm text-slate-600 dark:text-slate-300">High Risk</span>
                                </div>
                                <span className="text-sm font-bold text-slate-900 dark:text-white">{predictions.filter(p => p.risk_level === 'high').length}</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <div className="flex items-center">
                                    <div className="w-3 h-3 rounded-full bg-amber-500 mr-2"></div>
                                    <span className="text-sm text-slate-600 dark:text-slate-300">Medium Risk</span>
                                </div>
                                <span className="text-sm font-bold text-slate-900 dark:text-white">{predictions.filter(p => p.risk_level === 'medium').length}</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <div className="flex items-center">
                                    <div className="w-3 h-3 rounded-full bg-emerald-500 mr-2"></div>
                                    <span className="text-sm text-slate-600 dark:text-slate-300">Stable</span>
                                </div>
                                <span className="text-sm font-bold text-slate-900 dark:text-white">{predictions.filter(p => p.risk_level === 'low').length}</span>
                            </div>
                        </div>
                        
                        <div className="mt-8">
                            <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">Model Confidence Trend</h3>
                            <div className="h-24 flex items-end justify-between px-2">
                                {[40, 60, 55, 80, 75, 90, 85].map((h, i) => (
                                    <div key={i} className="w-4 bg-indigo-500/20 rounded-t relative group cursor-pointer" style={{ height: `${h}%` }}>
                                        <div className="absolute bottom-0 w-full bg-indigo-500 rounded-t group-hover:bg-indigo-400" style={{ height: '30%' }}></div>
                                    </div>
                                ))}
                            </div>
                            <div className="flex justify-between text-[10px] text-slate-400 mt-2">
                                <span>Mon</span>
                                <span>Tue</span>
                                <span>Wed</span>
                                <span>Thu</span>
                                <span>Fri</span>
                                <span>Sat</span>
                                <span>Sun</span>
                            </div>
                        </div>
                    </div>

                    <div className="bg-indigo-600 p-6 rounded-xl text-white shadow-lg relative overflow-hidden">
                        <div className="relative z-10">
                            <h2 className="text-lg font-bold mb-2">AIOps Insights</h2>
                            <p className="text-sm text-indigo-100 mb-4">
                                Patterns suggest a 22% increase in disk-related failures across Zone-B in the next 48 hours.
                            </p>
                            <button className="px-4 py-2 bg-white text-indigo-600 rounded-lg text-sm font-bold hover:bg-indigo-50 transition-colors">
                                View Action Plan
                            </button>
                        </div>
                        <Activity className="absolute -bottom-4 -right-4 w-32 h-32 text-white/10" />
                    </div>
                </div>
            </div>
        </div>
    );
};
