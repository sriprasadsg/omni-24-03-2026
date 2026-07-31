import React, { useEffect, useMemo, useState } from 'react';
import { fetchFleetGeo, FleetGeoResponse, FleetGeoAgent } from '../services/apiService';
import { WORLD_BACKDROP_SVG, WORLD_VIEWBOX } from './worldMapAsset';
import { MAP_VIEW_W, MAP_VIEW_H } from '../utils/worldMap';
import { clusterAgents } from '../utils/fleetClustering';
import { formatGeo, flagEmoji } from '../utils/geo';
import { showToast } from '../utils/toast';

// Fleet Geo Map (GMAP-01/02/03). Air-gapped: renders the self-contained
// worldMapAsset backdrop (no network) and plots agents from GET /api/fleet/geo
// via the equirectangular projection. Clustering + filtering are client-side
// (D-04); status/location come straight from the server payload — no
// client-side status recomputation (D-05/D-06). Unlocated agents are surfaced
// as an off-map count, never dropped (D-07).

// Marker fill + badge classes replicate AgentList.tsx `statusInfo` (D-05) —
// do not invent a new status palette.
const STATUS_FILL: Record<string, string> = {
  Online: '#22c55e',
  Offline: '#6b7280',
  Error: '#ef4444',
  Quarantined: '#f59e0b',
};
const statusFill = (s: string): string => STATUS_FILL[s] ?? '#3b82f6';

const STATUS_BADGE: Record<string, string> = {
  Online: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  Offline: 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  Error: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300 font-bold',
  Quarantined: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 font-bold',
};
const statusBadge = (s: string): string =>
  STATUS_BADGE[s] ?? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300';

const ALL_STATUSES = ['Online', 'Offline', 'Error', 'Quarantined'];
// Cluster cell size in the native 360×180 viewBox space (CSS-scaled on render).
const CELL = 6;

export function FleetGeoMap() {
  const [data, setData] = useState<FleetGeoResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tenantFilter, setTenantFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set(ALL_STATUSES));
  const [selected, setSelected] = useState<FleetGeoAgent | null>(null);
  const [expanded, setExpanded] = useState<FleetGeoAgent[] | null>(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchFleetGeo());
    } catch (e: any) {
      const message = e?.message || 'Failed to load fleet geo data';
      setError(message);
      showToast(message, 'error');
    } finally {
      setLoading(false);
    }
  }

  const toggleStatus = (s: string) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  };

  const filtered = useMemo(() => {
    const agents = data?.agents ?? [];
    return agents.filter(
      (a) => (tenantFilter === 'all' || a.tenantId === tenantFilter) && statusFilter.has(a.status),
    );
  }, [data, tenantFilter, statusFilter]);

  const located = useMemo(() => filtered.filter((a) => a.geo !== null), [filtered]);
  const unlocatedCount = filtered.length - located.length;
  const clusters = useMemo(
    () => clusterAgents(located, CELL, MAP_VIEW_W, MAP_VIEW_H),
    [located],
  );

  if (loading) {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <p className="text-gray-400 text-sm">Loading fleet geo map…</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6 bg-gray-900 min-h-screen text-white">
        <div className="mb-6"><h1 className="text-2xl font-bold">Fleet Geo Map</h1></div>
        <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  const tenants = data?.tenants ?? [];

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Fleet Geo Map</h1>
        <p className="text-gray-400 text-sm mt-1">
          Where the fleet physically is — {located.length} located
          {unlocatedCount > 0 ? `, ${unlocatedCount} unlocated` : ''} of {filtered.length} shown.
        </p>
      </div>

      {/* Filters (GMAP-02) */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <label className="text-xs text-gray-400">Tenant</label>
        <select
          value={tenantFilter}
          onChange={(e) => { setTenantFilter(e.target.value); setSelected(null); setExpanded(null); }}
          className="bg-gray-800 border border-gray-700 rounded-lg text-sm px-2 py-1"
        >
          <option value="all">All tenants</option>
          {tenants.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="flex gap-1.5">
          {ALL_STATUSES.map((s) => {
            const on = statusFilter.has(s);
            return (
              <button
                key={s}
                onClick={() => { toggleStatus(s); setSelected(null); setExpanded(null); }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                  on ? 'border-gray-500' : 'border-gray-800 opacity-40'
                }`}
                style={on ? { backgroundColor: statusFill(s), color: '#0b1220' } : undefined}
              >
                {s}
              </button>
            );
          })}
        </div>
        {unlocatedCount > 0 && (
          <span className="ml-auto text-xs text-gray-400 bg-gray-800 border border-gray-700 rounded-full px-3 py-1">
            Unlocated ({unlocatedCount})
          </span>
        )}
      </div>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Map (GMAP-01) */}
        <div className="flex-1 bg-gray-800/50 border border-gray-700 rounded-xl p-2 overflow-x-auto">
          <svg viewBox={WORLD_VIEWBOX} className="w-full h-auto" role="img" aria-label="Fleet geo map">
            <g dangerouslySetInnerHTML={{ __html: WORLD_BACKDROP_SVG }} />
            {clusters.map((c, i) => {
              if (c.count === 1) {
                const a = c.agents[0];
                return (
                  <circle
                    key={a.id}
                    cx={c.x} cy={c.y} r={1.8}
                    fill={statusFill(a.status)}
                    stroke="#0b1220" strokeWidth={0.4}
                    style={{ cursor: 'pointer' }}
                    onClick={() => { setSelected(a); setExpanded(null); }}
                  >
                    <title>{a.hostname} — {a.status}</title>
                  </circle>
                );
              }
              return (
                <g
                  key={`cluster-${i}`}
                  style={{ cursor: 'pointer' }}
                  onClick={() => { setExpanded(c.agents); setSelected(null); }}
                >
                  <circle cx={c.x} cy={c.y} r={3.2} fill={statusFill(c.worstStatus)} fillOpacity={0.85} stroke="#0b1220" strokeWidth={0.4} />
                  <text x={c.x} y={c.y + 1.4} textAnchor="middle" fontSize={3.6} fill="#0b1220" fontWeight="bold">
                    {c.count}
                  </text>
                  <title>{c.count} agents — worst: {c.worstStatus}</title>
                </g>
              );
            })}
          </svg>
          {/* Legend */}
          <div className="flex flex-wrap gap-3 mt-2 px-1">
            {ALL_STATUSES.map((s) => (
              <span key={s} className="flex items-center gap-1.5 text-xs text-gray-400">
                <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: statusFill(s) }} />
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* Drill-down / cluster expansion (GMAP-03) */}
        <div className="lg:w-80 shrink-0">
          {selected ? (
            <DrillDownPanel agent={selected} onClose={() => setSelected(null)} />
          ) : expanded ? (
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-medium text-sm">{expanded.length} agents here</h2>
                <button onClick={() => setExpanded(null)} className="text-gray-500 hover:text-gray-300 text-xs">Close</button>
              </div>
              <div className="space-y-1.5 max-h-96 overflow-y-auto">
                {expanded.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => { setSelected(a); setExpanded(null); }}
                    className="w-full flex items-center justify-between gap-2 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-left hover:border-gray-500"
                  >
                    <span className="text-sm truncate">{a.hostname}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadge(a.status)}`}>{a.status}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 text-gray-500 text-xs italic">
              Click a marker to inspect an agent.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DrillDownPanel({ agent, onClose }: { agent: FleetGeoAgent; onClose: () => void }) {
  const location = agent.geo
    ? `${flagEmoji(agent.geo.country_code || undefined)} ${formatGeo({ city: agent.geo.city || undefined, country: agent.geo.country || undefined })}`.trim()
    : 'Unlocated';
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-medium text-sm truncate">{agent.hostname}</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xs">Close</button>
      </div>
      <dl className="space-y-2 text-sm">
        <Field label="Status">
          <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadge(agent.status)}`}>{agent.status}</span>
        </Field>
        <Field label="LAN IP"><span className="text-gray-300">{agent.lanIp || '—'}</span></Field>
        <Field label="Public IP"><span className="text-gray-300">{agent.publicIp || '—'}</span></Field>
        <Field label="Location"><span className="text-gray-300">{location || '—'}</span></Field>
        <Field label="Tenant"><span className="text-gray-300">{agent.tenantId}</span></Field>
      </dl>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-gray-500 text-xs">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
