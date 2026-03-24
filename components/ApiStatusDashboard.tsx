import React, { useState, useEffect } from 'react';
import { fetchSystemRoutes, remediateRoute } from '../services/apiService';
import { CheckCircle, XCircle, Activity, Play, AlertTriangle, RefreshCw } from 'lucide-react';

interface ApiRoute {
    path: string;
    name: string;
    methods: string[];
    status: 'Active' | 'Inactive' | 'Error';
}

export const ApiStatusDashboard: React.FC = () => {
    const [routes, setRoutes] = useState<ApiRoute[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedRoute, setSelectedRoute] = useState<ApiRoute | null>(null);
    const [remediationResult, setRemediationResult] = useState<any>(null);
    const [fixing, setFixing] = useState(false);

    const loadRoutes = async () => {
        setLoading(true);
        const data = await fetchSystemRoutes();
        setRoutes(data);
        setLoading(false);
    };

    useEffect(() => {
        loadRoutes();
    }, []);

    const handleAutoFix = async (route: ApiRoute) => {
        setSelectedRoute(route);
        setFixing(true);
        try {
            const result = await remediateRoute(route.path, "500 Internal Server Error"); // Simulate error for now
            setRemediationResult(result);
        } catch (e) {
            setRemediationResult({ error: "Failed to run remediation." });
        }
        setFixing(false);
    };

    return (
        <div className="p-6 space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">System Health & API Status</h1>
                    <p className="text-gray-500 dark:text-gray-400">Real-time monitoring and auto-remediation of API endpoints.</p>
                </div>
                <button onClick={loadRoutes} className="flex items-center px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600">
                    <RefreshCw className="w-4 h-4 mr-2" /> Refresh
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                        <h2 className="font-semibold text-gray-900 dark:text-white flex items-center">
                            <Activity className="w-5 h-5 mr-2 text-primary-500" /> API Endpoints
                        </h2>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-gray-50 dark:bg-gray-700/50 text-gray-500 dark:text-gray-400 font-medium">
                                <tr>
                                    <th className="px-4 py-3">Path</th>
                                    <th className="px-4 py-3">Methods</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                                {routes.map((route, idx) => (
                                    <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                        <td className="px-4 py-3 font-mono text-xs text-gray-600 dark:text-gray-300">{route.path}</td>
                                        <td className="px-4 py-3">
                                            {route.methods.map(m => (
                                                <span key={m} className="inline-block px-2 py-0.5 mr-1 text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 rounded">
                                                    {m}
                                                </span>
                                            ))}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${route.status === 'Active' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
                                                }`}>
                                                {route.status === 'Active' ? <CheckCircle className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
                                                {route.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <button
                                                onClick={() => handleAutoFix(route)}
                                                className="text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium text-xs flex items-center"
                                            >
                                                <Play className="w-3 h-3 mr-1" /> Auto-Fix
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                    <h2 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                        <AlertTriangle className="w-5 h-5 mr-2 text-yellow-500" /> AI Remediation
                    </h2>
                    {selectedRoute ? (
                        <div className="space-y-4">
                            <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
                                <p className="text-xs text-gray-500 uppercase font-semibold mb-1">Target Endpoint</p>
                                <code className="text-sm font-mono text-primary-600 dark:text-primary-400">{selectedRoute.path}</code>
                            </div>

                            {fixing ? (
                                <div className="flex items-center justify-center py-8">
                                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                                    <span className="ml-3 text-sm text-gray-500">AI is analyzing the failure...</span>
                                </div>
                            ) : remediationResult ? (
                                <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                    <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
                                        <h3 className="text-sm font-bold text-blue-800 dark:text-blue-300 mb-2">Analysis</h3>
                                        <p className="text-sm text-blue-700 dark:text-blue-200 whitespace-pre-wrap">{remediationResult.analysis}</p>
                                    </div>
                                    <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-100 dark:border-green-800">
                                        <h3 className="text-sm font-bold text-green-800 dark:text-green-300 mb-2">Suggestion</h3>
                                        <p className="text-sm text-green-700 dark:text-green-200 whitespace-pre-wrap">{remediationResult.suggestion}</p>
                                    </div>
                                </div>
                            ) : (
                                <p className="text-sm text-gray-500">Click "Auto-Fix" on any route to start AI diagnosis.</p>
                            )}
                        </div>
                    ) : (
                        <div className="text-center py-12 text-gray-500">
                            <Activity className="w-12 h-12 mx-auto mb-3 opacity-20" />
                            <p>Select a route to view details</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
