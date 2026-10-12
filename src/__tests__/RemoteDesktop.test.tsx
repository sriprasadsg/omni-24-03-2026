/**
 * Remote desktop viewer — how a session the agent ends is reported:
 *  1. View mode shows the agent's reason (declined, capture ended) instead of
 *     the generic "No video received within 45s" watchdog message.
 *  2. The watchdog still fires when the agent never answers at all.
 *  3. The agent's "consent_timeout" reason gets the expired-request copy.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  startRemoteSession: vi.fn(),
  disconnectRemoteSession: vi.fn(),
}));

import { RemoteDesktop, remoteSessionEndedCopy } from '../../components/RemoteDesktop';

class FakeWebSocket {
  static OPEN = 1;
  static last: FakeWebSocket | null = null;
  readyState = FakeWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  constructor(public url: string) { FakeWebSocket.last = this; }
  send() {}
  close() {}
  emit(payload: object) { this.onmessage?.({ data: JSON.stringify(payload) }); }
}

const NO_VIDEO = /No video received from the agent within 45s/;
const ONLINE_HINT = /Ensure the agent is online/;

describe('RemoteDesktop', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeWebSocket);
    FakeWebSocket.last = null;
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const openView = () => {
    render(<RemoteDesktop agentId="agent-1" sessionId="s-1" mode="view" hostname="EILT0197" />);
    const ws = FakeWebSocket.last!;
    act(() => ws.onopen?.());
    return ws;
  };

  it('shows a declined view request instead of the 45s no-video message', () => {
    const ws = openView();
    act(() => ws.emit({ type: 'control_state', state: 'awaiting_consent' }));
    act(() => ws.emit({ type: 'control_state', state: 'ended', reason: 'consent_declined', message: 'Endpoint user declined control' }));
    act(() => { vi.advanceTimersByTime(46000); });

    expect(screen.getByText('View Ended')).toBeTruthy();
    expect(screen.getByText('Endpoint user declined the request to view the desktop.')).toBeTruthy();
    expect(screen.queryByText(NO_VIDEO)).toBeNull();
  });

  it("shows why the agent's desktop capture stopped in view mode", () => {
    const ws = openView();
    act(() => ws.emit({ type: 'control_state', state: 'active' }));
    const why = 'Desktop capture process ended (exit code 0x00000001: This script contains malicious content)';
    act(() => ws.emit({ type: 'error', message: why }));
    act(() => ws.emit({ type: 'control_state', state: 'ended', reason: 'capture_ended', message: why }));
    act(() => { vi.advanceTimersByTime(46000); });

    expect(screen.getByText('View Ended')).toBeTruthy();
    // Header plus the ended overlay; the "is the agent online?" panel stays hidden.
    expect(screen.getAllByText(why)).toHaveLength(2);
    expect(screen.queryByText(ONLINE_HINT)).toBeNull();
    expect(screen.getByText('capture_ended')).toBeTruthy();
    expect(screen.queryByText(NO_VIDEO)).toBeNull();
  });

  it('still reports no video when the agent never answers', () => {
    openView();
    act(() => { vi.advanceTimersByTime(46000); });
    expect(screen.getAllByText(NO_VIDEO).length).toBeGreaterThan(0);
    expect(screen.getByText(ONLINE_HINT)).toBeTruthy();
  });
});

describe('remoteSessionEndedCopy', () => {
  it('names the kind of request that was declined', () => {
    expect(remoteSessionEndedCopy('control', 'consent_declined', null)).toBe('Endpoint user declined the control request.');
    expect(remoteSessionEndedCopy('view', 'consent_declined', null)).toBe('Endpoint user declined the request to view the desktop.');
  });

  it("treats the agent's consent_timeout as an expired request", () => {
    expect(remoteSessionEndedCopy('view', 'consent_timeout', 'Consent request timed out'))
      .toBe('Endpoint user did not respond in time. The request has expired.');
  });

  it("falls back to the agent's message, then a mode-specific default", () => {
    expect(remoteSessionEndedCopy('view', 'capture_ended', 'Desktop capture process ended (exit code 0x00000001, no output)'))
      .toBe('Desktop capture process ended (exit code 0x00000001, no output)');
    expect(remoteSessionEndedCopy('view', null, null)).toBe('Desktop view ended.');
    expect(remoteSessionEndedCopy('control', null, null)).toBe('Control session ended.');
  });
});
