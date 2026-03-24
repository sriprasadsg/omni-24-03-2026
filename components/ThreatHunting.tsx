import React, { useState } from 'react';
import { Search, Terminal, AlertTriangle, CheckCircle, Play } from 'lucide-react';

interface ThreatHuntResult {
    success: boolean;
    data: any[];
    generated_pipeline: any[];
    error?: string;
}

export function ThreatHunting() {
    const [query, setQuery] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [result, setResult] = useState<ThreatHuntResult | null>(null);

    const handleHunt = async () => {
        if (!query.trim()) return;

        setIsLoading(true);
        setResult(null);

        try {
            const response = await fetch('/api/ai/threat-hunt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });

            const data = await response.json();
            setResult(data);
        } catch (err) {
            setResult({
                success: false,
                data: [],
                generated_pipeline: [],
                error: 'Failed to connect to backend'
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            <div className="flex flex-col gap-2">
                <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white">AI Threat Hunting</h1>
                <p className="text-gray-500 dark:text-gray-400">
                    Use natural language to query system metrics, logs, and security events across your fleet.
                </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg border-2 border-primary-500/20 shadow-sm">
                <div className="p-6">
                    <div className="flex gap-4">
                        <div className="relative flex-1">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Search className="h-5 w-5 text-gray-400" />
                            </div>
                            <input
                                className="block w-full pl-10 h-12 text-lg rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                placeholder="e.g., Show me hosts with CPU > 80% and failed logins in the last hour..."
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleHunt()}
                            />
                        </div>
                        <button
                            onClick={handleHunt}
                            disabled={isLoading}
                            className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-blue-400"
                        >
                            {isLoading ? (
                                <span className="animate-spin mr-2">⏳</span>
                            ) : (
                                <Play className="mr-2 h-5 w-5" />
                            )}
                            Run Hunt
                        </button>
                    </div>
                </div>
            </div>

            {result && (
                <div className="grid gap-6 md:grid-cols-3">
                    {/* Results Column */}
                    <div className="md:col-span-2 space-y-4">
                        <h2 className="text-xl font-semibold flex items-center text-gray-900 dark:text-white">
                            <CheckCircle className="mr-2 h-5 w-5 text-green-500" />
                            Hunt Results ({result.data.length})
                        </h2>

                        {result.error ? (
                            <div className="bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded-lg p-6 text-red-600 dark:text-red-400">
                                <div className="flex items-center mb-2">
                                    <AlertTriangle className="h-6 w-6 mr-2" />
                                    <span className="font-semibold">Error</span>
                                </div>
                                {result.error}
                            </div>
                        ) : (
                            <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                                <div className="max-h-[500px] overflow-auto rounded-md">
                                    <table className="w-full text-sm text-left">
                                        <thead className="bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 sticky top-0">
                                            <tr>
                                                {result.data.length > 0 && Object.keys(result.data[0]).map(key => (
                                                    <th key={key} className="p-3 font-medium">{key}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100">
                                            {result.data.map((row, i) => (
                                                <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                                                    {Object.values(row).map((val: any, j) => (
                                                        <td key={j} className="p-3 whitespace-nowrap">
                                                            {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                                        </td>
                                                    ))}
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                    {result.data.length === 0 && (
                                        <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                                            No matching records found.
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Technical Details Column */}
                    <div className="md:col-span-1 space-y-4">
                        <h2 className="text-xl font-semibold flex items-center text-gray-900 dark:text-white">
                            <Terminal className="mr-2 h-5 w-5 text-blue-500" />
                            Generated Logic
                        </h2>
                        <div className="bg-slate-950 text-slate-50 border border-slate-800 rounded-lg shadow overflow-hidden">
                            <div className="p-4 font-mono text-xs overflow-auto max-h-[500px]">
                                <pre>{JSON.stringify(result.generated_pipeline, null, 2)}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
