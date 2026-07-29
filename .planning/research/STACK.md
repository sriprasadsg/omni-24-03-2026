# Stack Research

**Domain:** Agent geo fleet map + VPN/hosting-ASN detection + fleet observability (time-series) for an air-gapped-capable enterprise security/compliance platform
**Researched:** 2026-07-29
**Confidence:** MEDIUM-HIGH (package versions verified directly against the npm/PyPI registries = HIGH; feature/licensing claims cross-checked across official docs + community sources via web search = MEDIUM)

This file covers ONLY the new v3.3 additions. It assumes the existing FastAPI + MongoDB (Motor) + React/TS/Vite/Tailwind + `backend/geoip_service.py` (MaxMind GeoLite2-City) + `agent_metrics_history` capped-by-app-logic collection already in place — do not re-research or replace those. (Note: this file replaces the prior milestone's STACK.md, which covered an unrelated domain — Rust crate bumps + CSPM SDKs — and is now stale; that content is preserved in git history / the archived v3.2 milestone.)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `react-simple-maps` + `d3-geo` + `topojson-client` + `world-atlas` | 3.0.0 / 3.1.1 / 3.1.0 / 2.0.2 | Fleet geo map (world SVG map, agent markers by city/country) | Pure client-side SVG — no tile server, no tile files, no network calls at runtime *at all*. The world outline is a bundled TopoJSON (`world-atlas`'s `countries-110m.json`, ~100KB, public-domain Natural Earth data) that ships inside the Vite JS bundle. This is the simplest possible air-gapped story for a country/city-level fleet map with clustering and tenant/status filters — no infra to stand up, no basemap licensing questions, no glyph/sprite self-hosting. `react-simple-maps` itself hasn't shipped a release since 2023, but its two real rendering engines (`d3-geo`, `topojson-client`) are independently maintained and this is a widely-used, stable pattern for exactly this kind of "dots on a world map" dashboard widget. |
| `supercluster` | 8.0.1 | Marker clustering for the fleet map | Renderer-agnostic geospatial clustering (KD-tree based) — works purely on `[lng, lat]` arrays, so it plugs into the SVG map above (or MapLibre, if you escalate to that later) without change. This is the standard clustering choice used by both Mapbox/MapLibre's own examples and Leaflet.markercluster's design lineage. |
| MaxMind **GeoIP2 Anonymous IP** database (commercial) | current `.mmdb` release (subscription-based, no fixed version number — MaxMind ships rolling updates) | VPN / public-proxy / hosting-provider / Tor-exit flagging for agent public IPs | This is the correct, purpose-built product for "VPN/proxy/hosting-ASN flagging" — it returns explicit `is_anonymous_vpn`, `is_hosting_provider`, `is_public_proxy`, `is_residential_proxy`, and `is_tor_exit_node` booleans per IP. It is a downloadable `.mmdb` file read with the exact same `maxminddb` Python reader already vendored in `backend/geoip_service.py` — zero new runtime dependency, zero per-lookup network calls, same "supplied out-of-band, degrades gracefully when absent" pattern already established for GeoLite2-City. Requires a paid MaxMind subscription (the project already has a commercial MaxMind relationship for GeoLite2-City licensing, so this is an add-on to an existing vendor, not a new one). |
| MongoDB **time-series collections** (native, MongoDB 5.0+; already running 8.0.26) | n/a (server feature, not a package) | Fleet observability — heartbeat/uptime timeline, health-history rollups for the new fleet-observability views | The backend already runs MongoDB 8.0.26, which fully supports time-series collections (`db.createCollection(..., timeseries={...})`), including 7.0+ downsampling. Time-series collections auto-bucket by `metaField` (e.g. `agent_id`) and `timeField`, giving 50–90% storage reduction and materially faster range/aggregation queries than a plain collection — the right structure for a new per-agent uptime/health timeline feature. **Do not migrate `agent_metrics_history`** (it already has a working TTL index + app-level 100-per-agent cap from `002_scale_indexes.py` / `agent_heartbeat_endpoints.py` — leave it as-is per the "don't rebuild" instruction). Use a time-series collection only for genuinely new v3.3 time-series data (e.g. a rolled-up hourly/daily uptime-percentage series, if the raw heartbeat cap isn't enough resolution for long-range charts). |
| `recharts` | ^3.5.1 already installed (latest is 3.10.1) | Health/uptime charting on the fleet observability dashboard | Already the project's charting library elsewhere — no new dependency. `AreaChart`/`LineChart` with a time-domain `XAxis` is the standard recharts pattern for uptime/CPU/mem sparklines and history views; reuse the existing chart component conventions rather than introducing a second charting library. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `X4BNet/lists_vpn` (data, not npm) | rolling (GitHub Actions auto-rebuild) | Free/open-source VPN & datacenter IP-range fallback | If there's no budget for the paid GeoIP2 Anonymous IP database, pull `output/vpn/ipv4.txt` / `output/datacenter/ipv4.txt` periodically (out-of-band, same as the GeoLite2 supply model) and load into an in-memory CIDR trie (`python-radix` or a hand-rolled sorted-interval lookup) for O(log n) IP→flag lookups. Weaker signal than MaxMind (no residential-proxy/Tor granularity) but zero cost and fully offline-compatible. |
| MaxMind **GeoLite2-ASN** (free) | rolling (free tier, license key + attribution required under GeoLite2 EULA) | Cheap ASN-name heuristic as a second fallback tier, or to enrich agent records with AS-org display name regardless of VPN detection | Returns ASN + AS-organization name only — it does **not** itself flag VPN/hosting status. Useful for a lightweight heuristic (substring-match AS-org name against a maintained list of cloud/hosting/VPN brand names) if you want a third, zero-cost tier below GeoIP2 Anonymous IP and X4BNet, or just to show "AWS / DigitalOcean / Hetzner" next to an agent's IP in the UI. |
| `maplibre-gl` + `pmtiles` + `tileserver-gl` (self-hosted) | 6.0.0 / 4.4.1 / current | Escalation path ONLY if product later wants true interactive pan/zoom/street-level basemap | MapLibre GL JS v6 is the actively-maintained open-source fork of Mapbox GL JS, ships as ES modules, and has zero forced network calls as long as you self-host the style JSON, sprite sheet, glyph PBFs, and a `.pmtiles` vector basemap (PMTiles supports single-file HTTP range-request serving — no separate tile database/server process required, just a static file on the existing app server). A full-planet vector tileset is ~80GB, but a basemap simplified to low zoom levels only (country/region borders, no street detail) is a few MB and is all a fleet-map widget needs. Reach for this only if the SVG approach above proves visually insufficient (e.g. product wants smooth zoom/pan into dense city clusters) — it's meaningfully more integration work (style/sprite/glyph self-hosting + a custom basemap build step) than `react-simple-maps`. |
| `react-map-gl` | 8.1.1 | React wrapper for MapLibre, only needed if escalating to MapLibre | Thin declarative React bindings over `maplibre-gl`; pairs with `supercluster` for clustering exactly as it would with the SVG approach. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| MaxMind account / license key (already provisioned) | Download GeoIP2 Anonymous IP `.mmdb` alongside the existing GeoLite2-City `.mmdb` | Same out-of-band supply mechanism already documented in `backend/geoip_service.py` — drop at a sibling path (e.g. `backend/data/geoip/GeoIP2-Anonymous-IP.mmdb`) and add a second lazy reader following the exact pattern already used (`_get_reader`, graceful `None` on absence). |
| `mongosh` / migration script | One-time `db.createCollection(<name>, {timeseries: {timeField: "ts", metaField: "agent_id", granularity: "minutes"}})` for any new v3.3 time-series collection | Time-series collections must be created with the `timeseries` option at creation time — they cannot be converted from an existing regular collection in place. Add as a new numbered migration (following the `002_scale_indexes.py` convention), do not touch `agent_metrics_history`. |

## Installation

```bash
# Core — fleet geo map (frontend)
npm install react-simple-maps d3-geo topojson-client world-atlas supercluster
npm install -D @types/react-simple-maps @types/d3-geo @types/topojson-client @types/supercluster

# recharts already installed (^3.5.1) — no action needed unless bumping to 3.10.1
```

```bash
# Backend — no new pip packages required.
# maxminddb>=2.5.0 (already in requirements.txt) reads GeoIP2 Anonymous IP .mmdb
# identically to how it reads GeoLite2-City.mmdb — same reader, different file.
```

If escalating to MapLibre later:

```bash
npm install maplibre-gl react-map-gl pmtiles supercluster
# plus a one-time offline build step to generate/trim a low-zoom .pmtiles basemap
# and self-host style.json + sprite + glyph assets under the existing static server.
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `react-simple-maps` (pure SVG, bundled TopoJSON) | `maplibre-gl` + self-hosted PMTiles/tileserver-gl | Use MapLibre when the fleet map needs to support real interactive pan/zoom into dense clusters at street/neighborhood level, or the roadmap anticipates tens of thousands of agents needing a proper slippy-map UX. It's fully air-gapped-viable too, just more integration work (self-hosted style/sprite/glyphs + a custom trimmed basemap build). |
| `react-simple-maps` | `react-leaflet` + self-hosted raster tiles or Leaflet.VectorGrid | Leaflet is mature and MIT-licensed, but its offline vector-tile story (VectorGrid plugin) is less actively maintained than MapLibre's native vector pipeline, and its raster-tile path means pre-rendering and shipping actual map images. Only reach for Leaflet if the team has existing Leaflet expertise/investment elsewhere in the codebase (it does not currently). |
| MaxMind GeoIP2 Anonymous IP (paid) | GeoLite2-ASN (free) + `X4BNet/lists_vpn` heuristic | Use the free tier if there's no budget for a second MaxMind commercial database. Accept weaker signal (no residential-proxy/Tor granularity, ASN-name substring matching is fuzzier than MaxMind's own classification) in exchange for $0 cost. |
| MongoDB native time-series collection (new collection, new data only) | Keep everything in `agent_metrics_history` as-is | Correct choice **for the existing collection** — it already has a working TTL + app-cap pattern; don't touch it. Only introduce a time-series collection for genuinely new v3.3 telemetry (e.g. rolled-up uptime-percentage series) where the existing 100-snapshot-per-agent cap doesn't give enough history depth for the requested charts. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Any tile provider requiring a live internet connection at runtime (Mapbox-hosted tiles, Google Maps JS API, OpenStreetMap public tile servers, `{s}.tile.openstreetmap.org`) | Breaks air-gapped deployments outright — the milestone explicitly calls this out as a hard requirement | `react-simple-maps` with a bundled TopoJSON (primary), or MapLibre + self-hosted PMTiles (escalation path) |
| Third-party VPN/IP-intel **web APIs** (IPQualityScore, ipinfo.io privacy API, IP2Proxy web service, AbuseIPDB) called per-lookup | All require live outbound HTTPS calls per IP lookup — same air-gapped violation as hosted map tiles | MaxMind GeoIP2 Anonymous IP `.mmdb` (downloaded once, read locally) or the free `X4BNet/lists_vpn` snapshot pulled out-of-band |
| Converting `agent_metrics_history` into a time-series collection in place | MongoDB cannot convert an existing regular collection into a time-series collection without a full rebuild/migration+backfill; the milestone explicitly says reuse, don't rebuild, existing heartbeat/ETW telemetry | Leave `agent_metrics_history` untouched; add a new time-series collection only for new v3.3 rollup data if/when the existing cap proves insufficient |
| MaxMind GeoLite2-ASN alone as a "VPN detector" | It returns ASN/AS-org name only — no VPN/hosting/proxy boolean fields exist in that database; treating raw ASN name matching as authoritative VPN detection will both over- and under-flag | GeoIP2 Anonymous IP (paid, purpose-built) or GeoLite2-ASN + a maintained hosting/VPN ASN-name list, clearly labeled as a heuristic, not a hard flag |

## Stack Patterns by Variant

**If the fleet map only needs country/city-level dots with clustering and filters (matches the stated v3.3 scope):**
- Use `react-simple-maps` + `d3-geo` + `topojson-client` + bundled `world-atlas` TopoJSON + `supercluster`
- Because it is zero-infrastructure, zero-network-call, and matches the existing lightweight frontend stack (no new backend endpoints beyond what already returns `geo` on agent/asset docs)

**If a future milestone wants true street-level interactive zoom/pan (not currently in scope):**
- Escalate to `maplibre-gl` + `react-map-gl` + self-hosted PMTiles basemap + self-hosted style/sprite/glyphs
- Because MapLibre is the only one of the three options that supports smooth GPU-accelerated pan/zoom into real basemap detail while still being fully self-hostable

**If budget allows a second MaxMind commercial database:**
- Use GeoIP2 Anonymous IP for VPN/proxy/hosting flags
- Because it is purpose-built, offline, and reuses the exact reader/pattern already in `backend/geoip_service.py`

**If there is no budget for a second commercial MaxMind database:**
- Use free GeoLite2-ASN + `X4BNet/lists_vpn` snapshot, clearly labeled in the UI as a heuristic/best-effort flag (not a hard VPN determination)
- Because it costs nothing and still works fully offline once the list is pulled out-of-band

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `react-simple-maps@3.0.0` | React 19.2.0 (project's current React version) | No official React 19 support declared by the upstream package (last published 2023); works in practice via d3-geo/topojson-client with no React-version-specific code, but if peer-dependency warnings during install are a blocker, use the community fork `react19-simple-maps` (or `@vnedyalk0v/react19-simple-maps`) instead — same API. |
| `maxminddb>=2.5.0` (already pinned) | GeoIP2 Anonymous IP `.mmdb` format | Same reader works for GeoLite2-City, GeoLite2-ASN, and GeoIP2 Anonymous IP — MaxMind DB format is generic; no new Python dependency needed to add the second database. |
| MongoDB time-series collections | MongoDB >= 5.0 (server running 8.0.26) | Time-series collections cannot be capped and cannot be converted in-place from a regular collection — must be created fresh via `createCollection(..., timeseries={...})` at migration time. |
| `supercluster@8.0.1` | Any map renderer (SVG, MapLibre, Leaflet) | Pure geospatial/JS, no map-library dependency — safe to adopt now with `react-simple-maps` and reuse unchanged if the map layer is swapped later. |

## Sources

- npm registry (`npm view <pkg> version`, direct query 2026-07-29) — confirmed current versions: `maplibre-gl@6.0.0`, `react-simple-maps@3.0.0`, `d3-geo@3.1.1`, `topojson-client@3.1.0`, `world-atlas@2.0.2`, `supercluster@8.0.1`, `pmtiles@4.4.1`, `react-map-gl@8.1.1`, `leaflet@1.9.4`, `react-leaflet@5.0.0`, `recharts@3.10.1` — HIGH confidence (primary registry source)
- PyPI (`pip index versions` / registry JSON, direct query 2026-07-29) — `maxminddb@3.1.1` (project pins `>=2.5.0`), `geoip2@5.3.0` (official MaxMind Python wrapper, optional) — HIGH confidence
- dev.maxmind.com/geoip/docs/databases/anonymous-ip/ and maxmind.com/en/geoip-anonymous-ip-database — GeoIP2 Anonymous IP field list (`is_anonymous_vpn`, `is_hosting_provider`, `is_public_proxy`, `is_residential_proxy`, `is_tor_exit_node`) — MEDIUM confidence (official vendor docs surfaced via web search, not fetched raw)
- maxmind.com/en/geolite/eula and dev.maxmind.com/geoip/geolite2-free-geolocation-data — GeoLite2-ASN free tier, license-key + attribution requirement — MEDIUM confidence
- github.com/X4BNet/lists_vpn — free VPN/datacenter IP list, GitHub-Actions auto-rebuilt — MEDIUM confidence
- mongodb.com/docs/manual/core/timeseries-collections/ and mongodb.com/docs/v8.2/core/timeseries-collections/ — time-series vs capped collection guidance, compression/query benefits — MEDIUM confidence
- maplibre.org/maplibre-gl-js/docs/, github.com/maplibre/maplibre-gl-js, github.com/maplibre/demotiles, keimaps.com self-hosted-basemap articles — self-hosted/offline MapLibre + PMTiles pattern — MEDIUM confidence
- npmjs.com/package/react-simple-maps, react-simple-maps.io, github.com/zcreativelabs/react-simple-maps — SVG/TopoJSON approach, staleness of upstream release, React-19 fork existence — MEDIUM confidence
- Codebase inspection (`backend/geoip_service.py`, `backend/agent_heartbeat_endpoints.py`, `backend/migrations/002_scale_indexes.py`, `backend/database.py`, `package.json`, live `mongod --version` = 8.0.26) — HIGH confidence (direct source read)

---
*Stack research for: Agent Geo & Fleet Observability (v3.3)*
*Researched: 2026-07-29*
