import React, { useState, useEffect } from 'react';
import { fetchMeshServices, fetchMeshMetrics, fetchMeshGraph } from '../services/apiService';
import { Layers, Activity, Server, Share2 } from 'lucide-react';

export const ServiceMeshDashboard: React.FC = () => {
    const [services, setServices] = useState<any[]>([]);
    const [metrics, setMetrics] = useState<any[]>([]);
    const [graph, setGraph] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [svcData, metricData, graphData] = await Promise.all([
                fetchMeshServices(),
                fetchMeshMetrics(),
                fetchMeshGraph()
            ]);
            setServices(svcData);
            setMetrics(metricData);
            setGraph(graphData);
        } catch (e) {
            console.error("Failed to load mesh data", e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6 space-y-6">
            <h1 className="text-2xl font-bold flex items-center gap-2">
                <Layers className="text-purple-400" />
                Service Mesh Observer
            </h1>
            <p className="text-gray-400">Real-time visibility into microservices traffic, sidecar status, and topology.</p>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-gray-800 p-4 rounded-lg border-l-4 border-green-500">
                    <div className="text-gray-400 text-sm">Active Services</div>
                    <div className="text-2xl font-bold">{services.length}</div>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border-l-4 border-blue-500">
                    <div className="text-gray-400 text-sm">Sidecars Injected</div>
                    <div className="text-2xl font-bold">{services.filter(s => s.sidecar?.injected).length}</div>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border-l-4 border-red-500">
                    <div className="text-gray-400 text-sm">Global Error Rate</div>
                    <div className="text-2xl font-bold">0.8%</div>
                </div>
                <div className="bg-gray-800 p-4 rounded-lg border-l-4 border-purple-500">
                    <div className="text-gray-400 text-sm">Mesh Status</div>
                    <div className="text-2xl font-bold text-green-400">Healthy</div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Services List */}
                <div className="bg-gray-800 rounded-lg lg:col-span-2">
                    <div className="px-6 py-4 border-b border-gray-700 flex justify-between items-center">
                        <h2 className="text-lg font-semibold flex items-center gap-2"><Server /> Services</h2>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-gray-900 text-gray-400 text-xs uppercase">
                                <tr>
                                    <th className="px-6 py-3">Service Name</th>
                                    <th className="px-6 py-3">Namespace</th>
                                    <th className="px-6 py-3">Sidecar</th>
                                    <th className="px-6 py-3">Health</th>
                                    <th className="px-6 py-3">Latency (P95)</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-700">
                                {services.map(svc => {
                                    const metric = metrics.find(m => m.serviceId === svc.id);
                                    return (
                                        <tr key={svc.id} className="hover:bg-gray-750">
                                            <td className="px-6 py-4 font-medium">{svc.name}</td>
                                            <td className="px-6 py-4 text-gray-400">{svc.namespace}</td>
                                            <td className="px-6 py-4">
                                                {svc.sidecar?.injected ? (
                                                    <span className="px-2 py-1 rounded text-xs bg-green-900 text-green-200">
                                                        v{svc.sidecar.version}
                                                    </span>
                                                ) : (
                                                    <span className="px-2 py-1 rounded text-xs bg-gray-700 text-gray-400">None</span>
                                                )}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className={`px-2 py-1 rounded text-xs ${svc.health === 'Healthy' ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'}`}>
                                                    {svc.health}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 font-mono text-sm">
                                                {metric ? `${metric.latencyP95.toFixed(2)}ms` : '-'}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Simplified Topology Graph Visualization */}
                <div className="bg-gray-800 rounded-lg">
                    <div className="px-6 py-4 border-b border-gray-700">
                        <h2 className="text-lg font-semibold flex items-center gap-2"><Share2 /> Topology</h2>
                    </div>
                    <div className="p-6">
                        {/* Simple visual representation for now */}
                        <div className="space-y-4">
                            {graph?.edges?.slice(0, 5).map((edge: any, idx: number) => (
                                <div key={idx} className="flex items-center justify-between text-sm bg-gray-900 p-3 rounded">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                                        <span>{edge.source}</span>
                                    </div>
                                    <div className="h-px bg-gray-600 flex-1 mx-4 relative">
                                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-gray-800 px-1 text-xs text-gray-500">
                                            {edge.weight} ops/s
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span>{edge.target}</span>
                                        <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="mt-4 text-center text-xs text-gray-500">
                            Visualizing top 5 localized traffic flows
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
