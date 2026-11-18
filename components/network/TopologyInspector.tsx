import React, { useEffect, useRef, useState } from 'react';
import { X, Cloud, Shield, Server, Layers, Printer, Monitor, Globe, RadioTower, Router, Radar, CircleCheck, CircleX, ArrowUp, ArrowDown } from 'lucide-react';
import { deviceFacts, formatAgo, formatBytes, formatPps, formatRate, isDown, isFreshRate } from './networkData';

export interface Neighbour { id: string; label: string; ip?: string; status?: string }
export interface Connection { id: string; label: string; ports: number[]; processes: string[]; connections: number }
/** One step of an endpoint's traced route to the server. */
export interface PathStep { id: string; label: string; ip?: string; rttMs?: number | null; answered: boolean }

const ICONS: Record<string, React.ElementType> = { cloud: Cloud, shield: Shield, server: Server, layers: Layers, printer: Printer, globe: Globe, isp: RadioTower, router: Router };

// Nodes that are not machines the platform found; say what they are.
const KIND_NOTES: Record<string, string> = {
    internet: 'The internet edge.',
    placeholder: 'A placeholder: no gateway is known for these endpoints yet (none in their neighbour tables or among scanned devices).',
    remote: 'A remote host an endpoint had an open connection to in its last report.',
    isp: 'The internet provider of the endpoints behind this gateway, named from the public address they report.',
    hop: 'A router on the path from an endpoint to the Omni-Agent server, found by the endpoint\'s route trace.',
    server: 'The Omni-Agent server the endpoints report to. Routes traced by endpoints end here.',
};

const PLATFORM_AGENT = 'This computer is the Omni-Agent server: every agent reports to it, and the routes endpoints trace end here.';

const SILENT_HOPS = 'These hops did not answer the trace. Routers, firewalls and cloud networks often drop trace probes; traffic still passes.';

const UNNAMED_ISP = 'No provider is known for this public address yet. The server names it from MaxMind\'s GeoLite2-ASN database when that is installed and the tenant tracks agent locations.';

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
    <div className="flex justify-between gap-4 py-1.5 text-[13px]">
        <dt className="text-gray-500 dark:text-gray-400 shrink-0">{label}</dt>
        <dd className="text-gray-800 dark:text-gray-200 text-right break-words min-w-0">{children}</dd>
    </div>
);

const LiveTransfer: React.FC<{ metrics: any }> = ({ metrics }) => {
    const fresh = isFreshRate(metrics);
    const total = typeof metrics?.bytesSent === 'number' && typeof metrics?.bytesRecv === 'number';
    return (
        <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Live transfer</h3>
            {fresh ? (
                <>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                        {([['Upload', ArrowUp, metrics.sentBps], ['Download', ArrowDown, metrics.recvBps]] as const).map(([label, Icon, bps]) => (
                            <div key={label} className="rounded-xl bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.05] px-3 py-2">
                                <p className="flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400"><Icon className="w-3 h-3" aria-hidden="true" />{label}</p>
                                <p className="mt-0.5 text-[15px] font-semibold tabular-nums text-gray-900 dark:text-white">{formatRate(bps)}</p>
                            </div>
                        ))}
                    </div>
                    {typeof metrics.sentPps === 'number' && typeof metrics.recvPps === 'number' && (
                        <p className="mt-1.5 text-[12px] tabular-nums text-gray-700 dark:text-gray-300">Packets: ↑ {formatPps(metrics.sentPps)} · ↓ {formatPps(metrics.recvPps)}</p>
                    )}
                    <p className="mt-1.5 text-[11px] text-gray-500 dark:text-gray-400">
                        Averaged over {Math.round(metrics.windowSeconds || 0)} s, measured {formatAgo(Date.parse(metrics.rateAt))}
                    </p>
                </>
            ) : (
                <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">No transfer measured in the last 5 minutes.</p>
            )}
            {total && (
                <p className="mt-1.5 text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">
                    Since the host started: ↑ {formatBytes(metrics.bytesSent)} · ↓ {formatBytes(metrics.bytesRecv)}
                </p>
            )}
        </section>
    );
};

const subhead = 'text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400';

const PathToServer: React.FC<{ path: PathStep[]; onSelect: (id: string) => void }> = ({ path, onSelect }) => (
    <section>
        <h3 className={subhead}>Path to the server ({path.length} steps)</h3>
        <ol className="mt-2">
            {path.map((step, i) => (
                <li key={step.id} className="relative pl-5">
                    {i < path.length - 1 && <span className="absolute left-[4px] top-4 bottom-0 w-px bg-gray-200 dark:bg-white/10" aria-hidden="true" />}
                    <span className={`absolute left-0 top-[11px] h-[9px] w-[9px] rounded-full ${step.answered ? 'bg-primary-500' : 'border border-gray-400 bg-transparent'}`} aria-hidden="true" />
                    <button type="button" onClick={() => onSelect(step.id)}
                        className="w-full flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-white/[0.05]">
                        <span className="min-w-0">
                            <span className="block text-[13px] text-gray-800 dark:text-gray-200 truncate">{step.label}</span>
                            {step.ip && <span className="block font-mono text-[11px] text-gray-500 dark:text-gray-400">{step.ip}</span>}
                        </span>
                        <span className="shrink-0 font-mono tabular-nums text-[11px] text-gray-500 dark:text-gray-400">{typeof step.rttMs === 'number' ? `${step.rttMs} ms` : ''}</span>
                    </button>
                </li>
            ))}
        </ol>
    </section>
);

type ScanState = { phase: 'idle' | 'sending' | 'sent' | 'error'; message?: string };

/** Ask the endpoint to scan its LAN; what it finds (gateway, firewall, other hosts) joins the map. */
const ScanNetwork: React.FC<{ onScan: () => Promise<void> }> = ({ onScan }) => {
    const [state, setState] = useState<ScanState>({ phase: 'idle' });
    const run = async () => {
        setState({ phase: 'sending' });
        try {
            await onScan();
            setState({ phase: 'sent' });
        } catch (e: any) {
            setState({ phase: 'error', message: e?.message || 'The scan could not be requested.' });
        }
    };
    return (
        <section>
            <h3 className={subhead}>Local network</h3>
            <button type="button" onClick={run} disabled={state.phase === 'sending'}
                className="mt-2 inline-flex items-center gap-2 h-9 px-3 rounded-xl text-sm font-medium border border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/[0.06] disabled:opacity-60">
                <Radar className={`w-4 h-4 ${state.phase === 'sending' ? 'animate-pulse' : ''}`} aria-hidden="true" />
                {state.phase === 'sending' ? 'Requesting scan…' : 'Scan this endpoint\'s network'}
            </button>
            <p role="status" className={`mt-1.5 text-[11px] ${state.phase === 'error' ? 'text-red-700 dark:text-red-300' : 'text-gray-500 dark:text-gray-400'}`}>
                {state.phase === 'sent' ? 'Scan requested. The endpoint pings its subnet and checks common ports; what it finds appears here after its next report, usually within a few minutes.'
                    : state.phase === 'error' ? state.message
                    : 'Finds the gateway, firewall and other devices on the endpoint\'s subnet, with their open ports.'}
            </p>
        </section>
    );
};

interface InspectorProps {
    node: any;
    neighbours: Neighbour[];
    connections: Connection[];
    path?: PathStep[];
    onScan?: () => Promise<void>;
    onSelect: (id: string) => void;
    onClose: () => void;
}

export const TopologyInspector: React.FC<InspectorProps> = ({ node, neighbours, connections, path, onScan, onSelect, onClose }) => {
    const closeRef = useRef<HTMLButtonElement>(null);
    useEffect(() => { closeRef.current?.focus({ preventScroll: true }); }, [node.id]);

    const Icon = ICONS[node.icon] || Monitor;
    const [title] = String(node.label || node.id).split('\n');
    const facts = deviceFacts(node.details);
    const note = node.isPlatform ? PLATFORM_AGENT : node.kind === 'isp' && !node.ispKnown ? UNNAMED_ISP : node.kind === 'hop' && !node.ip ? SILENT_HOPS : KIND_NOTES[node.kind];
    const down = isDown(node.status);

    return (
        <aside aria-label={`Details for ${title}`} className="h-full max-h-[48rem] min-h-[24rem] flex flex-col rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card animate-in fade-in slide-in-from-right-2 duration-200">
            <div className="flex items-start gap-3 p-4 border-b border-gray-200/70 dark:border-white/[0.07]">
                <span className="grid place-items-center h-10 w-10 rounded-xl bg-primary-500/10 ring-1 ring-inset ring-primary-500/20 text-primary-600 dark:text-primary-400 shrink-0" aria-hidden="true">
                    <Icon className="w-5 h-5" />
                </span>
                <div className="min-w-0 flex-1">
                    <h2 className="text-[15px] font-semibold text-gray-900 dark:text-white truncate" title={title}>{title}</h2>
                    {node.ip && <p className="font-mono text-xs text-gray-500 dark:text-gray-400 truncate">{node.ip}</p>}
                </div>
                <button ref={closeRef} type="button" onClick={onClose} aria-label="Close details"
                    className="grid place-items-center h-8 w-8 rounded-lg text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.06]">
                    <X className="w-4 h-4" aria-hidden="true" />
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-5 custom-scrollbar">
                {node.status && node.status !== 'Unknown' && (
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium ${down
                        ? 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300'
                        : 'bg-green-50 text-green-700 dark:bg-green-500/10 dark:text-green-300'}`}>
                        {down ? <CircleX className="w-3.5 h-3.5" aria-hidden="true" /> : <CircleCheck className="w-3.5 h-3.5" aria-hidden="true" />}
                        {down ? 'Down' : 'Up'}
                    </span>
                )}
                {note && <p className="text-[13px] text-gray-600 dark:text-gray-300">{note}</p>}
                {node.kind === 'agent' && <LiveTransfer metrics={node.metrics} />}
                {node.kind === 'agent' && !node.isPlatform && (path?.length
                    ? <PathToServer path={path} onSelect={onSelect} />
                    : <section><h3 className={subhead}>Path to the server</h3><p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">Not traced yet. Agents from version 2.1.20 trace their route to the server every 15 minutes.</p></section>)}
                {node.kind === 'agent' && onScan && <ScanNetwork key={node.id} onScan={onScan} />}

                <dl className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                    {node.zone && <Field label="Zone">{node.zone}</Field>}
                    {node.role && <Field label="Role">{node.role}</Field>}
                    {node.type && node.type !== 'Unknown' && <Field label="Type">{node.type}</Field>}
                    {!['internet', 'isp', 'remote'].includes(node.kind) && <Field label="VLAN">{node.vlanId ? <span className="font-mono">{node.vlanId}</span> : 'Untagged'}</Field>}
                    {facts.map(f => <Field key={f.label} label={f.label}>{f.value}</Field>)}
                </dl>

                {node.isVlan && Array.isArray(node.hosts) && (
                    <section>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Hosts in this segment ({node.hosts.length})</h3>
                        <ul className="mt-2 space-y-1.5">
                            {node.hosts.map((h: any, i: number) => (
                                <li key={`${h.ip}-${i}`} className="flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 bg-gray-50 dark:bg-white/[0.03]">
                                    <span className="min-w-0">
                                        <span className="block text-[13px] text-gray-800 dark:text-gray-200 truncate">{h.hostname}</span>
                                        <span className="block font-mono text-[11px] text-gray-500 dark:text-gray-400">{h.ip}</span>
                                    </span>
                                    <span className={`text-[11px] font-medium ${isDown(h.status) ? 'text-red-600 dark:text-red-400' : 'text-green-700 dark:text-green-400'}`}>{isDown(h.status) ? 'Down' : 'Up'}</span>
                                </li>
                            ))}
                        </ul>
                        {node.hosts.length === 0 && <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">No hosts detected in this segment.</p>}
                    </section>
                )}

                {node.kind === 'agent' && (
                    <section>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Latest connections ({connections.length})</h3>
                        {connections.length ? (
                            <ul className="mt-2 space-y-1">
                                {connections.map(c => (
                                    <li key={c.id}>
                                        <button type="button" onClick={() => onSelect(c.id)}
                                            className="w-full rounded-lg px-2.5 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-white/[0.05]">
                                            <span className="block font-mono text-[12px] text-gray-800 dark:text-gray-200 truncate">{String(c.label).split('\n')[0]}</span>
                                            <span className="block text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                                {[c.ports.length ? `port ${c.ports.join(', ')}` : '', c.processes.join(', '), `${c.connections} open`].filter(Boolean).join(' · ')}
                                            </span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">
                                None reported. Outbound connections come from the agent's Web Monitor; the Windows agent does not report them yet.
                            </p>
                        )}
                    </section>
                )}

                <section>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Connected to ({neighbours.length})</h3>
                    {neighbours.length ? (
                        <ul className="mt-2 space-y-1">
                            {neighbours.map(n => (
                                <li key={n.id}>
                                    <button type="button" onClick={() => onSelect(n.id)}
                                        className="w-full flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-white/[0.05]">
                                        <span className="text-[13px] text-gray-800 dark:text-gray-200 truncate">{String(n.label).split('\n')[0]}</span>
                                        {n.ip && <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400 shrink-0">{n.ip}</span>}
                                    </button>
                                </li>
                            ))}
                        </ul>
                    ) : <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">No links.</p>}
                </section>
            </div>
        </aside>
    );
};
