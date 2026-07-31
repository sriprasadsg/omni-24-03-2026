/**
 * Projection tests for the Fleet Geo Map (GMAP-01) — utils/worldMap.ts.
 * Pure math; no DOM, no network.
 */
import { describe, it, expect } from 'vitest';
import { projectLatLon, MAP_VIEW_W, MAP_VIEW_H } from '../../utils/worldMap';

describe('projectLatLon (equirectangular)', () => {
  it('maps (0,0) to the centre of the native canvas', () => {
    expect(projectLatLon(0, 0)).toEqual({ x: MAP_VIEW_W / 2, y: MAP_VIEW_H / 2 });
    expect(projectLatLon(0, 0)).toEqual({ x: 180, y: 90 });
  });

  it('maps the north-west corner (90,-180) to top-left (0,0)', () => {
    expect(projectLatLon(90, -180)).toEqual({ x: 0, y: 0 });
  });

  it('maps the south-east corner (-90,180) to bottom-right (360,180)', () => {
    expect(projectLatLon(-90, 180)).toEqual({ x: 360, y: 180 });
  });

  it('scales linearly with an explicit width/height', () => {
    expect(projectLatLon(0, 0, 720, 360)).toEqual({ x: 360, y: 180 });
    expect(projectLatLon(90, -180, 720, 360)).toEqual({ x: 0, y: 0 });
  });

  it('clamps out-of-range coordinates rather than throwing', () => {
    expect(() => projectLatLon(200, -500)).not.toThrow();
    // lat=200 clamps to 90 (y=0); lon=-500 clamps to -180 (x=0).
    expect(projectLatLon(200, -500)).toEqual({ x: 0, y: 0 });
  });
});
