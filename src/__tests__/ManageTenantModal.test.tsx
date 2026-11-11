/**
 * Spec C6: the Manage Tenant screen shows exactly the switch list the server enforces
 * (shared/tenant-feature-switches.json), and a sub-feature is unavailable while its
 * parent feature is off. The server-side rule is covered by
 * backend/tests/test_tenant_feature_switches.py.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
  // 2026-10-20: a tenant sees only what a Super Admin ticked, so a feature never brings its screens.
  it('switching a feature on ticks none of its screens; each is ticked one by one', () => {
    const onSave = vi.fn();
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={onSave} onDelete={() => {}} />);
    expect(switchBox('Deployment Approvals').disabled).toBe(true);
    fireEvent.click(switchBox('Patch Management'));
    expect(switchBox('Deployment Approvals')).toMatchObject({ checked: false, disabled: false });
    fireEvent.click(switchBox('Deployment Approvals'));
    fireEvent.click(screen.getByText('Save Changes'));
    const saved = onSave.mock.calls[0][1].features as string[];
    expect(saved).toEqual(expect.arrayContaining(['view:patching', 'screen:deploymentApprovals']));
    expect(saved).not.toContain('screen:patchManagement');
  });

  // D-27 (Phase 88): a plan is a ceiling, not a preset, so choosing one never ticks or unticks a box.
  it('D-27: choosing a plan changes no checkbox', () => {
    const onSave = vi.fn();
    const ticked = { ...tenant, enabledFeatures: ['view:reporting', 'screen:reporting'] } as unknown as Tenant;
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={ticked} onSave={onSave} onDelete={() => {}} />);
    fireEvent.change(screen.getByDisplayValue('Custom'), { target: { value: 'Pro' } });
    expect(switchBox('Security Operations').checked).toBe(false);
    fireEvent.click(screen.getByText('Save Changes'));
    const saved = onSave.mock.calls[0][1].features as string[];
    expect([...saved].sort()).toEqual(['screen:reporting', 'view:dashboard', 'view:reporting']);
    expect(onSave.mock.calls[0][1].tier).toBe('Pro');
  });

  it('switching Security on ticks none of its screens; a Super Admin ticks each one', () => {
    const onSave = vi.fn();
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={tenant} onSave={onSave} onDelete={() => {}} />);
    expect(screen.getAllByText(/tick each screen the tenant may use/)).toHaveLength(1);
    fireEvent.click(switchBox('Security Operations'));
    expect(switchBox('EDR (Real-Time)').checked).toBe(false);
    fireEvent.click(switchBox('EDR (Real-Time)'));
    fireEvent.click(screen.getByText('Save Changes'));
    const saved = onSave.mock.calls[0][1].features as string[];
    expect(saved).toEqual(expect.arrayContaining(['view:security', 'screen:edr']));
    expect(saved).not.toContain('screen:alertManagement');
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

// Phase 88 (LIC-04, D-27, D-28): the chosen plan's screen list is a ceiling for the boxes.
const planList = [
  { key: 'Free', seats: 5, trialDays: 14, screens: ['screen:dashboard', 'view:agents'], tenantCount: 1 },
  { key: 'Pro', seats: 50, trialDays: null, screens: ['screen:dashboard', 'view:agents', 'view:logs'], tenantCount: 1 },
  { key: 'Enterprise', seats: 500, trialDays: null, screens: ['screen:dashboard'], tenantCount: 1 },
  { key: 'Custom', seats: null, trialDays: null, screens: 'all', tenantCount: 1 },
];
const freeTenant = (enabledFeatures: string[] = []) => ({ id: 't2', name: 'Initech', subscriptionTier: 'Free', enabledFeatures }) as unknown as Tenant;

describe('ManageTenantModal plan ceiling (Phase 88)', () => {
  beforeEach(() => {
    vi.mocked(authFetch).mockImplementation(async (url: string) =>
      (String(url).includes('/platform/plans') ? { ok: true, json: async () => ({ plans: planList }) } : { ok: false, json: async () => [] }) as Response);
  });
  afterEach(() => {
    vi.mocked(authFetch).mockReset();
    vi.mocked(authFetch).mockResolvedValue({ ok: false, json: async () => [] } as Response);
  });

  it('offers Free, Pro, Enterprise and Custom', () => {
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={freeTenant()} onSave={() => {}} onDelete={() => {}} />);
    const select = screen.getByDisplayValue('Free') as HTMLSelectElement;
    expect([...select.options].map(o => o.value)).toEqual(['Free', 'Pro', 'Enterprise', 'Custom']);
  });

  it('disables a switch outside the plan with the reason, and enables it after choosing a plan that has it', async () => {
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={freeTenant()} onSave={() => {}} onDelete={() => {}} />);
    await waitFor(() => expect(switchBox('Log Explorer').disabled).toBe(true));
    expect(switchLabel('Log Explorer').getAttribute('title')).toBe('Not part of the Free plan');
    expect(switchBox('Overview').disabled).toBe(false);

    fireEvent.change(screen.getByDisplayValue('Free'), { target: { value: 'Pro' } });
    expect(switchBox('Log Explorer')).toMatchObject({ checked: false, disabled: false });
    expect(switchBox('Overview').checked).toBe(false);
  });

  it('keeps a screen the tenant already has outside the plan: ticked, marked, and gone for good once unticked', async () => {
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={freeTenant(['view:logs'])} onSave={() => {}} onDelete={() => {}} />);
    await waitFor(() => expect(within(switchLabel('Log Explorer')).queryByText('outside plan')).toBeTruthy());
    expect(switchBox('Log Explorer')).toMatchObject({ checked: true, disabled: false });

    fireEvent.click(switchBox('Log Explorer'));
    expect(switchBox('Log Explorer')).toMatchObject({ checked: false, disabled: true });
    expect(within(switchLabel('Log Explorer')).queryByText('outside plan')).toBeNull();
  });

  it('select all ticks only what the plan allows', async () => {
    const onSave = vi.fn();
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={freeTenant()} onSave={onSave} onDelete={() => {}} />);
    await waitFor(() => expect(switchBox('Log Explorer').disabled).toBe(true));
    fireEvent.click(within(screen.getByText('Enable All Standard Features').closest('label')!).getByRole('checkbox'));
    expect(switchBox('Overview').checked).toBe(true);
    expect(switchBox('Log Explorer').checked).toBe(false);
    fireEvent.click(screen.getByText('Save Changes'));
    expect([...onSave.mock.calls[0][1].features].sort()).toEqual(['screen:dashboard', 'view:agents', 'view:dashboard']);
    expect(onSave.mock.calls[0][1].tier).toBe('Free');
  });

  it('leaves every box enabled when the plans cannot be loaded (the server still refuses)', async () => {
    vi.mocked(authFetch).mockImplementation(async () => ({ ok: false, json: async () => [] }) as Response);
    render(<ManageTenantModal isOpen onClose={() => {}} tenant={freeTenant()} onSave={() => {}} onDelete={() => {}} />);
    await Promise.resolve();
    expect(switchBox('Log Explorer').disabled).toBe(false);
  });
});
