import React, { useState, useEffect } from 'react';
import {
  WebGPUModelSpec,
  WebGPUInferenceMetrics,
  WebGPUMetric,
  WebGPUModelStatus,
} from '../types';
import * as api from '../services/apiService';
import {
  CpuIcon,
  FlaskConicalIcon,
  GaugeIcon,
  MemoryStickIcon,
  BarChart3Icon,
  ActivityIcon,
  ZapIcon,
  RefreshCcwIcon,
  ClipboardListIcon,
  ArrowUpRightIcon,
} from './icons';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export const WebGPUDashboard: React.FC = () => {
  const [models, setModels] = useState<WebGPUModelSpec[]>([]);
  const [inferenceMetrics, setInferenceMetrics] = useState<WebGPUInferenceMetrics[]>([]);
  const [gpuMetrics, setGpuMetrics] = useState<WebGPUMetric[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [modelsData, inferenceData, gpuData] = await Promise.all([
        api.fetchWebGPUModels(),
        api.fetchWebGPUInferenceMetrics(),
        api.fetchWebGPUGPUMetrics(),
      ]);
      setModels(modelsData);
      setInferenceMetrics(inferenceData);
      setGpuMetrics(gpuData);
    } catch (error) {
      console.error('Error fetching WebGPU data:', error);
    } finally {
      setLoading(false);
    }
  };

  const compileModel = async () => {
    const onnxPath = prompt("Enter ONNX model path (e.g., 'path/to/model.onnx'):");
    if (!onnxPath) return;
    const modelName = prompt("Enter an optional model name:");
    try {
      await api.compileWebGPUModel(onnxPath, modelName || undefined);
      fetchData(); // Refresh data
      alert('Model compilation initiated successfully!');
    } catch (error) {
      console.error('Failed to compile model:', error);
      alert('Failed to compile model. Check console for details.');
    }
  };

  const getStatusColor = (status: WebGPUModelStatus | string) => {
    switch (status) {
      case 'loaded':
        return 'text-green-500';
      case 'unloaded':
        return 'text-yellow-500';
      case 'error':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusDot = (status: WebGPUModelStatus | string) => {
    const colorClass = getStatusColor(status);
    return <span className={`w-2 h-2 rounded-full inline-block mr-2 ${colorClass.replace('text-', 'bg-')}`}></span>;
  };

  // Aggregate GPU metrics for charting
  const gpuUtilizationChartData = gpuMetrics.map(m => ({
    timestamp: new Date(m.timestamp * 1000).toLocaleTimeString(),
    compute_utilization: m.compute_utilization * 100,
    memory_utilization: m.memory_used_mb / m.memory_total_mb * 100,
  }));

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full p-6">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
        <p className="ml-4 text-gray-600 dark:text-gray-300">Loading WebGPU Inference data...</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8 bg-gray-50 dark:bg-gray-900 min-h-screen">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center">
            <CpuIcon size={32} className="mr-3 text-secondary-600" />
            WebGPU/ONNX Inference Dashboard
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Accelerated AI inference using WebGPU for high-performance computing.
          </p>
        </div>
        <button
          onClick={compileModel}
          className="flex items-center px-6 py-3 bg-secondary-600 text-white rounded-lg shadow-md hover:bg-secondary-700 transition-colors duration-200"
        >
          <FlaskConicalIcon size={20} className="mr-2" />
          Compile New Model
        </button>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Models</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{models.length}</h2>
          </div>
          <FlaskConicalIcon size={40} className="text-yellow-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Inferences</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{inferenceMetrics.length}</h2>
          </div>
          <ZapIcon size={40} className="text-orange-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Avg Latency (ms)</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {(inferenceMetrics.reduce((sum, m) => sum + (m.latency_ms || 0), 0) / inferenceMetrics.length || 0).toFixed(2)}
            </h2>
          </div>
          <GaugeIcon size={40} className="text-blue-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Latest GPU Util</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {((gpuMetrics[0]?.compute_utilization || 0) * 100).toFixed(0)}%
            </h2>
          </div>
          <ActivityIcon size={40} className="text-red-400 opacity-60" />
        </div>
      </div>

      {/* Compiled Models */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <ClipboardListIcon size={24} className="mr-2 text-secondary-500" /> Compiled Models
        </h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Model ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Name</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Input Shape</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Output Shape</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Shaders</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {models.map(model => (
                <tr key={model.model_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{model.model_id.substring(0, 10)}...</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{model.name || 'N/A'}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {getStatusDot(model.status)} {model.status}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {model.input_shapes ? JSON.stringify(model.input_shapes) : 'N/A'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {model.output_shapes ? JSON.stringify(model.output_shapes) : 'N/A'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {Object.keys(model.wgsl_shaders).length}
                  </td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-3 text-center text-sm text-gray-500">No models compiled yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* GPU Utilization Chart */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <GaugeIcon size={24} className="mr-2 text-blue-500" /> GPU Utilization Trend
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={gpuUtilizationChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="timestamp" stroke="#9ca3af" />
            <YAxis yAxisId="left" orientation="left" stroke="#8884d8" label={{ value: 'Compute Util (%)', angle: -90, position: 'insideLeft' }} />
            <YAxis yAxisId="right" orientation="right" stroke="#82ca9d" label={{ value: 'Memory Util (%)', angle: 90, position: 'insideRight' }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="compute_utilization" stroke="#8884d8" name="Compute Utilization" unit="%" />
            <Line yAxisId="right" type="monotone" dataKey="memory_utilization" stroke="#82ca9d" name="Memory Utilization" unit="%" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Inference Latency Chart (Aggregated per model) */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <BarChart3Icon size={24} className="mr-2 text-green-500" /> Inference Latency per Model
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={inferenceMetrics.reduce((acc, metric) => {
            const existing = acc.find(item => item.model_id === metric.model_id);
            if (existing) {
              existing.total_latency += metric.latency_ms;
              existing.count += 1;
              existing.avg_latency = existing.total_latency / existing.count;
            } else {
              acc.push({ model_id: metric.model_id, total_latency: metric.latency_ms, count: 1, avg_latency: metric.latency_ms });
            }
            return acc;
          }, [] as any[]).sort((a,b) => a.avg_latency - b.avg_latency)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="model_id" tickFormatter={(v) => v.substring(0, 7)} stroke="#9ca3af" />
            <YAxis stroke="#9ca3af" label={{ value: 'Avg Latency (ms)', angle: -90, position: 'insideLeft' }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
            <Legend />
            <Line type="monotone" dataKey="avg_latency" stroke="#ffc658" name="Average Latency" unit="ms" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Recent Inference Logs */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <ArrowUpRightIcon size={24} className="mr-2 text-orange-500" /> Recent Inference Logs
        </h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Timestamp</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Model ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Latency (ms)</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Error</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {inferenceMetrics.slice(0, 5).map((metric, index) => (
                <tr key={index} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{new Date(metric.timestamp * 1000).toLocaleString()}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{metric.model_id.substring(0, 10)}...</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{metric.latency_ms.toFixed(2)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {getStatusDot(metric.success ? 'loaded' : 'error')} {metric.success ? 'Success' : 'Failed'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{metric.error || 'N/A'}</td>
                </tr>
              ))}
              {inferenceMetrics.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-3 text-center text-sm text-gray-500">No inference records yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default WebGPUDashboard;
