/**
 * Spec C6: the Manage Tenant screen shows exactly the switch list the server enforces
 * (shared/tenant-feature-switches.json), and a sub-feature is unavailable while its
 * parent feature is off. The server-side rule is covered by
 * backend/tests/test_tenant_feature_switches.py.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import type { Tenant } from '../../types';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn().mockResolvedValue({ ok: false, json: async () => [] }),
  fetchTenantLicense: vi.fn().mockReturnValue(new Promise(() => {})),
  updateTenantLicense: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { ManageTenantModal } from '../../components/ManageTenantModal';
import { authFetch } from '../../services/apiService';
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

const pricing = [
  { id: 'price-edr', name: 'EDR', category: 'Security', unit: 'per_agent_mo', price: 8 },
  { id: 'compliance-soc2', frameworkId: 'soc2', name: 'SOC 2 Type II', category: 'Compliance', unit: 'per_tenant_per_month', price: 20 },
  { id: 'compliance-hipaa', frameworkId: 'hipaa', name: 'HIPAA Security Rule', category: 'Compliance', unit: 'per_tenant_per_month', price: 5 },
];

describe('ManageTenantModal compliance frameworks', () => {
  it('lists framework prices, totals the ticked ones and saves the purchase', async () => {
    vi.mocked(authFetch).mockImplementation(async (url: string) =>
      (String(url).includes('/finops/pricing') ? { ok: true, json: async () => pricing } : { ok: false, json: async () => [] }) as Response);
    const onSave = vi.fn();
    const buyer = { ...tenant, purchasedFrameworks: ['hipaa'] } as Tenant;
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={buyer} onSave={onSave} onDelete={() => {}} />);
    await waitFor(() => expect(screen.getByText('SOC 2 Type II')).toBeTruthy());
    // Framework prices are not offered again as generic billable services.
    expect(screen.getAllByText('SOC 2 Type II')).toHaveLength(1);
    expect(screen.getByText('1 selected · $5.00 / month')).toBeTruthy();

    fireEvent.click(switchBox('SOC 2 Type II'));
    expect(screen.getByText('2 selected · $25.00 / month')).toBeTruthy();
    fireEvent.click(screen.getByText('Save Changes'));
    expect(onSave.mock.calls[0][1].purchasedFrameworks.sort()).toEqual(['hipaa', 'soc2']);
  });

  it('keeps the existing purchase when prices cannot be loaded', () => {
    vi.mocked(authFetch).mockImplementation(async () => ({ ok: false, json: async () => [] }) as Response);
    const onSave = vi.fn();
    const buyer = { ...tenant, purchasedFrameworks: ['soc2'] } as Tenant;
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={buyer} onSave={onSave} onDelete={() => {}} />);
    expect(screen.getByText('Framework prices could not be loaded. Purchases are unchanged.')).toBeTruthy();
    fireEvent.click(screen.getByText('Save Changes'));
    expect(onSave.mock.calls[0][1].purchasedFrameworks).toEqual(['soc2']);
  });
});

describe('ManageTenantModal sidebar screens', () => {
  it('switching a feature on ticks each of its screens, which can then be unticked one by one', () => {
    const onSave = vi.fn();
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={onSave} onDelete={() => {}} />);
    expect(switchBox('Deployment Approvals').disabled).toBe(true);
    fireEvent.click(switchBox('Patch Management'));
    expect(switchBox('Deployment Approvals').checked).toBe(true);
    fireEvent.click(switchBox('Deployment Approvals'));
    fireEvent.click(screen.getByText('Save Changes'));
    const saved = onSave.mock.calls[0][1].features as string[];
    expect(saved).toEqual(expect.arrayContaining(['view:patching', 'screen:patchManagement']));
    expect(saved).not.toContain('screen:deploymentApprovals');
  });

  it('choosing a tier keeps the screens of its features on', () => {
    const onSave = vi.fn();
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={onSave} onDelete={() => {}} />);
    fireEvent.change(screen.getByDisplayValue('Custom'), { target: { value: 'Pro' } });
    fireEvent.click(screen.getByText('Save Changes'));
    const saved = onSave.mock.calls[0][1].features as string[];
    expect(saved).toEqual(expect.arrayContaining(['view:security', 'screen:edr', 'screen:reporting', 'screen:dashboard']));
  });
});

describe('ManageTenantModal agent capabilities', () => {
  it('shows what the tenant has, keeps self-update on, and saves the ticked capabilities', () => {
    const onSave = vi.fn();
    const chosen = { ...tenant, agentCapabilities: ['fim', 'agent_update'] } as Tenant;
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={chosen} onSave={onSave} onDelete={() => {}} />);
    expect(switchBox('File Integrity Monitoring').checked).toBe(true);
    expect(switchBox('PII Data Scanner').checked).toBe(false);
    expect(switchBox('Agent Self-Update')).toMatchObject({ checked: true, disabled: true });
    fireEvent.click(switchBox('PII Data Scanner'));
    fireEvent.click(switchBox('File Integrity Monitoring'));
    fireEvent.click(screen.getByText('Save Changes'));
    expect(onSave.mock.calls[0][1].agentCapabilities.sort()).toEqual(['agent_update', 'pii_scanner']);
  });

  it('a tenant without a list shows only the always-on capability ticked', () => {
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={() => {}} onDelete={() => {}} />);
    expect(switchBox('Autonomous Patching').checked).toBe(false);
    expect(switchBox('Agent Self-Update').checked).toBe(true);
  });
});
