/**
 * Clustering tests for the Fleet Geo Map (GMAP-02) — utils/fleetClustering.ts.
 * Pure math; no DOM, no network.
 */
import { describe, it, expect } from 'vitest';
import { clusterAgents } from '../../utils/fleetClustering';
import { MAP_VIEW_W, MAP_VIEW_H } from '../../utils/worldMap';
import type { FleetGeoAgent } from '../../services/apiService';

const CELL = 24;
const W = 960;
const H = 480;

const agent = (
  id: string,
  lat: number | null,
  lon: number | null,
  status = 'Online',
): FleetGeoAgent => ({
  id,
  hostname: `host-${id}`,
  status,
  tenantId: 'tenant-a',
  lanIp: '10.0.0.1',
  publicIp: '203.0.113.1',
  geo: lat === null || lon === null
    ? null
    : { city: 'X', country: 'Y', country_code: 'YY', latitude: lat, longitude: lon },
});

describe('clusterAgents', () => {
  it('collapses near-identical positions into one cluster with a count', () => {
    const clusters = clusterAgents(
      [agent('a', 52.50, 13.40), agent('b', 52.51, 13.41)],
      CELL, W, H,
    );
    expect(clusters).toHaveLength(1);
    expect(clusters[0].count).toBe(2);
  });

  it('keeps far-apart agents as separate clusters', () => {
    const clusters = clusterAgents(
      [agent('a', 52.5, 13.4), agent('b', -33.9, 151.2)],
      CELL, W, H,
    );
    expect(clusters).toHaveLength(2);
    clusters.forEach((c) => expect(c.count).toBe(1));
  });

  it('reports the worst status in a cell (Quarantined > Error > Offline > Online)', () => {
    const clusters = clusterAgents(
      [
        agent('a', 52.50, 13.40, 'Online'),
        agent('b', 52.51, 13.41, 'Quarantined'),
        agent('c', 52.49, 13.39, 'Offline'),
      ],
      CELL, W, H,
    );
    expect(clusters).toHaveLength(1);
    expect(clusters[0].worstStatus).toBe('Quarantined');
  });

  it('returns [] for empty input', () => {
    expect(clusterAgents([], CELL, W, H)).toEqual([]);
  });

  it('ignores unlocated agents (geo === null)', () => {
    const clusters = clusterAgents(
      [agent('a', 52.5, 13.4), agent('b', null, null, 'Offline')],
      CELL, W, H,
    );
    expect(clusters).toHaveLength(1);
    expect(clusters[0].agents.map((a) => a.id)).toEqual(['a']);
  });

  it('positions a single-agent cluster at its projected coordinate', () => {
    const [c] = clusterAgents([agent('a', 0, 0)], CELL, W, H);
    expect(c.x).toBeCloseTo(MAP_VIEW_W / 2 / MAP_VIEW_W * W); // centre → W/2
    expect(c.y).toBeCloseTo(H / 2);
  });
});
