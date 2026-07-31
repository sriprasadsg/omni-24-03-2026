/**
 * Equirectangular (Plate Carrée) projection for the Fleet Geo Map (GMAP-01).
 *
 * The world backdrop (components/worldMapAsset.ts) is authored in a
 * viewBox="0 0 360 180" coordinate space, so at the native size the mapping is
 * a direct linear transform — no trig, no library:
 *
 *   x = (lon + 180) / 360 * width     lon ∈ [-180, 180] → x ∈ [0, width]
 *   y = (90  - lat) / 180 * height    lat ∈ [  90, -90] → y ∈ [0, height]  (north-up)
 *
 * Markers projected with the same width/height as the rendered <svg> line up
 * with the backdrop automatically.
 */

export const MAP_VIEW_W = 360;
export const MAP_VIEW_H = 180;

const clamp = (v: number, lo: number, hi: number): number =>
  v < lo ? lo : v > hi ? hi : v;

export function projectLatLon(
  lat: number,
  lon: number,
  width: number = MAP_VIEW_W,
  height: number = MAP_VIEW_H,
): { x: number; y: number } {
  const safeLat = clamp(lat, -90, 90);
  const safeLon = clamp(lon, -180, 180);
  return {
    x: ((safeLon + 180) / 360) * width,
    y: ((90 - safeLat) / 180) * height,
  };
}
