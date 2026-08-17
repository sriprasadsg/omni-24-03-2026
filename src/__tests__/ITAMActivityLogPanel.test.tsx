/**
 * Phase 65 (plan 65-02) ActivityLogPanel behavior:
 *  1. On mount, calls fetchItamAuditLogs and renders rows from the response.
 *  2. A rejected fetchItamAuditLogs renders the error message rather than a blank table.
 *  3. (Task 3) Choosing an entity type or typing an entity id refetches with that filter.
 *  4. (Task 3) Mounting with resourceType/resourceId props fetches pre-filtered and hides filters.
 *  5. (Task 3) The verify-integrity button renders the integrity result.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const fetchItamAuditLogs = vi.fn();
const verifyAuditIntegrity = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchItamAuditLogs: (...args: unknown[]) => fetchItamAuditLogs(...args),
  verifyAuditIntegrity: (...args: unknown[]) => verifyAuditIntegrity(...args),
}));

import { ActivityLogPanel } from '../../components/itam/ActivityLogPanel';

describe('ActivityLogPanel', () => {
  beforeEach(() => {
    fetchItamAuditLogs.mockReset();
    verifyAuditIntegrity.mockReset();
  });

  it("renders rows from a stubbed response", async () => {
    fetchItamAuditLogs.mockResolvedValue([
      {
        id: 'log-1',
        timestamp: '2026-08-12T10:00:00Z',
        userName: 'alice@tenant.com',
        action: 'itam_asset.create',
        resourceType: 'itam_asset',
        resourceId: 'asset-1',
        details: 'Created manual asset IT-0001',
      },
    ]);

    render(<ActivityLogPanel />);

    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalledWith({
      resourceType: undefined, resourceId: undefined, limit: 50, skip: 0,
    }));
    await waitFor(() => expect(screen.getByText('alice@tenant.com')).toBeInTheDocument());
    expect(screen.getByText('itam_asset.create')).toBeInTheDocument();
    expect(screen.getByText('asset-1')).toBeInTheDocument();
  });

  it('shows the empty state when there is no activity yet', async () => {
    fetchItamAuditLogs.mockResolvedValue([]);

    render(<ActivityLogPanel />);

    await waitFor(() => expect(screen.getByText('No activity recorded yet')).toBeInTheDocument());
  });

  it('a rejected fetchItamAuditLogs renders the error message rather than a blank table', async () => {
    fetchItamAuditLogs.mockRejectedValue(new Error('Your account does not have permission to view the audit log.'));

    render(<ActivityLogPanel />);

    await waitFor(() =>
      expect(screen.getByText('Your account does not have permission to view the audit log.')).toBeInTheDocument()
    );
  });

  it('choosing an entity type refetches with that resourceType', async () => {
    fetchItamAuditLogs.mockResolvedValue([]);

    render(<ActivityLogPanel />);
    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalledWith(
      expect.objectContaining({ resourceType: undefined })
    ));

    fireEvent.click(screen.getByLabelText('Filter by itam_asset'));

    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalledWith(
      expect.objectContaining({ resourceType: 'itam_asset', skip: 0 })
    ));
  });

  it('typing an entity id refetches with that resourceId', async () => {
    fetchItamAuditLogs.mockResolvedValue([]);

    render(<ActivityLogPanel />);
    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('Filter by entity ID'), { target: { value: 'asset-42' } });

    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalledWith(
      expect.objectContaining({ resourceId: 'asset-42' })
    ));
  });

  it('mounting with resourceType/resourceId props fetches pre-filtered and renders no filter controls', async () => {
    fetchItamAuditLogs.mockResolvedValue([]);

    render(<ActivityLogPanel resourceType="itam_asset" resourceId="asset-1" />);

    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalledWith(
      expect.objectContaining({ resourceType: 'itam_asset', resourceId: 'asset-1' })
    ));
    expect(screen.queryByLabelText('Filter by entity ID')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('All entity types')).not.toBeInTheDocument();
  });

  it('the verify button renders the integrity result', async () => {
    fetchItamAuditLogs.mockResolvedValue([]);
    verifyAuditIntegrity.mockResolvedValue({ valid: true, total_records: 12 });

    render(<ActivityLogPanel />);
    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText('Verify ledger integrity'));

    await waitFor(() => expect(screen.getByText(/Ledger verified — 12 record/)).toBeInTheDocument());
  });

  it('a rejected verify call renders the error, not a passing indicator', async () => {
    fetchItamAuditLogs.mockResolvedValue([]);
    verifyAuditIntegrity.mockRejectedValue(new Error('Integrity check failed'));

    render(<ActivityLogPanel />);
    await waitFor(() => expect(fetchItamAuditLogs).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText('Verify ledger integrity'));

    await waitFor(() => expect(screen.getByText('Integrity check failed')).toBeInTheDocument());
    expect(screen.queryByText(/Ledger verified/)).not.toBeInTheDocument();
  });
});
