import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { Activity, AlertCircle, LayoutGrid, List, Maximize, Network, Shuffle, ZoomIn, ZoomOut } from 'lucide-react';
import * as api from '../services/apiService';
import { socketService } from '../services/socketService';
import { ThemeContext } from '../contexts/ThemeContext';
import { PageHeader, LiveStatus, ghostButton, useLiveData } from './network/NetworkKit';
import { buildTopologyElements, isDeviceNode, isDown, topologyStats } from './network/networkData';
import { FLOW_COLORS, ROLE_LEGEND, TOPOLOGY_LAYOUT, topologyStylesheet } from './network/topologyStyle';
import { TopologyInspector, type Neighbour } from './network/TopologyInspector';

cytoscape.use(coseBilkent);

interface NetworkTopologyMapProps {
    refreshKey: number;
}

interface Packet { sourceId: string; targetId: string; progress: number; blocked: boolean }

const fetchTopology = async () => {
    const res = await api.authFetch('/api/network-devices/topology');
    if (!res.ok) throw new Error(`Could not load the topology (HTTP ${res.status})`);
    return buildTopologyElements(await res.json());
};

// Fit the graph, but never blow a small one (two nodes before any scan) up past 125%.
const fitView = (cy: cytoscape.Core) => {
    cy.fit(undefined, 56);
    if (cy.zoom() > 1.25) { cy.zoom(1.25); cy.center(); }
};

const reducedMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

const hudChipBase = 'inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm';
const hudChip = `${hudChipBase} text-gray-700 dark:text-gray-300`;
const hudButton = 'grid place-items-center h-8 w-8 rounded-lg text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.08]';

export const NetworkTopologyMap: React.FC<NetworkTopologyMapProps> = ({ refreshKey }) => {
    const dark = useContext(ThemeContext).theme === 'dark';
    const live = useLiveData(fetchTopology, 300_000);
    const { refresh } = live;
    const elements = useMemo(() => live.data ?? [], [live.data]);
    const [view, setView] = useState<'graph' | 'list'>('graph');
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [flowRate, setFlowRate] = useState(0);
    const [streamUp, setStreamUp] = useState(socketService.connected);
    const cyRef = useRef<cytoscape.Core | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const packetsRef = useRef<Packet[]>([]);
    const flowTimesRef = useRef<number[]>([]);
    const frameRef = useRef<number | undefined>(undefined);

    useEffect(() => { if (refreshKey) refresh(); }, [refreshKey, refresh]);

    const stylesheet = useMemo(() => topologyStylesheet(dark), [dark]);
    const stats = useMemo(() => topologyStats(elements), [elements]);
    // Remount (and lay out again) only when the set of nodes and links changes.
    const graphKey = useMemo(() => elements.map(e => e.data?.id).sort().join('|'), [elements]);
    const byId = useMemo(() => new Map(elements.map(e => [e.data?.id, e.data])), [elements]);
    const selected = selectedId ? byId.get(selectedId) : null;

    const neighboursOf = useCallback((id: string): Neighbour[] => elements
        .filter(e => e.data?.source === id || e.data?.target === id)
        .map(e => byId.get(e.data.source === id ? e.data.target : e.data.source))
        .filter(Boolean)
        .map((d: any) => ({ id: d.id, label: d.label, ip: d.ip, status: d.status })), [elements, byId]);

    const devices = useMemo(() => elements.map(e => e.data).filter(d => d && !d.isZone && !d.isVlan && !d.source), [elements]);

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

    // Live flows: drawn on a canvas over the graph, and the loop runs only while packets move.
    const draw = useCallback(() => {
        const cy = cyRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext('2d');
        if (!cy || cy.destroyed() || !canvas || !ctx) { frameRef.current = undefined; return; }
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        if (canvas.width !== Math.round(rect.width * dpr)) { canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr); }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, rect.width, rect.height);
        packetsRef.current = packetsRef.current.map(p => ({ ...p, progress: p.progress + 0.012 })).filter(p => p.progress < 1);
        for (const p of packetsRef.current) {
            const s = cy.getElementById(p.sourceId), t = cy.getElementById(p.targetId);
            if (s.empty() || t.empty()) continue;
            const a = s.renderedPosition(), b = t.renderedPosition();
            const x = a.x + (b.x - a.x) * p.progress, y = a.y + (b.y - a.y) * p.progress;
            const color = p.blocked ? FLOW_COLORS.blocked : FLOW_COLORS.allowed[dark ? 'dark' : 'light'];
            const tail = Math.max(0, p.progress - 0.08);
            ctx.globalAlpha = 0.35;
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(a.x + (b.x - a.x) * tail, a.y + (b.y - a.y) * tail);
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.globalAlpha = 1;
            ctx.shadowBlur = p.blocked ? 12 : 8;
            ctx.shadowColor = color;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x, y, p.blocked ? 4 : 3, 0, 2 * Math.PI);
            ctx.fill();
            ctx.shadowBlur = 0;
        }
        frameRef.current = packetsRef.current.length ? requestAnimationFrame(draw) : undefined;
    }, [dark]);

    useEffect(() => {
        const onTraffic = (event: any) => {
            flowTimesRef.current.push(Date.now());
            const cy = cyRef.current;
            if (!cy || cy.destroyed() || reducedMotion()) return;
            // Match on data, not a selector string: an address must never be parsed as selector syntax.
            const src = cy.nodes().filter(n => n.data('ip') === event?.source);
            const dst = cy.nodes().filter(n => n.data('ip') === event?.target);
            if (src.empty() || dst.empty()) return;
            packetsRef.current = [...packetsRef.current, { sourceId: src[0].id(), targetId: dst[0].id(), progress: 0, blocked: event?.status === 'blocked' }].slice(-50);
            if (frameRef.current === undefined) frameRef.current = requestAnimationFrame(draw);
        };
        socketService.on('network_traffic', onTraffic);
        const tick = setInterval(() => {
            const cutoff = Date.now() - 60_000;
            flowTimesRef.current = flowTimesRef.current.filter(t => t >= cutoff);
            setFlowRate(flowTimesRef.current.length);
            setStreamUp(socketService.connected);
        }, 5000);
        return () => {
            socketService.off('network_traffic', onTraffic);
            clearInterval(tick);
            if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current);
            frameRef.current = undefined;
        };
    }, [draw]);

    const zoomBy = (factor: number) => {
        const cy = cyRef.current;
        if (!cy) return;
        cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    };

    const flowText = !streamUp ? 'Flow stream offline' : flowRate ? `${flowRate} flow${flowRate === 1 ? '' : 's'} in the last minute` : 'Flow stream connected · no flows yet';

    return (
        <div className="space-y-4 pb-6">
            <PageHeader
                title="Network Topology"
                subtitle="Discovered devices, security zones and the links between them"
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
                                    key={graphKey}
                                    elements={elements}
                                    style={{ width: '100%', height: '100%', position: 'relative' }}
                                    stylesheet={stylesheet}
                                    layout={TOPOLOGY_LAYOUT}
                                    minZoom={0.2}
                                    maxZoom={3}
                                    cy={(cy: any) => {
                                        if (cyRef.current === cy) return;
                                        cyRef.current = cy;
                                        cy.on('tap', 'node', (evt: any) => { if (!evt.target.data('isZone')) setSelectedId(evt.target.id()); });
                                        cy.on('tap', (evt: any) => { if (evt.target === cy) setSelectedId(null); });
                                        cy.on('layoutstop', () => fitView(cy));
                                    }}
                                />
                            )}
                            <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none z-10 w-full h-full" aria-hidden="true" />

                            <div className="absolute top-3 left-3 z-20 flex flex-wrap gap-2 max-w-[calc(100%-5rem)]">
                                <span className={hudChip}><Network className="w-3.5 h-3.5 text-primary-500" aria-hidden="true" />{stats.devices} device{stats.devices === 1 ? '' : 's'}</span>
                                <span className={hudChip}>{stats.links} link{stats.links === 1 ? '' : 's'}</span>
                                <span className={hudChip}>{stats.zones} zone{stats.zones === 1 ? '' : 's'}</span>
                                {stats.segments > 0 && <span className={hudChip}>{stats.segments} VLAN{stats.segments === 1 ? '' : 's'}</span>}
                                {stats.down > 0 && <span className={`${hudChipBase} text-red-700 dark:text-red-300`}>{stats.down} down</span>}
                                <span className={hudChip}>
                                    <span className={`h-1.5 w-1.5 rounded-full ${streamUp ? 'bg-primary-500 dark:bg-primary-400' : 'bg-gray-400'}`} aria-hidden="true" />{flowText}
                                </span>
                            </div>

                            <div role="toolbar" aria-label="Map controls" className={`absolute top-3 ${selected ? 'right-[21.75rem]' : 'right-3'} z-20 flex flex-col p-1 rounded-xl bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm`}>
                                <button type="button" className={hudButton} onClick={() => zoomBy(1.25)} aria-label="Zoom in" title="Zoom in"><ZoomIn className="w-4 h-4" aria-hidden="true" /></button>
                                <button type="button" className={hudButton} onClick={() => zoomBy(0.8)} aria-label="Zoom out" title="Zoom out"><ZoomOut className="w-4 h-4" aria-hidden="true" /></button>
                                <button type="button" className={hudButton} onClick={() => cyRef.current && fitView(cyRef.current)} aria-label="Fit to screen" title="Fit to screen"><Maximize className="w-4 h-4" aria-hidden="true" /></button>
                                <button type="button" className={hudButton} onClick={() => cyRef.current?.layout(TOPOLOGY_LAYOUT as any).run()} aria-label="Arrange again" title="Arrange again"><Shuffle className="w-4 h-4" aria-hidden="true" /></button>
                            </div>

                            {live.data && stats.devices === 0 && (
                                <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-20 w-[min(30rem,calc(100%-2rem))] rounded-xl bg-white/90 dark:bg-gray-900/80 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm px-4 py-3 text-center pointer-events-none">
                                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100">No devices discovered yet</p>
                                    <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">Until a network discovery scan reports devices, the map shows only the internet edge and a placeholder gateway.</p>
                                </div>
                            )}

                            <ul aria-label="Legend" className="absolute bottom-3 left-3 right-3 z-20 flex flex-wrap items-center gap-x-4 gap-y-1.5 w-fit max-w-[calc(100%-1.5rem)] px-3 py-2 rounded-xl bg-white/85 dark:bg-gray-900/70 border border-gray-200/80 dark:border-white/[0.08] backdrop-blur-sm text-xs text-gray-600 dark:text-gray-300">
                                {ROLE_LEGEND.map(r => (
                                    <li key={r.group} className="flex items-center gap-1.5"><span className={`h-3 w-3 rounded-[4px] border-2 ${r.swatch}`} aria-hidden="true" />{r.label}</li>
                                ))}
                                <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-[4px] border-2 border-dashed border-[#d03b3b]" aria-hidden="true" />Down</li>
                                <li className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-primary-500 dark:bg-primary-400" aria-hidden="true" />Allowed flow</li>
                                <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#d03b3b]" aria-hidden="true" />Blocked flow</li>
                            </ul>
                        </>
                    ) : (
                        <div className="absolute inset-0 overflow-auto">
                            <table className="w-full text-left text-sm">
                                <caption className="sr-only">Devices on the network map</caption>
                                <thead className="sticky top-0 z-10 bg-white dark:bg-gray-800 text-[11px] font-semibold uppercase text-gray-500 dark:text-gray-400">
                                    <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                                        {['Device', 'IP address', 'Zone', 'Role', 'VLAN', 'Status', 'Links'].map(h => <th key={h} scope="col" className="px-4 py-3">{h}</th>)}
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
                                                {!isDeviceNode(d) && <span className="ml-2 text-[11px] text-gray-500 dark:text-gray-400">added by the map</span>}
                                            </td>
                                            <td className="px-4 py-3 font-mono text-[13px] text-gray-700 dark:text-gray-300">{d.ip || '—'}</td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{d.zone || '—'}</td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{d.role || '—'}</td>
                                            <td className="px-4 py-3 font-mono text-[13px] text-gray-700 dark:text-gray-300">{d.vlanId || '—'}</td>
                                            <td className={`px-4 py-3 font-medium ${isDown(d.status) ? 'text-red-700 dark:text-red-300' : 'text-green-700 dark:text-green-400'}`}>{isDown(d.status) ? 'Down' : 'Up'}</td>
                                            <td className="px-4 py-3 tabular-nums text-gray-700 dark:text-gray-300">{neighboursOf(d.id).length}</td>
                                        </tr>
                                    ))}
                                    {devices.length === 0 && (
                                        <tr><td colSpan={7} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">{live.data ? 'No devices on the map yet.' : 'Loading…'}</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {selected && (
                        <TopologyInspector node={selected} neighbours={neighboursOf(selected.id)} onSelect={setSelectedId} onClose={() => setSelectedId(null)} />
                    )}
                </div>
            )}
        </div>
    );
};
