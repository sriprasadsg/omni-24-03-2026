import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { Activity, AlertCircle, ArrowUpDown, LayoutGrid, Laptop, List, Maximize, Shuffle, ZoomIn, ZoomOut } from 'lucide-react';
import * as api from '../services/apiService';
import { socketService } from '../services/socketService';
import { ThemeContext } from '../contexts/ThemeContext';
import { PageHeader, LiveStatus, ghostButton, useLiveData } from './network/NetworkKit';
import { buildTopologyElements, formatRate, isDeviceNode, isDown, isFreshRate, topologyStats, withLiveTraffic, type LiveRate } from './network/networkData';
import { LINK_LEGEND, ROLE_LEGEND, TOPOLOGY_LAYOUT, topologyStylesheet } from './network/topologyStyle';
import { TopologyInspector, type Connection, type Neighbour } from './network/TopologyInspector';
import { useTopologyMotion } from './network/useTopologyMotion';

cytoscape.use(coseBilkent);

interface NetworkTopologyMapProps {
    refreshKey: number;
}

// Agents re-collect metrics about once a minute and beat every 20-40 s; the socket pushes each new
// rate as it is measured, and this poll picks up new endpoints, gateways and connections.
const POLL_MS = 15_000;

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

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

const hudChipBase = 'inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm';
const hudChip = `${hudChipBase} text-gray-700 dark:text-gray-300`;
const hudButton = 'grid place-items-center h-8 w-8 rounded-lg text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.08]';

export const NetworkTopologyMap: React.FC<NetworkTopologyMapProps> = ({ refreshKey }) => {
    const dark = useContext(ThemeContext).theme === 'dark';
    const live = useLiveData(fetchTopology, POLL_MS);
    const { refresh } = live;
    const [pushed, setPushed] = useState<Record<string, LiveRate>>({});
    const [now, setNow] = useState(Date.now());
    const [view, setView] = useState<'graph' | 'list'>('graph');
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [streamUp, setStreamUp] = useState(socketService.connected);
    const cyRef = useRef<cytoscape.Core | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const layoutKeyRef = useRef<string | null>(null);
    const fitNextRef = useRef(true);
    const { pulse } = useTopologyMotion(cyRef, canvasRef, dark);

    useEffect(() => { if (refreshKey) refresh(); }, [refreshKey, refresh]);

    const elements = useMemo(() => withLiveTraffic(live.data ?? [], pushed, now), [live.data, pushed, now]);
    const stylesheet = useMemo(() => topologyStylesheet(dark), [dark]);
    const stats = useMemo(() => topologyStats(elements, now), [elements, now]);
    const graphKey = useMemo(() => elements.map(e => e.data?.id).sort().join('|'), [elements]);
    const byId = useMemo(() => new Map(elements.map(e => [e.data?.id, e.data])), [elements]);
    const selected = selectedId ? byId.get(selectedId) : null;

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

    // List order: endpoints first, then the network around them, then what the map adds itself.
    const devices = useMemo(() => {
        const rank: Record<string, number> = { agent: 0, gateway: 1, device: 2, neighbour: 3, remote: 4, placeholder: 5, internet: 6 };
        return elements.map(e => e.data).filter(d => d && !d.isZone && !d.isVlan && !d.source)
            .sort((a, b) => (rank[a.kind] ?? 2) - (rank[b.kind] ?? 2) || String(a.label).localeCompare(String(b.label)));
    }, [elements]);

    // New nodes or links: arrange again from the current positions, keeping the viewer's zoom.
    useEffect(() => {
        const cy = cyRef.current;
        if (!cy || cy.destroyed() || view !== 'graph') return;
        if (layoutKeyRef.current === null || layoutKeyRef.current === graphKey) { layoutKeyRef.current = graphKey; return; }
        layoutKeyRef.current = graphKey;
        fitNextRef.current = false;
        cy.layout({ ...TOPOLOGY_LAYOUT, randomize: false, fit: false } as any).run();
    }, [graphKey, view]);

    // Selection drives the neighbourhood highlight on the graph.
    useEffect(() => {
        const cy = cyRef.current;
        if (!cy || cy.destroyed()) return;
        cy.batch(() => {
            cy.elements().removeClass('faded hl');
            cy.elements().unselect();
            if (!selectedId) return;
            const node = cy.getElementById(selectedId);
            if (node.empty()) return;
            node.select();
            const near = node.closedNeighborhood();
            cy.elements().not(near.union(near.nodes().ancestors())).addClass('faded');
            node.connectedEdges().addClass('hl');
        });
    }, [selectedId, graphKey, view]);

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
            if (!cy || cy.destroyed()) return;
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

    const transferText = stats.measured
        ? `↑ ${formatRate(stats.sentBps)}   ↓ ${formatRate(stats.recvBps)}`
        : 'No transfer measured in the last 5 min';

    return (
        <div className="space-y-4 pb-6">
            <PageHeader
                title="Network Topology"
                subtitle="Endpoints, the network around them, their latest connections and live transfer"
                status={<LiveStatus updatedAt={live.updatedAt} error={live.error} />}
                onRefresh={refresh}
                refreshing={live.loading}
            >
                <div role="group" aria-label="View" className="inline-flex h-9 p-0.5 rounded-xl border border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800">
                    {([['graph', 'Map', LayoutGrid], ['list', 'List', List]] as const).map(([key, label, Icon]) => (
                        <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}
                            className={`inline-flex items-center gap-1.5 px-3 rounded-[10px] text-sm font-medium transition-colors ${view === key
                                ? 'bg-primary-500/10 text-primary-700 dark:text-primary-300'
                                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}>
                            <Icon className="w-4 h-4" aria-hidden="true" />{label}
                        </button>
                    ))}
                </div>
            </PageHeader>

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
                <div className="relative h-[calc(100vh-15rem)] min-h-[520px] rounded-2xl overflow-hidden border border-gray-200/80 dark:border-white/[0.07] bg-white dark:bg-gray-800 shadow-card">
                    {!live.data && (
                        <div className="absolute inset-0 z-20 grid place-items-center" aria-busy="true">
                            <Activity className="w-10 h-10 text-primary-500 animate-pulse" aria-label="Loading the topology" />
                        </div>
                    )}

                    {view === 'graph' ? (
                        <>
                            <div className="absolute inset-0 opacity-60 dark:opacity-40 pointer-events-none [background-image:radial-gradient(rgb(var(--space-400)/0.35)_1px,transparent_1px)] [background-size:22px_22px]" aria-hidden="true" />
                            {live.data && (
                                <CytoscapeComponent
                                    elements={elements}
                                    style={{ width: '100%', height: '100%', position: 'relative' }}
                                    stylesheet={stylesheet}
                                    layout={TOPOLOGY_LAYOUT}
                                    minZoom={0.2}
                                    maxZoom={3}
                                    cy={(cy: any) => {
                                        if (cyRef.current === cy) return;
                                        cyRef.current = cy;
                                        layoutKeyRef.current = null;
                                        fitNextRef.current = true;
                                        cy.on('tap', 'node', (evt: any) => { if (!evt.target.data('isZone')) setSelectedId(evt.target.id()); });
                                        cy.on('tap', (evt: any) => { if (evt.target === cy) setSelectedId(null); });
                                        cy.on('layoutstop', () => { if (fitNextRef.current) fitView(cy); });
                                    }}
                                />
                            )}
                            <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none z-10 w-full h-full" aria-hidden="true" />

                            <div className={`absolute top-3 left-3 z-20 flex flex-wrap gap-2 ${selected ? 'max-w-[calc(100%-27rem)]' : 'max-w-[calc(100%-5rem)]'}`}>
                                <span className={hudChip}><Laptop className="w-3.5 h-3.5 text-primary-500" aria-hidden="true" />{plural(stats.endpoints, 'endpoint')}</span>
                                {stats.devices > 0 && <span className={hudChip}>{plural(stats.devices, 'LAN device')}</span>}
                                {stats.remote > 0 && <span className={hudChip}>{plural(stats.remote, 'remote host')}</span>}
                                <span className={hudChip}>{plural(stats.links, 'link')}</span>
                                {stats.segments > 0 && <span className={hudChip}>{plural(stats.segments, 'VLAN')}</span>}
                                {stats.down > 0 && <span className={`${hudChipBase} text-red-700 dark:text-red-300`}>{stats.down} down</span>}
                                <span className={hudChip} title={streamUp ? 'New rates arrive as soon as agents report them' : `Rates refresh every ${POLL_MS / 1000} s`}>
                                    <ArrowUpDown className="w-3.5 h-3.5 text-primary-500" aria-hidden="true" />
                                    <span className="tabular-nums">{transferText}</span>
                                    <span className={`h-1.5 w-1.5 rounded-full ${streamUp ? 'bg-primary-500 dark:bg-primary-400' : 'bg-gray-400'}`} aria-hidden="true" />
                                </span>
                            </div>

                            <div role="toolbar" aria-label="Map controls" className={`absolute top-3 ${selected ? 'right-[21.75rem]' : 'right-3'} z-20 flex flex-col p-1 rounded-xl bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm`}>
                                <button type="button" className={hudButton} onClick={() => zoomBy(1.25)} aria-label="Zoom in" title="Zoom in"><ZoomIn className="w-4 h-4" aria-hidden="true" /></button>
                                <button type="button" className={hudButton} onClick={() => zoomBy(0.8)} aria-label="Zoom out" title="Zoom out"><ZoomOut className="w-4 h-4" aria-hidden="true" /></button>
                                <button type="button" className={hudButton} onClick={() => cyRef.current && fitView(cyRef.current)} aria-label="Fit to screen" title="Fit to screen"><Maximize className="w-4 h-4" aria-hidden="true" /></button>
                                <button type="button" className={hudButton} aria-label="Arrange again" title="Arrange again"
                                    onClick={() => { fitNextRef.current = true; cyRef.current?.layout(TOPOLOGY_LAYOUT as any).run(); }}>
                                    <Shuffle className="w-4 h-4" aria-hidden="true" />
                                </button>
                            </div>

                            {live.data && stats.endpoints === 0 && stats.devices === 0 && (
                                <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[min(30rem,calc(100%-2rem))] rounded-xl bg-white/90 dark:bg-gray-900/80 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm px-4 py-3 text-center pointer-events-none">
                                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100">No endpoints or devices yet</p>
                                    <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">Endpoints appear when their agents check in; other devices when a network scan or an endpoint's neighbour table finds them.</p>
                                </div>
                            )}

                            <ul aria-label="Legend" className="absolute bottom-3 left-3 right-3 z-20 flex flex-wrap items-center gap-x-4 gap-y-1.5 w-fit max-w-[calc(100%-1.5rem)] px-3 py-2 rounded-xl bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm text-xs text-gray-600 dark:text-gray-300">
                                {ROLE_LEGEND.map(r => (
                                    <li key={r.group} className="flex items-center gap-1.5"><span className={`h-3 w-3 rounded-[4px] border-2 ${r.swatch}`} aria-hidden="true" />{r.label}</li>
                                ))}
                                <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-[4px] border-2 border-dashed border-[#d03b3b]" aria-hidden="true" />Down</li>
                                <li className="flex items-center gap-1.5"><span className={`w-5 border-t-2 border-dashed ${LINK_LEGEND.live}`} aria-hidden="true" />Live transfer (moves with the measured rate)</li>
                                <li className="flex items-center gap-1.5"><span className={`w-5 border-t-2 border-dotted ${LINK_LEGEND.connection}`} aria-hidden="true" />Latest connection</li>
                            </ul>
                        </>
                    ) : (
                        <div className="absolute inset-0 overflow-auto">
                            <table className="w-full text-left text-sm">
                                <caption className="sr-only">Nodes on the network map</caption>
                                <thead className="sticky top-0 z-10 bg-white dark:bg-gray-800 text-[11px] font-semibold uppercase text-gray-500 dark:text-gray-400">
                                    <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                        {['Name', 'IP address', 'Zone', 'Role', 'VLAN', 'Status', 'Live transfer', 'Links'].map(h => <th key={h} scope="col" className="px-4 py-3">{h}</th>)}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                                    {devices.map(d => (
                                        <tr key={d.id} onClick={() => setSelectedId(d.id)}
                                            className={`cursor-pointer transition-colors hover:bg-gray-50/80 dark:hover:bg-white/[0.03] ${selectedId === d.id ? 'bg-primary-500/[0.06]' : ''}`}>
                                            <td className="px-4 py-3">
                                                {/* The row click is a mouse shortcut; this button is the keyboard and screen-reader path. */}
                                                <button type="button" onClick={e => { e.stopPropagation(); setSelectedId(d.id); }}
                                                    className="font-medium text-left text-gray-900 dark:text-white hover:text-primary-700 dark:hover:text-primary-300">
                                                    {String(d.label).split('\n')[0]}
                                                </button>
                                                {(d.kind === 'internet' || d.kind === 'placeholder') && <span className="ml-2 text-[11px] text-gray-500 dark:text-gray-400">added by the map</span>}
                                            </td>
                                            <td className="px-4 py-3 font-mono text-[13px] text-gray-700 dark:text-gray-300">{d.ip || '—'}</td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{d.zone || '—'}</td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{d.role || '—'}</td>
                                            <td className="px-4 py-3 font-mono text-[13px] text-gray-700 dark:text-gray-300">{d.vlanId || '—'}</td>
                                            <td className={`px-4 py-3 font-medium ${!isDeviceNode(d) ? 'text-gray-500 dark:text-gray-400' : isDown(d.status) ? 'text-red-700 dark:text-red-300' : 'text-green-700 dark:text-green-400'}`}>
                                                {!isDeviceNode(d) ? '—' : isDown(d.status) ? 'Down' : 'Up'}
                                            </td>
                                            <td className="px-4 py-3 tabular-nums text-gray-700 dark:text-gray-300 whitespace-nowrap">
                                                {isFreshRate(d.metrics, now) ? `↑ ${formatRate(d.metrics.sentBps)} · ↓ ${formatRate(d.metrics.recvBps)}` : '—'}
                                            </td>
                                            <td className="px-4 py-3 tabular-nums text-gray-700 dark:text-gray-300">{neighboursOf(d.id).length + connectionsOf(d.id).length}</td>
                                        </tr>
                                    ))}
                                    {devices.length === 0 && (
                                        <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">{live.data ? 'Nothing on the map yet.' : 'Loading…'}</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {selected && (
                        <TopologyInspector node={selected} neighbours={neighboursOf(selected.id)} connections={connectionsOf(selected.id)}
                            onSelect={setSelectedId} onClose={() => setSelectedId(null)} />
                    )}
                </div>
            )}
        </div>
    );
};
