/**
 * Phase 77 / ACC-08, ACC-09, D-01, D-03, D-15: deleting a custom role through the real API, the
 * confirmation, the pending state and the refusal dialog that names the holders.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react';

vi.mock('../../services/roleApi', async () => {
  const actual = await vi.importActual<any>('../../services/roleApi');
  return { ...actual, fetchRoles: vi.fn(), fetchRoleVisibility: vi.fn(() => new Promise(() => {})), deleteRole: vi.fn() };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { fetchRoles, deleteRole, RoleInUseError, RoleApiError } from '../../services/roleApi';
import { showToast } from '../../utils/toast';
import { SettingsRolesTab } from '../../components/SettingsRolesTab';

const mockFetch = fetchRoles as unknown as ReturnType<typeof vi.fn>;
const mockDelete = deleteRole as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

const helpdesk = { id: 'role-h', name: 'Helpdesk', description: 'Tier 1', permissions: [], isEditable: true, builtIn: false, tenantId: 'tenant-a' } as any;
const viewer = { id: 'role-viewer', name: 'Viewer', description: 'Read only', permissions: [], isEditable: false, builtIn: true } as any;

function setup(props: any = {}) {
  const onDelete = vi.fn();
  const onGoToUsers = vi.fn();
  render(<SettingsRolesTab roles={[viewer, helpdesk]} tenantId="tenant-a" canManageRBAC onEdit={() => {}} onDelete={onDelete} onNew={() => {}} onGoToUsers={onGoToUsers} {...props} />);
  return { onDelete, onGoToUsers };
}

const clickDelete = () => fireEvent.click(screen.getByRole('button', { name: 'Delete role Helpdesk' }));
const confirm = () => fireEvent.click(screen.getByRole('button', { name: 'Delete role', exact: true }));

beforeEach(() => {
  mockFetch.mockReset(); mockFetch.mockRejectedValue(new Error('offline'));
  mockDelete.mockReset(); mockToast.mockReset();
});

describe('delete confirmation', () => {
  it('opens a destructive confirmation with the exact copy and Keep role closes it without a request', () => {
    setup();
    clickDelete();
    expect(screen.getByText('Delete the custom role "Helpdesk"? This can\'t be undone.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Keep role' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Keep role' }));
    expect(mockDelete).not.toHaveBeenCalled();
    expect(screen.queryByText('Delete the custom role "Helpdesk"? This can\'t be undone.')).toBeNull();
  });

  it('204: calls deleteRole(id, tenantId), removes the row, toasts and notifies the parent', async () => {
    mockDelete.mockResolvedValue(undefined);
    const { onDelete } = setup();
    clickDelete(); confirm();
    await waitFor(() => expect(screen.queryByText('Helpdesk')).toBeNull());
    expect(mockDelete).toHaveBeenCalledWith('role-h', 'tenant-a');
    expect(mockToast).toHaveBeenCalledWith('Role "Helpdesk" deleted.', 'success');
    expect(onDelete).toHaveBeenCalledWith('role-h');
  });

  it('while pending the row is dimmed and inert and the trash button shows a spinner', async () => {
    let release: () => void = () => {};
    mockDelete.mockReturnValue(new Promise<void>(r => { release = r; }));
    setup();
    clickDelete(); confirm();
    const row = screen.getByText('Helpdesk').closest('tr')!;
    await waitFor(() => expect(row.className).toContain('opacity-60'));
    expect(row.className).toContain('pointer-events-none');
    expect(within(row).getByTestId('role-delete-spinner')).toBeTruthy();
    await act(async () => { release(); });
  });
});

describe('delete refused (role_in_use)', () => {
  const refuse = (detail: any) => mockDelete.mockRejectedValue(new RoleInUseError({ code: 'role_in_use', holderCount: 0, holders: [], mappingCount: 0, mappings: [], ...detail }));

  it('one holder: title, singular sentence, reassign hint, name over email; row returns to idle', async () => {
    refuse({ holderCount: 1, holders: [{ name: 'Ann', email: 'ann@x' }] });
    setup();
    clickDelete(); confirm();
    await screen.findByText('Can\'t delete "Helpdesk" yet');
    expect(screen.getByText('1 user still holds this role.')).toBeTruthy();
    expect(screen.getByText('Reassign them to another role, then delete it.')).toBeTruthy();
    const list = screen.getByRole('list');
    expect(within(list).getByText('Ann')).toBeTruthy();
    expect(within(list).getByText('ann@x')).toBeTruthy();
    expect(list.className).toContain('max-h-48');
    expect(screen.getByText('Helpdesk', { selector: 'span.truncate' }).closest('tr')!.className).not.toContain('opacity-60');
    expect(mockToast).not.toHaveBeenCalled();
  });

  it('60 holders with 50 listed: 50 rows plus "and 10 more"; a holder without a name shows the email as the bold line', async () => {
    const holders = Array.from({ length: 50 }, (_, i) => ({ name: i === 0 ? '' : `User ${i}`, email: `u${i}@x` }));
    refuse({ holderCount: 60, holders });
    setup();
    clickDelete(); confirm();
    await screen.findByText('60 users still hold this role.');
    expect(screen.getByText('and 10 more')).toBeTruthy();
    const items = within(screen.getAllByRole('list')[0]).getAllByRole('listitem');
    expect(items.length).toBe(51);
    const first = within(items[0]);
    expect(first.getAllByText('u0@x').length).toBe(1); // email shown once, as the bold line
    expect(first.getByText('u0@x').className).toContain('font-semibold');
  });

  it('mappings: plural sentence and a Sign-in mappings list with group over SAML/LDAP', async () => {
    refuse({ mappingCount: 2, mappings: [{ group: 'cn=helpdesk', source: 'LDAP' }, { group: 'Helpdesk-SSO', source: 'SAML' }] });
    setup();
    clickDelete(); confirm();
    await screen.findByText('2 sign-in mappings also use it.');
    expect(screen.getByText('Sign-in mappings')).toBeTruthy();
    expect(screen.getByText('cn=helpdesk')).toBeTruthy();
    expect(screen.getByText('LDAP')).toBeTruthy();
    expect(screen.getByText('SAML')).toBeTruthy();
    expect(screen.queryByText(/still hold/)).toBeNull();
    expect(screen.queryByText(/still holds/)).toBeNull();
  });

  it('one mapping reads singular', async () => {
    refuse({ mappingCount: 1, mappings: [{ group: 'g', source: 'SAML' }] });
    setup();
    clickDelete(); confirm();
    await screen.findByText('1 sign-in mapping also uses it.');
  });

  it('Go to User Management calls onGoToUsers and closes; the heading receives focus on open', async () => {
    refuse({ holderCount: 1, holders: [{ name: 'Ann', email: 'ann@x' }] });
    const { onGoToUsers } = setup();
    clickDelete(); confirm();
    const heading = await screen.findByText('Can\'t delete "Helpdesk" yet');
    await waitFor(() => expect(document.activeElement).toBe(heading));
    fireEvent.click(screen.getByRole('button', { name: 'Go to User Management' }));
    expect(onGoToUsers).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByText('Can\'t delete "Helpdesk" yet')).toBeNull());
  });

  it('Close dismisses the dialog without navigating', async () => {
    refuse({ holderCount: 1, holders: [{ name: 'Ann', email: 'ann@x' }] });
    const { onGoToUsers } = setup();
    clickDelete(); confirm();
    await screen.findByText('Can\'t delete "Helpdesk" yet');
    fireEvent.click(screen.getByRole('button', { name: 'Close', exact: true }));
    expect(onGoToUsers).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText('Can\'t delete "Helpdesk" yet')).toBeNull());
  });
});

describe('other failures', () => {
  it('500 with a detail toasts the server message and the row stays', async () => {
    mockDelete.mockRejectedValue(new RoleApiError(500, 'boom'));
    const { onDelete } = setup();
    clickDelete(); confirm();
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Couldn\'t delete the role: boom. Try again.', 'error'));
    const row = screen.getByText('Helpdesk').closest('tr')!;
    expect(row.className).not.toContain('opacity-60');
    expect(onDelete).not.toHaveBeenCalled();
  });
});
