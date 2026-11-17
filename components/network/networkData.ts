// Pure data helpers for the Network Topology, Data Utilization and Web Monitoring screens.
// Kept free of React so the shapes agents and the API really send can be tested directly.

export const formatBytes = (bytes: number, decimals = 1): string => {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : decimals))} ${sizes[i]}`;
};

export const formatShare = (part: number, whole: number): string => {
    if (!whole) return '0%';
    const pct = (part / whole) * 100;
    return pct > 0 && pct < 1 ? '<1%' : `${Math.round(pct)}%`;
};

/** "just now", "40 s ago", "3 min ago", "2 h ago" — for the live status pill. */
export const formatAgo = (from: number, now: number = Date.now()): string => {
    const s = Math.max(0, Math.round((now - from) / 1000));
    if (s < 5) return 'just now';
    if (s < 60) return `${s} s ago`;
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    return `${Math.floor(s / 3600)} h ago`;
};

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/;

/**
 * The Python agent stamps web connections with a naive local time (no zone), so it cannot be
 * converted to the viewer's zone. Those are shown as written, flagged as the agent's clock.
 */
export const formatAgentTime = (ts?: string): { text: string; naive: boolean } => {
    if (!ts) return { text: '—', naive: false };
    if (HAS_ZONE.test(ts)) {
        const d = new Date(ts);
        return Number.isNaN(d.getTime()) ? { text: ts, naive: false } : { text: d.toLocaleString(), naive: false };
    }
    return { text: ts.replace('T', ' ').slice(0, 19), naive: true };
};

// ── Web Monitoring ──────────────────────────────────────────────────────────

export interface WebConnection {
    hostname: string;
    process: string;
    pid?: number;
    destination: string;
    port: number;
    timestamp?: string;
}

export type WebServer = 'Nginx' | 'Apache' | 'IIS' | 'Other';

export interface WebLogLine {
    hostname: string;
    message: string;
    time?: string;
    server: WebServer;
}

export interface WebActivity {
    connections: WebConnection[];
    logs: WebLogLine[];
    totalAgents: number;
    /** Agents whose last report carried web-connection data (the Linux agent's Web Monitor). */
    reportingAgents: number;
}

const ENCRYPTED_PORTS = new Set([443, 8443]);
export const isEncrypted = (port: number) => ENCRYPTED_PORTS.has(port);

// An HTTP request line or status line, or a web server named as the event source.
const WEB_LINE = /\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS) \/|\bHTTP\/\d/;
const WEB_SOURCE = /nginx|apache|httpd|w3svc|w3wp|\biis\b/i;

export const classifyWebServer = (text: string): WebServer => {
    const t = text.toLowerCase();
    if (t.includes('nginx')) return 'Nginx';
    if (t.includes('apache') || t.includes('httpd')) return 'Apache';
    if (/\biis\b/.test(t) || t.includes('w3svc') || t.includes('w3wp')) return 'IIS';
    return 'Other';
};

/** The Python agent sends {logs: [...]}, the Rust agent {recent_events: [...]}; older builds an array. */
const logEntries = (lc: unknown): any[] => {
    if (Array.isArray(lc)) return lc;
    if (lc && typeof lc === 'object') {
        const o = lc as Record<string, unknown>;
        if (Array.isArray(o.logs)) return o.logs;
        if (Array.isArray(o.recent_events)) return o.recent_events;
    }
    return [];
};

export const collectWebActivity = (agents: any[]): WebActivity => {
    const connections: WebConnection[] = [];
    const logs: WebLogLine[] = [];
    let reportingAgents = 0;

    for (const agent of agents || []) {
        const meta = agent?.meta || {};
        const hostname = agent?.hostname || agent?.id || 'Unknown';
        const wm = meta.web_monitor;
        if (wm && Array.isArray(wm.web_connections)) {
            reportingAgents += 1;
            for (const c of wm.web_connections) {
                const destination = c?.remote_host || c?.remote_ip;
                if (!destination) continue;
                connections.push({
                    hostname,
                    process: c.process || 'unknown',
                    pid: typeof c.pid === 'number' ? c.pid : undefined,
                    destination,
                    port: Number(c.port) || 0,
                    timestamp: c.timestamp,
                });
            }
        }
        for (const entry of logEntries(meta.log_collection)) {
            const message = String(entry?.message || '');
            const source = String(entry?.source || '');
            if (!WEB_LINE.test(message) && !WEB_SOURCE.test(source)) continue;
            logs.push({ hostname, message, time: entry.time || entry.timestamp, server: classifyWebServer(`${source} ${message}`) });
        }
    }
    return { connections, logs, totalAgents: (agents || []).length, reportingAgents };
};

export interface RankedItem { key: string; label: string; value: number; note?: string }

/** Count items by a key, most frequent first. */
export const rankBy = <T,>(items: T[], keyOf: (item: T) => string, limit = 8): RankedItem[] => {
    const counts = new Map<string, number>();
    for (const item of items) counts.set(keyOf(item), (counts.get(keyOf(item)) || 0) + 1);
    return [...counts.entries()]
        .map(([key, value]) => ({ key, label: key, value }))
        .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
        .slice(0, limit);
};

// ── Network Topology ────────────────────────────────────────────────────────

/** Same id the backend gives zone parents (Python str.replace swaps every space). */
export const zoneId = (zone: string) => `zone-${zone.replace(/ /g, '-')}`;

// Nodes that are not machines on the network: the Internet, the placeholder gateway, remote hosts.
const SYNTHETIC_NODES = new Set(['internet', 'virtual-gateway']);
const NOT_DEVICES = new Set(['internet', 'placeholder', 'remote']);

/**
 * Cytoscape elements from GET /api/network-devices/topology. Every zone a node belongs to gets a
 * parent (the API also places nodes in a DMZ), VLAN parents the API assigned are kept, and edges
 * or parents that point at missing nodes are dropped instead of erroring in Cytoscape.
 */
export const buildTopologyElements = (data: any): any[] => {
    const nodes: any[] = data?.elements?.nodes || [];
    const edges: any[] = data?.elements?.edges || [];
    const ids = new Set(nodes.map(n => n?.data?.id).filter(Boolean));
    const zones = new Map<string, string>();

    const mapped = nodes.filter(n => n?.data?.id).map(n => {
        const d = n.data;
        let parent: string | undefined = d.parent;
        if (parent && !parent.startsWith('zone-') && !ids.has(parent)) parent = undefined;
        if (!parent && !d.isVlan) parent = zoneId(d.zone || 'Internal LAN');
        if (parent?.startsWith('zone-')) zones.set(parent, d.zone || parent.slice(5).replace(/-/g, ' '));
        return { ...n, data: { ...d, parent } };
    });

    const zoneNodes = [...zones.entries()].map(([id, label]) => ({ data: { id, label, isZone: true }, selectable: false }));
    const vlans = mapped.filter(n => n.data.isVlan);
    const rest = mapped.filter(n => !n.data.isVlan);
    const liveEdges = edges.filter(e => ids.has(e?.data?.source) && ids.has(e?.data?.target));
    return [...zoneNodes, ...vlans, ...rest, ...liveEdges];
};

export const isDeviceNode = (d: any) => !!d && !d.isZone && !d.isVlan && !d.source && !SYNTHETIC_NODES.has(d.id) && !NOT_DEVICES.has(d.kind);

export const isDown = (status?: string) => !!status && status.toLowerCase() === 'down';

// ── Live transfer ───────────────────────────────────────────────────────────

/** A rate the backend measured between two changes of an agent's byte counters (network_rate.py). */
export interface LiveRate { sentBps: number; recvBps: number; at: string; windowSeconds?: number }

// Same freshness the API applies (network_topology_service.RATE_FRESH_FOR).
export const RATE_FRESH_MS = 5 * 60 * 1000;

export const formatRate = (bps?: number) => `${formatBytes(bps ?? 0)}/s`;

export const isFreshRate = (m: any, now: number = Date.now()) =>
    !!m?.rateAt && typeof m.sentBps === 'number' && typeof m.recvBps === 'number' && now - Date.parse(m.rateAt) <= RATE_FRESH_MS;

/**
 * Overlays rates pushed over the socket (newer than the last fetch) on the endpoint nodes, then
 * sets what the map draws on every link. Every field is always written: Cytoscape merges data on
 * update, so a field left out would keep its old value.
 */
export const withLiveTraffic = (elements: any[], pushed: Record<string, LiveRate>, now: number = Date.now()): any[] => {
    const metricsById = new Map<string, any>();
    const withRates = elements.map(el => {
        const d = el.data;
        if (!d || d.source || d.kind !== 'agent') return el;
        const current = d.metrics || {};
        const push = pushed[d.agentId];
        const newer = push && (!current.rateAt || Date.parse(push.at) > Date.parse(current.rateAt));
        const metrics = newer ? { ...current, sentBps: push.sentBps, recvBps: push.recvBps, rateAt: push.at, windowSeconds: push.windowSeconds } : current;
        metricsById.set(d.id, metrics);
        return newer ? { ...el, data: { ...d, metrics } } : el;
    });
    return withRates.map(el => {
        const d = el.data;
        if (!d?.source) return el;
        const m = d.kind === 'uplink' ? metricsById.get(d.target) : undefined;
        const live = !!m && isFreshRate(m, now) && (m.sentBps > 0 || m.recvBps > 0);
        const total = live ? m.sentBps + m.recvBps : 0;
        return {
            ...el,
            data: {
                ...d,
                active: live,
                rateLabel: live ? `↑ ${formatRate(m.sentBps)}   ↓ ${formatRate(m.recvBps)}` : '',
                width: live ? Math.min(6, 1.5 + Math.log10(1 + total / 1024)) : 1.5,
                // Dashes run the way most bytes go: down to the endpoint, or up to its gateway.
                towardTarget: live ? m.recvBps >= m.sentBps : true,
                bps: total,
            },
        };
    });
};

export const topologyStats = (elements: any[], now: number = Date.now()) => {
    const data = elements.map(e => e.data || {});
    const endpoints = data.filter(d => d.kind === 'agent');
    const measured = endpoints.filter(d => isFreshRate(d.metrics, now));
    return {
        endpoints: endpoints.length,
        devices: data.filter(d => isDeviceNode(d) && d.kind !== 'agent').length,
        remote: data.filter(d => d.kind === 'remote').length,
        down: data.filter(d => isDeviceNode(d) && isDown(d.status)).length,
        links: data.filter(d => d.source).length,
        zones: data.filter(d => d.isZone).length,
        segments: data.filter(d => d.isVlan).length,
        measured: measured.length,
        sentBps: measured.reduce((s, d) => s + d.metrics.sentBps, 0),
        recvBps: measured.reduce((s, d) => s + d.metrics.recvBps, 0),
    };
};

/** Device-record facts worth showing, skipping the scanner's "Unknown" placeholders. */
export const deviceFacts = (details: any): { label: string; value: string }[] => {
    if (!details || typeof details !== 'object') return [];
    const known = (v: unknown) => v !== undefined && v !== null && v !== '' && v !== 'Unknown';
    const facts: { label: string; value: string }[] = [];
    const add = (label: string, v: unknown) => { if (known(v)) facts.push({ label, value: String(v) }); };
    add('MAC address', details.macAddress);
    add('Vendor', details.vendor);
    add('Model', details.model);
    add('OS', details.osVersion);
    add('Subnet', details.subnet);
    add('Public IP', details.publicIp);
    add('Agent version', details.agentVersion);
    add('Found in', details.source);
    if (Array.isArray(details.openPorts) && details.openPorts.length) {
        facts.push({ label: 'Open ports', value: [...details.openPorts].sort((a, b) => Number(a) - Number(b)).join(', ') });
    }
    if (known(details.lastSeen)) {
        const d = new Date(details.lastSeen);
        facts.push({ label: 'Last seen', value: Number.isNaN(d.getTime()) ? String(details.lastSeen) : d.toLocaleString() });
    }
    return facts;
};
