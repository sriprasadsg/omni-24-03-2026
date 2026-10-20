/**
 * Regression tests for OS patching in the UI: the OS Patches tab hid "Deploy All"
 * for agents reporting status "Online", and the jobs table's Rollback called the
 * staged-deployment route, which never knows a patch job.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({
  authFetch: (...args: unknown[]) => authFetch(...args),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { OsPatchesTab, OsAssetPatch } from '../../components/OsPatchesTab';
import { PatchDeploymentJobs } from '../../components/PatchDeploymentJobs';
import { PatchManagementDashboard } from '../../components/PatchManagementDashboard';
import type { PatchDeploymentJob } from '../../types';

const windowsAsset: OsAssetPatch = {
  agent_id: 'agent-win', hostname: 'EILT0197', os: 'Windows', os_version: '11', status: 'Online',
  pending_count: 1, last_checked: '2026-10-12T08:00:00Z', pending_updates: ['KB5034441'],
  pending_details: [{ id: 'KB5034441', title: '2026-10 Cumulative Update', severity: 'Critical' }],
};

describe('OsPatchesTab', () => {
  it('offers Deploy All for an agent reporting "Online" and sends the KB ids', () => {
    const onApply = vi.fn();
    render(<OsPatchesTab osPatches={[windowsAsset]} osPatchesMeta={null} osPatchesLoading={false}
      deployingAssetPatches={new Set()} onRefresh={vi.fn()} onApplyOsPatches={onApply} />);
    expect(screen.getByText(/2026-10 Cumulative Update/)).toBeTruthy();
    fireEvent.click(screen.getByText(/Deploy All/));
    expect(onApply).toHaveBeenCalledWith('agent-win', ['KB5034441']);
  });

  it('says the scan failed instead of "Up to date" when the agent reports a scan error', () => {
    const failed = { ...windowsAsset, pending_count: 0, pending_updates: [], pending_details: [],
      scan_error: 'Windows Update search failed: 0x8024402C' };
    render(<OsPatchesTab osPatches={[failed]} osPatchesMeta={null} osPatchesLoading={false}
      deployingAssetPatches={new Set()} onRefresh={vi.fn()} onApplyOsPatches={vi.fn()} />);
    expect(screen.getByText('Scan failed')).toBeTruthy();
    expect(screen.queryByText('Up to date')).toBeNull();
    expect(screen.getByText(/0x8024402C/)).toBeTruthy();
  });
});

describe('PatchDeploymentJobs', () => {
  beforeEach(() => authFetch.mockReset());

  const job: PatchDeploymentJob = {
    id: 'job-1', scheduledAt: '2026-10-12T08:00:00Z', startedAt: null, completedAt: null,
    targetPatchIds: undefined as unknown as string[], targetAssetIds: undefined as unknown as string[],
    patchIds: ['KB5034441', 'KB5035845'], dispatchedAgents: ['agent-win'], status: 'Partially Completed',
    progress: 100, statusLog: [], deploymentType: 'Immediate', rebootRequired: true,
  };

  it('counts the stored patchIds / dispatchedAgents and rolls back through the patch route', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    authFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ success: true, job_id: 'rollback-1' }) });
    render(<PatchDeploymentJobs jobs={[job]} />);
    expect(screen.getByText(/2 Patches to 1 Assets/)).toBeTruthy();
    expect(screen.getByText(/reboot required/)).toBeTruthy();
    fireEvent.click(screen.getByTitle('Rollback Deployment'));
    await waitFor(() => expect(authFetch).toHaveBeenCalled());
    expect(authFetch.mock.calls[0][0]).toBe('/api/patches/deployment-jobs/job-1/rollback');
  });
});

describe('PatchManagementDashboard tenant view', () => {
  beforeEach(() => authFetch.mockReset());

  // A super admin viewing a customer tenant must see that tenant's endpoints
  // (e.g. its Windows laptops), not only the platform's own server.
  it('asks for the viewed tenant\'s OS patches', async () => {
    authFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ assets: [], total_pending_os_patches: 0 }) });
    render(<PatchManagementDashboard patches={[]} assets={[]} patchDeploymentJobs={[]} vulnerabilityScanJobs={[]}
      onSchedulePatchDeployment={vi.fn()} onScheduleVulnerabilityScan={vi.fn()} tenantId="tenant_b574366f4158" />);
    fireEvent.click(screen.getByText(/OS Patches/));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/patches/os?tenant_id=tenant_b574366f4158'));
  });

  it('uses the caller\'s own tenant when none is being viewed', async () => {
    authFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ assets: [], total_pending_os_patches: 0 }) });
    render(<PatchManagementDashboard patches={[]} assets={[]} patchDeploymentJobs={[]} vulnerabilityScanJobs={[]}
      onSchedulePatchDeployment={vi.fn()} onScheduleVulnerabilityScan={vi.fn()} tenantId={null} />);
    fireEvent.click(screen.getByText(/OS Patches/));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/patches/os'));
  });
});
