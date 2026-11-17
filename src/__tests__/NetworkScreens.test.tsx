/**
 * Network Topology, Data Utilization and Web Monitoring:
 *  1. Web activity is read from both agents' log shapes ({logs} and {recent_events}) and the
 *     Web Monitor connections, and a coverage count says how many agents report.
 *  2. Topology elements keep API-assigned VLAN parents, get a parent for every zone (incl. DMZ),
 *     and drop links to missing nodes.
 *  3. useLiveData never lets an older reply overwrite a newer one.
 *  4. The three screens render real data, and the topology list view opens a device's details.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
const socketHandlers: Record<string, (data: any) => void> = {};
vi.mock('../../services/socketService', () => ({
    socketService: { on: (ev: string, fn: (data: any) => void) => { socketHandlers[ev] = fn; }, off: vi.fn(), connected: false },
}));
vi.mock('react-cytoscapejs', () => ({ default: () => null }));
vi.mock('cytoscape', () => ({ default: { use: vi.fn() } }));
vi.mock('cytoscape-cose-bilkent', () => ({ default: {} }));

import { collectWebActivity, buildTopologyElements, topologyStats, formatAgentTime, deviceFacts, formatBytes, withLiveTraffic } from '../../components/network/networkData';
import { useLiveData } from '../../components/network/NetworkKit';
import { WebMonitoringDashboard } from '../../components/WebMonitoringDashboard';
import { DataUtilizationDashboard } from '../../components/DataUtilizationDashboard';
import { NetworkTopologyMap } from '../../components/NetworkTopologyMap';
import { topologyRows, zoneShares, rowMatches } from '../../components/network/topologyData';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

// Shapes as the live agents report them (Python agent on Linux, Rust agent on Windows).
const linuxAgent = {
    id: 'a-linux', hostname: 'Omniai-copy',
    meta: {
        web_monitor: { status: 'success', web_connections: [
            { process: 'claude', pid: 22708, remote_ip: '160.79.104.10', remote_host: '160.79.104.10', port: 443, timestamp: '2026-11-17T17:58:18.586396' },
            { process: 'curl', pid: 9, remote_ip: '93.184.215.14', remote_host: 'example.com', port: 80, timestamp: '2026-11-17T17:58:18.6' },
        ] },
        log_collection: { count: 2, logs: [
            { message: 'nginx: 10.0.0.5 "GET /health HTTP/1.1" 200', level: 'INFO' },
            { message: 'TARGET reached', level: 'INFO' },
        ] },
    },
};
const windowsAgent = {
    id: 'a-win', hostname: 'EILT0197',
    meta: { log_collection: { error_count: 0, recent_events: [
        { source: 'Microsoft-Windows-IIS-W3SVC', message: 'Worker process started', time: '2026-11-17T23:28:55+05:30' },
        { source: 'Microsoft-Windows-WindowsUpdateClient', message: 'Installation Successful', time: '2026-11-17T23:28:55+05:30' },
    ] } },
};

describe('collectWebActivity', () => {
    it('reads connections, both log shapes and the coverage count', () => {
        const a = collectWebActivity([linuxAgent, windowsAgent]);
        expect(a.totalAgents).toBe(2);
        expect(a.reportingAgents).toBe(1);
        expect(a.connections.map(c => c.destination)).toEqual(['160.79.104.10', 'example.com']);
        expect(a.connections[0].hostname).toBe('Omniai-copy');
        expect(a.logs.map(l => [l.hostname, l.server])).toEqual([['Omniai-copy', 'Nginx'], ['EILT0197', 'IIS']]);
    });

    it('still accepts the older array shape', () => {
        const a = collectWebActivity([{ hostname: 'old', meta: { log_collection: [{ message: 'POST /login HTTP/2 302' }] } }]);
        expect(a.logs).toHaveLength(1);
        expect(a.logs[0].server).toBe('Other');
    });
});

describe('formatAgentTime', () => {
    it('keeps a zone-less agent time as written and flags it', () => {
        expect(formatAgentTime('2026-11-17T17:58:18.586396')).toEqual({ text: '2026-11-17 17:58:18', naive: true });
        expect(formatAgentTime('2026-11-17T17:58:18Z').naive).toBe(false);
    });
});

describe('buildTopologyElements', () => {
    const data = { elements: {
        nodes: [
            { data: { id: 'internet', zone: 'Internet', type: 'cloud', label: 'Internet' } },
            { data: { id: 'gw', zone: 'Perimeter', role: 'Gateway', label: 'gw' } },
            { data: { id: 'web', zone: 'DMZ', role: 'Server', label: 'web', status: 'Down' } },
            { data: { id: 'vlan-10', isVlan: true, vlanId: 10, parent: 'zone-Internal-LAN', label: 'VLAN 10' } },
            { data: { id: 'pc', zone: 'Internal LAN', parent: 'vlan-10', label: 'pc' } },
            { data: { id: 'orphan', zone: 'Internal LAN', parent: 'vlan-99', label: 'orphan' } },
        ],
        edges: [
            { data: { id: 'e1', source: 'internet', target: 'gw' } },
            { data: { id: 'e2', source: 'gw', target: 'web' } },
            { data: { id: 'e3', source: 'gw', target: 'ghost' } },
        ],
    } };

    it('gives every zone a parent, keeps VLAN parents and drops dangling references', () => {
        const els = buildTopologyElements(data);
        const byId = new Map(els.map(e => [e.data.id, e]));
        expect(byId.get('zone-DMZ')?.data.isZone).toBe(true);
        expect(byId.get('zone-DMZ')?.selectable).toBe(false);
        expect(byId.get('web')?.data.parent).toBe('zone-DMZ');
        expect(byId.get('pc')?.data.parent).toBe('vlan-10');
        expect(byId.get('orphan')?.data.parent).toBe('zone-Internal-LAN');
        expect(byId.has('e3')).toBe(false);
        expect(topologyStats(els)).toMatchObject({ endpoints: 0, devices: 4, remote: 0, down: 1, links: 2, zones: 4, segments: 1, measured: 0 });
    });

    it('lists only real device facts', () => {
        expect(deviceFacts({ macAddress: 'aa:bb', vendor: 'Unknown', openPorts: [443, 22] }))
            .toEqual([{ label: 'MAC address', value: 'aa:bb' }, { label: 'Open ports', value: '22, 443' }]);
    });
});

describe('useLiveData', () => {
    it('ignores a slow older reply that lands after a newer one', async () => {
        const resolvers: ((v: string) => void)[] = [];
        const fetcher = () => new Promise<string>(r => resolvers.push(r));
        let api: ReturnType<typeof useLiveData<string>> | null = null;
        const Probe = () => { api = useLiveData(fetcher, 0); return <p>{api.data ?? 'none'}</p>; };
        render(<Probe />);
        await act(async () => { api!.refresh(); });
        await act(async () => { resolvers[1]('new'); });
        await act(async () => { resolvers[0]('old'); });
        expect(screen.getByText('new')).toBeTruthy();
    });
});

describe('screens', () => {
    // A block body: a function returned from beforeEach would be run as a teardown hook.
    beforeEach(() => { authFetch.mockReset(); });

    it('Web Monitoring pages through every agent and shows what they report', async () => {
        authFetch.mockImplementation(async (url: string) => url.includes('page=1')
            ? ok({ items: [linuxAgent], hasNext: true })
            : ok({ items: [windowsAgent], hasNext: false }));
        render(<WebMonitoringDashboard />);
        await screen.findByText('From 1 of 2 agents');
        expect(authFetch).toHaveBeenCalledTimes(2);
        expect(screen.getAllByText('example.com').length).toBeGreaterThan(0);
        expect(screen.getByText('Worker process started')).toBeTruthy();
        expect(screen.getByText('Unencrypted (HTTP)')).toBeTruthy();
    });

    it('Data Utilization shows totals and sorts the endpoint table', async () => {
        authFetch.mockResolvedValue(ok({ totalBytesSent: 3072, totalBytesRecv: 1024, agents: [
            { id: 'a1', hostname: 'alpha', ipAddress: '10.0.0.1', os: 'Linux', bytesSent: 1024, bytesRecv: 1024 },
            { id: 'a2', hostname: 'bravo', ipAddress: '10.0.0.2', os: 'Windows', bytesSent: 2048, bytesRecv: 0 },
        ] }));
        render(<DataUtilizationDashboard />);
        expect(await screen.findByText(formatBytes(4096))).toBeTruthy();
        const firstHost = () => screen.getAllByRole('row')[1].textContent;
        expect(firstHost()).toContain('alpha');
        fireEvent.click(screen.getByRole('button', { name: /Endpoint/ }));
        expect(firstHost()).toContain('alpha');
        fireEvent.click(screen.getByRole('button', { name: /Endpoint/ }));
        expect(firstHost()).toContain('bravo');
    });

    it('Data Utilization explains a failed load and can retry', async () => {
        authFetch.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) });
        render(<DataUtilizationDashboard />);
        expect(await screen.findByText('Utilization data could not be loaded')).toBeTruthy();
        authFetch.mockResolvedValueOnce(ok({ totalBytesSent: 0, totalBytesRecv: 0, agents: [] }));
        fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
        await waitFor(() => expect(screen.queryByText('Utilization data could not be loaded')).toBeNull());
    });

    it('Topology node table opens a device', async () => {
        authFetch.mockImplementation(async (url: string) => url.includes('/traffic') ? ok(emptyTraffic) : ok({ elements: {
            nodes: [
                { data: { id: 'internet', zone: 'Internet', type: 'cloud', label: 'Internet (External)\n1.2.3.4', ip: '1.2.3.4', status: 'up' } },
                { data: { id: 'pc', zone: 'Internal LAN', label: 'pc-01\n(10.0.0.9)', ip: '10.0.0.9', status: 'Up', details: { macAddress: 'aa:bb:cc' } } },
            ],
            edges: [{ data: { id: 'e', source: 'internet', target: 'pc' } }],
        } }));
        render(<NetworkTopologyMap refreshKey={0} />);
        fireEvent.click(await screen.findByRole('button', { name: 'pc-01' }));
        const panel = await screen.findByRole('complementary', { name: 'Details for pc-01' });
        expect(panel.textContent).toContain('aa:bb:cc');
        expect(panel.textContent).toContain('Internet (External)');
        fireEvent.keyDown(window, { key: 'Escape' });
        await waitFor(() => expect(screen.queryByRole('complementary')).toBeNull());
    });

    it('Topology shows an endpoint’s live transfer and latest connections, and takes pushed rates', async () => {
        authFetch.mockImplementation(async (url: string) => url.includes('/traffic') ? ok(emptyTraffic) : ok(endpointTopology(new Date(Date.now() - 20_000).toISOString())));
        render(<NetworkTopologyMap refreshKey={0} />);
        const table = await screen.findByRole('table', { name: /Nodes on the network map/ });
        // 41 000 + 178 000 bytes/s, shown in bits as network tools do.
        expect(within(table).getByText('1.8 Mbps')).toBeTruthy();
        fireEvent.click(within(table).getByRole('button', { name: 'EILT0197' }));
        const panel = await screen.findByRole('complementary', { name: 'Details for EILT0197' });
        expect(panel.textContent).toContain('Upload');
        expect(panel.textContent).toContain('api.anthropic.com');
        expect(panel.textContent).toContain('port 443 · claude, node · 2 open');
        act(() => socketHandlers.endpoint_traffic({ agentId: 'a-win', sentBps: 2048, recvBps: 4096, at: new Date().toISOString(), windowSeconds: 30 }));
        expect(await within(table).findByText('49.2 Kbps')).toBeTruthy();
    });

    it('Topology flags what is down, filters by zone and pauses pushed rates', async () => {
        const topo = endpointTopology(new Date(Date.now() - 20_000).toISOString());
        topo.elements.nodes.push({ data: { id: 'nb-192.168.0.7', label: 'printer-2\n(192.168.0.7)', ip: '192.168.0.7', zone: 'Internal LAN', role: 'Neighbour', kind: 'neighbour', status: 'Down' } } as any);
        authFetch.mockImplementation(async (url: string) => url.includes('/traffic') ? ok(emptyTraffic) : ok(topo));
        render(<NetworkTopologyMap refreshKey={0} />);
        const table = await screen.findByRole('table', { name: /Nodes on the network map/ });
        expect(within(screen.getByRole('banner')).getByText('1 down')).toBeTruthy();
        expect(within(table).getAllByRole('row')).toHaveLength(6); // header + 5 nodes

        fireEvent.click(screen.getByRole('button', { name: /^Perimeter/ }));
        await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
        expect(within(table).getByRole('button', { name: 'Gateway' })).toBeTruthy();
        expect(screen.getByText('Showing 1 of 5 nodes')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Clear the zone and search filters' }));
        await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(6));

        fireEvent.click(screen.getByRole('button', { name: 'Pause updates' }));
        act(() => socketHandlers.endpoint_traffic({ agentId: 'a-win', sentBps: 2048, recvBps: 4096, at: new Date().toISOString(), windowSeconds: 30 }));
        expect(within(table).queryByText('49.2 Kbps')).toBeNull();
        expect(within(table).getByText('1.8 Mbps')).toBeTruthy();
    });
});

const emptyTraffic = { series: [], current: { txBps: 0, rxBps: 0, measured: 0, online: 0, endpoints: 0 }, average: null, previousAverage: null, endpoints: [], connections: [], protocols: [], notCollected: [] };

// What GET /api/network-devices/topology answers for one Windows endpoint behind its gateway.
function endpointTopology(rateAt: string) {
    return { elements: {
        nodes: [
            { data: { id: 'internet', label: 'Internet', zone: 'Internet', kind: 'internet', status: 'up', icon: 'cloud' } },
            { data: { id: 'gw-192.168.0.1', label: 'Gateway\n(192.168.0.1)', ip: '192.168.0.1', zone: 'Perimeter', role: 'Gateway', kind: 'gateway', status: 'Up' } },
            { data: { id: 'agent-a-win', label: 'EILT0197\n(192.168.0.105)', ip: '192.168.0.105', zone: 'Internal LAN', role: 'Endpoint', kind: 'agent', agentId: 'a-win', status: 'Up',
                metrics: { sentBps: 41_000, recvBps: 178_000, rateAt, windowSeconds: 42, bytesSent: 1, bytesRecv: 2 } } },
            { data: { id: 'remote-api.anthropic.com', label: 'api.anthropic.com', zone: 'Internet', role: 'Remote host', kind: 'remote', status: 'Up', icon: 'globe' } },
        ],
        edges: [
            { data: { id: 'e1', source: 'internet', target: 'gw-192.168.0.1', kind: 'uplink' } },
            { data: { id: 'e2', source: 'gw-192.168.0.1', target: 'agent-a-win', kind: 'uplink' } },
            { data: { id: 'e3', source: 'agent-a-win', target: 'remote-api.anthropic.com', kind: 'flow', ports: [443], processes: ['claude', 'node'], connections: 2 } },
        ],
    } };
}

describe('withLiveTraffic', () => {
    const at = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();

    it('animates an uplink only while its endpoint has a fresh rate, and always writes every field', () => {
        const els = withLiveTraffic(buildTopologyElements(endpointTopology(at(20_000))), {});
        const edge = (id: string) => els.find(e => e.data.id === id).data;
        expect(edge('e2')).toMatchObject({ active: true, towardTarget: true });
        expect(edge('e2').rateLabel).toContain('↑');
        expect(edge('e2').width).toBeGreaterThan(1.5);
        expect(edge('e3')).toMatchObject({ active: false, rateLabel: '', width: 1.5 });
        expect(topologyStats(els)).toMatchObject({ endpoints: 1, remote: 1, measured: 1, sentBps: 41_000 });

        const stale = withLiveTraffic(buildTopologyElements(endpointTopology(at(10 * 60_000))), {});
        expect(stale.find(e => e.data.id === 'e2').data).toMatchObject({ active: false, rateLabel: '' });
    });

    it('takes a pushed rate only when it is newer than the fetched one', () => {
        const fetched = buildTopologyElements(endpointTopology(at(20_000)));
        const newer = withLiveTraffic(fetched, { 'a-win': { sentBps: 1, recvBps: 0, at: at(0) } });
        expect(newer.find(e => e.data.id === 'agent-a-win').data.metrics.sentBps).toBe(1);
        expect(newer.find(e => e.data.id === 'e2').data.towardTarget).toBe(false);
        const older = withLiveTraffic(fetched, { 'a-win': { sentBps: 1, recvBps: 0, at: at(60_000) } });
        expect(older.find(e => e.data.id === 'agent-a-win').data.metrics.sentBps).toBe(41_000);
    });
});

describe('topologyRows', () => {
    const at = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();

    it('ranks the busiest node first and says what each one is, where it hangs off and how it is', () => {
        const rows = topologyRows(withLiveTraffic(buildTopologyElements(endpointTopology(at(20_000))), {}));
        expect(rows.map(r => r.name)).toEqual(['EILT0197', 'Gateway', 'api.anthropic.com', 'Internet']);
        expect(rows[0]).toMatchObject({ group: 'Endpoints', via: 'Gateway', status: 'Live', sentBps: 41_000, recvBps: 178_000, links: 2 });
        expect(rows[1]).toMatchObject({ group: 'Gateways', via: 'Internet', status: 'Up' });
        expect(rows[2]).toMatchObject({ group: 'Remote', role: 'Remote', via: 'EILT0197', status: 'Connected', sentBps: null });
        expect(rows[3]).toMatchObject({ group: null, status: null });
        expect(rowMatches(rows[0], '192.168.0.105')).toBe(true);
        expect(rowMatches(rows[0], 'nope')).toBe(false);
    });

    it('marks an online endpoint without a fresh rate as not measured, and sums zones', () => {
        const rows = topologyRows(withLiveTraffic(buildTopologyElements(endpointTopology(at(10 * 60_000))), {}));
        expect(rows.find(r => r.group === 'Endpoints')).toMatchObject({ status: 'Not measured', sentBps: null });
        const fresh = zoneShares(topologyRows(withLiveTraffic(buildTopologyElements(endpointTopology(at(20_000))), {})));
        expect(fresh[0]).toMatchObject({ zone: 'Internal LAN', endpoints: 1, sentBps: 41_000, recvBps: 178_000 });
        expect(fresh.map(z => z.zone)).toEqual(['Internal LAN', 'Internet', 'Perimeter']);
    });
});

// The same endpoint reaching the internet through its provider (backend _provider / isp_node).
function ispTopology(rateAt: string, isp: Record<string, unknown>) {
    const topo = endpointTopology(rateAt);
    topo.elements.nodes.push({ data: { zone: 'Internet', role: 'ISP', kind: 'isp', icon: 'isp', type: 'Internet provider', ...isp } } as any);
    const ispId = isp.id as string;
    topo.elements.edges = topo.elements.edges.filter(e => e.data.id !== 'e1');
    topo.elements.edges.push({ data: { id: 'e-isp-1', source: 'internet', target: ispId, kind: 'uplink' } } as any,
        { data: { id: 'e-isp-2', source: ispId, target: 'gw-192.168.0.1', kind: 'uplink' } } as any);
    return topo;
}

describe('internet provider', () => {
    const at = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();
    const named = { id: 'isp-as24560', label: 'Bharti Airtel Ltd.\n(AS24560)', ip: '103.174.161.211', status: 'Up', ispKnown: true,
        details: { isp: 'Bharti Airtel Ltd.', asn: 24560, publicIp: '103.174.161.211', location: 'Chennai, India', reportedBy: 'EILT0197' } };

    it('sits between the Internet and the gateway and is listed as an ISP', () => {
        const rows = topologyRows(withLiveTraffic(buildTopologyElements(ispTopology(at(20_000), named)), {}));
        expect(rows.find(r => r.id === 'isp-as24560')).toMatchObject({ name: 'Bharti Airtel Ltd.', group: 'ISP', role: 'ISP', via: 'Internet', status: 'Up', ip: '103.174.161.211' });
        expect(rows.find(r => r.id === 'gw-192.168.0.1')?.via).toBe('Bharti Airtel Ltd.');
        expect(topologyStats(buildTopologyElements(ispTopology(at(20_000), named)))).toMatchObject({ devices: 1 }); // the gateway only
        expect(deviceFacts(named.details)).toEqual([
            { label: 'Provider', value: 'Bharti Airtel Ltd.' }, { label: 'AS number', value: 'AS24560' },
            { label: 'Public IP', value: '103.174.161.211' }, { label: 'Location', value: 'Chennai, India' }, { label: 'Reported by', value: 'EILT0197' },
        ]);
    });

    it('says why a provider is not named, without claiming it is up', async () => {
        const unnamed = { id: 'isp-ip-103.174.161.211', label: 'ISP not identified\n(103.174.161.211)', ip: '103.174.161.211', status: 'Unknown', ispKnown: false,
            details: { publicIp: '103.174.161.211', reportedBy: 'EILT0197' } };
        authFetch.mockImplementation(async (url: string) => url.includes('/traffic') ? ok(emptyTraffic) : ok(ispTopology(at(20_000), unnamed)));
        render(<NetworkTopologyMap refreshKey={0} />);
        const table = await screen.findByRole('table', { name: /Nodes on the network map/ });
        fireEvent.click(within(table).getByRole('button', { name: 'ISP not identified' }));
        const panel = await screen.findByRole('complementary', { name: 'Details for ISP not identified' });
        expect(panel.textContent).toContain('GeoLite2-ASN');
        expect(panel.textContent).toContain('103.174.161.211');
        expect(within(panel).queryByText('Up')).toBeNull();
        expect(panel.textContent).not.toContain('VLAN');
    });
});
