import React, { useState, useEffect } from 'react';
import {
  CustomerVectorCollection,
  VectorAccessPolicy,
  VectorPipelineSource,
  VectorPipelineRun,
  VectorRole,
  VectorDataClassification,
  VectorSourceType,
  VectorPipelineStatus,
  VectorIndexStats,
} from '../types';
import * as api from '../services/apiService';
import {
  DatabaseIcon,
  ShieldCheckIcon,
  SettingsIcon,
  ActivityIcon,
  RefreshCcwIcon,
  PlusIcon,
  ClipboardListIcon,
  PlayIcon,
  PauseCircleIcon,
  GaugeIcon,
  BarChart3Icon,
  GitMergeIcon,
} from './icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';

export const EnhancedVectorDashboard: React.FC = () => {
  const [collections, setCollections] = useState<CustomerVectorCollection[]>([]);
  const [indexStats, setIndexStats] = useState<{ [key: string]: VectorIndexStats }>({});
  const [accessPolicies, setAccessPolicies] = useState<{ [key: string]: VectorAccessPolicy }>({});
  const [pipelineSources, setPipelineSources] = useState<VectorPipelineSource[]>([]);
  const [pipelineRuns, setPipelineRuns] = useState<VectorPipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCollectionName, setSelectedCollectionName] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      // Assuming a default tenant_id for listing. In a real app, this would come from user context.
      const tenantId = 'default-tenant';

      const [collectionsData, pipelineSourcesData, pipelineRunsData] = await Promise.all([
        api.listVectorCollections(tenantId),
        api.listVectorPipelineSources(tenantId),
        api.listVectorPipelineRuns(),
      ]);

      setCollections(collectionsData);
      setPipelineSources(pipelineSourcesData);
      setPipelineRuns(pipelineRunsData);

      // Fetch index stats and access policies for each collection
      const statsPromises = collectionsData.map(c => api.getVectorIndexStats(c.collection_name).then(data => ({ [c.collection_name]: data })).catch(() => ({})));
      const policyPromises = collectionsData.map(c => api.getVectorAccessPolicy(tenantId, c.collection_name).then(data => ({ [c.collection_name]: data })).catch(() => ({})));

      const [allStats, allPolicies] = await Promise.all([
        Promise.all(statsPromises),
        Promise.all(policyPromises),
      ]);

      setIndexStats(Object.assign({}, ...allStats));
      setAccessPolicies(Object.assign({}, ...allPolicies));

    } catch (error) {
      console.error('Error fetching vector DB data:', error);
    } finally {
      setLoading(false);
    }
  };

  const createCollection = async () => {
    const tenant_id = prompt("Enter tenant ID:");
    const collection_name = prompt("Enter new collection name:");
    const dimensions = parseInt(prompt("Enter vector dimensions (e.g., 1536):") || "1536");
    if (!tenant_id || !collection_name || isNaN(dimensions)) {
      alert("Invalid input.");
      return;
    }
    try {
      await api.createVectorCollection({ tenant_id, collection_name, dimensions });
      fetchData();
      alert("Collection created successfully!");
    } catch (error) {
      console.error('Failed to create collection:', error);
      alert('Failed to create collection. Check console.');
    }
  };

  const addDataSource = async () => {
    const name = prompt("Enter source name (e.g., 'customer-feedback'):");
    const sourceType = prompt("Enter source type (e.g., 'database', 'api', 'file', 'stream'):");
    const tenant_id = prompt("Enter tenant ID:");
    const collection_name = prompt("Enter target collection name:");
    if (!name || !sourceType || !tenant_id || !collection_name) {
      alert("All fields are required.");
      return;
    }
    // Basic config for demonstration; real implementation would have more detailed forms
    const config = {
      // Basic config for demonstration; real implementation would have more detailed forms
      // Will adjust based on actual VectorSourceType requirements
      // For now, leaving as a generic object
    };

    try {
      await api.addVectorPipelineSource({
        name,
        source_type: sourceType as VectorSourceType,
        config,
        tenant_id,
        collection_name,
      });
      fetchData();
      alert("Data source added successfully!");
    } catch (error) {
      console.error('Failed to add data source:', error);
      alert('Failed to add data source. Check console.');
    }
  };

  const runPipeline = async (sourceId: string) => {
    try {
      await api.runVectorPipeline(sourceId);
      fetchData();
      alert('Pipeline run initiated!');
    } catch (error) {
      console.error('Failed to run pipeline:', error);
      alert('Failed to run pipeline. Check console.');
    }
  };

  const getStatusColor = (status: VectorPipelineStatus | 'active' | 'inactive') => {
    switch (status) {
      case 'completed':
      case 'active':
        return 'text-green-500';
      case 'running':
        return 'text-blue-500';
      case 'failed':
      case 'inactive':
        return 'text-red-500';
      case 'pending':
        return 'text-yellow-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusDot = (status: VectorPipelineStatus | 'active' | 'inactive') => {
    const colorClass = getStatusColor(status);
    return <span className={`w-2 h-2 rounded-full inline-block mr-2 ${colorClass.replace('text-', 'bg-')}`}></span>;
  };

  // Chart data for index quality (e.g., query latency vs recall)
  const indexQualityChartData = Object.keys(indexStats).map(collectionName => {
    const stats = indexStats[collectionName];
    return {
      collection: collectionName,
      avg_query_latency: stats.avg_query_latency,
      approx_recall: stats.approx_recall,
      vector_count: stats.vector_count,
    };
  }).filter(d => d.vector_count > 0).sort((a,b) => a.collection.localeCompare(b.collection));

  // Chart data for pipeline runs over time
  const pipelineRunChartData = pipelineRuns.map(run => ({
    timestamp: new Date(run.started_at * 1000).toLocaleTimeString(),
    processed_count: run.records_processed,
    failed_count: run.records_failed,
  })).sort((a,b) => a.timestamp.localeCompare(b.timestamp)); // Sort by timestamp

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full p-6">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
        <p className="ml-4 text-gray-600 dark:text-gray-300">Loading Enhanced Vector DB data...</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8 bg-gray-50 dark:bg-gray-900 min-h-screen">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center">
            <DatabaseIcon size={32} className="mr-3 text-tertiary-600" />
            Enhanced Customer Vector Database
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Tenant-isolated vector storage, search, and ETL with advanced access control.
          </p>
        </div>
        <div className="flex space-x-4">
          <button
            onClick={createCollection}
            className="flex items-center px-6 py-3 bg-tertiary-600 text-white rounded-lg shadow-md hover:bg-tertiary-700 transition-colors duration-200"
          >
            <PlusIcon size={20} className="mr-2" />
            Create Collection
          </button>
          <button
            onClick={addDataSource}
            className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg shadow-md hover:bg-blue-700 transition-colors duration-200"
          >
            <GitMergeIcon size={20} className="mr-2" />
            Add Data Source
          </button>
          <button
            onClick={() => api.startVectorPipelineScheduler()}
            className="flex items-center px-6 py-3 bg-green-600 text-white rounded-lg shadow-md hover:bg-green-700 transition-colors duration-200"
          >
            <PlayIcon size={20} className="mr-2" />
            Start Scheduler
          </button>
          <button
            onClick={() => api.stopVectorPipelineScheduler()}
            className="flex items-center px-6 py-3 bg-red-600 text-white rounded-lg shadow-md hover:bg-red-700 transition-colors duration-200"
          >
            <PauseCircleIcon size={20} className="mr-2" />
            Stop Scheduler
          </button>
        </div>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Collections</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{collections.length}</h2>
          </div>
          <DatabaseIcon size={40} className="text-tertiary-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Data Sources</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{pipelineSources.length}</h2>
          </div>
          <GitMergeIcon size={40} className="text-blue-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Avg Recall</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {(Object.values(indexStats).reduce((sum, s) => sum + (s.approx_recall || 0), 0) / Object.values(indexStats).filter(s => s.approx_recall !== undefined).length || 0).toFixed(2)}
            </h2>
          </div>
          <GaugeIcon size={40} className="text-green-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Active Pipelines</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {pipelineSources.filter(s => s.enabled).length}
            </h2>
          </div>
          <ActivityIcon size={40} className="text-yellow-400 opacity-60" />
        </div>
      </div>

      {/* Collections Table */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <ClipboardListIcon size={24} className="mr-2 text-tertiary-500" /> Vector Collections
        </h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Collection Name</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Tenant ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Vectors</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Avg Latency</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Approx Recall</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Data Class.</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {collections.map(collection => (
                <tr key={collection.collection_name} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{collection.collection_name}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{collection.tenant_id}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{indexStats[collection.collection_name]?.vector_count || 0}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{(indexStats[collection.collection_name]?.avg_query_latency || 0).toFixed(2)}ms</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{(indexStats[collection.collection_name]?.approx_recall || 0).toFixed(2)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {accessPolicies[collection.collection_name]?.classification || 'internal'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium">
                    <button
                      onClick={() => setSelectedCollectionName(collection.collection_name)}
                      className="text-tertiary-600 hover:text-tertiary-900 mr-2"
                    >
                      Details
                    </button>
                    {/* Add more actions like "Set Policy", "Auto-tune Index" */}
                  </td>
                </tr>
              ))}
              {collections.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-3 text-center text-sm text-gray-500">No collections found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Index Quality Chart */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <SettingsIcon size={24} className="mr-2 text-purple-500" /> Index Quality & Performance
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={indexQualityChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="collection" stroke="#9ca3af" />
            <YAxis yAxisId="left" orientation="left" stroke="#8884d8" label={{ value: 'Avg Query Latency (ms)', angle: -90, position: 'insideLeft' }} />
            <YAxis yAxisId="right" orientation="right" stroke="#82ca9d" label={{ value: 'Approx Recall', angle: 90, position: 'insideRight' }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="avg_query_latency" stroke="#8884d8" name="Avg Query Latency" unit="ms" />
            <Line yAxisId="right" type="monotone" dataKey="approx_recall" stroke="#82ca9d" name="Approx Recall" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Data Pipelines Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <GitMergeIcon size={24} className="mr-2 text-blue-500" /> Data Pipeline Sources
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Source Name</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Type</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Target Collection</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {pipelineSources.map(source => (
                  <tr key={source.source_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{source.name}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{source.source_type}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{source.collection_name}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {getStatusDot(source.enabled ? 'active' : 'inactive')} {source.enabled ? 'Active' : 'Inactive'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium">
                      <button
                        onClick={() => runPipeline(source.source_id)}
                        className="text-blue-600 hover:text-blue-900 mr-2"
                      >
                        Run Now
                      </button>
                    </td>
                  </tr>
                ))}
                {pipelineSources.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-3 text-center text-sm text-gray-500">No data sources configured.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <ActivityIcon size={24} className="mr-2 text-yellow-500" /> Recent Pipeline Runs
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Run ID</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Source ID</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Processed</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Started At</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {pipelineRuns.slice(0, 5).map(run => (
                  <tr key={run.run_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{run.run_id.substring(0, 10)}...</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{run.source_id.substring(0, 10)}...</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {getStatusDot(run.status)} {run.status}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{run.records_processed}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {new Date(run.started_at * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))}
                {pipelineRuns.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-3 text-center text-sm text-gray-500">No pipeline runs recorded.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Pipeline Run Metrics Chart */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <BarChart3Icon size={24} className="mr-2 text-yellow-500" /> Pipeline Processed vs Failed
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={pipelineRunChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="timestamp" stroke="#9ca3af" />
            <YAxis stroke="#9ca3af" label={{ value: 'Count', angle: -90, position: 'insideLeft' }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
            <Legend />
            <Bar dataKey="processed_count" fill="#82ca9d" name="Processed" />
            <Bar dataKey="failed_count" fill="#ff7300" name="Failed" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Selected Collection Detail Modal (simple version) */}
      {selectedCollectionName && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">Collection Details: {selectedCollectionName}</h3>
              <button onClick={() => setSelectedCollectionName(null)} className="text-gray-400 hover:text-gray-600">
                &times;
              </button>
            </div>
            <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
              <p><strong>Tenant ID:</strong> {collections.find(c => c.collection_name === selectedCollectionName)?.tenant_id}</p>
              <p><strong>Vectors:</strong> {indexStats[selectedCollectionName]?.vector_count || 0}</p>
              <p><strong>Avg Query Latency:</strong> {(indexStats[selectedCollectionName]?.avg_query_latency || 0).toFixed(2)}ms</p>
              <p><strong>Approx Recall:</strong> {(indexStats[selectedCollectionName]?.approx_recall || 0).toFixed(2)}</p>
              <p><strong>Data Classification:</strong> {accessPolicies[selectedCollectionName]?.classification || 'internal'}</p>
              <p><strong>PII Fields:</strong> {(accessPolicies[selectedCollectionName]?.pii_fields || []).join(', ') || 'None'}</p>
              <p><strong>Quarantine Enabled:</strong> {accessPolicies[selectedCollectionName]?.quarantine_enabled ? 'Yes' : 'No'}</p>
              {/* More details here */}
            </div>
            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
              <button onClick={() => setSelectedCollectionName(null)} className="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EnhancedVectorDashboard;
