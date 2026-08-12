/**
 * Phase 65 (plan 65-02) ActivityLogPanel behavior:
 *  1. On mount, calls fetchAuditLogs and renders rows from the response.
 *  2. A rejected fetchAuditLogs renders the error message rather than a blank table.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const fetchAuditLogs = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchAuditLogs: (...args: unknown[]) => fetchAuditLogs(...args),
}));

import { ActivityLogPanel } from '../../components/itam/ActivityLogPanel';

describe('ActivityLogPanel', () => {
  beforeEach(() => {
    fetchAuditLogs.mockReset();
  });

  it("renders rows from a stubbed response", async () => {
    fetchAuditLogs.mockResolvedValue([
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

    await waitFor(() => expect(fetchAuditLogs).toHaveBeenCalledWith({ resourceType: undefined, resourceId: undefined, limit: 100 }));
    await waitFor(() => expect(screen.getByText('alice@tenant.com')).toBeInTheDocument());
    expect(screen.getByText('itam_asset.create')).toBeInTheDocument();
    expect(screen.getByText('asset-1')).toBeInTheDocument();
  });

  it('shows the empty state when there is no activity yet', async () => {
    fetchAuditLogs.mockResolvedValue([]);

    render(<ActivityLogPanel />);

    await waitFor(() => expect(screen.getByText('No activity recorded yet')).toBeInTheDocument());
  });

  it('a rejected fetchAuditLogs renders the error message rather than a blank table', async () => {
    fetchAuditLogs.mockRejectedValue(new Error('Your account does not have permission to view the audit log.'));

    render(<ActivityLogPanel />);

    await waitFor(() =>
      expect(screen.getByText('Your account does not have permission to view the audit log.')).toBeInTheDocument()
    );
  });
});
