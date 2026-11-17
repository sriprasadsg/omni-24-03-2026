/**
 * Network Operations console (GET /api/network-devices/traffic):
 *  1. Rates show in bits per second; min/max/p95 and the period delta come from the series.
 *  2. Measured rates fill the KPIs; latency and packet loss say they are not measured.
 *  3. Search filters the tables; a row opens the drawer with the endpoint's path and its own history.
 *  4. The range picker reloads with the new range; a pushed rate refreshes unless paused.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
const socketHandlers: Record<string, (data: any) => void> = {};
vi.mock('../../services/socketService', () => ({
    socketService: { on: (ev: string, fn: (data: any) => void) => { socketHandlers[ev] = fn; }, off: vi.fn(), connected: true },
}));

import { formatBitRate, percentile, periodDelta, seriesStats } from '../../components/network/opsData';
import { NetworkOperationsConsole } from '../../components/NetworkOperationsConsole';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const at = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();

function summary(range = '1h') {
    return {
        generatedAt: at(0), range, rangeSeconds: 3600, bucketSeconds: 120,
        series: [{ t: at(240_000), txBps: 1000, rxBps: 4000 }, { t: at(120_000), txBps: null, rxBps: null }, { t: at(0), txBps: 3000, rxBps: 8000 }],
        current: { txBps: 35_000, rxBps: 174_000, measured: 1, online: 2, endpoints: 2 },
        average: { txBps: 2000, rxBps: 6000 }, previousAverage: { txBps: 1000, rxBps: 3000 },
        endpoints: [
            { agentId: 'a-win', hostname: 'EILT0197', ip: '192.168.0.105', os: 'Windows 11', lastSeen: at(20_000), status: 'Live',
              txBps: 35_000, rxBps: 174_000, rateAt: at(20_000), windowSeconds: 42, rangeTxBytes: 1_000_000, rangeRxBytes: 5_000_000,
              bytesSent: 10, bytesRecv: 20, gateway: { ip: '192.168.0.1', mac: '60-32-b1-08-ba-d6' }, publicIp: '103.174.161.211',
              interfaces: [{ name: 'Wi-Fi', bytesSent: 5, bytesRecv: 6, packetsSent: 7, packetsRecv: 8 }], connections: 0 },
            { agentId: 'a-lin', hostname: 'Omniai-copy', ip: '10.0.0.4', status: 'Idle', txBps: null, rxBps: null,
              rangeTxBytes: 0, rangeRxBytes: 0, gateway: null, interfaces: [], connections: 1 },
        ],
        connections: [{ agentId: 'a-lin', hostname: 'Omniai-copy', sourceIp: '10.0.0.4', destination: 'api.anthropic.com', destinationIp: '160.79.104.10',
                        port: 443, protocol: 'HTTPS', process: 'claude', pid: 7, scope: 'External' }],
        protocols: [{ name: 'HTTPS', connections: 1 }, { name: 'HTTP', connections: 0 }, { name: 'Other', connections: 0 }, { name: 'Internal', connections: 0 }],
        notCollected: ['latency', 'packetLoss'],
    };
}

describe('opsData', () => {
    it('shows rates in bits per second and computes range statistics', () => {
        expect(formatBitRate(500_000)).toBe('4.0 Mbps');
        expect(formatBitRate(100)).toBe('800 bps');
        expect(formatBitRate(null)).toBe('—');
        expect(percentile([1, 2, 3, 4, 100], 95)).toBe(100);
        expect(seriesStats(summary().series as any, 'rxBps')).toEqual({ min: 4000, max: 8000, p95: 8000 });
        expect(periodDelta(8000, 4000)).toBe(100);
        expect(periodDelta(1, 0)).toBeNull();
    });
});

describe('NetworkOperationsConsole', () => {
    beforeEach(() => { authFetch.mockReset(); authFetch.mockImplementation(async (url: string) => ok(summary(new URL(url, 'http://x').searchParams.get('range') || '1h'))); });

    it('fills the KPIs from measured rates and says what is not measured', async () => {
        render(<NetworkOperationsConsole />);
        const total = await screen.findByRole('region', { name: 'Total throughput' });
        expect(total.textContent).toContain(formatBitRate(209_000));
        expect(total.textContent).toContain('100%');  // 8000 vs 4000 average
        expect(screen.getAllByText('Not measured')).toHaveLength(2);
        expect(screen.getByText('DNS · SSH · UDP')).toBeTruthy();
        expect(screen.getByText(/Stream: Live/)).toBeTruthy();
    });

    it('filters the tables and opens an endpoint with its path and own history', async () => {
        render(<NetworkOperationsConsole />);
        await screen.findByRole('button', { name: 'EILT0197' });
        fireEvent.change(screen.getByRole('searchbox', { name: 'Search endpoints and connections' }), { target: { value: 'omniai' } });
        expect(screen.queryByRole('button', { name: 'EILT0197' })).toBeNull();
        fireEvent.change(screen.getByRole('searchbox', { name: 'Search endpoints and connections' }), { target: { value: '' } });
        fireEvent.click(screen.getByRole('button', { name: 'EILT0197' }));
        const drawer = await screen.findByRole('dialog', { name: 'EILT0197' });
        expect(within(drawer).getByText('192.168.0.1')).toBeTruthy();
        expect(drawer.textContent).toContain('103.174.161.211');
        expect(drawer.textContent).toContain('Latency: not measured');
        await waitFor(() => expect(authFetch.mock.calls.some(([u]) => String(u).includes('agentId=a-win'))).toBe(true));
        fireEvent.keyDown(drawer, { key: 'Escape' });
        await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    });

    it('lists latest connections under their own tab', async () => {
        render(<NetworkOperationsConsole />);
        fireEvent.click(await screen.findByRole('tab', { name: /Connections/ }));
        expect(screen.getByText('api.anthropic.com')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'HTTP' }));
        expect(screen.queryByText('api.anthropic.com')).toBeNull();
    });

    it('reloads for a new range and refreshes on a pushed rate unless paused', async () => {
        render(<NetworkOperationsConsole />);
        await screen.findByRole('button', { name: 'EILT0197' });
        fireEvent.click(screen.getByRole('button', { name: '6h' }));
        await waitFor(() => expect(authFetch.mock.calls.some(([u]) => String(u).includes('range=6h'))).toBe(true));
        const before = authFetch.mock.calls.length;
        fireEvent.click(screen.getByRole('button', { name: 'Pause updates' }));
        act(() => socketHandlers.endpoint_traffic({ agentId: 'a-win' }));
        expect(authFetch.mock.calls.length).toBe(before);
        fireEvent.click(screen.getByRole('button', { name: 'Resume updates' }));
        act(() => socketHandlers.endpoint_traffic({ agentId: 'a-win' }));
        await waitFor(() => expect(authFetch.mock.calls.length).toBeGreaterThan(before));
    });
});
