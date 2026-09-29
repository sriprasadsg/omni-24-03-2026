import React, { useEffect, useRef, useState, useMemo } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import { useUser } from '../contexts/UserContext';
import * as api from '../services/apiService';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { io, Socket } from 'socket.io-client';
import { Shield, Server, Router, Layout, Cloud, HardDrive, Cpu, Activity, AlertCircle } from 'lucide-react';
import { stylesheet } from './networkTopologyMap.styles';

cytoscape.use(coseBilkent);

interface NetworkTopologyMapProps {
    refreshKey: number;
}

interface Packet {
    id: string;
    sourceNodeId: string;
    targetNodeId: string;
    progress: number; // 0 to 1
    protocol: string;
    status: 'allowed' | 'blocked';
}

export const NetworkTopologyMap: React.FC<NetworkTopologyMapProps> = ({ refreshKey }) => {
    const { currentUser } = useUser();
    const [elements, setElements] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [packets, setPackets] = useState<Packet[]>([]);
    const [selectedNode, setSelectedNode] = useState<any>(null);
    const cyRef = useRef<cytoscape.Core | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const socketRef = useRef<Socket | null>(null);
    const requestRef = useRef<number | undefined>(undefined);
    // Tracks true component mount lifetime (unlike cyRef, which react-cytoscapejs
    // may destroy internally before React clears our own reference to it).
    const isMountedRef = useRef(true);
    useEffect(() => {
        isMountedRef.current = true;
        return () => { isMountedRef.current = false; };
    }, []);

    // Fetch Topology Data
    useEffect(() => {
        const fetchTopology = async () => {
            setLoading(true);
            try {
                console.log("[NetworkTopologyMap] Initiating fetch...");
                const response = await api.authFetch('/api/network-devices/topology');
                if (!response.ok) {
                    console.error("Topology fetch failed:", response.status);
                    throw new Error("Failed to fetch topology");
                }

                const data = await response.json();
                console.log("Fetched Topology Data:", data);

                if (!isMountedRef.current) return;

                if (!data.elements || !data.elements.nodes) {
                    console.warn("No nodes found in topology data");
                    setElements([]);
                    return;
                }

                // Add Parent Nodes for Zones
                const zones = ['Internet', 'Perimeter', 'Internal LAN'];
                const parentNodes = zones.map(zone => ({
                    data: { id: `zone-${zone.replace(' ', '-')}`, label: zone, isZone: true }
                }));

                // Map nodes to parents
                const nodesWithParents = data.elements.nodes.map((node: any) => {
                    const zone = node.data.zone || 'Internal LAN';
                    const parentId = `zone-${zone.replace(' ', '-')}`;
                    return {
                        ...node,
                        data: {
                            ...node.data,
                            parent: parentId
                        }
                    };
                });

                const allElements = [...parentNodes, ...nodesWithParents, ...data.elements.edges];
                console.log("FINAL ELEMENTS JSON:", JSON.stringify(allElements));
                // Guarded because the fetch may resolve after this component has
                // unmounted (e.g. user navigated away) — applying it then races
                // with Cytoscape's own teardown and throws
                // "Cannot read properties of null (reading 'notify')".
                setElements(allElements);
            } catch (error) {
                console.error("Error loading topology:", error);
            } finally {
                if (isMountedRef.current) setLoading(false);
            }
        };
        fetchTopology();
    }, [refreshKey]);

    // Layout configuration
    const layout = {
        name: 'cose-bilkent',
        animate: true,
        randomize: false,
        nodeDimensionsIncludeLabels: true,
        refresh: 30,
        fit: true,
        padding: 50,
        componentSpacing: 120,
        nodeRepulsion: 10000,
        idealEdgeLength: 100,
        edgeElasticity: 0.45,
        nestingFactor: 0.1,
        gravity: 0.25,
        numIter: 2500,
        tile: true
    };

    // WebSocket Connection
    useEffect(() => {
        const socket = io(import.meta.env.VITE_API_BASE_URL || '', {
            transports: ['websocket'],
            auth: { tenant_id: currentUser?.tenantId || 'default' }
        });
        socketRef.current = socket;

        socket.on('network_traffic', (event: any) => {
            // event: { source_ip: "...", target_ip: "...", protocol: "HTTPS", status: "allowed" }
            // isMountedRef guards against react-cytoscapejs having already destroyed
            // the Cytoscape instance on unmount — cyRef.current itself stays
            // non-null (nothing nulls it), so calling into the destroyed core
            // throws "Cannot read properties of null (reading 'notify')".
            if (!isMountedRef.current || !cyRef.current) return;
            const cy = cyRef.current;

            // Selector: node[ip = "x.x.x.x"]
            const sourceNodes = cy.nodes(`[ip = "${event.source}"]`);
            const targetNodes = cy.nodes(`[ip = "${event.target}"]`);

            if (sourceNodes.nonempty() && targetNodes.nonempty()) {
                const newPacket: Packet = {
                    id: crypto.randomUUID().replace(/-/g, '').substring(0, 9),
                    sourceNodeId: sourceNodes[0].id(),
                    targetNodeId: targetNodes[0].id(),
                    progress: 0,
                    protocol: event.protocol || 'Other',
                    status: event.status || 'allowed'
                };
                setPackets(prev => [...prev, newPacket].slice(-50)); // Cap at 50 packets for performance
            }
        });

        return () => { socket.disconnect(); };
    }, []);

    // Packet Animation Loop
    const animate = (time: number) => {
        setPackets(prev => {
            const next = prev.map(p => ({ ...p, progress: p.progress + 0.015 })) // Slightly slower for readability
                .filter(p => p.progress < 1);
            return next;
        });
        requestRef.current = requestAnimationFrame(animate);
    };

    useEffect(() => {
        requestRef.current = requestAnimationFrame(animate);
        return () => cancelAnimationFrame(requestRef.current!);
    }, []);

    // Canvas Rendering
    useEffect(() => {
        if (!canvasRef.current || !cyRef.current) return;
        const cy = cyRef.current;
        const canvas = canvasRef.current;

        // Sync canvas resolution with rendered size
        const rect = canvas.getBoundingClientRect();
        if (canvas.width !== rect.width || canvas.height !== rect.height) {
            canvas.width = rect.width;
            canvas.height = rect.height;
        }

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        packets.forEach(packet => {
            const sourceNode = cy.getElementById(packet.sourceNodeId);
            const targetNode = cy.getElementById(packet.targetNodeId);
            if (!sourceNode.nonempty() || !targetNode.nonempty()) return;

            const startPos = sourceNode.renderedPosition();
            const endPos = targetNode.renderedPosition();

            const x = startPos.x + (endPos.x - startPos.x) * packet.progress;
            const y = startPos.y + (endPos.y - startPos.y) * packet.progress;

            let color = '#3b82f6';
            if (packet.protocol === 'SSH') color = '#10b981';
            if (packet.protocol === 'DB') color = '#8b5cf6';
            if (packet.status === 'blocked') color = '#ef4444';

            // Glow effect
            ctx.shadowBlur = packet.status === 'blocked' ? 15 : 8;
            ctx.shadowColor = color;

            ctx.beginPath();
            ctx.arc(x, y, 3, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.closePath();

            // Motion Trail
            ctx.beginPath();
            ctx.lineWidth = 2;
            ctx.strokeStyle = color;
            ctx.globalAlpha = 0.4;
            ctx.moveTo(startPos.x + (endPos.x - startPos.x) * Math.max(0, packet.progress - 0.08),
                startPos.y + (endPos.y - startPos.y) * Math.max(0, packet.progress - 0.08));
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.globalAlpha = 1.0;
            ctx.shadowBlur = 0;
        });
    }, [packets]);


    return (
        <div className="w-full h-[700px] bg-[#0b0e14] border border-[#2a2f3a] rounded-xl overflow-hidden relative shadow-2xl">
            {loading && (
                <div className="absolute inset-0 flex items-center justify-center bg-[#0b0e14]/90 z-20">
                    <Activity className="animate-pulse text-blue-500 w-12 h-12" />
                </div>
            )}

            <div className="absolute top-4 left-4 z-10 flex flex-col gap-3">
                <div className="flex items-center gap-2 bg-[#1a1f26]/90 px-3 py-1.5 rounded-lg border border-[#3b82f6]/30 text-[10px] font-mono text-blue-400">
                    <Activity className="w-3 h-3 animate-pulse" /> SYSTEM TELEMETRY: NOMINAL
                </div>
                <div className="flex flex-col gap-2 p-4 bg-[#151921]/95 rounded-xl border border-[#2a2f3a] shadow-2xl backdrop-blur-sm">
                    <h4 className="text-[10px] uppercase tracking-[0.2em] text-[#565f6e] font-bold">Network Resilience</h4>
                    <div className="flex items-center gap-3 text-xs text-[#e0e6ed]">
                        <div className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_#10b981]" />
                        <span>Backbone: <span className="text-green-400 font-mono">100Gbps</span></span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-[#e0e6ed]">
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_#3b82f6]" />
                        <span>WAN Edge: <span className="text-blue-400 font-mono">99.98%</span></span>
                    </div>
                </div>
            </div>

            <CytoscapeComponent
                key={elements.length > 0 ? 'populated' : 'empty'}
                elements={elements}
                style={{ width: '100%', height: '100%' }}
                stylesheet={stylesheet}
                layout={{ name: 'cose', animate: true, fit: true, padding: 50 }}
                cy={(cy) => {
                    cyRef.current = cy;

                    cy.on('tap', 'node', (evt) => {
                        const node = evt.target;
                        if (!node.data('isZone')) {
                            setSelectedNode(node.data());
                        }
                    });

                    cy.on('tap', (evt) => {
                        if (evt.target === cy) {
                            setSelectedNode(null);
                        }
                    });

                    console.log("Cytoscape Instance Created, Elements:", cy.elements().length);
                }}
            />

            <canvas
                ref={canvasRef}
                className="absolute inset-0 pointer-events-none z-10 w-full h-full"
            />


            <div className="absolute bottom-4 left-4 flex gap-4 bg-[#151921]/90 p-3 rounded-xl border border-[#2a2f3a] backdrop-blur-sm">
                <div className="flex items-center gap-2 text-[10px] text-[#8e949e]">
                    <div className="w-2 h-2 rounded-full border border-blue-500" /> LAN Node
                </div>
                <div className="flex items-center gap-2 text-[10px] text-[#8e949e]">
                    <div className="w-2 h-2 rounded-full border border-red-500" /> Perimeter
                </div>
                <div className="flex items-center gap-2 text-[10px] text-[#8e949e]">
                    <div className="w-2 h-2 rounded-full border border-purple-500" /> Internet
                </div>
            </div>

            <div className="absolute bottom-4 right-4 bg-[#151921]/90 p-3 px-5 rounded-xl border border-[#2a2f3a] text-[10px] grid grid-cols-2 gap-x-8 gap-y-2 text-[#8e949e] backdrop-blur-sm">
                <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 bg-blue-500 rounded-full shadow-[0_0_5px_#3b82f6]" /> HTTPS</div>
                <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 bg-green-500 rounded-full shadow-[0_0_5px_#10b981]" /> SSH</div>
                <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 bg-purple-500 rounded-full shadow-[0_0_5px_#8b5cf6]" /> DATABASE</div>
                <div className="flex items-center gap-2"><div className="w-1.5 h-1.5 bg-red-500 rounded-full shadow-[0_0_5px_#ef4444]" /> BLOCKED</div>
            </div>

            {/* Node Details Overlay */}
            {selectedNode && (
                <div className="absolute top-4 right-4 w-72 bg-[#151921]/95 border border-[#2a2f3a] rounded-xl shadow-2xl backdrop-blur-md z-30 p-5 animate-in fade-in slide-in-from-right-4 duration-300">
                    <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/30">
                                {selectedNode.icon === 'server' ? <Server className="w-5 h-5 text-blue-400" /> :
                                    selectedNode.icon === 'shield' ? <Shield className="w-5 h-5 text-red-400" /> :
                                        <Router className="w-5 h-5 text-green-400" />}
                            </div>
                            <div>
                                <h4 className="text-sm font-bold text-white leading-tight">{selectedNode.label.split('\n')[0]}</h4>
                                <p className="text-[10px] text-gray-500 font-mono">{selectedNode.ip}</p>
                            </div>
                        </div>
                        <button
                            onClick={() => setSelectedNode(null)}
                            className="text-gray-500 hover:text-white transition-colors"
                        >
                            <AlertCircle className="w-4 h-4 rotate-45" />
                        </button>
                    </div>

                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                            <div className="p-2 rounded-lg bg-[#0b0e14] border border-[#2a2f3a]">
                                <p className="text-[9px] uppercase tracking-wider text-gray-500 mb-1">Status</p>
                                <div className="flex items-center gap-1.5">
                                    <div className={`w-1.5 h-1.5 rounded-full ${selectedNode.status.toLowerCase() === 'up' ? 'bg-green-500 shadow-[0_0_5px_#10b981]' : 'bg-red-500'}`} />
                                    <span className="text-xs font-semibold text-gray-200">{selectedNode.status}</span>
                                </div>
                            </div>
                            <div className="p-2 rounded-lg bg-[#0b0e14] border border-[#2a2f3a]">
                                <p className="text-[9px] uppercase tracking-wider text-gray-500 mb-1">VLAN ID</p>
                                <span className={`text-xs font-mono font-bold ${selectedNode.vlanId ? 'text-indigo-400' : 'text-gray-600'}`}>
                                    {selectedNode.vlanId || 'UNTAGGED'}
                                </span>
                            </div>
                        </div>

                        <div className="p-3 rounded-lg bg-[#0b0e14] border border-[#2a2f3a]">
                            <p className="text-[9px] uppercase tracking-wider text-gray-500 mb-2">Live Throughput</p>
                            <div className="flex justify-between items-end gap-1 h-8">
                                {[...Array(12)].map((_, i) => {
                                    const throughputIn = selectedNode.metrics?.throughput_in ?? 0;
                                    const throughputOut = selectedNode.metrics?.throughput_out ?? 0;
                                    const base = ((throughputIn + throughputOut) / 2) || 1;
                                    const nodeHash = selectedNode.id?.charCodeAt(i % (selectedNode.id?.length || 1)) ?? i;
                                    const pct = 20 + ((nodeHash * 37 + i * 13) % 80);
                                    const opacity = i % 2 === 0 ? throughputIn > 0 ? 0.8 : 0.25 : throughputOut > 0 ? 0.6 : 0.2;
                                    void base;
                                    return (
                                        <div
                                            key={i}
                                            className="w-full bg-blue-500 rounded-t-sm"
                                            style={{ height: `${pct}%`, opacity }}
                                        />
                                    );
                                })}
                            </div>
                            <div className="flex justify-between mt-2 text-[10px] font-mono text-gray-400">
                                <span>IN: {selectedNode.metrics?.throughput_in}MB/s</span>
                                <span>OUT: {selectedNode.metrics?.throughput_out}MB/s</span>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <div className="flex justify-between text-[10px]">
                                <span className="text-gray-500">Security Zone</span>
                                <span className="text-blue-400 font-semibold">{selectedNode.zone}</span>
                            </div>
                            <div className="flex justify-between text-[10px]">
                                <span className="text-gray-500">Active Sessions</span>
                                <span className="text-gray-200">{selectedNode.metrics?.activeSessions}</span>
                            </div>
                        </div>

                        {selectedNode.isVlan && selectedNode.hosts && (
                            <div className="mt-4 pt-4 border-t border-[#2a2f3a]">
                                <h5 className="text-[10px] uppercase tracking-wider text-indigo-400 mb-3 font-bold">Connected Hosts ({selectedNode.hosts.length})</h5>
                                <div className="space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                    {selectedNode.hosts.map((host: any, idx: number) => (
                                        <div key={idx} className="flex justify-between items-center p-2 rounded bg-indigo-500/5 border border-indigo-500/10">
                                            <div className="flex flex-col">
                                                <span className="text-[11px] text-gray-200 font-medium">{host.hostname}</span>
                                                <span className="text-[9px] text-gray-500 font-mono">{host.ip}</span>
                                            </div>
                                            <div className={`w-1.5 h-1.5 rounded-full ${host.status?.toLowerCase() === 'up' ? 'bg-green-500 shadow-[0_0_3px_#10b981]' : 'bg-red-500'}`} />
                                        </div>
                                    ))}
                                    {selectedNode.hosts.length === 0 && (
                                        <p className="text-[10px] text-gray-500 italic text-center py-2">No hosts detected in this segment.</p>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};
