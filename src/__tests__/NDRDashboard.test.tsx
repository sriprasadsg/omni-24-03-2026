/**
 * NDR screen, 88.1 stage 1: it shows only what sensor records say.
 *  1. No sensor: says so, and calls none of the removed fake routes.
 *  2. A failed or malformed response is an error, never "no sensor" and never "live".
 *  3. A sensor record is shown with its real state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));

import NDRDashboard from '../../components/NDRDashboard';

const reply = (body: unknown, ok = true) => ({ ok, json: async () => body });
const NO_SENSOR = 'No network sensor is connected';

describe('NDRDashboard', () => {
  beforeEach(() => authFetch.mockReset());

  it('says no sensor is connected and asks only for the summary', async () => {
    authFetch.mockResolvedValue(reply({ sensors: [] }));
    render(<NDRDashboard />);

    expect(await screen.findByText(NO_SENSOR)).toBeTruthy();
    expect(authFetch.mock.calls.map(call => call[0])).toEqual(['/api/ndr/summary']);
    expect(screen.queryByText(/Detection engine active/i)).toBeNull();
    expect(screen.queryByText(/Demo Data/i)).toBeNull();
  });

  it.each([
    ['a failed request', reply({ detail: 'boom' }, false)],
    ['a body without a sensor list', reply({})],
  ])('shows an error for %s, not "no sensor" and not "live"', async (_name, response) => {
    authFetch.mockResolvedValue(response);
    render(<NDRDashboard />);

    expect((await screen.findByRole('alert')).textContent).toContain("Couldn't load sensor status");
    expect(screen.queryByText(NO_SENSOR)).toBeNull();
    expect(screen.queryByText(/^Live/)).toBeNull();
  });

  it('loads again when Retry is pressed after a failure', async () => {
    authFetch.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(reply({ sensors: [] }));
    render(<NDRDashboard />);

    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));

    expect(await screen.findByText(NO_SENSOR)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows a sensor with its state and never claims there is none', async () => {
    authFetch.mockResolvedValue(reply({ sensors: [
      { sensorId: 's1', name: 'core switch', state: 'degraded', reason: 'no_packet_growth',
        lastStatsAt: '2026-11-14T12:00:00+00:00', retiredAt: null },
    ] }));
    render(<NDRDashboard />);

    expect(await screen.findByText('core switch')).toBeTruthy();
    expect(screen.getByText('Degraded: sees no traffic')).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(NO_SENSOR)).toBeNull());
  });
});
