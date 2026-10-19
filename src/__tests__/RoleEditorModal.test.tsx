/**
 * Phase 77 / ACC-08, D-01, D-02, D-11, D-13: the server-backed custom role editor.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../services/roleApi', async () => {
  const actual = await vi.importActual<any>('../../services/roleApi');
  return { ...actual, fetchPermissionCatalogue: vi.fn(), createRole: vi.fn(), updateRole: vi.fn() };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { fetchPermissionCatalogue, createRole, updateRole, RoleApiError } from '../../services/roleApi';
import { showToast } from '../../utils/toast';
import { RoleEditorModal } from '../../components/RoleEditorModal';
import { UserContext } from '../../contexts/UserContext';

const mCatalogue = fetchPermissionCatalogue as unknown as ReturnType<typeof vi.fn>;
const mCreate = createRole as unknown as ReturnType<typeof vi.fn>;
const mUpdate = updateRole as unknown as ReturnType<typeof vi.fn>;
const mToast = showToast as unknown as ReturnType<typeof vi.fn>;

const builtinViewer = { id: 'role-viewer', name: 'Viewer', description: 'ro', permissions: [], isEditable: false, builtIn: true } as any;
const existing = { id: 'role-c1', name: 'Auditors', description: 'Audit things', permissions: ['view:agents'], isEditable: true, builtIn: false, tenantId: 'tenant-a' } as any;

function renderModal(props: any = {}) {
  const onSave = vi.fn();
  const onClose = vi.fn();
  render(
    <UserContext.Provider value={{ currentUser: null, enabledFeatures: [] } as any}>
      <RoleEditorModal isOpen onClose={onClose} onSave={onSave} role={null} allRoles={[builtinViewer]} tenantId="tenant-a" {...props} />
    </UserContext.Provider>
  );
  return { onSave, onClose };
}

beforeEach(() => {
  mCatalogue.mockReset(); mCreate.mockReset(); mUpdate.mockReset(); mToast.mockReset();
  mCatalogue.mockResolvedValue({ permissions: ['view:agents', 'view:assets'], superAdmin: true });
});

describe('RoleEditorModal create (tracer)', () => {
  it('fetches the catalogue with the tenant id and lists its permissions with label or raw string', async () => {
    mCatalogue.mockResolvedValue({ permissions: ['view:agents', 'x:unlabelled'], superAdmin: true });
    renderModal();
    expect(await screen.findByLabelText('Agent Fleet Management')).toBeTruthy();
    expect(screen.getByText('x:unlabelled')).toBeTruthy();
    expect(mCatalogue).toHaveBeenCalledWith('tenant-a');
  });

  it('creates through the API, passes the server role to onSave and toasts', async () => {
    const saved = { ...existing, id: 'role-new', name: 'Helpdesk' };
    mCreate.mockResolvedValue(saved);
    const { onSave } = renderModal();
    fireEvent.click(await screen.findByLabelText('Agent Fleet Management'));
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Helpdesk' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Front line' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(saved));
    expect(mCreate).toHaveBeenCalledWith({ name: 'Helpdesk', description: 'Front line', permissions: ['view:agents'], tenantId: 'tenant-a' });
    expect(mToast).toHaveBeenCalledWith('Role "Helpdesk" saved.', 'success');
  });

  it('starts empty and blocks submit until a name is entered (C33)', async () => {
    renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    expect((screen.getByLabelText('Role Name') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Description') as HTMLTextAreaElement).value).toBe('');
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    expect(mCreate).not.toHaveBeenCalled();
  });

  it('shows Saving... disabled with disabled inputs while pending, Cancel stays enabled (C34)', async () => {
    mCreate.mockReturnValue(new Promise(() => {}));
    renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Helpdesk' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    const saving = await screen.findByRole('button', { name: 'Saving...' });
    expect((saving as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText('Role Name') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Agent Fleet Management') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Cancel' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('keeps the modal and inputs on a server 400 and shows the red error block (C35)', async () => {
    mCreate.mockRejectedValue(new RoleApiError(400, 'x'));
    const { onSave } = renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Helpdesk' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    const alert = await screen.findByText("Couldn't save the role: x. Your changes are still here, fix the issue and try again.");
    expect(alert.closest('[role="alert"]')).not.toBeNull();
    expect((screen.getByLabelText('Role Name') as HTMLInputElement).value).toBe('Helpdesk');
    expect(onSave).not.toHaveBeenCalled();
  });

  it('shows the no-message fallback on a network failure', async () => {
    mCreate.mockRejectedValue(new Error(''));
    renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Helpdesk' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    expect(await screen.findByText("Couldn't save the role. Check your connection and try again.")).toBeTruthy();
  });

  it('shows a 409 server message inline under the name field', async () => {
    mCreate.mockRejectedValue(new RoleApiError(409, 'A role named Helpdesk already exists in this tenant.'));
    renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Helpdesk' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    const msg = await screen.findByText('A role named Helpdesk already exists in this tenant.');
    expect(msg.getAttribute('role')).toBe('alert');
  });
});

describe('RoleEditorModal edit', () => {
  it('disables the name with the D-13 helper and sends no name', async () => {
    mUpdate.mockResolvedValue({ ...existing, description: 'New text' });
    const { onSave } = renderModal({ role: existing });
    await screen.findByLabelText('Agent Fleet Management');
    expect((screen.getByLabelText('Role Name') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("A role's name can't be changed. To rename, create a new role and reassign its users.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'New text' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(mUpdate).toHaveBeenCalledWith('role-c1', { description: 'New text', permissions: ['view:agents'] }, 'tenant-a');
    expect(mCreate).not.toHaveBeenCalled();
  });
});

describe('RoleEditorModal implied, locked and ceiling states', () => {
  it('shows implied rows checked, disabled and "Included with Manage" while manage is ticked, then restores them', async () => {
    mCatalogue.mockResolvedValue({ permissions: ['manage:assets', 'view:assets'], superAdmin: true });
    renderModal();
    const manage = await screen.findByLabelText('manage:assets') as HTMLInputElement;
    const view = screen.getByLabelText('Asset Management') as HTMLInputElement;
    expect(view.checked).toBe(false);
    fireEvent.click(manage);
    expect(view.checked).toBe(true);
    expect(view.disabled).toBe(true);
    expect(screen.getByText('Included with Manage')).toBeTruthy();
    fireEvent.click(manage);
    expect(view.checked).toBe(false);
    expect(view.disabled).toBe(false);
    expect(screen.queryByText('Included with Manage')).toBeNull();
  });

  it('submits exactly the visibly checked set, implied rows included', async () => {
    mCatalogue.mockResolvedValue({ permissions: ['manage:assets', 'view:assets'], superAdmin: true });
    mCreate.mockResolvedValue({ ...existing, name: 'Ops' });
    renderModal();
    fireEvent.click(await screen.findByLabelText('manage:assets'));
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Ops' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'd' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    await waitFor(() => expect(mCreate).toHaveBeenCalled());
    expect([...mCreate.mock.calls[0][0].permissions].sort()).toEqual(['manage:assets', 'view:assets']);
  });

  it('renders a permission the catalogue does not list as checked, disabled and locked, and keeps it on save', async () => {
    mCatalogue.mockResolvedValue({ permissions: ['view:agents'], superAdmin: false });
    mUpdate.mockResolvedValue(existing);
    const role = { ...existing, permissions: ['view:agents', 'view:security'] };
    renderModal({ role });
    const locked = await screen.findByLabelText('Security Operations') as HTMLInputElement;
    expect(locked.checked).toBe(true);
    expect(locked.disabled).toBe(true);
    expect(screen.getByText("Your role doesn't include this permission, so you can't change it.")).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(mUpdate).toHaveBeenCalled());
    expect([...mUpdate.mock.calls[0][1].permissions].sort()).toEqual(['view:agents', 'view:security']);
  });

  it('shows the ceiling banner only for a non-Super-Admin catalogue', async () => {
    mCatalogue.mockResolvedValue({ permissions: ['view:agents'], superAdmin: false });
    const { unmount } = (() => { renderModal(); return { unmount: () => {} }; })();
    expect(await screen.findByText('You can only grant permissions you hold yourself.')).toBeTruthy();
    unmount();
  });

  it('shows no banner for a Super Admin catalogue', async () => {
    renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    expect(screen.queryByText('You can only grant permissions you hold yourself.')).toBeNull();
  });

  it('refuses a built-in name inline before the round trip', async () => {
    renderModal();
    await screen.findByLabelText('Agent Fleet Management');
    fireEvent.change(screen.getByLabelText('Role Name'), { target: { value: 'Viewer' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'd' } });
    expect(screen.getByText('That name matches the built-in role "Viewer". Choose a different name.').getAttribute('role')).toBe('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Create Role' }));
    expect(mCreate).not.toHaveBeenCalled();
  });

  it('groups the list by catalogue group and shows a raw string in font-mono for an unlabelled permission', async () => {
    mCatalogue.mockResolvedValue({ permissions: ['view:assets', 'x:unlabelled'], superAdmin: true });
    renderModal();
    await screen.findByLabelText('Asset Management');
    expect(screen.getByRole('group', { name: 'Infrastructure & Assets' })).toBeTruthy();
    expect(screen.getByRole('group', { name: 'Other' })).toBeTruthy();
    const raw = screen.getByText('x:unlabelled');
    expect(raw.className).toContain('font-mono');
  });
});
