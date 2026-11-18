import React from 'react';
import { Bot, Crosshair, ExternalLink, MonitorSmartphone, Radar, ShieldCheck, Trash2 } from 'lucide-react';
import { EmptyNote, Panel, RankedList, ghostButton } from '../../network/NetworkKit';
import { FEED_NAME, formatSince, type Approval, type SocSummary } from './socData';
import { SeverityCounts, subhead } from './SocKit';

export interface QueueFocus { type?: string; agentId?: string; label: string }

/** Active alerts by detection type; a row opens the queue on that type. */
export const TopDetections: React.FC<{ data: SocSummary; rangeLabel: string; onFocus: (f: QueueFocus) => void }> = ({ data, rangeLabel, onFocus }) => {
    const items = data.byType.filter(t => t.active > 0 || t.inRange > 0);
    return (
        <Panel title="Top detections" note={`Active alerts by type · new in the last ${rangeLabel}`}>
            {items.length ? (
                <>
                    <RankedList items={items.slice(0, 6).map(t => ({ key: t.type || 'other', label: t.label, value: t.active, note: `${t.inRange} new` }))} />
                    <div className="mt-4 flex flex-wrap gap-2">
                        {items.slice(0, 6).map(t => (
                            <button key={t.type || 'other'} type="button" onClick={() => onFocus({ type: t.type, label: t.label })}
                                className="text-xs font-medium text-primary-700 dark:text-primary-300 hover:underline">
                                Show {t.label.toLowerCase()} alerts
                            </button>
                        ))}
                    </div>
                </>
            ) : <EmptyNote icon={<Radar className="w-5 h-5" />} title="No active alerts">Nothing is waiting for an analyst.</EmptyNote>}
        </Panel>
    );
};

export const EndpointsAtRisk: React.FC<{ data: SocSummary; onFocus: (f: QueueFocus) => void }> = ({ data, onFocus }) => (
    <Panel title="Endpoints at risk" note="Endpoints with active alerts, by risk (0-100)">
        {data.endpoints.length ? (
            <ul className="divide-y divide-gray-100 dark:divide-white/[0.06] -my-2">
                {data.endpoints.map(e => {
                    const name = e.known ? e.hostname : `Removed endpoint (${(e.agentId || '').replace(/^agent-/, '').slice(0, 8)})`;
                    return (
                        <li key={e.agentId || 'none'}>
                            <button type="button" disabled={!e.agentId} onClick={() => e.agentId && onFocus({ agentId: e.agentId, label: name })}
                                className="w-full flex items-center gap-3 py-2.5 text-left rounded-lg hover:bg-gray-50 dark:hover:bg-white/[0.03] disabled:cursor-default">
                                <span className={`h-2 w-2 shrink-0 rounded-full ${e.online ? 'bg-green-500' : 'bg-gray-400'}`} aria-hidden="true" />
                                <span className="min-w-0 flex-1">
                                    <span className="block truncate text-sm font-medium text-gray-900 dark:text-white">{name}</span>
                                    <span className="block text-[11px] text-gray-500 dark:text-gray-400">
                                        {e.known ? (e.online ? 'Online' : 'Offline') : 'No longer enrolled'} · last alert {formatSince(e.lastAlertAt)}
                                    </span>
                                </span>
                                <SeverityCounts counts={e} className="justify-end" />
                                <span className="font-mono tabular-nums text-sm font-semibold text-gray-900 dark:text-white w-10 text-right" title={`Risk ${e.risk ?? 0} of 100`}>{e.risk ?? e.active}<span className="sr-only"> risk</span></span>
                            </button>
                        </li>
                    );
                })}
            </ul>
        ) : <EmptyNote icon={<MonitorSmartphone className="w-5 h-5" />} title="No endpoint has an active alert" />}
        {data.users && data.users.length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100 dark:border-white/[0.06]">
                <h3 className={subhead}>Users at risk</h3>
                <ul className="mt-2 flex flex-wrap gap-2">
                    {data.users.map(u => (
                        <li key={u.user} className="rounded-lg px-2 py-1 text-xs bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.06] text-gray-700 dark:text-gray-300">
                            {u.user} <span className="font-mono tabular-nums font-semibold">{u.risk}</span> · {u.active} alert{u.active === 1 ? '' : 's'}
                        </li>
                    ))}
                </ul>
            </div>
        )}
    </Panel>
);

const attackUrl = (t: string) => `https://attack.mitre.org/techniques/${t.replace('.', '/')}/`;

export const MitreTechniques: React.FC<{ data: SocSummary }> = ({ data }) => (
    <Panel title="MITRE ATT&CK techniques" note="Named by active and recent alerts">
        {data.mitre.length ? (
            <ul className="space-y-2.5">
                {data.mitre.map(m => (
                    <li key={m.technique} className="flex items-start gap-3">
                        <a href={attackUrl(m.technique)} target="_blank" rel="noopener noreferrer"
                            className="shrink-0 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[12px] bg-gray-100 dark:bg-white/[0.06] text-gray-800 dark:text-gray-200 hover:text-primary-700 dark:hover:text-primary-300">
                            {m.technique}<ExternalLink className="w-3 h-3" aria-hidden="true" /><span className="sr-only"> (opens MITRE ATT&CK)</span>
                        </a>
                        <span className="min-w-0 flex-1">
                            <span className="block text-sm text-gray-900 dark:text-white">{m.name}</span>
                            {m.tactic && <span className="block text-[11px] text-gray-500 dark:text-gray-400">{m.tactic}</span>}
                        </span>
                        <span className="font-mono tabular-nums text-sm text-gray-700 dark:text-gray-300">{m.count}</span>
                    </li>
                ))}
            </ul>
        ) : (
            <EmptyNote icon={<Crosshair className="w-5 h-5" />} title="No techniques named">
                None of these alerts names a MITRE technique. Runtime and Windows behaviour rules do when they match.
            </EmptyNote>
        )}
    </Panel>
);

const DAY = 86_400_000;

/** When each detection source last raised an alert, how many agents run each check, and approved AI. */
export const DetectionHealth: React.FC<{ data: SocSummary; approvals: Approval[] | null; onRevoke: (a: Approval) => void; busyId: string | null }> = ({ data, approvals, onRevoke, busyId }) => {
    const now = Date.now();
    const agents = data.kpis.endpoints;
    return (
        <Panel title="Detection health" note="When each source last raised an alert, and what is switched on">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <section>
                    <h3 className={subhead}>Sources</h3>
                    <ul className="mt-2 divide-y divide-gray-100 dark:divide-white/[0.06]">
                        {data.sources.map(s => {
                            const age = s.lastAlertAt ? now - Date.parse(s.lastAlertAt) : null;
                            return (
                                <li key={s.type} className="flex items-baseline justify-between gap-3 py-1.5 text-sm">
                                    <span className="text-gray-800 dark:text-gray-200">{s.label}</span>
                                    <span className="text-xs text-gray-500 dark:text-gray-400 text-right">
                                        {s.lastAlertAt ? <>last {formatSince(s.lastAlertAt, now)}{age != null && age > 7 * DAY ? ' · quiet' : ''}</> : 'no alerts yet'}
                                        <span className="font-mono tabular-nums"> · {s.total}</span>
                                    </span>
                                </li>
                            );
                        })}
                    </ul>
                </section>
                <section className="space-y-5">
                    <div>
                        <h3 className={subhead}>Checks on agents</h3>
                        <ul className="mt-2 flex flex-wrap gap-2">
                            {data.coverage.map(c => (
                                <li key={c.check} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.06] text-gray-700 dark:text-gray-300">
                                    <ShieldCheck className={`w-3.5 h-3.5 ${c.agents ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`} aria-hidden="true" />
                                    {c.label} <span className="font-mono tabular-nums">{c.agents}/{agents}</span>
                                </li>
                            ))}
                        </ul>
                        {data.threatIntel && (
                            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                                Threat intel: {data.threatIntel.indicators} indicator{data.threatIntel.indicators === 1 ? '' : 's'}{data.threatIntel.feeds.map(f => ` · ${FEED_NAME[f.source] || f.source}: ${f.needsKey ? 'needs a free abuse.ch key' : f.ok ? `updated ${formatSince(f.at)}` : 'last download failed'}`).join('')}
                            </p>
                        )}
                        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                            {data.counts.openCases ?? 0} open case{data.counts.openCases === 1 ? '' : 's'} · {data.counts.siemRules ?? 0} SIEM correlation rules · {data.counts.activeHunts ?? 0} active threat hunts
                        </p>
                    </div>
                    <div>
                        <h3 className={subhead}>Approved AI processes</h3>
                        {approvals == null ? <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Loading…</p>
                            : approvals.length ? (
                                <ul className="mt-2 space-y-2">
                                    {approvals.map(a => (
                                        <li key={a.id} className="flex items-start gap-2 text-sm">
                                            <Bot className="w-4 h-4 mt-0.5 shrink-0 text-gray-400" aria-hidden="true" />
                                            <span className="min-w-0 flex-1">
                                                <span className="font-mono text-[13px] text-gray-900 dark:text-white">{a.process}</span>
                                                <span className="text-gray-600 dark:text-gray-300"> on {a.agentId ? (a.hostname || 'one endpoint') : 'all endpoints'}</span>
                                                {a.reason && <span className="block text-[11px] text-gray-500 dark:text-gray-400">{a.reason}</span>}
                                            </span>
                                            <button type="button" className={`${ghostButton} h-8 px-2`} disabled={busyId === a.id} onClick={() => onRevoke(a)}
                                                aria-label={`Stop approving ${a.process}${a.hostname ? ` on ${a.hostname}` : ''}`}>
                                                <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />Remove
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            ) : <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">None. Approve a process from its alert to stop alerts about it.</p>}
                    </div>
                </section>
            </div>
        </Panel>
    );
};
