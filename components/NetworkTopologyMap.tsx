import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { Activity, AlertCircle, Maximize, Shuffle, X, ZoomIn, ZoomOut } from 'lucide-react';
import * as api from '../services/apiService';
import { socketService } from '../services/socketService';
import { ThemeContext } from '../contexts/ThemeContext';
import { Skeleton } from './ui/skeleton';
import { ghostButton, useLiveData } from './network/NetworkKit';
import { buildTopologyElements, formatRate, topologyStats, withLiveTraffic, type LiveRate } from './network/networkData';
import { fetchTraffic, type RangeKey } from './network/opsData';
import { RX, TX } from './network/ops/OpsKpis';
import { rowMatches, topDestinations, topologyRows, zoneShares } from './network/topologyData';
import { LINK_LEGEND, ROLE_LEGEND, TOPOLOGY_LAYOUT, topologyStylesheet } from './network/topologyStyle';
import { TopologyInspector, type Connection, type Neighbour } from './network/TopologyInspector';
import { prefersReducedMotion, useTopologyMotion } from './network/useTopologyMotion';
import { TopologyHeader } from './network/topology/TopologyHeader';
import { TopologyKpis } from './network/topology/TopologyKpis';
import { ZoneBreakdown } from './network/topology/ZoneBreakdown';
import { NodeTable } from './network/topology/NodeTable';

cytoscape.use(coseBilkent);

interface NetworkTopologyMapProps {
    refreshKey: number;
}

// Agents re-collect metrics about once a minute and beat every 20-40 s; the socket pushes each new
// rate as it is measured, and this poll picks up new endpoints, gateways and connections.
const POLL_MS = 15_000;
// Trend lines in the tiles (GET /api/network-devices/traffic) move slower than the map.
const TREND_POLL_MS = 60_000;
const RANGE_LABEL: Record<RangeKey, string> = { '15m': '15 minutes', '1h': 'hour', '6h': '6 hours', '24h': '24 hours' };
// The map and the panel beside it share one height on wide screens.
const MAP_HEIGHT = 'h-[clamp(28rem,62vh,46rem)]';
const SIDE_HEIGHT = 'xl:h-[clamp(28rem,62vh,46rem)]';

const fetchTopology = async () => {
    const res = await api.authFetch('/api/network-devices/topology');
    if (!res.ok) throw new Error(`Could not load the topology (HTTP ${res.status})`);
    return buildTopologyElements(await res.json());
};

// Fit the graph, but never blow a small one up past 125%.
const fitView = (cy: cytoscape.Core) => {
    cy.fit(undefined, 56);
    if (cy.zoom() > 1.25) { cy.zoom(1.25); cy.center(); }
};

// A force layout has no preferred direction: turn a tall graph on its side in a wide view (and a
// wide one upright in a tall view), so the fit can zoom in further.
const orientToView = (cy: cytoscape.Core) => {
    const bb = cy.elements().boundingBox();
    if (!bb.w || !bb.h || (bb.w >= bb.h) === (cy.width() >= cy.height())) return;
    cy.nodes().not(':parent').positions((n: any) => ({ x: n.position('y'), y: n.position('x') }));
};

// Layouts that end in a fit run without animation, so the turn and the fit land in the same frame.
const FIT_LAYOUT = { ...TOPOLOGY_LAYOUT, animate: false };

const overlay = 'bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm';
const hudButton = 'grid place-items-center h-8 w-8 rounded-lg text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.08]';

export const NetworkTopologyMap: React.FC<NetworkTopologyMapProps> = ({ refreshKey }) => {
    const dark = useContext(ThemeContext).theme === 'dark';
    const live = useLiveData(fetchTopology, POLL_MS);
    const { refresh } = live;
    const [range, setRange] = useState<RangeKey>('1h');
    const trendFetcher = useCallback(() => fetchTraffic(api.authFetch, range), [range]);
    const trend = useLiveData(trendFetcher, TREND_POLL_MS);
    const [paused, setPaused] = useState(false);
    const [pushed, setPushed] = useState<Record<string, LiveRate>>({});
    const [now, setNow] = useState(Date.now());
    const [zone, setZone] = useState('');
    const [query, setQuery] = useState('');
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [streamUp, setStreamUp] = useState(socketService.connected);
    const cyRef = useRef<cytoscape.Core | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const mapRef = useRef<HTMLElement>(null);
    const layoutKeyRef = useRef<string | null>(null);
    const fitNextRef = useRef(true);
    const pausedRef = useRef(paused);
    pausedRef.current = paused;
    const { pulse } = useTopologyMotion(cyRef, canvasRef, dark);

    useEffect(() => { if (refreshKey) refresh(); }, [refreshKey, refresh]);

    // Pause stops both polls; pushed rates are ignored below while paused.
    const { setPaused: pauseMap } = live;
    const { setPaused: pauseTrend, refresh: refreshTrend } = trend;
    useEffect(() => { pauseMap(paused); pauseTrend(paused); }, [paused, pauseMap, pauseTrend]);

    // A new trend range loads at once (the first load is useLiveData's own).
    const firstRange = useRef(true);
    useEffect(() => {
        if (firstRange.current) { firstRange.current = false; return; }
        refreshTrend();
    }, [range, refreshTrend]);

    const elements = useMemo(() => withLiveTraffic(live.data ?? [], pushed, now), [live.data, pushed, now]);
    const stylesheet = useMemo(() => topologyStylesheet(dark), [dark]);
    const stats = useMemo(() => topologyStats(elements, now), [elements, now]);
    const rows = useMemo(() => topologyRows(elements, now), [elements, now]);
    const zones = useMemo(() => zoneShares(rows), [rows]);
    const destinations = useMemo(() => topDestinations(elements), [elements]);
    const visibleRows = useMemo(() => rows.filter(r => (!zone || r.zone === zone) && rowMatches(r, query)), [rows, zone, query]);
    const graphKey = useMemo(() => elements.map(e => e.data?.id).sort().join('|'), [elements]);
    const byId = useMemo(() => new Map(elements.map(e => [e.data?.id, e.data])), [elements]);
    const selected = selectedId ? byId.get(selectedId) : null;
    const filtering = !!zone || !!query.trim();
    const focusKey = filtering ? visibleRows.map(r => r.id).join('|') : '';

    // An endpoint's outbound connections are listed apart from the links it sits on.
    const neighboursOf = useCallback((id: string): Neighbour[] => elements
        .filter(e => (e.data?.source === id || e.data?.target === id) && !(e.data.kind === 'flow' && e.data.source === id))
        .map(e => byId.get(e.data.source === id ? e.data.target : e.data.source))
        .filter(Boolean)
        .map((d: any) => ({ id: d.id, label: d.label, ip: d.ip, status: d.status })), [elements, byId]);

    const connectionsOf = useCallback((id: string): Connection[] => elements
        .filter(e => e.data?.kind === 'flow' && e.data.source === id && byId.has(e.data.target))
        .map(e => ({ id: e.data.target, label: byId.get(e.data.target).label, ports: e.data.ports || [], processes: e.data.processes || [], connections: e.data.connections || 0 })),
    [elements, byId]);

    // New nodes or links: arrange again from the current positions, keeping the viewer's zoom.
    useEffect(() => {
        const cy = cyRef.current;
        if (!cy || cy.destroyed()) return;
        if (layoutKeyRef.current === null || layoutKeyRef.current === graphKey) { layoutKeyRef.current = graphKey; return; }
        layoutKeyRef.current = graphKey;
        fitNextRef.current = false;
        cy.layout({ ...TOPOLOGY_LAYOUT, randomize: false, fit: false } as any).run();
    }, [graphKey]);

    // A selection highlights its neighbourhood; otherwise the zone and search filters fade the rest.
    useEffect(() => {
        const cy = cyRef.current;
        if (!cy || cy.destroyed()) return;
        cy.batch(() => {
            cy.elements().removeClass('faded hl');
            cy.elements().unselect();
            if (selectedId) {
                const node = cy.getElementById(selectedId);
                if (node.empty()) return;
                node.select();
                const near = node.closedNeighborhood();
                cy.elements().not(near.union(near.nodes().ancestors())).addClass('faded');
                node.connectedEdges().addClass('hl');
                return;
            }
            if (!focusKey && !filtering) return;
            const ids = new Set(focusKey.split('|'));
            const keep = cy.nodes().filter(n => ids.has(n.id()));
            cy.elements().not(keep.union(keep.ancestors()).union(keep.edgesWith(keep))).addClass('faded');
        });
    }, [selectedId, graphKey, focusKey, filtering]);

    useEffect(() => { if (selectedId && !byId.has(selectedId)) setSelectedId(null); }, [byId, selectedId]);

    useEffect(() => {
        if (!selectedId) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelectedId(null); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [selectedId]);

    useEffect(() => {
        // A new rate measured on an agent's heartbeat (backend network_rate.py).
        const onEndpointTraffic = (ev: any) => {
            if (pausedRef.current) return;
            if (!ev?.agentId || typeof ev.sentBps !== 'number' || typeof ev.recvBps !== 'number' || !ev.at) return;
            setPushed(p => ({ ...p, [ev.agentId]: { sentBps: ev.sentBps, recvBps: ev.recvBps, at: ev.at, windowSeconds: ev.windowSeconds } }));
            const cy = cyRef.current;
            if (!cy || cy.destroyed()) return;
            const nodeId = `agent-${ev.agentId}`;
            cy.getElementById(nodeId).connectedEdges('[kind = "uplink"]').forEach(edge => {
                const gateway = edge.source().id() === nodeId ? edge.target().id() : edge.source().id();
                if (ev.recvBps > 0) pulse(gateway, nodeId);
                if (ev.sentBps > 0) pulse(nodeId, gateway);
            });
        };
        // A single flow between two addresses, from a flow source (none sends these yet).
        const onFlow = (ev: any) => {
            const cy = cyRef.current;
            if (pausedRef.current || !cy || cy.destroyed()) return;
            // Match on data, not a selector string: an address must never be parsed as selector syntax.
            const src = cy.nodes().filter(n => n.data('ip') === ev?.source);
            const dst = cy.nodes().filter(n => n.data('ip') === ev?.target);
            if (!src.empty() && !dst.empty()) pulse(src[0].id(), dst[0].id(), ev?.status === 'blocked');
        };
        socketService.on('endpoint_traffic', onEndpointTraffic);
        socketService.on('network_traffic', onFlow);
        const tick = setInterval(() => { setNow(Date.now()); setStreamUp(socketService.connected); }, 5000);
        return () => {
            socketService.off('endpoint_traffic', onEndpointTraffic);
            socketService.off('network_traffic', onFlow);
            clearInterval(tick);
        };
    }, [pulse]);

    const zoomBy = (factor: number) => {
        const cy = cyRef.current;
        if (!cy) return;
        cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    };

    // Opening a node from the table brings the map (and its highlight) back into view.
    const openNode = useCallback((id: string) => {
        setSelectedId(id);
        mapRef.current?.scrollIntoView?.({ block: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
    }, []);

    const endpointsUp = rows.filter(r => r.group === 'Endpoints' && r.status !== 'Down').length;
    const down = rows.filter(r => r.status === 'Down').length;
    const notMeasured = rows.filter(r => r.status === 'Not measured').length;
    const summary = live.data
        ? `${rows.length} nodes · ${stats.links} links · ${endpointsUp} endpoint${endpointsUp === 1 ? '' : 's'} online · refresh ${POLL_MS / 1000} s`
        : 'Loading the map…';

    return (
        <div className="space-y-3 pb-6">
            <TopologyHeader
                summary={summary}
                updatedAt={live.updatedAt}
                error={live.error}
                streamUp={streamUp}
                pollSeconds={POLL_MS / 1000}
                paused={paused}
                onTogglePause={() => setPaused(p => !p)}
                onRefresh={() => { refresh(); refreshTrend(); }}
                refreshing={live.loading}
                range={range}
                onRange={setRange}
                zones={zones.map(z => z.zone).sort()}
                zone={zone}
                onZone={setZone}
                query={query}
                onQuery={setQuery}
                down={down}
                notMeasured={notMeasured}
                hasData={!!live.data}
            />

            {live.error && !live.data ? (
                <div role="alert" className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-5 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" aria-hidden="true" />
                    <div className="flex-1">
                        <p className="font-medium text-red-800 dark:text-red-200">The topology could not be loaded</p>
                        <p className="mt-1 text-sm text-red-700 dark:text-red-300">{live.error}</p>
                    </div>
                    <button type="button" onClick={refresh} className={ghostButton}>Try again</button>
                </div>
            ) : (
                <>
                    {live.data
                        ? <TopologyKpis rows={rows} totals={stats} traffic={trend.data} range={range} rangeLabel={RANGE_LABEL[range]} />
                        : <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3" aria-busy="true">{[0, 1, 2, 3].map(i => <Skeleton key={i} variant="card" height={136} />)}</div>}

                    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,65fr)_minmax(0,35fr)] gap-3">
                        <section ref={mapRef} aria-labelledby="topology-map-title"
                            className={`${MAP_HEIGHT} flex flex-col rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-w-0`}>
                            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 pt-3.5 pb-2.5">
                                <div className="flex items-baseline gap-3 min-w-0">
                                    <h2 id="topology-map-title" className="text-[15px] font-semibold text-gray-900 dark:text-white">Map</h2>
                                    <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                        {stats.zones} zones · {stats.segments} VLANs · drag to pan, scroll to zoom
                                    </span>
                                </div>
                                <dl className="flex items-center gap-4 font-mono text-[12px]" title={streamUp ? 'New rates arrive as soon as agents report them' : `Rates refresh every ${POLL_MS / 1000} s`}>
                                    {[{ s: RX, name: 'Rx', v: stats.recvBps }, { s: TX, name: 'Tx', v: stats.sentBps }].map(({ s, name, v }) => (
                                        <div key={name} className="flex items-center gap-1.5">
                                            <dt className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400"><span className={`h-0.5 w-3.5 rounded-full ${s.bg}`} aria-hidden="true" />{name}</dt>
                                            <dd className="tabular-nums font-semibold text-gray-900 dark:text-white">{stats.measured ? formatRate(v) : '—'}</dd>
                                        </div>
                                    ))}
                                </dl>
                            </div>

                            <div className="relative flex-1 min-h-0 mx-3 mb-3 rounded-xl overflow-hidden border border-gray-100 dark:border-white/[0.05] bg-gray-50/70 dark:bg-gray-950/40">
                                <div className="absolute inset-0 opacity-60 dark:opacity-40 pointer-events-none [background-image:radial-gradient(rgb(var(--space-400)/0.35)_1px,transparent_1px)] [background-size:22px_22px]" aria-hidden="true" />
                                {!live.data && (
                                    <div className="absolute inset-0 z-20 grid place-items-center" aria-busy="true">
                                        <Activity className="w-10 h-10 text-primary-500 animate-pulse" aria-label="Loading the topology" />
                                    </div>
                                )}
                                {live.data && (
                                    <CytoscapeComponent
                                        elements={elements}
                                        style={{ width: '100%', height: '100%', position: 'relative' }}
                                        stylesheet={stylesheet}
                                        minZoom={0.2}
                                        maxZoom={3}
                                        cy={(cy: any) => {
                                            if (cyRef.current === cy) return;
                                            cyRef.current = cy;
                                            layoutKeyRef.current = null;
                                            fitNextRef.current = true;
                                            cy.on('tap', 'node', (evt: any) => { if (!evt.target.data('isZone')) setSelectedId(evt.target.id()); });
                                            cy.on('tap', (evt: any) => { if (evt.target === cy) setSelectedId(null); });
                                            cy.on('layoutstop', () => { if (fitNextRef.current) { orientToView(cy); fitView(cy); } });
                                            // The first layout runs here, after the listeners, rather than from a layout prop
                                            // (which the component runs before handing over the instance).
                                            cy.layout(FIT_LAYOUT as any).run();
                                        }}
                                    />
                                )}
                                <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none z-10 w-full h-full" aria-hidden="true" />

                                {filtering && !selected && (
                                    <div className={`absolute top-3 left-3 z-20 inline-flex items-center gap-2 h-8 pl-3 pr-1 rounded-lg text-xs font-medium text-gray-700 dark:text-gray-300 ${overlay}`}>
                                        <span className="tabular-nums">Showing {visibleRows.length} of {rows.length} nodes</span>
                                        <button type="button" onClick={() => { setZone(''); setQuery(''); }} aria-label="Clear the zone and search filters" className="grid place-items-center h-6 w-6 rounded-md hover:bg-gray-100 dark:hover:bg-white/[0.08]">
                                            <X className="w-3.5 h-3.5" aria-hidden="true" />
                                        </button>
                                    </div>
                                )}

                                <div role="toolbar" aria-label="Map controls" className={`absolute top-3 right-3 z-20 flex flex-col p-1 rounded-xl ${overlay}`}>
                                    <button type="button" className={hudButton} onClick={() => zoomBy(1.25)} aria-label="Zoom in" title="Zoom in"><ZoomIn className="w-4 h-4" aria-hidden="true" /></button>
                                    <button type="button" className={hudButton} onClick={() => zoomBy(0.8)} aria-label="Zoom out" title="Zoom out"><ZoomOut className="w-4 h-4" aria-hidden="true" /></button>
                                    <button type="button" className={hudButton} onClick={() => cyRef.current && fitView(cyRef.current)} aria-label="Fit to screen" title="Fit to screen"><Maximize className="w-4 h-4" aria-hidden="true" /></button>
                                    <button type="button" className={hudButton} aria-label="Arrange again" title="Arrange again"
                                        onClick={() => { fitNextRef.current = true; cyRef.current?.layout(FIT_LAYOUT as any).run(); }}>
                                        <Shuffle className="w-4 h-4" aria-hidden="true" />
                                    </button>
                                </div>

                                {live.data && stats.endpoints === 0 && stats.devices === 0 && (
                                    <div className={`absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[min(30rem,calc(100%-2rem))] rounded-xl px-4 py-3 text-center pointer-events-none ${overlay}`}>
                                        <p className="text-sm font-medium text-gray-800 dark:text-gray-100">No endpoints or devices yet</p>
                                        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">Endpoints appear when their agents check in; other devices when a network scan or an endpoint's neighbour table finds them.</p>
                                    </div>
                                )}

                                <ul aria-label="Legend" className={`absolute bottom-3 left-3 z-20 flex flex-wrap items-center gap-x-4 gap-y-1.5 w-fit max-w-[calc(100%-1.5rem)] px-3 py-2 rounded-xl text-[11px] text-gray-600 dark:text-gray-300 ${overlay}`}>
                                    {ROLE_LEGEND.map(r => (
                                        <li key={r.group} className="flex items-center gap-1.5"><span className={`h-3 w-3 rounded-[4px] border-2 ${r.swatch}`} aria-hidden="true" />{r.label}</li>
                                    ))}
                                    <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-[4px] border-2 border-dashed border-[#d03b3b]" aria-hidden="true" />Down</li>
                                    <li className="flex items-center gap-1.5"><span className={`w-5 border-t-2 border-dashed ${LINK_LEGEND.live}`} aria-hidden="true" />Live transfer</li>
                                    <li className="flex items-center gap-1.5"><span className={`w-5 border-t-2 border-dotted ${LINK_LEGEND.connection}`} aria-hidden="true" />Latest connection</li>
                                </ul>
                            </div>
                        </section>

                        <div className={`min-w-0 ${SIDE_HEIGHT}`}>
                            {selected ? (
                                <TopologyInspector node={selected} neighbours={neighboursOf(selected.id)} connections={connectionsOf(selected.id)}
                                    onSelect={setSelectedId} onClose={() => setSelectedId(null)} />
                            ) : live.data ? (
                                <ZoneBreakdown zones={zones} zone={zone} onZone={setZone} destinations={destinations} onOpen={setSelectedId} />
                            ) : <Skeleton variant="card" height="100%" className="min-h-[16rem]" />}
                        </div>
                    </div>

                    {live.data && <NodeTable rows={visibleRows} selectedId={selectedId} onOpen={openNode} now={now} />}

                    <footer className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
                        <span>{rows.length} nodes · {stats.links} links tracked · a rate counts as live for 5 min · map refresh {POLL_MS / 1000} s{paused ? ' · paused' : ''}</span>
                        <span>Rates: agent heartbeats · neighbours: agent ARP tables · connections: agent Web Monitor</span>
                    </footer>
                </>
            )}
        </div>
    );
};
