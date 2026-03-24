import React, { useEffect, useRef, useState, useMemo } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import { UserContext } from '../contexts/UserContext';
import * as api from '../services/apiService';
import cytoscape from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { io, Socket } from 'socket.io-client';
import { Shield, Server, Router, Layout, Cloud, HardDrive, Cpu, Activity, AlertCircle } from 'lucide-react';

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

// Helper to generate SVG Data URIs for Cytoscape from Lucide icon names/colors
const getIconDataUri = (type: string, color: string = '%233b82f6') => {
    // Basic SVG templates for common network icons
    let svgPath = '';
    // SVG Paths for: cloud, shield, server, router, layers (switch), monitor (endpoint)
    if (type === 'cloud') svgPath = 'M17.5 19c.5 0 1-.1 1.5-.3 2-1 3.5-3 3.5-5.2 0-3.3-2.7-6-6-6-.3 0-.7 0-1 .1C14.4 5.3 12.4 4 10 4 6.1 4 3 7.1 3 11c0 .4 0 .7.1 1.1C1.9 12.8 1 14.3 1 16c0 2.2 1.8 4 4 4h12.5';
    else if (type === 'shield') svgPath = 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z';
    else if (type === 'server') svgPath = 'M2 10V6a2 2 0 012-2h16a2 2 0 012 2v4M2 14v4a2 2 0 002 2h16a2 2 0 002-2v-4M6 6h.01M6 18h.01';
    else if (type === 'router') svgPath = 'M2 13v6a2 2 0 002 2h16a2 2 0 002-2v-6M12 3v10M12 3l-4 4M12 3l4 4';
    else if (type === 'switch' || type === 'layers' || type === 'subnet') svgPath = 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5';
    else svgPath = 'M4 6a2 2 0 012-2h12a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 20h-4M12 15v3';

    return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${type === 'server' ? '<rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line>' : `<path d="${svgPath}"></path>`}</svg>`;
};

export const NetworkTopologyMap: React.FC<NetworkTopologyMapProps> = ({ refreshKey }) => {
    const [elements, setElements] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [packets, setPackets] = useState<Packet[]>([]);
    const [selectedNode, setSelectedNode] = useState<any>(null);
    const cyRef = useRef<cytoscape.Core | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const socketRef = useRef<Socket | null>(null);
    const requestRef = useRef<number>();

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
                setElements(allElements);
            } catch (error) {
                console.error("Error loading topology:", error);
            } finally {
                setLoading(false);
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
        const socket = io('http://localhost:5000', {
            transports: ['websocket'],
            auth: { tenant_id: 'default' }
        });
        socketRef.current = socket;

        socket.on('network_traffic', (event: any) => {
            // event: { source_ip: "...", target_ip: "...", protocol: "HTTPS", status: "allowed" }
            if (!cyRef.current) return;
            const cy = cyRef.current;

            // Selector: node[ip = "x.x.x.x"]
            const sourceNodes = cy.nodes(`[ip = "${event.source}"]`);
            const targetNodes = cy.nodes(`[ip = "${event.target}"]`);

            if (sourceNodes.nonempty() && targetNodes.nonempty()) {
                const newPacket: Packet = {
                    id: Math.random().toString(36).substr(2, 9),
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


    const stylesheet = [
        {
            selector: 'node',
            style: {
                'label': 'data(label)',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '10px',
                'color': '#8e949e',
                'font-family': 'JetBrains Mono, monospace',
                'text-margin-y': 6,
                'background-color': '#1a1f26',
                'width': 44,
                'height': 44,
                'border-width': 2,
                'border-color': '#3b82f6',
                'background-image': (ele: any) => getIconDataUri(ele.data('icon') || 'monitor'),
                'background-fit': 'contain',
                'background-clip': 'none',
                'background-width': '65%',
                'background-height': '65%',
                'background-position-x': '50%',
                'background-position-y': '50%'
            }
        },
        {
            selector: ':parent',
            style: {
                'background-opacity': 0.08,
                'background-color': '#1e293b',
                'border-color': '#334155',
                'border-width': 1,
                'border-style': 'solid',
                'text-valign': 'top',
                'text-halign': 'center',
                'text-margin-y': -10,
                'font-weight': 'bold',
                'font-size': '11px',
                'color': '#475569',
                'text-transform': 'uppercase',
                'letter-spacing': '0.1em'
            }
        },
        {
            selector: 'node[type = "cloud"]',
            style: { 'border-color': '#8b5cf6', 'background-image': (ele: any) => getIconDataUri('cloud', '%238b5cf6') }
        },
        {
            selector: 'node[type = "firewall"]',
            style: { 'border-color': '#f43f5e', 'background-image': (ele: any) => getIconDataUri('shield', '%23f43f5e') }
        },
        {
            selector: 'node[icon = "server"]',
            style: { 'border-color': '#0ea5e9', 'background-image': (ele: any) => getIconDataUri('server', '%230ea5e9') }
        },
        {
            selector: 'node[status = "down"]',
            style: { 'border-color': '#ef4444', 'border-opacity': 0.5, 'opacity': 0.6 }
        },
        {
            selector: 'node[isVlan = true]',
            style: {
                'background-opacity': 0.1,
                'background-color': '#6366f1',
                'border-color': '#818cf8',
                'border-width': 1.5,
                'border-style': 'solid',
                'text-valign': 'top',
                'text-halign': 'center',
                'text-margin-y': 5,
                'font-size': '10px',
                'font-weight': 'bold',
                'color': '#c7d2fe',
                'padding': '30px'
            }
        },
        {
            selector: 'edge',
            style: {
                'width': 1.5,
                'line-color': '#1e293b',
                'target-arrow-color': '#1e293b',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                'opacity': 0.6
            }
        }
    ];

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
                                {[...Array(12)].map((_, i) => (
                                    <div
                                        key={i}
                                        className="w-full bg-blue-500/20 rounded-t-sm"
                                        style={{ height: `${20 + Math.random() * 80}%` }}
                                    />
                                ))}
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
