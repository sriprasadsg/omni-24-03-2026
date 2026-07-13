import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import * as api from '../services/apiService';
import { Risk } from '../types';

interface RiskFairModalProps {
    isOpen: boolean;
    risk: Risk | null;
    onClose: () => void;
    onComplete: () => void;
}

const formatCurrency = (value: number) => {
    if (value >= 1_000_000) {
        return `$${(value / 1_000_000).toFixed(1)}M`;
    }
    if (value >= 1_000) {
        return `$${(value / 1_000).toFixed(0)}K`;
    }
    return `$${value.toFixed(0)}`;
};

export const RiskFairModal: React.FC<RiskFairModalProps> = ({ isOpen, risk, onClose, onComplete }) => {
    const [lefMin, setLefMin] = useState(1);
    const [lefLikely, setLefLikely] = useState(2);
    const [lefMax, setLefMax] = useState(3);
    const [lmMin, setLmMin] = useState(1000);
    const [lmLikely, setLmLikely] = useState(10000);
    const [lmMax, setLmMax] = useState(100000);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<Risk['fair_results'] | null>(null);

    useEffect(() => {
        if (risk?.fair_inputs) {
            setLefMin(risk.fair_inputs.lef_min);
            setLefLikely(risk.fair_inputs.lef_likely);
            setLefMax(risk.fair_inputs.lef_max);
            setLmMin(risk.fair_inputs.lm_min);
            setLmLikely(risk.fair_inputs.lm_likely);
            setLmMax(risk.fair_inputs.lm_max);
        } else {
            // Reset to defaults if no fair_inputs
            setLefMin(1);
            setLefLikely(2);
            setLefMax(3);
            setLmMin(1000);
            setLmLikely(10000);
            setLmMax(100000);
        }
        setResults(risk?.fair_results || null);
        setError(null);
    }, [risk]);

    if (!isOpen || !risk) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setRunning(true);
        setError(null);
        setResults(null);

        const inputs = {
            lef_min: lefMin,
            lef_likely: lefLikely,
            lef_max: lefMax,
            lm_min: lmMin,
            lm_likely: lmLikely,
            lm_max: lmMax,
            iterations: 10000 // Default iterations
        };

        try {
            const updatedRisk = await api.runFairSimulation(risk.id, inputs);
            setResults(updatedRisk.fair_results || null);
            onComplete(); // Trigger refresh in parent
        } catch (err: any) {
            setError(err.message || "Failed to run FAIR simulation. Please check inputs.");
            console.error("FAIR simulation error:", err);
        } finally {
            setRunning(false);
        }
    };

    const isLefValid = lefMin <= lefLikely && lefLikely <= lefMax;
    const isLmValid = lmMin <= lmLikely && lmLikely <= lmMax;
    const isFormValid = isLefValid && isLmValid;

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-2xl overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                    <h3 className="font-semibold text-lg text-gray-900 dark:text-white">
                        Quantify Risk: {risk.title}
                    </h3>
                    <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-6">
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Loss Event Frequency (LEF) per year
                            </label>
                            <div className="grid grid-cols-3 gap-4">
                                <div>
                                    <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Min</span>
                                    <input
                                        type="number"
                                        min="0"
                                        value={lefMin}
                                        onChange={e => setLefMin(Number(e.target.value))}
                                        className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                    />
                                </div>
                                <div>
                                    <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Likely</span>
                                    <input
                                        type="number"
                                        min="0"
                                        value={lefLikely}
                                        onChange={e => setLefLikely(Number(e.target.value))}
                                        className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                    />
                                </div>
                                <div>
                                    <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Max</span>
                                    <input
                                        type="number"
                                        min="0"
                                        value={lefMax}
                                        onChange={e => setLefMax(Number(e.target.value))}
                                        className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                    />
                                </div>
                            </div>
                            {!isLefValid && (
                                <p className="mt-2 text-xs text-red-500">Min &le; Likely &le; Max must be true for LEF.</p>
                            )}
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Loss Magnitude (LM) in USD
                            </label>
                            <div className="grid grid-cols-3 gap-4">
                                <div>
                                    <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Min</span>
                                    <input
                                        type="number"
                                        min="0"
                                        step="100"
                                        value={lmMin}
                                        onChange={e => setLmMin(Number(e.target.value))}
                                        className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                    />
                                </div>
                                <div>
                                    <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Likely</span>
                                    <input
                                        type="number"
                                        min="0"
                                        step="100"
                                        value={lmLikely}
                                        onChange={e => setLmLikely(Number(e.target.value))}
                                        className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                    />
                                </div>
                                <div>
                                    <span className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Max</span>
                                    <input
                                        type="number"
                                        min="0"
                                        step="100"
                                        value={lmMax}
                                        onChange={e => setLmMax(Number(e.target.value))}
                                        className="w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                    />
                                </div>
                            </div>
                            {!isLmValid && (
                                <p className="mt-2 text-xs text-red-500">Min &le; Likely &le; Max must be true for LM.</p>
                            )}
                        </div>
                    </div>

                    {error && (
                        <div className="bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
                            {error}
                        </div>
                    )}

                    {results && (
                        <div className="space-y-4 bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                            <h4 className="font-semibold text-gray-900 dark:text-white">Simulation Results (Annualized Loss)</h4>
                            <div className="grid grid-cols-2 gap-4 text-sm">
                                <div><span className="text-gray-500 dark:text-gray-400">Mean:</span> <span className="font-medium text-gray-900 dark:text-white">{formatCurrency(results.mean)}</span></div>
                                <div><span className="text-gray-500 dark:text-gray-400">10th Percentile (P10):</span> <span className="font-medium text-gray-900 dark:text-white">{formatCurrency(results.p10)}</span></div>
                                <div><span className="text-gray-500 dark:text-gray-400">50th Percentile (P50):</span> <span className="font-medium text-gray-900 dark:text-white">{formatCurrency(results.p50)}</span></div>
                                <div><span className="text-gray-500 dark:text-gray-400">90th Percentile (P90):</span> <span className="font-medium text-gray-900 dark:text-white">{formatCurrency(results.p90)}</span></div>
                            </div>
                            <div className="mt-4">
                                <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Loss Exceedance Curve (Top Risks)</h5>
                                <div className="flex flex-wrap gap-2">
                                    {results.exceedance_curve.filter(ec => ec.probability > 0).slice(0, 5).map((point, index) => (
                                        <span key={index} className="bg-blue-100 text-blue-800 text-xs font-medium px-2 py-0.5 rounded dark:bg-blue-900/30 dark:text-blue-400">
                                            {formatCurrency(point.loss)} ({ (point.probability * 100).toFixed(0) }%)
                                        </span>
                                    ))}
                                    {results.exceedance_curve.filter(ec => ec.probability > 0).length === 0 && (
                                        <span className="text-gray-500 dark:text-gray-400 text-sm">No exceedance data.</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="flex justify-end gap-3 pt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={running || !isFormValid}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
                        >
                            {running ? 'Running...' : 'Run Simulation'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
