/**
 * Grid-bucket clustering for the Fleet Geo Map (GMAP-02).
 *
 * Located agents are projected to pixel space (utils/worldMap.projectLatLon)
 * and bucketed into fixed square cells of `cellPx`. Each non-empty cell yields
 * one cluster positioned at the mean of its members, carrying the member count
 * and the worst status in the cell. No distance math, no external library.
 * Unlocated agents (geo === null) are ignored here — the caller surfaces them
 * as a separate off-map count (D-07).
 */
import type { FleetGeoAgent } from '../services/apiService';
import { projectLatLon } from './worldMap';

export interface GeoCluster {
  x: number;
  y: number;
  agents: FleetGeoAgent[];
  count: number;
  worstStatus: string;
}

// Higher rank = more severe. Unknown statuses rank below Online.
const STATUS_RANK: Record<string, number> = {
  Online: 1,
  Offline: 2,
  Error: 3,
  Quarantined: 4,
};

const rank = (status: string): number => STATUS_RANK[status] ?? 0;

export function clusterAgents(
  agents: FleetGeoAgent[],
  cellPx: number,
  width: number,
  height: number,
): GeoCluster[] {
  const buckets = new Map<string, { sx: number; sy: number; agents: FleetGeoAgent[] }>();

  for (const agent of agents) {
    if (!agent.geo) continue; // unlocated — handled by the caller
    const { x, y } = projectLatLon(agent.geo.latitude, agent.geo.longitude, width, height);
    const key = `${Math.floor(x / cellPx)}:${Math.floor(y / cellPx)}`;
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.sx += x;
      bucket.sy += y;
      bucket.agents.push(agent);
    } else {
      buckets.set(key, { sx: x, sy: y, agents: [agent] });
    }
  }

  const clusters: GeoCluster[] = [];
  for (const { sx, sy, agents: members } of buckets.values()) {
    const worstStatus = members.reduce(
      (worst, a) => (rank(a.status) > rank(worst) ? a.status : worst),
      members[0].status,
    );
    clusters.push({
      x: sx / members.length,
      y: sy / members.length,
      agents: members,
      count: members.length,
      worstStatus,
    });
  }

  // Deterministic ordering (top-left → bottom-right) so renders are stable.
  clusters.sort((a, b) => a.y - b.y || a.x - b.x);
  return clusters;
}
