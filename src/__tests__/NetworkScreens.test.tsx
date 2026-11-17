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
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../services/socketService', () => ({ socketService: { on: vi.fn(), off: vi.fn(), connected: false } }));
vi.mock('react-cytoscapejs', () => ({ default: () => null }));
vi.mock('cytoscape', () => ({ default: { use: vi.fn() } }));
vi.mock('cytoscape-cose-bilkent', () => ({ default: {} }));

import { collectWebActivity, buildTopologyElements, topologyStats, formatAgentTime, deviceFacts, formatBytes } from '../../components/network/networkData';
import { useLiveData } from '../../components/network/NetworkKit';
import { WebMonitoringDashboard } from '../../components/WebMonitoringDashboard';
import { DataUtilizationDashboard } from '../../components/DataUtilizationDashboard';
import { NetworkTopologyMap } from '../../components/NetworkTopologyMap';

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
        expect(topologyStats(els)).toEqual({ devices: 4, down: 1, links: 2, zones: 4, segments: 1 });
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

    it('Topology list view opens a device, including a VLAN segment member', async () => {
        authFetch.mockResolvedValue(ok({ elements: {
            nodes: [
                { data: { id: 'internet', zone: 'Internet', type: 'cloud', label: 'Internet (External)\n1.2.3.4', ip: '1.2.3.4', status: 'up' } },
                { data: { id: 'pc', zone: 'Internal LAN', label: 'pc-01\n(10.0.0.9)', ip: '10.0.0.9', status: 'Up', details: { macAddress: 'aa:bb:cc' } } },
            ],
            edges: [{ data: { id: 'e', source: 'internet', target: 'pc' } }],
        } }));
        render(<NetworkTopologyMap refreshKey={0} />);
        fireEvent.click(await screen.findByRole('button', { name: 'List' }));
        fireEvent.click(await screen.findByRole('button', { name: 'pc-01' }));
        const panel = await screen.findByRole('complementary', { name: 'Details for pc-01' });
        expect(panel.textContent).toContain('aa:bb:cc');
        expect(panel.textContent).toContain('Internet (External)');
        fireEvent.keyDown(window, { key: 'Escape' });
        await waitFor(() => expect(screen.queryByRole('complementary')).toBeNull());
    });
});
