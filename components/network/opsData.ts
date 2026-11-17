// Data helpers for the Network Operations console (GET /api/network-devices/traffic,
// backend/network_ops_service.py). Rates arrive in bytes per second and are shown in bits per
// second, as network tools do; amounts moved stay in bytes.

export type RangeKey = '15m' | '1h' | '6h' | '24h';
export const RANGES: { key: RangeKey; label: string }[] = [
    { key: '15m', label: '15m' }, { key: '1h', label: '1h' }, { key: '6h', label: '6h' }, { key: '24h', label: '24h' },
];

export interface SeriesPoint { t: string; txBps: number | null; rxBps: number | null }
export interface OpsEndpoint {
    agentId: string; hostname: string; ip?: string; platform?: string; os?: string; lastSeen?: string;
    status: 'Live' | 'Idle' | 'Down'; txBps: number | null; rxBps: number | null; rateAt?: string | null; windowSeconds?: number | null;
    rangeTxBytes: number; rangeRxBytes: number; bytesSent?: number; bytesRecv?: number;
    gateway?: { ip: string; mac?: string } | null; publicIp?: string;
    interfaces: { name: string; mac?: string; bytesSent?: number; bytesRecv?: number; packetsSent?: number; packetsRecv?: number }[];
    connections: number;
}
export interface OpsConnection {
    agentId: string; hostname: string; sourceIp?: string; destination: string; destinationIp?: string;
    port: number | null; protocol: 'HTTPS' | 'HTTP' | 'Other'; process?: string; pid?: number; scope: 'Internal' | 'External';
}
export interface TrafficSummary {
    generatedAt: string; range: RangeKey; rangeSeconds: number; bucketSeconds: number;
    series: SeriesPoint[];
    current: { txBps: number; rxBps: number; measured: number; online: number; endpoints: number };
    average: { txBps: number; rxBps: number } | null;
    previousAverage: { txBps: number; rxBps: number } | null;
    endpoints: OpsEndpoint[]; connections: OpsConnection[];
    protocols: { name: string; connections: number }[];
    notCollected: string[];
}

/** Bytes per second as bits per second, decimal units: "2.9 Mbps". */
export const formatBitRate = (bytesPerSecond?: number | null): string => {
    if (bytesPerSecond == null || !Number.isFinite(bytesPerSecond)) return '—';
    let bits = bytesPerSecond * 8;
    const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
    let i = 0;
    while (bits >= 1000 && i < units.length - 1) { bits /= 1000; i += 1; }
    return `${i === 0 ? Math.round(bits) : bits.toFixed(bits >= 100 ? 0 : 1)} ${units[i]}`;
};

/** Nearest-rank percentile of the known values, or null when there are none. */
export const percentile = (values: number[], p: number): number | null => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))];
};

export interface SeriesStats { min: number | null; max: number | null; p95: number | null }

export const seriesStats = (series: SeriesPoint[], key: 'txBps' | 'rxBps'): SeriesStats => {
    const values = series.map(p => p[key]).filter((v): v is number => typeof v === 'number');
    return { min: values.length ? Math.min(...values) : null, max: values.length ? Math.max(...values) : null, p95: percentile(values, 95) };
};

/** Change of the range's average against the same length of time before it, in percent. */
export const periodDelta = (now: number | null | undefined, before: number | null | undefined): number | null => {
    if (now == null || before == null || before <= 0) return null;
    return ((now - before) / before) * 100;
};

export const totalOf = (p: { txBps: number | null; rxBps: number | null } | null | undefined): number | null =>
    p && (p.txBps != null || p.rxBps != null) ? (p.txBps ?? 0) + (p.rxBps ?? 0) : null;

export const fetchTraffic = async (authFetch: (url: string) => Promise<Response>, range: RangeKey, agentId?: string): Promise<TrafficSummary> => {
    const params = new URLSearchParams({ range });
    if (agentId) params.set('agentId', agentId);
    const res = await authFetch(`/api/network-devices/traffic?${params}`);
    if (!res.ok) throw new Error(`Could not load network traffic (HTTP ${res.status})`);
    return res.json();
};
