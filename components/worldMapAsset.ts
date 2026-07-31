/**
 * Self-contained world backdrop for the Fleet Geo Map (GMAP-01).
 *
 * Authored in the projection's coordinate space (viewBox="0 0 360 180", see
 * utils/worldMap.ts) so markers layered over it align by construction. Fully
 * air-gapped: inline SVG markup only — no external image references, no map
 * raster sources, no remote hosts, no network requests of any kind.
 *
 * This ships the guaranteed graticule fallback locked in D-01: an ocean fill
 * plus a 30° longitude/latitude grid with an emphasized equator (y=90) and
 * prime meridian (x=180). To upgrade to true landmasses, prepend a
 * public-domain equirectangular land outline (Natural Earth 1:110m is public
 * domain) as `<path d="…" fill="…"/>` elements to WORLD_BACKDROP_SVG — nothing
 * else needs to change, since the outline shares this same 360×180 space.
 */

export const WORLD_VIEWBOX = '0 0 360 180';

const OCEAN = '#0b1220';
const GRID_LINE = '#1c2b45';
const GRID_EMPHASIS = '#33507a';

const WORLD_BACKDROP_SVG: string = (() => {
  const parts: string[] = [];
  // Ocean base fill covering the whole equirectangular canvas.
  parts.push(`<rect x="0" y="0" width="360" height="180" fill="${OCEAN}"/>`);
  // Meridians every 30° of longitude (x = 0,30,…,360); prime meridian emphasized.
  for (let lon = 0; lon <= 360; lon += 30) {
    const emph = lon === 180;
    parts.push(
      `<line x1="${lon}" y1="0" x2="${lon}" y2="180" stroke="${emph ? GRID_EMPHASIS : GRID_LINE}" stroke-width="${emph ? 0.6 : 0.3}"/>`,
    );
  }
  // Parallels every 30° of latitude (y = 0,30,…,180); equator emphasized.
  for (let lat = 0; lat <= 180; lat += 30) {
    const emph = lat === 90;
    parts.push(
      `<line x1="0" y1="${lat}" x2="360" y2="${lat}" stroke="${emph ? GRID_EMPHASIS : GRID_LINE}" stroke-width="${emph ? 0.6 : 0.3}"/>`,
    );
  }
  return parts.join('');
})();

export { WORLD_BACKDROP_SVG };
