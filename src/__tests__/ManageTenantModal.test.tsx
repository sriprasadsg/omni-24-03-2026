/**
 * Spec C6: the Manage Tenant screen shows exactly the switch list the server enforces
 * (shared/tenant-feature-switches.json), and a sub-feature is unavailable while its
 * parent feature is off. The server-side rule is covered by
 * backend/tests/test_tenant_feature_switches.py.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { Tenant } from '../../types';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn().mockResolvedValue({ ok: false, json: async () => [] }),
  fetchTenantLicense: vi.fn().mockReturnValue(new Promise(() => {})),
  updateTenantLicense: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { ManageTenantModal } from '../../components/ManageTenantModal';
import featureSwitches from '../../shared/tenant-feature-switches.json';

const tenant = { id: 't1', name: 'Acme', subscriptionTier: 'Custom', enabledFeatures: ['view:reporting'] } as unknown as Tenant;
const switchLabel = (label: string) => screen.getAllByText(label).map(el => el.closest('label')).find(Boolean)!;
const switchBox = (label: string) => within(switchLabel(label)).getByRole('checkbox') as HTMLInputElement;

describe('ManageTenantModal feature switches (spec C6)', () => {
  it('lists every switch from the shared catalogue and no profile switch', () => {
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={() => {}} onDelete={() => {}} />);
    for (const group of featureSwitches.groups) {
      for (const feature of group.features) expect(switchLabel(feature.label)).toBeTruthy();
    }
    expect(screen.queryByText('User Profile')).toBeNull();
  });

  it('a sub-feature is unavailable until its parent is on, and save sends both', () => {
    const onSave = vi.fn();
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={onSave} onDelete={() => {}} />);
    expect(switchBox('Export Reports').disabled).toBe(false);
    expect(switchBox('Deploy Patches').disabled).toBe(true);

    fireEvent.click(switchBox('Patch Management'));
    expect(switchBox('Deploy Patches').disabled).toBe(false);
    fireEvent.click(switchBox('Deploy Patches'));

    fireEvent.click(screen.getByText('Save Changes'));
    const saved = onSave.mock.calls[0][1].features as string[];
    expect(saved).toEqual(expect.arrayContaining(['view:reporting', 'view:patching', 'manage:patches', 'view:dashboard']));
    expect(saved).not.toContain('view:security');
  });
});
