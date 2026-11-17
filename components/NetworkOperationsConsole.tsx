import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, Search } from 'lucide-react';
import { authFetch } from '../services/apiService';
import { socketService } from '../services/socketService';
import { Skeleton } from './ui/skeleton';
import { LiveStatus, PageHeader, ghostButton, useLiveData } from './network/NetworkKit';
import { RANGES, fetchTraffic, type RangeKey } from './network/opsData';
import { OpsKpis } from './network/ops/OpsKpis';
import { ThroughputChart } from './network/ops/ThroughputChart';
import { TrafficDistribution } from './network/ops/TrafficDistribution';
import { OpsTables, type OpsSelection } from './network/ops/OpsTables';
import { OpsDrawer } from './network/ops/OpsDrawer';

// Agents measure a new rate about once a minute; the socket pushes each one (endpoint_traffic) and
// this poll catches anything a push missed. Pushes refresh at most this often.
const POLL_MS = 15_000;
const PUSH_REFRESH_MS = 5_000;
const RANGE_LABEL: Record<RangeKey, string> = { '15m': '15 minutes', '1h': 'hour', '6h': '6 hours', '24h': '24 hours' };

const field = 'h-9 rounded-xl text-sm bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.08] text-gray-900 dark:text-white';

export const NetworkOperationsConsole: React.FC = () => {
    const [range, setRange] = useState<RangeKey>('1h');
    const [agentId, setAgentId] = useState('');
    const [query, setQuery] = useState('');
    const [selection, setSelection] = useState<OpsSelection | null>(null);
    const [streamUp, setStreamUp] = useState(socketService.connected);
    const [endpointOptions, setEndpointOptions] = useState<{ agentId: string; hostname: string }[]>([]);

    const fetcher = useCallback(() => fetchTraffic(authFetch, range, agentId || undefined), [range, agentId]);
    const live = useLiveData(fetcher, POLL_MS);
    const { refresh, paused, data } = live;
    const pausedRef = useRef(paused);
    pausedRef.current = paused;

    // A new range or endpoint loads at once (the first load is useLiveData's own).
    const firstRun = useRef(true);
    useEffect(() => {
        if (firstRun.current) { firstRun.current = false; return; }
        refresh();
    }, [range, agentId, refresh]);

    // The endpoint picker keeps every endpoint seen unfiltered, so filtering never empties it.
    useEffect(() => {
        if (data && !agentId) setEndpointOptions(data.endpoints.map(e => ({ agentId: e.agentId, hostname: e.hostname })));
    }, [data, agentId]);

    useEffect(() => {
        let last = 0;
        const onPush = () => {
            if (pausedRef.current || Date.now() - last < PUSH_REFRESH_MS) return;
            last = Date.now();
            refresh();
        };
        socketService.on('endpoint_traffic', onPush);
        const tick = setInterval(() => setStreamUp(socketService.connected), 5000);
        return () => { socketService.off('endpoint_traffic', onPush); clearInterval(tick); };
    }, [refresh]);

    const loadHistory = useCallback((id: string) => fetchTraffic(authFetch, range, id), [range]);
    const scope = agentId ? (endpointOptions.find(e => e.agentId === agentId)?.hostname ?? 'one endpoint') : 'all endpoints';

    return (
        <div className="space-y-4 pb-8">
            <PageHeader
                title="Network Operations"
                subtitle="Live transfer of your endpoints, their connections and their path to the internet"
                status={
                    <span title={streamUp ? 'New rates are pushed as agents report them' : `Refreshing every ${POLL_MS / 1000} s; live push is not connected`}>
                        <LiveStatus updatedAt={live.updatedAt} error={live.error} paused={paused} liveLabel={streamUp ? 'Stream: Live' : 'Live (polling)'} />
                    </span>
                }
                paused={paused}
                onTogglePause={() => live.setPaused(p => !p)}
                onRefresh={refresh}
                refreshing={live.loading}
            >
                <div role="group" aria-label="Time range" className="inline-flex h-9 p-0.5 rounded-xl border border-gray-200/80 dark:border-white/[0.08] bg-white dark:bg-gray-800">
                    {RANGES.map(r => (
                        <button key={r.key} type="button" aria-pressed={range === r.key} onClick={() => setRange(r.key)}
                            className={`px-2.5 rounded-[10px] text-sm font-mono font-medium transition-colors ${range === r.key
                                ? 'bg-primary-500/10 text-primary-700 dark:text-primary-300'
                                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}>{r.label}</button>
                    ))}
                </div>
                <label className="sr-only" htmlFor="ops-endpoint">Endpoint</label>
                <select id="ops-endpoint" value={agentId} onChange={e => setAgentId(e.target.value)} className={`${field} px-3 max-w-[12rem]`}>
                    <option value="">All endpoints</option>
                    {endpointOptions.map(e => <option key={e.agentId} value={e.agentId}>{e.hostname}</option>)}
                </select>
                <label className="relative block">
                    <span className="sr-only">Search endpoints and connections</span>
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" aria-hidden="true" />
                    <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search IP, host, process"
                        className={`${field} w-56 pl-9 pr-3 placeholder:text-gray-400`} />
                </label>
            </PageHeader>

            {!data ? (
                live.error ? (
                    <div role="alert" className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-5 flex items-start gap-3">
                        <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5" aria-hidden="true" />
                        <div className="flex-1">
                            <p className="font-medium text-red-800 dark:text-red-200">Network traffic could not be loaded</p>
                            <p className="mt-1 text-sm text-red-700 dark:text-red-300">{live.error}</p>
                        </div>
                        <button type="button" onClick={refresh} className={ghostButton}>Try again</button>
                    </div>
                ) : (
                    <div className="space-y-3" aria-busy="true">
                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">{[0, 1, 2, 3].map(i => <Skeleton key={i} variant="card" height={132} />)}</div>
                        <Skeleton variant="card" height={360} />
                    </div>
                )
            ) : (
                <>
                    <OpsKpis data={data} rangeLabel={RANGE_LABEL[range]} />
                    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,65fr)_minmax(0,35fr)] gap-3">
                        <ThroughputChart data={data} scope={scope} />
                        <TrafficDistribution data={data} rangeLabel={RANGE_LABEL[range]} />
                    </div>
                    <OpsTables data={data} query={query} rangeLabel={range} onOpen={setSelection} />
                </>
            )}

            {selection && data && (
                <OpsDrawer selection={selection} data={data} rangeLabel={RANGE_LABEL[range]} loadHistory={loadHistory} onClose={() => setSelection(null)} />
            )}
        </div>
    );
};
