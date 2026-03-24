import React, { useState, useCallback, useRef } from 'react';
import ReactFlow, {
    ReactFlowProvider,
    addEdge,
    useNodesState,
    useEdgesState,
    Controls,
    Background,
    Connection,
    Edge,
    Node,
    Handle,
    Position
} from 'reactflow';
import 'reactflow/dist/style.css';
import { PlayIcon, SaveIcon, PlusIcon, BoltIcon, ShieldBanIcon, ShieldCheckIcon, MessageSquareIcon, GlobeIcon, DatabaseIcon } from 'lucide-react';
import { useApi } from '../hooks/useApi';

// Custom Node Components
const TriggerNode = ({ data }: any) => (
    <div className="bg-purple-900/60 border-2 border-purple-500 rounded-lg p-3 shadow-lg w-48 font-sans">
        <div className="flex items-center gap-2 text-purple-200 mb-2">
            <BoltIcon size={16} className="text-purple-400" />
            <span className="font-bold text-sm">Alert Trigger</span>
        </div>
        <div className="text-xs text-purple-300 bg-black/30 p-1.5 rounded truncate">
            {data.label || 'On Any Critical Alert'}
        </div>
        <Handle type="source" position={Position.Bottom} className="w-3 h-3 bg-purple-500" />
    </div>
);

const ActionNode = ({ data, type }: any) => {
    let bg = "bg-blue-900/60";
    let border = "border-blue-500";
    let textColor = "text-blue-200";
    let Icon = DatabaseIcon;

    if (data.actionType === 'block_ip_firewall') {
        bg = "bg-red-900/60"; border = "border-red-500"; textColor = "text-red-200"; Icon = ShieldBanIcon;
    } else if (data.actionType === 'isolate_host') {
        bg = "bg-orange-900/60"; border = "border-orange-500"; textColor = "text-orange-200"; Icon = ShieldBanIcon;
    } else if (data.actionType === 'suspend_okta_user') {
        bg = "bg-yellow-900/60"; border = "border-yellow-500"; textColor = "text-yellow-200"; Icon = ShieldCheckIcon;
    } else if (data.actionType === 'enrich_ip_vt') {
        bg = "bg-green-900/60"; border = "border-green-500"; textColor = "text-green-200"; Icon = GlobeIcon;
    } else if (data.actionType === 'send_slack_message') {
        bg = "bg-indigo-900/60"; border = "border-indigo-500"; textColor = "text-indigo-200"; Icon = MessageSquareIcon;
    }

    return (
        <div className={`${bg} border-2 ${border} rounded-lg p-3 shadow-lg w-48 font-sans transition-all hover:brightness-110`}>
            <Handle type="target" position={Position.Top} className={`w-3 h-3 ${bg.replace('/60', '')}`} />
            <div className={`flex items-center gap-2 ${textColor} mb-2`}>
                <Icon size={16} />
                <span className="font-bold text-sm">{data.title || 'Action'}</span>
            </div>
            <div className="text-xs text-white/70 bg-black/30 p-1.5 rounded truncate">
                {data.label || 'Execute integration'}
            </div>
            <Handle type="source" position={Position.Bottom} className={`w-3 h-3 ${bg.replace('/60', '')}`} />
        </div>
    );
};

const nodeTypes = {
    trigger: TriggerNode,
    action: ActionNode,
};

const initialNodes: Node[] = [
    {
        id: 'trigger_1',
        type: 'trigger',
        position: { x: 250, y: 50 },
        data: { label: 'On Brute Force Alert (Okta)' },
    },
];

const initialEdges: Edge[] = [];

// Sidebar draggable elements
const ActionDraggable = ({ type, title, label, icon: Icon, colorClass }: any) => (
    <div
        className={`flex items-center gap-3 p-3 rounded-lg border border-white/10 ${colorClass} bg-opacity-10 hover:bg-opacity-20 cursor-grab active:cursor-grabbing transition-colors`}
        draggable
        onDragStart={(event) => {
            event.dataTransfer.setData('application/reactflow', JSON.stringify({ type: 'action', actionType: type, title, label }));
            event.dataTransfer.effectAllowed = 'move';
        }}
    >
        <Icon size={18} />
        <div className="flex flex-col">
            <span className="text-sm font-semibold">{title}</span>
            <span className="text-xs opacity-70">{label}</span>
        </div>
    </div>
);

export const PlaybookBuilder: React.FC = () => {
    // API
    const fetchApi = async (url: string, options: any = {}) => {
        const response = await fetch(url, options);
        if (!response.ok) throw new Error(`API error: ${response.status}`);
        return response.json();
    };

    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);

    const [saving, setSaving] = useState(false);
    const [running, setRunning] = useState(false);
    const [playbookName, setPlaybookName] = useState('New Automated Playbook');
    const [runLog, setRunLog] = useState<any[]>([]);

    const onConnect = useCallback((params: Connection | Edge) => setEdges((eds) => addEdge({ ...params, animated: true }, eds)), [setEdges]);

    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    const onDrop = useCallback(
        (event: React.DragEvent) => {
            event.preventDefault();

            const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect();
            const stringData = event.dataTransfer.getData('application/reactflow');

            if (!stringData || !reactFlowBounds || !reactFlowInstance) return;

            const elementData = JSON.parse(stringData);
            const position = reactFlowInstance.project({
                x: event.clientX - reactFlowBounds.left,
                y: event.clientY - reactFlowBounds.top,
            });

            const newNode: Node = {
                id: `node_${Date.now()}`,
                type: elementData.type,
                position,
                data: elementData,
            };

            setNodes((nds) => nds.concat(newNode));
        },
        [reactFlowInstance, setNodes]
    );

    const handleSavePlaybook = async () => {
        setSaving(true);
        try {
            const def = {
                name: playbookName,
                description: "Created via Visual Builder",
                nodes: nodes.map(n => ({ id: n.id, type: n.data.actionType || n.type, position: n.position, data: n.data })),
                edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target, data: e.data || {} })),
            };

            await fetchApi('/api/soar/playbooks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(def)
            });
            alert('Playbook saved successfully!');
        } catch (err) {
            console.error(err);
            alert('Failed to save playbook');
        } finally {
            setSaving(false);
        }
    };

    const handleTestRun = async () => {
        setRunning(true);
        setRunLog([{ msg: "Initialising SOAR Engine...", time: new Date().toISOString() }]);

        try {
            // In a real scenario, this executes the DAG on the backend.
            // For immediate UI feedback, we'll simulate the graph traversal here visually
            let log = [...runLog];
            const logMsg = (m: string) => { log.push({ msg: m, time: new Date().toISOString() }); setRunLog([...log]); };

            logMsg(`Triggering playbook: ${playbookName}`);

            const triggers = nodes.filter(n => n.type === 'trigger');
            if (triggers.length === 0) {
                logMsg("ERROR: No trigger node found.");
                setRunning(false); return;
            }

            let queue = [...triggers.map(t => t.id)];
            let visited = new Set();

            while (queue.length > 0) {
                const currId = queue.shift();
                // @ts-ignore
                if (visited.has(currId)) continue;
                visited.add(currId);

                const node = nodes.find(n => n.id === currId);
                if (!node) continue;

                // Highlight node (simulated execution)
                setNodes(nds => nds.map(n => {
                    if (n.id === currId) {
                        n.style = { ...n.style, boxShadow: '0 0 15px 5px rgba(59, 130, 246, 0.5)' };
                    }
                    return n;
                }));

                logMsg(`Executing node: ${node.data.title || 'Trigger'} [${node.data.actionType || 'start'}]`);
                await new Promise(r => setTimeout(r, 800)); // fake delay

                // De-highlight
                setNodes(nds => nds.map(n => {
                    if (n.id === currId) {
                        n.style = { ...n.style, boxShadow: 'none' };
                    }
                    return n;
                }));

                // Queue children
                const childrenEdges = edges.filter(e => e.source === currId);
                childrenEdges.forEach(e => {
                    // Highlight edge
                    setEdges(eds => eds.map(edg => {
                        if (edg.id === e.id) { edg.animated = true; edg.style = { stroke: '#3b82f6', strokeWidth: 2 }; }
                        return edg;
                    }));
                    queue.push(e.target);
                });
                await new Promise(r => setTimeout(r, 400));
            }
            logMsg("Playbook execution completed successfully.");

        } catch (e) {
            console.error(e);
        } finally {
            setRunning(false);
        }
    };

    return (
        <div className="flex h-[calc(100vh-100px)] gap-4">

            {/* Sidebar Tools */}
            <div className="w-80 glass rounded-xl p-4 flex flex-col h-full overflow-y-auto">
                <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                    <PlusIcon /> SOAR Actions
                </h2>
                <p className="text-xs text-white/60 mb-6">Drag and drop nodes onto the canvas to build automated remediation playbooks.</p>

                <div className="space-y-4">
                    <h3 className="text-xs font-semibold text-white/40 uppercase tracking-wider">Integrations</h3>

                    <ActionDraggable
                        type="enrich_ip_vt" title="Enrich IP (VirusTotal)" label="Query VT API for reputation score"
                        icon={GlobeIcon} colorClass="text-green-400 bg-green-500"
                    />

                    <ActionDraggable
                        type="block_ip_firewall" title="Block IP on Firewall" label="PAN-OS API: Add to blocklist"
                        icon={ShieldBanIcon} colorClass="text-red-400 bg-red-500"
                    />

                    <ActionDraggable
                        type="suspend_okta_user" title="Suspend IAM User" label="Okta API: Force session termination"
                        icon={ShieldCheckIcon} colorClass="text-yellow-400 bg-yellow-500"
                    />

                    <ActionDraggable
                        type="isolate_host" title="Isolate Endpoint" label="Omni-Agent: Network quarantine"
                        icon={ShieldBanIcon} colorClass="text-orange-400 bg-orange-500"
                    />

                    <ActionDraggable
                        type="send_slack_message" title="Slack Notification" label="Send interactive message to SOC"
                        icon={MessageSquareIcon} colorClass="text-indigo-400 bg-indigo-500"
                    />
                </div>

                {/* Console / Run Log */}
                {runLog.length > 0 && (
                    <div className="mt-8 flex-1 border-t border-white/10 pt-4 flex flex-col">
                        <h3 className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-2">Execution Log</h3>
                        <div className="bg-black/40 rounded p-2 text-xs font-mono text-green-400 overflow-y-auto flex-1 space-y-1">
                            {runLog.map((l, i) => (
                                <div key={i}><span className="text-white/30">{new Date(l.time).toLocaleTimeString()}</span> {l.msg}</div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* Main Canvas Area */}
            <div className="flex-1 flex flex-col glass rounded-xl overflow-hidden">
                {/* Header toolbar */}
                <div className="h-14 bg-black/20 border-b border-white/10 px-4 flex items-center justify-between">
                    <input
                        value={playbookName}
                        onChange={(e) => setPlaybookName(e.target.value)}
                        className="bg-transparent text-lg font-semibold text-white focus:outline-none focus:border-b-2 border-blue-500 w-1/2"
                    />

                    <div className="flex gap-3">
                        <button
                            onClick={handleTestRun}
                            disabled={running}
                            className="flex items-center gap-2 px-4 py-1.5 bg-green-600/20 text-green-400 hover:bg-green-600/40 rounded-lg transition-colors border border-green-500/30 text-sm font-medium disabled:opacity-50"
                        >
                            <PlayIcon size={16} className={running ? "animate-pulse" : ""} />
                            {running ? 'Running...' : 'Test Run'}
                        </button>
                        <button
                            onClick={handleSavePlaybook}
                            disabled={saving}
                            className="flex items-center gap-2 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors shadow-lg shadow-blue-500/20 text-sm font-medium"
                        >
                            <SaveIcon size={16} />
                            {saving ? 'Saving...' : 'Save Playbook'}
                        </button>
                    </div>
                </div>

                {/* ReactFlow Canvas */}
                <div className="flex-1 relative" ref={reactFlowWrapper}>
                    <ReactFlowProvider>
                        <ReactFlow
                            nodes={nodes}
                            edges={edges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onConnect={onConnect}
                            onInit={setReactFlowInstance}
                            onDrop={onDrop}
                            onDragOver={onDragOver}
                            nodeTypes={nodeTypes}
                            fitView
                            className="bg-[#0f111a]"
                        >
                            <Controls className="!bg-black/50 !border-white/10 [&>button]:!border-b-white/10 [&>button]:!bg-transparent text-white" />
                            <Background color="#ffffff" gap={16} size={1} className="opacity-5" />
                        </ReactFlow>
                    </ReactFlowProvider>
                </div>
            </div>
        </div>
    );
};

export default PlaybookBuilder;
