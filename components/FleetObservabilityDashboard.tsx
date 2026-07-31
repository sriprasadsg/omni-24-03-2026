import React, { useEffect, useState } from 'react';
import { fetchFleetObservability, FleetObservability, FleetObservabilityAgent } from '../services/apiService';
import { showToast } from '../utils/toast';

// Admin-gated Fleet Observability panel (D-03, D-07, FOBS-03). Pure renderer
// over GET /api/fleet/observability (Plan 48-03) — offline detection and
// version-drift compare both happen server-side (monitor_agent_status() +
// _LATEST_AGENT_VERSION/_parse_ver). This component MUST NOT recompute
// offline/drift status on the client (Don't Hand-Roll / T-48-14).
export function FleetObservabilityDashboard() {
  const [data, setData] = useState<FleetObservability | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchFleetObservability();
      setData(result);
    } catch (e: any) {
      const message = e?.message || 'Failed to load fleet observability data';
      setError(message);
      showToast(message, 'error');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <p className="text-gray-400 text-sm">Loading fleet observability…</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Fleet Observability</h1>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  const offlineAgents = data?.offline_agents ?? [];
  const versionDrift = data?.version_drift ?? [];

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Fleet Observability</h1>
        <p className="text-gray-400 text-sm mt-1">
          Fleet-wide offline agents and version drift, relative to the latest agent version
          {data?.latest_version ? ` (${data.latest_version})` : ''}.
        </p>
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium text-sm">Offline Agents</h2>
          <span className="text-gray-400 text-xs">{data?.offline_count ?? 0}</span>
        </div>
        {offlineAgents.length === 0 ? (
          <p className="text-gray-500 text-xs italic">No offline agents</p>
        ) : (
          <div className="space-y-2">
            {offlineAgents.map((agent) => (
              <AgentRow key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </div>

      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium text-sm">Version Drift</h2>
          <span className="text-gray-400 text-xs">{data?.drift_count ?? 0}</span>
        </div>
        {versionDrift.length === 0 ? (
          <p className="text-gray-500 text-xs italic">All agents on the latest version</p>
        ) : (
          <div className="space-y-2">
            {versionDrift.map((agent) => (
              <AgentRow key={agent.id} agent={agent} showLatestVersion={data?.latest_version} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AgentRow({ agent, showLatestVersion }: { agent: FleetObservabilityAgent; showLatestVersion?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 flex-wrap bg-gray-900 border border-gray-700 rounded-lg px-3 py-2">
      <div className="flex-1 min-w-[160px]">
        <p className="text-sm font-medium">{agent.hostname || agent.id}</p>
        <p className="text-gray-500 text-xs mt-0.5">{agent.status}</p>
      </div>
      <div className="text-right text-xs text-gray-400">
        {showLatestVersion ? (
          <span>
            {agent.version ?? 'unknown'} <span className="text-gray-600">→</span> {showLatestVersion}
          </span>
        ) : (
          <span>{agent.version ?? 'unknown'}</span>
        )}
      </div>
    </div>
  );
}
