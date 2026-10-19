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
