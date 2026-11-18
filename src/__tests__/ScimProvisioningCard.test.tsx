/**
 * SCIM provisioning card (User Management): the tenant URL and token list, a new token shown once, revoke with
 * a confirmation, a select-a-tenant note for the platform scope, and nothing at all for a role that is refused.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const authFetch = vi.fn();
vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: (...a: unknown[]) => authFetch(...a) }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { ScimProvisioningCard } from '../../components/ScimProvisioningCard';

const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body });
const token = { id: 'scimtok-1', prefix: 'omni_scim_abc123', label: 'Entra', createdBy: 'admin@a', createdAt: '2026-11-18T10:00:00Z', lastUsedAt: null, revokedAt: null };

beforeEach(() => { authFetch.mockReset(); });

describe('SCIM provisioning card', () => {
  it('shows the tenant URL and tokens, shows a new token once, and revokes after confirming', async () => {
    let items = [token];
    authFetch.mockImplementation(async (url: string, init?: { method?: string; body?: string }) => {
      if (init?.method === 'POST') {
        items = [{ ...token, id: 'scimtok-2', prefix: 'omni_scim_new999', label: JSON.parse(init.body!).label }, ...items];
        return reply(200, { ...items[0], token: 'omni_scim_new999SECRET', basePath: '/api/scim/v2' });
      }
      if (init?.method === 'DELETE') return reply(200, { success: true });
      return reply(200, { items, basePath: '/api/scim/v2' });
    });
    render(<ScimProvisioningCard />);
    expect(await screen.findByText(`${window.location.origin}/api/scim/v2`)).toBeTruthy();
    expect(screen.getByText('omni_scim_abc123…')).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: 'Label' }), { target: { value: 'Okta' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create token' }));
    expect((await screen.findByRole('alert')).textContent).toContain('omni_scim_new999SECRET');
    const post = authFetch.mock.calls.find(([, i]) => i?.method === 'POST');
    expect(JSON.parse(post![1].body)).toEqual({ label: 'Okta' });
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByText(/SECRET/)).toBeNull();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: 'Revoke token omni_scim_abc123' }));
    await waitFor(() => expect(authFetch.mock.calls.some(([u, i]) => i?.method === 'DELETE' && u === '/api/admin/sso/scim/tokens/scimtok-1')).toBe(true));
  });

  it('asks the platform scope to open a tenant and shows nothing to a refused role', async () => {
    authFetch.mockResolvedValue(reply(400, { detail: 'Select a tenant: a SCIM token belongs to one organization' }));
    const { unmount } = render(<ScimProvisioningCard />);
    expect((await screen.findByRole('status')).textContent).toContain('Open a tenant first');
    expect(screen.queryByRole('button', { name: 'Create token' })).toBeNull();
    unmount();
    authFetch.mockResolvedValue(reply(403, { detail: 'Missing required permission: manage:users' }));
    const { container } = render(<ScimProvisioningCard />);
    await waitFor(() => expect(container.innerHTML).toBe(''));
  });
});
