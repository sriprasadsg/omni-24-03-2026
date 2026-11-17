import React, { useEffect, useState } from 'react';
import { ChevronDown, CircleAlert, CircleCheck, Network, Pause, Play, RefreshCw, Search, TriangleAlert } from 'lucide-react';
import { LiveStatus } from '../NetworkKit';
import { RANGES, type RangeKey } from '../opsData';

// The console bar on top of the Network Topology screen: stream state, pause, trend range, zone and
// search filters, what needs attention, and the viewer's clock.

const field = 'h-9 rounded-xl text-sm bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.08] text-gray-900 dark:text-white';
const iconButton = 'grid place-items-center h-9 w-9 rounded-xl border border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-white/[0.06] transition-colors disabled:opacity-60';
const badge = 'inline-flex items-center gap-1.5 h-9 px-3 rounded-xl text-[13px] font-medium border whitespace-nowrap';

const zoneOffset = (d: Date) => {
    try { return new Intl.DateTimeFormat(undefined, { timeZoneName: 'shortOffset' }).formatToParts(d).find(p => p.type === 'timeZoneName')?.value ?? ''; }
    catch { return ''; }
};

const ConsoleClock: React.FC = () => {
    const [now, setNow] = useState(() => new Date());
    useEffect(() => {
        const id = setInterval(() => setNow(new Date()), 1000);
        return () => clearInterval(id);
    }, []);
    return (
        <time dateTime={now.toISOString()} className={`${badge} hidden md:inline-flex font-mono tabular-nums border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100`}>
            {now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
            <span className="text-[11px] text-gray-500 dark:text-gray-400">{zoneOffset(now)}</span>
        </time>
    );
};

interface TopologyHeaderProps {
    summary: string;
    updatedAt: number | null;
    error: string | null;
    streamUp: boolean;
    pollSeconds: number;
    paused: boolean;
    onTogglePause: () => void;
    onRefresh: () => void;
    refreshing: boolean;
    range: RangeKey;
    onRange: (r: RangeKey) => void;
    zones: string[];
    zone: string;
    onZone: (z: string) => void;
    query: string;
    onQuery: (q: string) => void;
    down: number;
    notMeasured: number;
    hasData: boolean;
}

export const TopologyHeader: React.FC<TopologyHeaderProps> = p => (
    <header className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card">
        <div className="flex flex-wrap items-center gap-3 px-4 pt-3 pb-2.5">
            <span className="grid place-items-center h-10 w-10 rounded-xl bg-primary-500/10 ring-1 ring-inset ring-primary-500/25 text-primary-600 dark:text-primary-400 shrink-0" aria-hidden="true">
                <Network className="w-5 h-5" />
            </span>
            <div className="min-w-0 mr-auto">
                <h1 className="page-title leading-tight">Network Topology</h1>
                <p className="font-mono text-[11px] text-gray-500 dark:text-gray-400 truncate">{p.summary}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
                {p.down > 0 && (
                    <span className={`${badge} border-red-300 dark:border-red-500/40 bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300`}>
                        <CircleAlert className="w-4 h-4" aria-hidden="true" />{p.down} down
                    </span>
                )}
                {p.notMeasured > 0 && (
                    <span title="Online endpoints with no transfer measured in the last 5 minutes"
                        className={`${badge} border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300`}>
                        <TriangleAlert className="w-4 h-4" aria-hidden="true" />{p.notMeasured} not measured
                    </span>
                )}
                {p.hasData && p.down === 0 && p.notMeasured === 0 && (
                    <span className={`${badge} border-green-300 dark:border-green-500/30 bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-300`}>
                        <CircleCheck className="w-4 h-4" aria-hidden="true" />All up
                    </span>
                )}
                <ConsoleClock />
            </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-gray-100 dark:border-white/[0.06]">
            <span title={p.streamUp ? 'New rates are pushed as agents report them' : `Refreshing every ${p.pollSeconds} s; live push is not connected`}>
                <LiveStatus updatedAt={p.updatedAt} error={p.error} paused={p.paused} liveLabel={p.streamUp ? 'Stream: Live' : 'Live (polling)'} />
            </span>
            <button type="button" onClick={p.onTogglePause} aria-pressed={p.paused} className={iconButton}
                aria-label={p.paused ? 'Resume updates' : 'Pause updates'} title={p.paused ? 'Resume updates' : 'Pause updates'}>
                {p.paused ? <Play className="w-4 h-4" aria-hidden="true" /> : <Pause className="w-4 h-4" aria-hidden="true" />}
            </button>
            <button type="button" onClick={p.onRefresh} disabled={p.refreshing} className={iconButton} aria-label="Refresh" title="Refresh">
                <RefreshCw className={`w-4 h-4 ${p.refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
            </button>

            <div role="group" aria-label="Trend range" title="Range of the trend lines and the comparison in the tiles"
                className="inline-flex h-9 p-0.5 rounded-xl border border-gray-200/80 dark:border-white/[0.08] bg-gray-50 dark:bg-white/[0.03]">
                {RANGES.map(r => (
                    <button key={r.key} type="button" aria-pressed={p.range === r.key} onClick={() => p.onRange(r.key)}
                        className={`px-2.5 rounded-[10px] text-sm font-mono font-medium transition-colors ${p.range === r.key
                            ? 'bg-white dark:bg-white/[0.08] text-gray-900 dark:text-white shadow-sm'
                            : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}>{r.label}</button>
                ))}
            </div>

            <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto sm:ml-auto">
                <label className="relative">
                    <span className="sr-only">Zone</span>
                    <select value={p.zone} onChange={e => p.onZone(e.target.value)} className={`${field} appearance-none pl-3 pr-9 min-w-[9.5rem]`}>
                        <option value="">All zones</option>
                        {p.zones.map(z => <option key={z} value={z}>{z}</option>)}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" aria-hidden="true" />
                </label>
                <label className="relative block grow sm:grow-0">
                    <span className="sr-only">Search nodes</span>
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" aria-hidden="true" />
                    <input type="search" value={p.query} onChange={e => p.onQuery(e.target.value)} placeholder="Search host, IP, MAC…"
                        className={`${field} w-full sm:w-64 pl-9 pr-3 placeholder:text-gray-400`} />
                </label>
            </div>
        </div>
    </header>
);
