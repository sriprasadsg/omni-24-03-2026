import React, { useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import { Pause, Play, RefreshCw } from 'lucide-react';
import { ThemeContext } from '../../contexts/ThemeContext';
import { formatAgo, formatShare, type RankedItem } from './networkData';

// Shared pieces of the network screens (Topology, Data Utilization, Web Monitoring), on the
// Spatial Glass tokens (design-system/omni-agent-2030/MASTER.md).

// Two-series palette, validated with the dataviz validator against #FFFFFF and the #161E30 card.
export const SERIES = {
    sent: { name: 'Sent', light: '#0891B2', dark: '#0EA5C4', swatch: 'bg-[#0891B2] dark:bg-[#0EA5C4]' },
    received: { name: 'Received', light: '#eb6834', dark: '#d95926', swatch: 'bg-[#eb6834] dark:bg-[#d95926]' },
} as const;

export const useChartTheme = () => {
    const dark = useContext(ThemeContext).theme === 'dark';
    return {
        dark,
        grid: dark ? 'rgba(255,255,255,0.07)' : '#E3E8EF',
        text: dark ? '#8F9BB0' : '#637089',
        surface: dark ? '#161E30' : '#FFFFFF',
        cursor: dark ? 'rgba(255,255,255,0.04)' : 'rgba(6,10,20,0.04)',
    };
};

interface LiveState<T> { data: T | null; updatedAt: number | null; error: string | null; loading: boolean }

/**
 * Polls `fetcher` every `intervalMs` (skipped while the tab is hidden or the viewer paused).
 * Only the newest request may write, so a slow older reply never overwrites a newer one.
 */
export function useLiveData<T>(fetcher: () => Promise<T>, intervalMs: number) {
    const [state, setState] = useState<LiveState<T>>({ data: null, updatedAt: null, error: null, loading: true });
    const [paused, setPaused] = useState(false);
    const seq = useRef(0);
    const fetcherRef = useRef(fetcher);
    fetcherRef.current = fetcher;

    const refresh = useCallback(async () => {
        const mine = ++seq.current;
        setState(s => ({ ...s, loading: true }));
        try {
            const data = await fetcherRef.current();
            if (mine === seq.current) setState({ data, updatedAt: Date.now(), error: null, loading: false });
        } catch (e: any) {
            if (mine === seq.current) setState(s => ({ ...s, error: e?.message || 'Update failed', loading: false }));
        }
    }, []);

    useEffect(() => {
        refresh();
        return () => { seq.current += 1; };
    }, [refresh]);

    useEffect(() => {
        if (paused || !intervalMs) return;
        const id = setInterval(() => { if (!document.hidden) refresh(); }, intervalMs);
        return () => clearInterval(id);
    }, [paused, intervalMs, refresh]);

    return { ...state, paused, setPaused, refresh };
}

const useNow = (everyMs: number) => {
    const [now, setNow] = useState(Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), everyMs);
        return () => clearInterval(id);
    }, [everyMs]);
    return now;
};

/** Freshness pill: says how old the numbers are, and whether they still update. */
export const LiveStatus: React.FC<{ updatedAt: number | null; error: string | null; paused?: boolean; liveLabel?: string }> = ({ updatedAt, error, paused, liveLabel = 'Live' }) => {
    const now = useNow(5000);
    const ago = updatedAt ? formatAgo(updatedAt, now) : null;
    let dot = 'bg-primary-500 dark:bg-primary-400';
    let text = ago ? `${liveLabel} · updated ${ago}` : 'Connecting…';
    if (error) { dot = 'bg-amber-500'; text = ago ? `Update failed · data from ${ago}` : 'Update failed'; }
    else if (paused) { dot = 'bg-gray-400'; text = ago ? `Paused · updated ${ago}` : 'Paused'; }
    const pulsing = !error && !paused && !!updatedAt;
    return (
        <span className="inline-flex items-center gap-2 h-9 px-3 rounded-xl text-[13px] font-medium bg-white/70 dark:bg-white/[0.04] border border-gray-200/80 dark:border-white/[0.08] text-gray-700 dark:text-gray-300 whitespace-nowrap">
            <span className="relative flex h-2 w-2" aria-hidden="true">
                {pulsing && <span className="absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-60 animate-ping" />}
                <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
            </span>
            {text}
            {/* The ticking text is not a live region; only a failed update is announced. */}
            <span role="status" className="sr-only">{error ? `Update failed: ${error}` : ''}</span>
        </span>
    );
};

export const ghostButton = 'inline-flex items-center gap-2 h-9 px-3 rounded-xl text-sm font-medium border border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/[0.06] transition-colors disabled:opacity-60 cursor-pointer';

interface PageHeaderProps {
    title: string;
    subtitle: string;
    status?: React.ReactNode;
    onRefresh?: () => void;
    refreshing?: boolean;
    paused?: boolean;
    onTogglePause?: () => void;
    children?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, status, onRefresh, refreshing, paused, onTogglePause, children }) => (
    <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
            <h1 className="page-title">{title}</h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
            {status}
            {children}
            {onTogglePause && (
                <button type="button" onClick={onTogglePause} className={ghostButton} aria-pressed={paused}>
                    {paused ? <Play className="w-4 h-4" aria-hidden="true" /> : <Pause className="w-4 h-4" aria-hidden="true" />}
                    {paused ? 'Resume updates' : 'Pause updates'}
                </button>
            )}
            {onRefresh && (
                <button type="button" onClick={onRefresh} disabled={refreshing} className={ghostButton}>
                    <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
                    Refresh
                </button>
            )}
        </div>
    </header>
);

export const Panel: React.FC<{ title: string; note?: React.ReactNode; actions?: React.ReactNode; className?: string; children: React.ReactNode }> = ({ title, note, actions, className = '', children }) => {
    const id = useId();
    return (
        <section aria-labelledby={id} className={`rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-5 min-w-0 ${className}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <h2 id={id} className="text-[15px] font-semibold text-gray-900 dark:text-white">{title}</h2>
                    {note && <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{note}</p>}
                </div>
                {actions}
            </div>
            <div className="mt-4">{children}</div>
        </section>
    );
};

export const EmptyNote: React.FC<{ icon: React.ReactNode; title: string; children?: React.ReactNode }> = ({ icon, title, children }) => (
    <div className="h-full min-h-[160px] grid place-items-center text-center px-4">
        <div className="max-w-sm">
            <span className="mx-auto grid place-items-center h-10 w-10 rounded-xl bg-gray-100 dark:bg-white/[0.05] text-gray-400" aria-hidden="true">{icon}</span>
            <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-200">{title}</p>
            {children && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{children}</p>}
        </div>
    </div>
);

/** Ranked magnitudes in one hue: text carries the value, the bar only the proportion. */
export const RankedList: React.FC<{ items: RankedItem[]; format?: (v: number) => string; mono?: boolean; total?: number }> = ({ items, format = String, mono, total }) => {
    const max = Math.max(1, ...items.map(i => i.value));
    return (
        <ol className="space-y-3">
            {items.map(item => (
                <li key={item.key}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className={`truncate text-gray-800 dark:text-gray-200 ${mono ? 'font-mono text-[13px]' : ''}`} title={item.label}>{item.label}</span>
                        <span className="shrink-0 tabular-nums text-gray-600 dark:text-gray-300">
                            {format(item.value)}
                            {total ? <span className="text-gray-500 dark:text-gray-400"> · {formatShare(item.value, total)}</span> : null}
                            {item.note && <span className="text-gray-500 dark:text-gray-400"> · {item.note}</span>}
                        </span>
                    </div>
                    <div aria-hidden="true" className="mt-1.5 h-1.5 rounded-full bg-gray-100 dark:bg-white/[0.06] overflow-hidden">
                        <div className="h-full w-full rounded-full bg-primary-500 dark:bg-primary-400 origin-left transition-transform duration-500" style={{ transform: `scaleX(${item.value / max})` }} />
                    </div>
                </li>
            ))}
        </ol>
    );
};

export interface Segment { label: string; value: number; swatch: string; display: string; icon?: React.ReactNode }

/** A whole split into a few labelled parts (sent vs received, encrypted vs plain). */
export const SplitBar: React.FC<{ segments: Segment[]; label: string }> = ({ segments, label }) => {
    const total = segments.reduce((a, s) => a + s.value, 0);
    return (
        <div>
            <div role="img" aria-label={`${label}: ${segments.map(s => `${s.label} ${formatShare(s.value, total)}`).join(', ')}`} className="flex h-2.5 gap-0.5 rounded-full overflow-hidden bg-gray-100 dark:bg-white/[0.06]">
                {total > 0 && segments.filter(s => s.value > 0).map(s => (
                    <div key={s.label} className={`h-full first:rounded-l-full last:rounded-r-full ${s.swatch}`} style={{ flexGrow: s.value, flexBasis: 0 }} />
                ))}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
                {segments.map(s => (
                    <li key={s.label} className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                        <span className={`h-2.5 w-2.5 rounded-sm ${s.swatch}`} aria-hidden="true" />
                        {s.icon}
                        <span>{s.label}</span>
                        <span className="tabular-nums text-gray-500 dark:text-gray-400">{s.display} · {formatShare(s.value, total)}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
};
