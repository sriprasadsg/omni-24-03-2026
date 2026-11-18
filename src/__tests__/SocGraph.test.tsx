/**
 * SOC console, investigation graph: it lays out endpoint, alerts, what they name and other endpoints; picking an
 * item lists its links, the list view holds the same items, and "Open the alert" hands the alert id back.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { InvestigationGraph } from '../../components/security/soc/InvestigationGraph';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

const graph = {
    nodes: [
        { id: 'host:h1', kind: 'host', label: 'web-1', agentId: 'h1', primary: true },
        { id: 'alert:a1', kind: 'alert', label: 'Malware: evil.exe', alertId: 'a1', severity: 'critical', status: 'open', sub: 'Malware', at: '2026-11-18T08:00:00Z', focus: true },
        { id: 'user:alice', kind: 'user', label: 'Alice', count: 1 },
        { id: 'host:h2', kind: 'host', label: 'db-1', agentId: 'h2', primary: false, count: 3 },
    ],
    edges: [{ from: 'host:h1', to: 'alert:a1', label: 'raised' }, { from: 'alert:a1', to: 'user:alice', label: 'user' },
            { from: 'user:alice', to: 'host:h2', label: 'also seen (3 alerts)' }],
    truncated: false, alerts: 1, alertsTotal: 1, pivotDays: 7, focus: 'alert:a1', incidentId: 'SINC-1',
};

beforeEach(() => { authFetch.mockReset(); authFetch.mockImplementation(async () => ok(graph)); });

describe('Investigation graph', () => {
    it('shows the endpoint, alerts, what they name and other endpoints, and hands an alert back', async () => {
        const onOpenAlert = vi.fn();
        render(<InvestigationGraph of="incidents" id="SINC-1" title="Malware on web-1" onClose={vi.fn()} onOpenAlert={onOpenAlert} />);
        const svg = await screen.findByRole('group', { name: 'Investigation graph' });
        expect(authFetch.mock.calls[0][0]).toBe('/api/security/soc/incidents/SINC-1/graph');
        expect(within(svg).getByRole('button', { name: 'Endpoint: web-1' })).toBeTruthy();
        expect(within(svg).getByRole('button', { name: 'Alert: Malware: evil.exe, Critical' }).getAttribute('aria-pressed')).toBe('true');
        expect(screen.getByText(/name the same user, process, file or IP/)).toBeTruthy();

        fireEvent.click(within(svg).getByRole('button', { name: 'User: Alice' }));
        const side = screen.getByRole('complementary', { name: 'Selected item' });
        expect(within(side).getByText('db-1')).toBeTruthy();
        expect(within(side).getByText('Endpoint · also seen (3 alerts)')).toBeTruthy();

        fireEvent.click(within(side).getByRole('button', { name: /Malware: evil.exe/ }));
        fireEvent.click(within(side).getByRole('button', { name: 'Open the alert' }));
        expect(onOpenAlert).toHaveBeenCalledWith('a1');

        fireEvent.click(screen.getByRole('button', { name: 'List' }));
        const list = screen.getByRole('list', { name: 'Everything in the graph' });
        expect(within(list).getByText('Endpoint (other endpoint)')).toBeTruthy();
    });
});
