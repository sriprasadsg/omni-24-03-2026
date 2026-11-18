import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Crosshair, FileText, Globe, List, Monitor, Network, Bell, Cpu, User, X } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { ghostButton } from '../../network/NetworkKit';
import { fetchGraph, formatWhen, SEVERITY_META, STATUS_LABEL, type GraphKind, type GraphNode, type InvestigationGraphData } from './socData';
import { SEVERITY_ICON, segment, segmented, subhead } from './SocKit';

// Columns read left to right: the endpoint, its alerts, what they name, other endpoints where that showed up.
const KIND_META: Record<GraphKind, { label: string; icon: React.ElementType }> = {
    host: { label: 'Endpoint', icon: Monitor }, alert: { label: 'Alert', icon: Bell }, user: { label: 'User', icon: User },
    process: { label: 'Process', icon: Cpu }, file: { label: 'File', icon: FileText }, ip: { label: 'IP address', icon: Globe },
    technique: { label: 'MITRE technique', icon: Crosshair },
};
const ENTITY_ORDER: GraphKind[] = ['user', 'process', 'file', 'ip', 'technique'];
const COL_X = [20, 270, 540, 810];
const NODE_W = 210, NODE_H = 34, ROW_H = 44, TOP = 34, WIDTH = 1040;

const columnOf = (n: GraphNode): number => (n.kind === 'host' ? (n.primary ? 0 : 3) : n.kind === 'alert' ? 1 : 2);
const clip = (s: string, max = 27) => (s.length > max ? `${s.slice(0, max - 1)}…` : s);

interface Props { of: 'incidents' | 'alerts'; id: string; title: string; onClose: () => void; onOpenAlert?: (alertId: string) => void }

/** The investigation graph of an incident or alert, as an overlay above the drawers. */
export const InvestigationGraph: React.FC<Props> = ({ of, id, title, onClose, onOpenAlert }) => {
    const [data, setData] = useState<InvestigationGraphData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [selected, setSelected] = useState<string | null>(null);
    const [hovered, setHovered] = useState<string | null>(null);
    const [asList, setAsList] = useState(false);
    const closeRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        const returnTo = document.activeElement as HTMLElement | null;
        closeRef.current?.focus();
        return () => { returnTo?.focus?.(); };
    }, []);
    useEffect(() => {
        fetchGraph(authFetch, of, id).then(g => { setData(g); setSelected(g.focus); })
            .catch(e => setError(e instanceof Error ? e.message : 'The investigation graph could not be loaded'));
    }, [of, id]);

    const layout = useMemo(() => {
        if (!data) return null;
        const cols: GraphNode[][] = [[], [], [], []];
        const rank = (n: GraphNode) => ENTITY_ORDER.indexOf(n.kind);
        data.nodes.forEach(n => cols[columnOf(n)].push(n));
        cols[2].sort((a, b) => rank(a) - rank(b) || (b.count ?? 0) - (a.count ?? 0));
        const rows = Math.max(1, ...cols.map(c => c.length));
        const pos: Record<string, { x: number; y: number }> = {};
        cols.forEach((col, ci) => {
            const offset = ((rows - col.length) * ROW_H) / 2;
            col.forEach((n, ri) => { pos[n.id] = { x: COL_X[ci], y: TOP + offset + ri * ROW_H }; });
        });
        return { pos, height: TOP + rows * ROW_H + 10, byId: Object.fromEntries(data.nodes.map(n => [n.id, n])) as Record<string, GraphNode> };
    }, [data]);

    const active = hovered ?? selected;
    const neighbours = useMemo(() => {
        const out = new Set<string>();
        if (!data || !active) return out;
        data.edges.forEach(e => { if (e.from === active) out.add(e.to); if (e.to === active) out.add(e.from); });
        return out;
    }, [data, active]);
    const sel = selected && layout ? layout.byId[selected] : null;
    const links = sel && data ? data.edges.filter(e => e.from === sel.id || e.to === sel.id)
        .map(e => ({ label: e.label, node: layout!.byId[e.from === sel.id ? e.to : e.from] })).filter(l => l.node) : [];

    const onKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };

    return (
        <div className="fixed inset-0 z-[60]" onKeyDown={onKeyDown}>
            <div className="absolute inset-0 bg-gray-950/50 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
            <div role="dialog" aria-modal="true" aria-labelledby="soc-graph-title"
                className="absolute inset-2 sm:inset-6 flex flex-col rounded-2xl bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-white/10 shadow-2xl">
                <div className="flex flex-wrap items-start gap-3 px-5 py-4 border-b border-gray-200/70 dark:border-white/[0.07]">
                    <div className="min-w-0 flex-1">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Investigation graph</p>
                        <h2 id="soc-graph-title" className="mt-1 text-[17px] font-semibold text-gray-900 dark:text-white break-words">{title}</h2>
                        {data && <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                            {data.alerts} of {data.alertsTotal} alert{data.alertsTotal === 1 ? '' : 's'} shown; other endpoints are those whose alerts in the last {data.pivotDays} days name the same user, process, file or IP.
                            {data.truncated && ' Some items were left out to keep the graph readable.'}
                        </p>}
                    </div>
                    <div role="group" aria-label="View" className={segmented}>
                        <button type="button" aria-pressed={!asList} onClick={() => setAsList(false)} className={segment(!asList)}><Network className="inline w-4 h-4 mr-1" aria-hidden="true" />Graph</button>
                        <button type="button" aria-pressed={asList} onClick={() => setAsList(true)} className={segment(asList)}><List className="inline w-4 h-4 mr-1" aria-hidden="true" />List</button>
                    </div>
                    <button ref={closeRef} type="button" onClick={onClose} aria-label="Close the investigation graph"
                        className="grid place-items-center h-8 w-8 rounded-lg text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/[0.06]">
                        <X className="w-4 h-4" aria-hidden="true" />
                    </button>
                </div>
                {error && <p role="alert" className="p-5 text-sm text-red-700 dark:text-red-300">{error}</p>}
                {!data && !error && <p className="p-5 text-sm text-gray-500 dark:text-gray-400">Loading…</p>}
                {data && layout && (
                    <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_20rem]">
                        <div className="min-h-0 overflow-auto custom-scrollbar p-3">
                            {asList ? (
                                <ul className="space-y-3" aria-label="Everything in the graph">
                                    {data.nodes.map(n => {
                                        const Icon = KIND_META[n.kind].icon;
                                        return (
                                            <li key={n.id}>
                                                <button type="button" onClick={() => setSelected(n.id)} aria-pressed={selected === n.id}
                                                    className="w-full text-left flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                                    <Icon className="w-4 h-4 mt-0.5 text-gray-500 dark:text-gray-400" aria-hidden="true" />
                                                    <span className="min-w-0"><span className="text-[13px] font-medium text-gray-900 dark:text-white break-words">{n.label}</span>
                                                        <span className="block text-[11px] text-gray-500 dark:text-gray-400">{KIND_META[n.kind].label}{n.kind === 'host' && !n.primary ? ' (other endpoint)' : ''}</span></span>
                                                </button>
                                            </li>
                                        );
                                    })}
                                </ul>
                            ) : (
                                <svg viewBox={`0 0 ${WIDTH} ${layout.height}`} className="w-full min-w-[760px]" style={{ height: layout.height }} role="group" aria-label="Investigation graph">
                                    {['Endpoint', 'Alerts', 'What they name', 'Other endpoints'].map((h, i) => (
                                        <text key={h} x={COL_X[i]} y={16} className="fill-gray-500 dark:fill-gray-400 text-[11px] font-semibold uppercase tracking-wide">{h}</text>
                                    ))}
                                    {data.edges.map(e => {
                                        const a = layout.pos[e.from], b = layout.pos[e.to];
                                        if (!a || !b) return null;
                                        const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2, mid = (x1 + x2) / 2;
                                        const lit = active && (e.from === active || e.to === active);
                                        return <path key={`${e.from}>${e.to}`} d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`} fill="none"
                                            strokeWidth={lit ? 2 : 1.25} strokeDasharray={e.label.startsWith('also seen') ? '5 4' : undefined}
                                            className={lit ? 'stroke-primary-500 dark:stroke-primary-400' : `stroke-gray-300 dark:stroke-white/20 ${active ? 'opacity-40' : ''}`}>
                                            <title>{e.label}</title></path>;
                                    })}
                                    {data.nodes.map(n => {
                                        const p = layout.pos[n.id];
                                        const Icon = n.kind === 'alert' && n.severity ? SEVERITY_ICON[n.severity] : KIND_META[n.kind].icon;
                                        const dim = active && n.id !== active && !neighbours.has(n.id);
                                        const isSel = selected === n.id;
                                        const name = `${KIND_META[n.kind].label}: ${n.label}${n.severity ? `, ${SEVERITY_META[n.severity].label}` : ''}`;
                                        return (
                                            <g key={n.id} transform={`translate(${p.x},${p.y})`} tabIndex={0} role="button" aria-label={name} aria-pressed={isSel}
                                                className={`cursor-pointer outline-none ${dim ? 'opacity-40' : ''}`}
                                                onClick={() => setSelected(n.id)} onMouseEnter={() => setHovered(n.id)} onMouseLeave={() => setHovered(null)}
                                                onFocus={() => setHovered(n.id)} onBlur={() => setHovered(null)}
                                                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(n.id); } }}>
                                                <title>{name}{n.sub ? ` · ${n.sub}` : ''}</title>
                                                <rect width={NODE_W} height={NODE_H} rx={9} strokeWidth={isSel || n.focus || n.primary ? 2 : 1}
                                                    className={`fill-white dark:fill-gray-800 ${isSel ? 'stroke-primary-600 dark:stroke-primary-300' : n.focus || n.primary ? 'stroke-primary-400 dark:stroke-primary-500' : 'stroke-gray-200 dark:stroke-white/15'}`} />
                                                {n.severity && <rect x={0} y={6} width={3} height={NODE_H - 12} rx={1.5} fill={SEVERITY_META[n.severity].hex} />}
                                                <Icon x={10} y={10} width={14} height={14} aria-hidden="true"
                                                    className={n.severity ? SEVERITY_META[n.severity].text : 'text-gray-500 dark:text-gray-400'} />
                                                <text x={30} y={21.5} className="fill-gray-900 dark:fill-white text-[12px] font-medium">{clip(n.label)}</text>
                                                {(n.count ?? 0) > 1 && n.kind !== 'alert' && (
                                                    <text x={NODE_W - 8} y={21.5} textAnchor="end" className="fill-gray-500 dark:fill-gray-400 text-[11px] tabular-nums">×{n.count}</text>
                                                )}
                                            </g>
                                        );
                                    })}
                                </svg>
                            )}
                        </div>
                        <aside aria-label="Selected item" className="border-t lg:border-t-0 lg:border-l border-gray-200/70 dark:border-white/[0.07] p-4 overflow-y-auto custom-scrollbar">
                            {!sel ? <p className="text-sm text-gray-500 dark:text-gray-400">Pick an item to see what it is connected to.</p> : (
                                <div className="space-y-3">
                                    <div>
                                        <p className={subhead}>{KIND_META[sel.kind].label}{sel.kind === 'host' && !sel.primary ? ' (other endpoint)' : ''}</p>
                                        <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white break-words">{sel.label}</p>
                                        {sel.sub && <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-300 break-all">{sel.sub}</p>}
                                        {sel.kind === 'alert' && <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                                            {sel.severity && `${SEVERITY_META[sel.severity].label} · `}{sel.status && STATUS_LABEL[sel.status]} · {formatWhen(sel.at)}</p>}
                                        {sel.kind !== 'alert' && (sel.count ?? 0) > 0 && <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                                            {sel.kind === 'host' ? `${sel.count} alert${sel.count === 1 ? '' : 's'} there name the same thing` : `Named by ${sel.count} alert${sel.count === 1 ? '' : 's'} here`}</p>}
                                    </div>
                                    {sel.kind === 'alert' && sel.alertId && onOpenAlert && (
                                        <button type="button" className={ghostButton} onClick={() => onOpenAlert(sel.alertId!)}>Open the alert</button>
                                    )}
                                    <div>
                                        <p className={subhead}>Connected to</p>
                                        <ul className="mt-1.5 space-y-1">
                                            {links.map(l => (
                                                <li key={l.node.id}>
                                                    <button type="button" onClick={() => setSelected(l.node.id)} className="w-full text-left rounded-lg px-1.5 py-1 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                                                        <span className="block text-[13px] text-gray-900 dark:text-white break-words">{l.node.label}</span>
                                                        <span className="block text-[11px] text-gray-500 dark:text-gray-400">{KIND_META[l.node.kind].label} · {l.label}</span>
                                                    </button>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            )}
                        </aside>
                    </div>
                )}
            </div>
        </div>
    );
};
