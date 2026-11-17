import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { formatAgo, formatBytes } from '../networkData';
import { formatBitRate, type OpsConnection, type OpsEndpoint, type TrafficSummary } from '../opsData';
import { RX, Sparkline, TX } from './OpsKpis';
import { ProtocolBadge, StatusBadge, type OpsSelection } from './OpsTables';

const subhead = 'text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400';
const mono = 'font-mono tabular-nums';

interface Hop { name: string; detail: React.ReactNode; state: 'ok' | 'down' | 'unknown' }

/** Endpoint -> gateway -> destination, with what is known about each hop. Hop latency is not collected. */
const PathHealth: React.FC<{ hops: Hop[] }> = ({ hops }) => (
    <ol className="mt-3">
        {hops.map((hop, i) => (
            <li key={hop.name} className="relative pl-6 pb-4 last:pb-0">
                {i < hops.length - 1 && <span className="absolute left-[5px] top-3 bottom-0 w-px bg-gray-200 dark:bg-white/10" aria-hidden="true" />}
                <span className={`absolute left-0 top-1.5 h-[11px] w-[11px] rounded-full ring-2 ring-white dark:ring-gray-800 ${hop.state === 'ok' ? 'bg-green-500' : hop.state === 'down' ? 'bg-red-500' : 'bg-gray-400'}`} aria-hidden="true" />
                <p className="text-[13px] font-medium text-gray-900 dark:text-white">{hop.name}
                    <span className="sr-only"> ({hop.state === 'ok' ? 'reachable' : hop.state === 'down' ? 'down' : 'unknown'})</span></p>
                <div className="text-xs text-gray-600 dark:text-gray-300">{hop.detail}</div>
                <p className="text-[11px] text-gray-500 dark:text-gray-400">Latency: not measured</p>
            </li>
        ))}
    </ol>
);

const endpointHops = (e: OpsEndpoint): Hop[] => [
    { name: e.hostname, state: e.status === 'Down' ? 'down' : 'ok',
      detail: <><span className={mono}>{e.ip || 'no address'}</span> · {e.status === 'Down' ? 'no report for over 5 minutes' : `last report ${e.lastSeen ? formatAgo(Date.parse(e.lastSeen)) : 'unknown'}`}</> },
    e.gateway
        ? { name: 'Gateway', state: 'ok', detail: <><span className={mono}>{e.gateway.ip}</span>{e.gateway.mac ? <> · MAC <span className={mono}>{e.gateway.mac}</span></> : null} · in the endpoint's neighbour table</> }
        : { name: 'Gateway', state: 'unknown', detail: 'Not known: none in the endpoint\'s neighbour table' },
    e.publicIp
        ? { name: 'Internet', state: 'ok', detail: <>Public address <span className={mono}>{e.publicIp}</span></> }
        : { name: 'Internet', state: 'unknown', detail: 'Public address not reported' },
];

const Rates: React.FC<{ e: OpsEndpoint }> = ({ e }) => (
    <section>
        <h3 className={subhead}>Now</h3>
        {e.rxBps != null ? (
            <>
                <dl className="mt-2 grid grid-cols-2 gap-2">
                    {[{ s: RX, label: 'Inbound (Rx)', v: e.rxBps }, { s: TX, label: 'Outbound (Tx)', v: e.txBps }].map(({ s, label, v }) => (
                        <div key={label} className="rounded-xl bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.05] px-3 py-2">
                            <dt className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400"><span className={`h-2 w-2 rounded-sm ${s.bg}`} aria-hidden="true" />{label}</dt>
                            <dd className={`${mono} mt-0.5 text-[15px] font-semibold text-gray-900 dark:text-white`}>{formatBitRate(v)}</dd>
                        </div>
                    ))}
                </dl>
                <p className="mt-1.5 text-[11px] text-gray-500 dark:text-gray-400">
                    Averaged over {Math.round(e.windowSeconds || 0)} s, measured {e.rateAt ? formatAgo(Date.parse(e.rateAt)) : ''}
                </p>
            </>
        ) : <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">No transfer measured in the last 5 minutes.</p>}
    </section>
);

const EndpointDetails: React.FC<{ e: OpsEndpoint; history: TrafficSummary | null; rangeLabel: string; connections: OpsConnection[] }> = ({ e, history, rangeLabel, connections }) => (
    <div className="space-y-6">
        <Rates e={e} />
        <section>
            <h3 className={subhead}>Last {rangeLabel}</h3>
            {history && history.series.some(p => p.rxBps != null)
                ? <div className="mt-2"><Sparkline className="h-16" lines={[{ values: history.series.map(p => p.rxBps), stroke: RX.stroke }, { values: history.series.map(p => p.txBps), stroke: TX.stroke }]} /></div>
                : <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">{history ? 'No rates recorded in this range.' : 'Loading…'}</p>}
            <p className={`mt-2 text-xs text-gray-600 dark:text-gray-300 ${mono}`}>Moved: ↓ {formatBytes(e.rangeRxBytes)} · ↑ {formatBytes(e.rangeTxBytes)}</p>
            {e.bytesSent != null && e.bytesRecv != null && (
                <p className={`text-[11px] text-gray-500 dark:text-gray-400 ${mono}`}>Since the host started: ↓ {formatBytes(e.bytesRecv)} · ↑ {formatBytes(e.bytesSent)}</p>
            )}
        </section>
        <section>
            <h3 className={subhead}>Path health</h3>
            <PathHealth hops={endpointHops(e)} />
        </section>
        <section>
            <h3 className={subhead}>Interfaces</h3>
            {e.interfaces.length ? (
                <ul className="mt-2 space-y-1.5">
                    {e.interfaces.map(i => (
                        <li key={`${i.name}-${i.mac}`} className="rounded-lg bg-gray-50 dark:bg-white/[0.03] px-2.5 py-1.5">
                            <p className="text-[13px] text-gray-800 dark:text-gray-200 truncate" title={i.name}>{i.name}</p>
                            <p className={`text-[11px] text-gray-500 dark:text-gray-400 ${mono}`}>
                                {i.bytesSent != null
                                    ? `↓ ${formatBytes(i.bytesRecv || 0)} (${(i.packetsRecv ?? 0).toLocaleString()} pkts) · ↑ ${formatBytes(i.bytesSent)} (${(i.packetsSent ?? 0).toLocaleString()} pkts)`
                                    : i.mac ? `MAC ${i.mac}` : 'no counters reported'}
                            </p>
                        </li>
                    ))}
                </ul>
            ) : <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">None reported.</p>}
            <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">Packet inspection (drops, errors, payloads) is not collected.</p>
        </section>
        <section>
            <h3 className={subhead}>Latest connections ({connections.length})</h3>
            {connections.length ? (
                <ul className="mt-2 space-y-1">
                    {connections.slice(0, 12).map((c, i) => (
                        <li key={i} className="flex items-center justify-between gap-2 text-[12.5px]">
                            <span className={`${mono} truncate text-gray-800 dark:text-gray-200`}>{c.destination}</span>
                            <span className="flex items-center gap-2 shrink-0 text-gray-500 dark:text-gray-400">{c.process}<ProtocolBadge protocol={c.protocol} port={c.port} /></span>
                        </li>
                    ))}
                </ul>
            ) : <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">None reported. Only Linux agents report outbound connections today.</p>}
        </section>
    </div>
);

const ConnectionDetails: React.FC<{ c: OpsConnection; endpoint?: OpsEndpoint }> = ({ c, endpoint }) => (
    <div className="space-y-6">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
            {[['Source', <span className={mono}>{c.sourceIp || '—'}</span>], ['Endpoint', c.hostname],
              ['Protocol', <ProtocolBadge protocol={c.protocol} port={c.port} />], ['Port', <span className={mono}>{c.port ?? '—'}</span>],
              ['Process', <span className={mono}>{c.process || '—'}{c.pid != null ? ` · ${c.pid}` : ''}</span>], ['Scope', c.scope]].map(([k, v]) => (
                <div key={String(k)}><dt className="text-[11px] text-gray-500 dark:text-gray-400">{k}</dt><dd className="text-gray-900 dark:text-white">{v}</dd></div>
            ))}
        </dl>
        <section>
            <h3 className={subhead}>Path health</h3>
            <PathHealth hops={[
                ...(endpoint ? endpointHops(endpoint).slice(0, c.scope === 'Internal' ? 1 : 2) : []),
                { name: c.destination, state: 'unknown', detail: <><span className={mono}>{c.destinationIp || c.destination}{c.port ? `:${c.port}` : ''}</span> · open in the endpoint's latest report</> },
            ]} />
        </section>
        <p className="text-[11px] text-gray-500 dark:text-gray-400">Bandwidth, latency and packets per connection are not collected yet.</p>
    </div>
);

export const OpsDrawer: React.FC<{ selection: OpsSelection; data: TrafficSummary; rangeLabel: string;
    loadHistory: (agentId: string) => Promise<TrafficSummary>; onClose: () => void }> = ({ selection, data, rangeLabel, loadHistory, onClose }) => {
    const panelRef = useRef<HTMLDivElement>(null);
    const closeRef = useRef<HTMLButtonElement>(null);
    const [history, setHistory] = useState<TrafficSummary | null>(null);
    const agentId = selection.kind === 'endpoint' ? selection.agentId : selection.connection.agentId;
    const endpoint = data.endpoints.find(e => e.agentId === agentId);

    useEffect(() => {
        const returnTo = document.activeElement as HTMLElement | null;
        closeRef.current?.focus();
        return () => { returnTo?.focus?.(); };
    }, []);

    // The endpoint's own history, loaded once per selection and range (not on every poll).
    useEffect(() => {
        if (selection.kind !== 'endpoint') return;
        let alive = true;
        setHistory(null);
        loadHistory(selection.agentId)
            .then(h => { if (alive) setHistory(h); })
            .catch(() => { if (alive) setHistory({ series: [] } as unknown as TrafficSummary); });
        return () => { alive = false; };
    }, [selection, loadHistory]);

    // Escape closes; Tab stays inside the drawer while it is open.
    const onKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
        if (e.key !== 'Tab' || !panelRef.current) return;
        const focusable = panelRef.current.querySelectorAll<HTMLElement>('button, [href], input, select, [tabindex]:not([tabindex="-1"])');
        if (!focusable.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };

    const title = selection.kind === 'endpoint' ? (endpoint?.hostname ?? 'Endpoint') : selection.connection.destination;
    return (
        <div className="fixed inset-0 z-50" onKeyDown={onKeyDown}>
            <div className="absolute inset-0 bg-gray-950/40 backdrop-blur-[2px] animate-in fade-in duration-150" onClick={onClose} aria-hidden="true" />
            <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="ops-drawer-title"
                className="absolute inset-y-0 right-0 w-[min(28rem,100%)] flex flex-col bg-white dark:bg-gray-900 border-l border-gray-200/80 dark:border-white/10 shadow-2xl animate-in slide-in-from-right-8 duration-200">
                <div className="flex items-start gap-3 px-5 py-4 border-b border-gray-200/70 dark:border-white/[0.07]">
                    <div className="min-w-0 flex-1">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{selection.kind === 'endpoint' ? 'Endpoint' : 'Connection'}</p>
                        <h2 id="ops-drawer-title" className={`text-[17px] font-semibold text-gray-900 dark:text-white truncate ${selection.kind === 'connection' ? mono : ''}`}>{title}</h2>
                        {selection.kind === 'endpoint' && endpoint && (
                            <p className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400"><span className={mono}>{endpoint.ip}</span><StatusBadge status={endpoint.status} /></p>
                        )}
                    </div>
                    <button ref={closeRef} type="button" onClick={onClose} aria-label="Close details"
                        className="grid place-items-center h-8 w-8 rounded-lg text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.06]">
                        <X className="w-4 h-4" aria-hidden="true" />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto px-5 py-5 custom-scrollbar">
                    {selection.kind === 'endpoint'
                        ? endpoint
                            ? <EndpointDetails e={endpoint} history={history} rangeLabel={rangeLabel} connections={data.connections.filter(c => c.agentId === endpoint.agentId)} />
                            : <p className="text-sm text-gray-500 dark:text-gray-400">This endpoint is no longer in the data.</p>
                        : <ConnectionDetails c={selection.connection} endpoint={endpoint} />}
                </div>
            </div>
        </div>
    );
};
