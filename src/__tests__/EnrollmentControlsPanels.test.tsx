/**
 * Enrollment control panels (spec C4).
 * protects=the license panel saves allowlist mode, sub-limits and an expiry (and clears it with
 * null); a new install key is shown once with its plaintext and revoke asks first; the allowlist
 * import reports skipped rows by line; fails_when=a control is dropped from the PATCH, the key is
 * shown again after "Done", or revoke fires unasked; no_claim=the backend (calls are mocked).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const authFetch = vi.fn();
const fetchTenantLicense = vi.fn();
const updateTenantLicense = vi.fn();

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: (...args: unknown[]) => authFetch(...args),
  fetchTenantLicense: (...args: unknown[]) => fetchTenantLicense(...args),
  updateTenantLicense: (...args: unknown[]) => updateTenantLicense(...args),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { TenantLicensePanel } from '../../components/TenantLicensePanel';
import { TenantEnrollmentKeysPanel } from '../../components/TenantEnrollmentKeysPanel';
import { TenantAllowlistPanel } from '../../components/TenantAllowlistPanel';

const LICENSE = {
  tenantId: 't1', maxAgents: 10, seatsUsed: 4, seatsAvailable: 6, overBy: 0, inactiveReclaimDays: 30,
  allowlistMode: 'off', subLimits: [], expiresAt: '2027-01-31T23:59:59+00:00',
};
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

describe('TenantLicensePanel controls', () => {
  beforeEach(() => { fetchTenantLicense.mockReset(); updateTenantLicense.mockReset(); });

  it('saves allowlist mode and a sub-limit', async () => {
    fetchTenantLicense.mockResolvedValue(LICENSE);
    updateTenantLicense.mockResolvedValue({ ...LICENSE, allowlistMode: 'enforce', subLimits: [{ key: 'os:windows_server', max: 2 }] });
    render(<TenantLicensePanel tenantId="t1" />);
    await waitFor(() => screen.getByDisplayValue('2027-01-31'));
    fireEvent.change(screen.getByDisplayValue('Off: any machine may enroll'), { target: { value: 'enforce' } });
    fireEvent.click(screen.getByText('+ Add sub-limit'));
    fireEvent.change(screen.getByLabelText('Sub-limit key'), { target: { value: 'os:windows_server' } });
    fireEvent.change(screen.getByLabelText('Sub-limit max'), { target: { value: '2' } });
    fireEvent.click(screen.getByText('Save license'));
    await waitFor(() => expect(updateTenantLicense).toHaveBeenCalled());
    const [, changes] = updateTenantLicense.mock.calls[0];
    expect(changes.allowlistMode).toBe('enforce');
    expect(changes.subLimits).toEqual([{ key: 'os:windows_server', max: 2 }]);
    expect('expiresAt' in changes).toBe(false); // untouched expiry is not resent
  });

  it('clears the expiry with null', async () => {
    fetchTenantLicense.mockResolvedValue(LICENSE);
    updateTenantLicense.mockResolvedValue({ ...LICENSE, expiresAt: null });
    render(<TenantLicensePanel tenantId="t1" />);
    const date = await waitFor(() => screen.getByDisplayValue('2027-01-31'));
    fireEvent.change(date, { target: { value: '' } });
    fireEvent.click(screen.getByText('Save license'));
    await waitFor(() => expect(updateTenantLicense).toHaveBeenCalled());
    expect(updateTenantLicense.mock.calls[0][1].expiresAt).toBeNull();
  });
});

describe('TenantEnrollmentKeysPanel', () => {
  beforeEach(() => authFetch.mockReset());

  it('shows a new key once and revokes only after confirmation', async () => {
    const legacy = { id: 'ek-1', name: 'Legacy key', prefix: 'reg_0123', legacy: true, maxUses: null, uses: 7,
      expiresAt: null, defaultGroupId: null, revokedAt: null, createdAt: '2026-10-14', problem: null };
    authFetch
      .mockResolvedValueOnce(ok({ keys: [legacy] }))
      .mockResolvedValueOnce(ok({ id: 'ek-2', name: 'Lab', key: 'ek_secretvalue123', prefix: 'ek_secre' }))
      .mockResolvedValueOnce(ok({ keys: [legacy] }))
      .mockResolvedValueOnce(ok({ ...legacy, revokedAt: 'now' }))
      .mockResolvedValueOnce(ok({ keys: [] }));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<TenantEnrollmentKeysPanel tenantId="t1" canManage />);
    await waitFor(() => screen.getByText('Legacy key'));
    fireEvent.change(screen.getByLabelText('Key name'), { target: { value: 'Lab' } });
    fireEvent.change(screen.getByLabelText('Max uses'), { target: { value: '5' } });
    fireEvent.click(screen.getByText('Create key'));
    await waitFor(() => screen.getByText('ek_secretvalue123'));
    expect(JSON.parse(authFetch.mock.calls[1][1].body)).toEqual({ name: 'Lab', maxUses: 5 });
    fireEvent.click(screen.getByText('Done'));
    expect(screen.queryByText('ek_secretvalue123')).toBeNull();

    fireEvent.click(screen.getByText('Revoke'));
    expect(authFetch).toHaveBeenCalledTimes(3);
    fireEvent.click(screen.getByText('Revoke'));
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/tenants/t1/enrollment-keys/ek-1/revoke', { method: 'POST' }));
    expect(confirm.mock.calls[1][0]).toContain('Legacy key');
  });

  it('is read-only without manage rights', async () => {
    authFetch.mockResolvedValue(ok({ keys: [] }));
    render(<TenantEnrollmentKeysPanel tenantId="t1" canManage={false} />);
    await waitFor(() => expect(authFetch).toHaveBeenCalled());
    expect(screen.queryByText('Create key')).toBeNull();
  });
});

describe('TenantAllowlistPanel', () => {
  beforeEach(() => authFetch.mockReset());

  it('imports CSV and lists the skipped rows', async () => {
    authFetch
      .mockResolvedValueOnce(ok({ entries: [], total: 0 }))
      .mockResolvedValueOnce(ok({ imported: 2, skipped: 1, errors: [{ row: 3, error: 'invalid macAddress: \'zz\'' }] }))
      .mockResolvedValueOnce(ok({ entries: [{ id: 'al-1', serialNumber: 'PF3ABC12', addedAt: 'x' }], total: 2 }));
    render(<TenantAllowlistPanel tenantId="t1" canManage />);
    await waitFor(() => expect(authFetch).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('Allowlist CSV'), { target: { value: 'PF3ABC12,,,\nSN2,,,\nSN3,,zz,' } });
    fireEvent.click(screen.getByText('Import'));
    await waitFor(() => screen.getByText(/Row 3: invalid macAddress/));
    expect(screen.getByText('2 imported')).toBeTruthy();
    expect(JSON.parse(authFetch.mock.calls[1][1].body)).toEqual({ csv: 'PF3ABC12,,,\nSN2,,,\nSN3,,zz,' });
    expect(screen.getByText('S/N PF3ABC12')).toBeTruthy();
  });
});
