// Rows, statuses and zone shares for the Network Topology console (header badges, zone panel and
// node table). Pure, so the shapes GET /api/network-devices/topology really sends can be tested.
import { isDown, isFreshRate } from './networkData';

export type NodeStatus = 'Live' | 'Idle' | 'Not measured' | 'Up' | 'Down' | 'Connected' | 'Unknown';
export type NodeGroup = 'Endpoints' | 'Gateways' | 'ISP' | 'Devices' | 'Remote';
export const NODE_GROUPS: NodeGroup[] = ['Endpoints', 'Gateways', 'ISP', 'Devices', 'Remote'];

export interface TopologyRow {
    id: string;
    name: string;
    ip?: string;
    mac?: string;
    group: NodeGroup | null;
    role: string;
    zone: string;
    vlanId?: string;
    /** The node one hop upstream: an endpoint's gateway, a gateway's internet, a remote host's endpoint. */
    via: string | null;
    viaCount: number;
    status: NodeStatus | null;
    sentBps: number | null;
    recvBps: number | null;
    links: number;
    updated: string | null;
}

export interface ZoneShare { zone: string; nodes: number; endpoints: number; down: number; sentBps: number; recvBps: number; vlans: string[] }

const firstLine = (label: unknown) => String(label ?? '').split('\n')[0];

const SHORT_ROLE: Record<string, string> = { Infrastructure: 'Infra', 'Remote host': 'Remote' };

export const nodeGroup = (d: any): NodeGroup | null => {
    if (d?.kind === 'internet') return null;
    if (d?.kind === 'agent') return 'Endpoints';
    if (d?.kind === 'remote') return 'Remote';
    if (d?.kind === 'isp') return 'ISP';
    if (d?.kind === 'gateway' || d?.kind === 'placeholder' || d?.role === 'Gateway') return 'Gateways';
    return 'Devices';
};

/**
 * Internet and the placeholder gateway are drawn by the map itself, so they have no status. A provider
 * is Up while an online endpoint reaches the platform through it; nothing else is known about it.
 */
export const nodeStatus = (d: any, now: number = Date.now()): NodeStatus | null => {
    if (d?.kind === 'internet' || d?.kind === 'placeholder') return null;
    if (d?.kind === 'remote') return 'Connected';
    if (d?.kind === 'isp') return d.status === 'Up' ? 'Up' : 'Unknown';
    if (isDown(d?.status)) return 'Down';
    if (d?.kind !== 'agent') return 'Up';
    if (!isFreshRate(d.metrics, now)) return 'Not measured';
    return d.metrics.sentBps + d.metrics.recvBps > 0 ? 'Live' : 'Idle';
};

const GROUP_RANK: Record<string, number> = { Endpoints: 0, Gateways: 1, ISP: 2, Devices: 3, Remote: 4 };

/** One row per node on the map, the busiest first, then endpoints, gateways, devices and remote hosts. */
export const topologyRows = (elements: any[], now: number = Date.now()): TopologyRow[] => {
    const data = elements.map(e => e?.data).filter(Boolean);
    const nodes = data.filter(d => !d.isZone && !d.isVlan && !d.source);
    const byId = new Map(nodes.map(d => [d.id, d]));
    const edges = data.filter(d => d.source);

    const rows = nodes.map((d): TopologyRow => {
        const incoming = edges.filter(e => e.target === d.id && byId.has(e.source));
        const fresh = d.kind === 'agent' && isFreshRate(d.metrics, now);
        const seenAt = d.kind === 'remote' ? incoming.map(e => e.seenAt).filter(Boolean).sort().pop() : undefined;
        return {
            id: d.id,
            name: firstLine(d.label) || d.id,
            ip: d.ip || undefined,
            mac: d.details?.macAddress,
            group: nodeGroup(d),
            role: SHORT_ROLE[d.role] ?? d.role ?? (d.kind === 'internet' ? 'Internet' : 'Device'),
            zone: d.zone || 'Other',
            vlanId: d.vlanId ? String(d.vlanId) : undefined,
            via: incoming.length ? firstLine(byId.get(incoming[0].source).label) : null,
            viaCount: incoming.length,
            status: nodeStatus(d, now),
            sentBps: fresh ? d.metrics.sentBps : null,
            recvBps: fresh ? d.metrics.recvBps : null,
            links: edges.filter(e => e.source === d.id || e.target === d.id).length,
            updated: fresh ? d.metrics.rateAt : seenAt || d.details?.lastSeen || null,
        };
    });
    const load = (r: TopologyRow) => (r.sentBps == null ? -1 : r.sentBps + (r.recvBps ?? 0));
    return rows.sort((a, b) => load(b) - load(a)
        || (GROUP_RANK[a.group ?? ''] ?? 5) - (GROUP_RANK[b.group ?? ''] ?? 5)
        || a.name.localeCompare(b.name));
};

/** Nodes, endpoints, outages and measured transfer per zone, the busiest zone first. */
export const zoneShares = (rows: TopologyRow[]): ZoneShare[] => {
    const zones = new Map<string, ZoneShare>();
    for (const r of rows) {
        const z = zones.get(r.zone) ?? { zone: r.zone, nodes: 0, endpoints: 0, down: 0, sentBps: 0, recvBps: 0, vlans: [] };
        z.nodes += 1;
        if (r.group === 'Endpoints') z.endpoints += 1;
        if (r.status === 'Down') z.down += 1;
        z.sentBps += r.sentBps ?? 0;
        z.recvBps += r.recvBps ?? 0;
        if (r.vlanId && !z.vlans.includes(r.vlanId)) z.vlans.push(r.vlanId);
        zones.set(r.zone, z);
    }
    return [...zones.values()].sort((a, b) => (b.sentBps + b.recvBps) - (a.sentBps + a.recvBps) || b.nodes - a.nodes || a.zone.localeCompare(b.zone));
};

export const rowMatches = (r: TopologyRow, query: string): boolean => {
    const q = query.trim().toLowerCase();
    return !q || [r.name, r.ip, r.mac, r.role, r.zone, r.via].some(v => String(v ?? '').toLowerCase().includes(q));
};

export interface Destination { id: string; name: string; ip?: string; ports: number[]; processes: string[]; connections: number; from: string[] }

/** Remote hosts endpoints had open connections to in their latest reports, the most used first. */
export const topDestinations = (elements: any[], limit = 6): Destination[] => {
    const data = elements.map(e => e?.data).filter(Boolean);
    const byId = new Map(data.filter(d => !d.source).map(d => [d.id, d]));
    const dest = new Map<string, Destination>();
    for (const e of data) {
        if (e.kind !== 'flow' || !byId.has(e.target) || !byId.has(e.source)) continue;
        const target = byId.get(e.target);
        const d: Destination = dest.get(e.target) ?? { id: e.target, name: firstLine(target.label), ip: target.ip || undefined, ports: [], processes: [], connections: 0, from: [] };
        d.connections += Number(e.connections) || 0;
        for (const port of e.ports || []) if (!d.ports.includes(port)) d.ports.push(port);
        for (const proc of e.processes || []) if (!d.processes.includes(proc)) d.processes.push(proc);
        d.from.push(firstLine(byId.get(e.source).label));
        dest.set(e.target, d);
    }
    return [...dest.values()].sort((a, b) => b.connections - a.connections || a.name.localeCompare(b.name)).slice(0, limit);
};
