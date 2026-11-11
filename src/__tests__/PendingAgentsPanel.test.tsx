/**
 * Pending agents panel (spec C3).
 * protects=super admins see every waiting agent with its host details and can approve,
 * approve-and-raise-the-limit after a 409 no_free_seat, reject (after confirming) and bulk
 * approve; tenant users get the same list read-only; nothing renders while none wait;
 * fails_when=a tenant user is offered decisions, the raise-limit path is lost, or reject
 * fires without confirmation; no_claim=the backend (authFetch is mocked) and styling.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
const showToast = vi.fn();
vi.mock('../../utils/toast', () => ({ showToast: (...args: unknown[]) => showToast(...args) }));

import { PendingAgentsPanel } from '../../components/PendingAgentsPanel';

const AGENT = {
  id: 'agent-9', tenantId: 'tenant-a', hostname: 'FIN-LT-042', status: 'Pending', pendingReason: 'seat_limit',
  pendingSince: '2026-10-14T08:00:00Z', lastSeen: '2026-10-14T08:05:00Z', ipAddress: '10.1.2.3',
  sourceIp: '203.0.113.7', version: '2.1.13', loggedInUser: 'CORP\\jdoe',
  hardware: { serialNumber: 'PF3ABC12', smbiosUuid: '4c4c4544-0042', macAddresses: ['3c:52:82:aa:bb:cc'], osFamily: 'windows' },
};
const list = (canDecide: boolean, agents: unknown[] = [AGENT]) => ({
  ok: true, status: 200,
  json: async () => ({ agents, canDecide,
    tenants: { 'tenant-a': { name: 'Acme', license: { maxAgents: 5, seatsUsed: 5, seatsAvailable: 0 } } } }),
});
const ok = (body: unknown = {}) => ({ ok: true, status: 200, json: async () => body });

describe('PendingAgentsPanel', () => {
  beforeEach(() => { authFetch.mockReset(); showToast.mockReset(); });

  it('renders nothing while no agent is waiting', async () => {
    authFetch.mockResolvedValue(list(true, []));
    const { container } = render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending', { method: 'GET' }));
    expect(container.innerHTML).toBe('');
  });

  it('shows host details and offers to raise the limit when no seat is free', async () => {
    authFetch
      .mockResolvedValueOnce(list(true))
      .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({
        error: 'no_free_seat: the tenant has no free agent seat', license: { maxAgents: 5, seatsUsed: 5, seatsAvailable: 0 } }) })
      .mockResolvedValueOnce(ok({ status: 'Offline' }))
      .mockResolvedValueOnce(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    expect(screen.getByText('S/N PF3ABC12')).toBeTruthy();
    expect(screen.getByText('Acme')).toBeTruthy();
    expect(screen.getByText('License limit reached')).toBeTruthy();

    fireEvent.click(screen.getByText('Approve'));
    await waitFor(() => screen.getByText('Approve and raise limit by 1'));
    expect(screen.getByRole('alert').textContent).toContain('5/5 in use');
    fireEvent.click(screen.getByText('Approve and raise limit by 1'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-9/approve',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ raiseLimitBy: 1 }) })));
  });

  it('rejects only after confirmation', async () => {
    authFetch.mockResolvedValueOnce(list(true)).mockResolvedValueOnce(ok()).mockResolvedValueOnce(list(true, []));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<PendingAgentsPanel tenantId="tenant-a" />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    fireEvent.click(screen.getByText('Reject'));
    expect(authFetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Reject'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-9/reject', { method: 'POST' }));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(authFetch.mock.calls[0][0]).toBe('/api/agents/pending?tenantId=tenant-a');
  });

  it('bulk-approves the selected agents, adding seats on request', async () => {
    authFetch.mockResolvedValueOnce(list(true)).mockResolvedValueOnce(ok({ succeeded: 1, failed: 0 }))
      .mockResolvedValueOnce(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    fireEvent.click(screen.getByLabelText('Select FIN-LT-042'));
    fireEvent.click(screen.getByText('Approve 1 and add seats'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/bulk', expect.objectContaining({
      body: JSON.stringify({ action: 'approve', agentIds: ['agent-9'], raiseLimit: true }) })));
  });

  it('is read-only for tenant users', async () => {
    authFetch.mockResolvedValue(list(false));
    render(<PendingAgentsPanel tenantId="tenant-a" />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
    expect(screen.queryByLabelText('Select FIN-LT-042')).toBeNull();
    expect(screen.getByText(/Contact your provider if one of them should be let in/)).toBeTruthy();
  });
});

/**
 * Phase 88 holds (88-14; LIC-05, LIC-06, LIC-03; D-07, D-31, D-33, D-36, D-37, D-42, D-45).
 * protects=a tenant admin reads each new hold plainly, is offered no decision and never sees another
 * organization's name; a platform decider can allow a network (exact address or a typed range), must
 * confirm a cross-tenant move, sees a changed reason reload, and keeps the typed range through the
 * seat-limit retry; bulk approve confirms moves and new networks first.
 * fails_when=another organization's name reaches a tenant view, widenTo is sent empty or dropped on the
 * retry, a move or bulk approval fires without confirmation, a 422 closes the row, or reason_changed is
 * shown as a plain failure; no_claim=the backend (authFetch is mocked) and styling.
 */
const NEW_NET = { ...AGENT, id: 'agent-n', hostname: 'NET-LT-1', pendingReason: 'new_network', sourceIp: '198.51.100.9' };
const CROSS = { ...AGENT, id: 'agent-x', hostname: 'MOVE-LT-2', pendingReason: 'cross_tenant_duplicate',
  crossTenant: { agentId: 'agent-o', tenantId: 'tenant-b', tenantName: 'Globex', hostname: 'MOVE-LT-2-OLD' } };
const TRIAL = { ...AGENT, id: 'agent-t', hostname: 'TRIAL-LT-3', pendingReason: 'trial_ended' };
const fail = (status: number, body: unknown) => ({ ok: false, status, json: async () => body });

describe('PendingAgentsPanel Phase 88 holds', () => {
  beforeEach(() => { authFetch.mockReset(); showToast.mockReset(); });

  it('tenant admins read each hold plainly, get no controls and never see another organization', async () => {
    authFetch.mockResolvedValue(list(false, [NEW_NET, CROSS, TRIAL]));
    const { container } = render(<PendingAgentsPanel tenantId="tenant-a" />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    expect(screen.getByText('New network 198.51.100.9, waiting for platform approval')).toBeTruthy();
    expect(screen.getByText('This computer is enrolled in another organization; waiting for platform approval')).toBeTruthy();
    expect(screen.getByText('Free trial ended')).toBeTruthy();
    expect(screen.queryByText(/Allow network/)).toBeNull();
    expect(screen.queryByText(/Approve/)).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
    expect(screen.queryByLabelText(/Range/)).toBeNull();
    expect(container.innerHTML).not.toContain('Globex');
    expect(container.innerHTML).not.toContain('MOVE-LT-2-OLD');
  });

  it('a new network without an observed address cannot be allowed', async () => {
    authFetch.mockResolvedValue(list(true, [{ ...NEW_NET, sourceIp: undefined }]));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('New network unknown address, waiting for platform approval'));
    expect((screen.getByLabelText('Allow network for NET-LT-1') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('No address was observed, so no network can be allowed.')).toBeTruthy();
  });

  it('allows the exact address when the range is empty and sends widenTo only when typed', async () => {
    authFetch.mockResolvedValueOnce(list(true, [NEW_NET]))
      .mockResolvedValueOnce(ok({ networkAllowed: true, network: '198.51.100.9/32' }))
      .mockResolvedValueOnce(list(true, [NEW_NET]))
      .mockResolvedValueOnce(ok({ networkAllowed: true, network: '198.51.100.0/24' }))
      .mockResolvedValue(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    expect(screen.getByText((_, el) => el?.id === 'range-help-agent-n'
      && /^Leave empty to allow only 198\.51\.100\.9\. A range must contain it and be at most a \/24 \(IPv6: \/48\)\.$/.test(el.textContent || ''))).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Allow network for NET-LT-1'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-n/approve',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ raiseLimitBy: 0 }) })));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Approved. 198.51.100.9/32 is now an allowed network.', 'success'));
    await waitFor(() => screen.getByLabelText('Range (optional)'));
    fireEvent.change(screen.getByLabelText('Range (optional)'), { target: { value: ' 198.51.100.0/24 ' } });
    fireEvent.click(screen.getByLabelText('Allow network for NET-LT-1'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-n/approve',
      expect.objectContaining({ body: JSON.stringify({ raiseLimitBy: 0, widenTo: '198.51.100.0/24' }) })));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('Approved. 198.51.100.0/24 is now an allowed network.', 'success'));
  });

  it('says so when the approved network was not added', async () => {
    authFetch.mockResolvedValueOnce(list(true, [NEW_NET]))
      .mockResolvedValueOnce(ok({ networkAllowed: false, network: '198.51.100.9/32' }))
      .mockResolvedValue(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    fireEvent.click(screen.getByLabelText('Allow network for NET-LT-1'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(
      'Approved. 198.51.100.9/32 was not added: it is already allowed, or the list of allowed networks is full.', 'success'));
  });

  it('shows a 422 under the range field and keeps the row and the typed value', async () => {
    authFetch.mockResolvedValueOnce(list(true, [NEW_NET]))
      .mockResolvedValueOnce(fail(422, { error: 'range is wider than a /24' }));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    fireEvent.change(screen.getByLabelText('Range (optional)'), { target: { value: '198.51.0.0/16' } });
    fireEvent.click(screen.getByLabelText('Allow network for NET-LT-1'));
    await waitFor(() => screen.getByText("Couldn't allow this network: range is wider than a /24. Try again."));
    expect(screen.getByText("Couldn't allow this network: range is wider than a /24. Try again.").getAttribute('role')).toBe('alert');
    expect((screen.getByLabelText('Range (optional)') as HTMLInputElement).value).toBe('198.51.0.0/16');
    expect(screen.getByText('NET-LT-1')).toBeTruthy();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('keeps the typed range when a seat shortage turns into approve-and-raise', async () => {
    authFetch.mockResolvedValueOnce(list(true, [NEW_NET]))
      .mockResolvedValueOnce(fail(409, { error: 'no_free_seat: the tenant has no free agent seat',
        license: { maxAgents: 5, seatsUsed: 5, seatsAvailable: 0 } }))
      .mockResolvedValueOnce(ok({ networkAllowed: true, network: '198.51.100.0/24' }))
      .mockResolvedValue(list(true, []));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    fireEvent.change(screen.getByLabelText('Range (optional)'), { target: { value: '198.51.100.0/24' } });
    fireEvent.click(screen.getByLabelText('Allow network for NET-LT-1'));
    await waitFor(() => screen.getByText('Approve and raise limit by 1'));
    fireEvent.click(screen.getByText('Approve and raise limit by 1'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-n/approve',
      expect.objectContaining({ body: JSON.stringify({ raiseLimitBy: 1, widenTo: '198.51.100.0/24' }) })));
  });

  it('shows the other organization to the decider and approves a move only after confirmation', async () => {
    authFetch.mockResolvedValueOnce(list(true, [CROSS])).mockResolvedValueOnce(ok({ agentId: 'agent-x' }))
      .mockResolvedValue(list(true, []));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('MOVE-LT-2'));
    expect(screen.getByText('Live in Globex as MOVE-LT-2-OLD')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Approve move of MOVE-LT-2'));
    expect(authFetch).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenLastCalledWith('Approve moves this computer to Acme. Its agent in Globex is retired and that seat is freed.');
    fireEvent.click(screen.getByLabelText('Approve move of MOVE-LT-2'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/agent-x/approve',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ raiseLimitBy: 0 }) })));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(
      'Approved. MOVE-LT-2 moved to Acme; its agent in Globex was retired.', 'success'));
  });

  it('falls back to another organization when the name is missing', async () => {
    authFetch.mockResolvedValue(list(true, [{ ...CROSS, crossTenant: { agentId: 'agent-o', tenantId: 'tenant-b' } }]));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('Live in another organization'));
  });

  it('a changed reason shows a warning, reloads the list and drops the typed range', async () => {
    authFetch.mockResolvedValueOnce(list(true, [NEW_NET]))
      .mockResolvedValueOnce(fail(409, { error: 'reason_changed: this computer is enrolled in another organization; review it again' }))
      .mockResolvedValueOnce(list(true, [{ ...NEW_NET, pendingReason: 'cross_tenant_duplicate',
        crossTenant: { agentId: 'agent-o', tenantId: 'tenant-b', tenantName: 'Globex' } }]));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    fireEvent.change(screen.getByLabelText('Range (optional)'), { target: { value: '198.51.100.0/24' } });
    fireEvent.click(screen.getByLabelText('Allow network for NET-LT-1'));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(
      'The reason for this hold changed: this computer is now enrolled in another organization. Review it again.', 'warning'));
    await waitFor(() => screen.getByLabelText('Approve move of NET-LT-1'));
    expect(screen.queryByLabelText('Range (optional)')).toBeNull();
  });

  it('bulk approve confirms moves and new networks first, and only when they are selected', async () => {
    authFetch.mockResolvedValueOnce(list(true, [NEW_NET, CROSS, AGENT]))
      .mockResolvedValueOnce(ok({ succeeded: 3, failed: 0 })).mockResolvedValue(list(true, []));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('NET-LT-1'));
    fireEvent.click(screen.getByLabelText('Select NET-LT-1'));
    fireEvent.click(screen.getByLabelText('Select MOVE-LT-2'));
    fireEvent.click(screen.getByLabelText('Select FIN-LT-042'));
    fireEvent.click(screen.getByText('Approve 3'));
    expect(confirm).toHaveBeenLastCalledWith(
      'Approve 3 computers? 1 is enrolled in another organization: approving moves each one and retires its agent there. '
      + '1 waits for a new network: approving allows each one\'s address exactly.');
    expect(authFetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Approve 3'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/bulk', expect.objectContaining({
      body: JSON.stringify({ action: 'approve', agentIds: ['agent-n', 'agent-x', 'agent-9'], raiseLimit: false }) })));
  });

  it('bulk approve of plain holds asks nothing', async () => {
    authFetch.mockResolvedValueOnce(list(true)).mockResolvedValueOnce(ok({ succeeded: 1, failed: 0 })).mockResolvedValue(list(true, []));
    const confirm = vi.spyOn(window, 'confirm');
    confirm.mockClear();
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('FIN-LT-042'));
    fireEvent.click(screen.getByLabelText('Select FIN-LT-042'));
    fireEvent.click(screen.getByText('Approve 1'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/agents/pending/bulk', expect.anything()));
    expect(confirm).not.toHaveBeenCalled();
  });

  it('rejecting a cross-tenant or duplicate hold says the machine is not blocked', async () => {
    authFetch.mockResolvedValue(list(true, [CROSS]));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText('MOVE-LT-2'));
    fireEvent.click(screen.getByText('Reject'));
    expect(confirm).toHaveBeenLastCalledWith(
      'Reject MOVE-LT-2? It stays out of this organization. The computer is not added to the blocked list.');
  });

  it('the intro text no longer speaks only of seats', async () => {
    authFetch.mockResolvedValue(list(true, [TRIAL]));
    render(<PendingAgentsPanel tenantId={null} />);
    await waitFor(() => screen.getByText(/These computers were held by a license rule and wait for your decision/));
  });
});
