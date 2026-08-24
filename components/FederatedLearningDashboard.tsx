import React, { useState, useEffect } from 'react';
import {
  FLParticipant,
  FLTrainingRound,
  FLModelVersion,
  FLRoundStatus,
} from '../types';
import * as api from '../services/apiService';
import {
  ActivityIcon,
  BrainCircuitIcon,
  FlaskConicalIcon,
  BookOpenCheckIcon,
  ClipboardListIcon,
  BoxIcon,
  ServerIcon,
  SettingsIcon,
  ShieldCheckIcon,
  RefreshCcwIcon,
  Share2Icon,
  Users2Icon,
  BarChart3Icon,
} from './icons';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';

export const FederatedLearningDashboard: React.FC = () => {
  const [rounds, setRounds] = useState<FLTrainingRound[]>([]);
  const [participants, setParticipants] = useState<FLParticipant[]>([]);
  const [models, setModels] = useState<FLModelVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRound, setSelectedRound] = useState<FLTrainingRound | null>(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [roundsData, participantsData, modelsData] = await Promise.all([
        api.fetchFLRounds(),
        api.fetchFLParticipants(),
        api.fetchFLModels(),
      ]);
      setRounds(roundsData);
      setParticipants(participantsData);
      setModels(modelsData);
    } catch (error) {
      console.error('Error fetching federated learning data:', error);
    } finally {
      setLoading(false);
    }
  };

  const startNewRound = async () => {
    // This would typically involve selecting participants and a base model
    // For now, simulate with some default values
    const readyParticipants = participants.filter(p => p.status !== 'offline').map(p => p.participant_id);
    if (readyParticipants.length === 0) {
      alert('No active participants to start a round.');
      return;
    }
    const latestModel = models.find(m => m.status === 'active')?.version || 'initial_model_v1';
    try {
      await api.startFLRound(readyParticipants, latestModel);
      fetchData(); // Refresh data
    } catch (error) {
      console.error('Failed to start new round:', error);
      alert('Failed to start new round.');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'complete':
      case 'active':
      case 'registered':
      case 'idle':
        return 'text-green-500';
      case 'aggregating':
      case 'training':
      case 'pending':
        return 'text-yellow-500';
      case 'offline':
      case 'failed':
      case 'deprecated':
      case 'archived':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusDot = (status: string) => {
    const colorClass = getStatusColor(status);
    return <span className={`w-2 h-2 rounded-full inline-block mr-2 ${colorClass.replace('text-', 'bg-')}`}></span>;
  };

  const modelMetricsChartData = models.map(m => ({
    version: m.version,
    loss: m.metrics?.aggregated_loss ?? 0,
    participants: m.participants.length,
    samples: m.total_samples,
  })).sort((a, b) => (a.samples || 0) - (b.samples || 0));

  const roundMetricsChartData = rounds.map(r => ({
    round_id: r.round_id,
    participants: r.participant_ids.length,
    updates: Object.keys(r.updates).length,
  })).sort((a, b) => a.round_id.localeCompare(b.round_id));

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full p-6">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
        <p className="ml-4 text-gray-600 dark:text-gray-300">Loading Federated Learning data...</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8 bg-gray-50 dark:bg-gray-900 min-h-screen">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center">
            <BookOpenCheckIcon size={32} className="mr-3 text-primary-600" />
            Federated Learning Dashboard
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Secure, distributed AI model training across tenant data.
          </p>
        </div>
        <button
          onClick={startNewRound}
          className="flex items-center px-6 py-3 bg-primary-600 text-white rounded-lg shadow-md hover:bg-primary-700 transition-colors duration-200"
        >
          <RefreshCcwIcon size={20} className="mr-2" />
          Start New Round
        </button>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Rounds</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{rounds.length}</h2>
          </div>
          <BrainCircuitIcon size={40} className="text-primary-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Active Participants</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {participants.filter(p => p.status !== 'offline').length}
            </h2>
          </div>
          <Users2Icon size={40} className="text-green-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Global Models</p>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{models.length}</h2>
          </div>
          <BoxIcon size={40} className="text-purple-400 opacity-60" />
        </div>
        <div className="card p-6 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Latest Model</p>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              {models.find(m => m.status === 'active')?.version.split('_')[1] || 'N/A'}
            </h2>
          </div>
          <FlaskConicalIcon size={40} className="text-blue-400 opacity-60" />
        </div>
      </div>

      {/* Rounds & Models Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Rounds */}
        <div className="card p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <ClipboardListIcon size={24} className="mr-2 text-primary-500" /> Recent Training Rounds
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Round ID</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Participants</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Model Version</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Started</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {rounds.slice(0, 5).map(round => (
                  <tr key={round.round_id} className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer" onClick={() => setSelectedRound(round)}>
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{round.round_id.substring(0, 10)}...</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {getStatusDot(round.status)} {round.status}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{round.participant_ids.length}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{round.global_model_version.split('_')[1] || 'N/A'}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {new Date(round.started_at * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))}
                {rounds.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-3 text-center text-sm text-gray-500">No rounds completed yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Global Models */}
        <div className="card p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <BoxIcon size={24} className="mr-2 text-purple-500" /> Global Model Versions
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Version</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Loss</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Participants</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {models.slice(0, 5).map(model => (
                  <tr key={model.version} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{model.version.substring(0, 10)}...</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {getStatusDot(model.status)} {model.status}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{(model.metrics.aggregated_loss || 0).toFixed(4)}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{model.participants.length}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                      {new Date(model.created_at * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))}
                 {models.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-3 text-center text-sm text-gray-500">No global models available.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Participants */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <Share2Icon size={24} className="mr-2 text-teal-500" /> Federated Participants
        </h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Participant ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Tenant ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Model Version</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Local Loss</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Last Seen</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {participants.map(participant => (
                <tr key={participant.participant_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">{participant.participant_id.substring(0, 10)}...</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{participant.tenant_id}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {getStatusDot(participant.status)} {participant.status}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{participant.model_version.split('_')[1] || 'N/A'}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">{participant.local_loss.toFixed(4)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300">
                    {new Date(participant.last_seen * 1000).toLocaleString()}
                  </td>
                </tr>
              ))}
              {participants.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-3 text-center text-sm text-gray-500">No participants registered.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Model Performance Trend */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <ActivityIcon size={24} className="mr-2 text-blue-500" /> Global Model Loss Trend
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={modelMetricsChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="version" tickFormatter={(v) => v.split('_')[1] || v.substring(0,7)} stroke="#9ca3af" />
            <YAxis stroke="#9ca3af" label={{ value: 'Aggregated Loss', angle: -90, position: 'insideLeft' }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
            <Legend />
            <Line type="monotone" dataKey="loss" stroke="#8884d8" name="Loss" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Round Participation */}
      <div className="card p-6">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <BarChart3Icon size={24} className="mr-2 text-green-500" /> Round Participation
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={roundMetricsChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="round_id" tickFormatter={(v) => v.split('_')[2] || v.substring(0,7)} stroke="#9ca3af" />
            <YAxis stroke="#9ca3af" label={{ value: 'Participants', angle: -90, position: 'insideLeft' }} />
            <Tooltip contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '0.5rem' }} />
            <Legend />
            <Bar dataKey="participants" fill="#4CAF50" name="Participants" />
            <Bar dataKey="updates" fill="#2196F3" name="Updates Submitted" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Selected Round Detail Modal */}
      {selectedRound && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">Round Details: {selectedRound.round_id.substring(0, 15)}...</h3>
              <button onClick={() => setSelectedRound(null)} className="text-gray-400 hover:text-gray-600">
                &times;
              </button>
            </div>
            <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
              <p><strong>Status:</strong> {getStatusDot(selectedRound.status)} {selectedRound.status}</p>
              <p><strong>Global Model:</strong> {selectedRound.global_model_version}</p>
              <p><strong>Started At:</strong> {new Date(selectedRound.started_at * 1000).toLocaleString()}</p>
              <div>
                <strong>Participants:</strong>
                <ul className="list-disc list-inside ml-4">
                  {selectedRound.participant_ids.map(id => <li key={id}>{id}</li>)}
                </ul>
              </div>
              <div>
                <strong>Updates Submitted:</strong>
                <ul className="list-disc list-inside ml-4">
                  {Object.keys(selectedRound.updates).map(id => <li key={id}>{id} (Loss: {(selectedRound.updates[id]?.local_loss ?? 0).toFixed(4)})</li>)}
                </ul>
              </div>
            </div>
            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
              <button onClick={() => setSelectedRound(null)} className="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg text-gray-800 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FederatedLearningDashboard;
