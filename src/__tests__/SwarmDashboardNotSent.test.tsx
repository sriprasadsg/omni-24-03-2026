/**
 * Phase 83 / RESP-11, D-18, UI-SPEC section 8: the swarm screen answers honestly when nothing was sent.
 * propagateAntibody is mocked, so the payloads follow the 83-06 contract (status not_sent, dispatched 0,
 * message). A server answer that sent nothing must show the server's message verbatim in the amber style
 * (never the green success style) and wrap inside the status element.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  fetchSwarmMissions: vi.fn(async () => []),
  fetchSwarmTopology: vi.fn(async () => ({ nodes: [] })),
  startSwarmMission: vi.fn(),
  propagateAntibody: vi.fn(),
}));

import { propagateAntibody } from '../../services/apiService';
import SwarmDashboard from '../../components/SwarmDashboard';

const mockPropagate = propagateAntibody as unknown as ReturnType<typeof vi.fn>;

const FALLBACK =
  'Nothing was sent. Antibody propagation no longer sends containment to agents on its own. Containment is handled in Autonomous Ops.';

async function propagate() {
  render(<SwarmDashboard />);
  fireEvent.change(screen.getByPlaceholderText(/IP, hash, or domain indicator/i), { target: { value: '45.33.32.156' } });
  fireEvent.click(screen.getByRole('button', { name: /^Propagate$/ }));
}

/** The status element: the box holding the icon, the message and the close button. */
function statusElement(message: HTMLElement | string) {
  const el = typeof message === 'string' ? screen.getByText(message) : message;
  return el.closest('[role="status"], [role="alert"]') as HTMLElement;
}

beforeEach(() => mockPropagate.mockReset());

describe('SwarmDashboard not-sent answer', () => {
  it('shows the server message verbatim in the amber style, never green', async () => {
    mockPropagate.mockResolvedValue({ ok: true, status: 200, data: { status: 'not_sent', dispatched: 0, message: FALLBACK } });
    await propagate();
    const box = statusElement(await screen.findByText(FALLBACK));
    expect(box.className).toContain('bg-amber-50');
    expect(box.className).toContain('break-words');
    expect(box.className).not.toMatch(/green/);
    expect(screen.queryByText(/Antibody dispatched/i)).toBeNull();
  });

  it('renders a 300-character server message whole and lets it wrap', async () => {
    const long = ('Nothing was sent. ' + 'Containment is handled in Autonomous Ops. '.repeat(10)).slice(0, 300);
    expect(long).toHaveLength(300);
    mockPropagate.mockResolvedValue({ ok: true, status: 200, data: { status: 'not_sent', dispatched: 0, message: long } });
    await propagate();
    const box = statusElement(await screen.findByText(long));
    expect(box.className).toContain('break-words');
    expect(box.className).not.toMatch(/green/);
    expect(box.textContent).toContain(long);
  });

  it('uses the fallback sentence when the server sent no message', async () => {
    mockPropagate.mockResolvedValue({ ok: true, status: 200, data: { dispatched: 0 } });
    await propagate();
    const box = statusElement(await screen.findByText(FALLBACK));
    expect(box.className).toContain('bg-amber-50');
  });

  it('treats status not_sent as not sent even if a count is present', async () => {
    mockPropagate.mockResolvedValue({ ok: true, status: 200, data: { status: 'not_sent', dispatched: 4, message: 'Held.' } });
    await propagate();
    const box = statusElement(await screen.findByText('Held.'));
    expect(box.className).not.toMatch(/green/);
  });

  it('keeps the green style for a real dispatched count above zero', async () => {
    mockPropagate.mockResolvedValue({ ok: true, status: 200, data: { dispatched: 3 } });
    await propagate();
    const box = statusElement(await screen.findByText('Antibody dispatched to 3 agents.'));
    expect(box.className).toContain('bg-green-50');
  });

  it('keeps the red style for a failure', async () => {
    mockPropagate.mockResolvedValue({ ok: false, status: 500, data: { detail: 'Propagation failed.' } });
    await propagate();
    await waitFor(() => expect(screen.getByText('Propagation failed.')).toBeTruthy());
    expect(statusElement('Propagation failed.').className).toContain('bg-red-50');
  });
});
