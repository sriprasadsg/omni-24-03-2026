/**
 * Compliance framework prices on Service Pricing Configuration: never below $5, never
 * deleted, category and unit fixed. The server enforces the same rules
 * (backend/tests/test_compliance_framework_purchases.py).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  fetchServicePricing: vi.fn(),
  createServicePricing: vi.fn(),
  updateSingleServicePricing: vi.fn(),
  deleteServicePricing: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { ServicePricingPage } from '../../components/ServicePricingPage';
import { fetchServicePricing, updateSingleServicePricing } from '../../services/apiService';

const services = [
  { id: 'price-edr', name: 'EDR', category: 'Security', unit: 'per_agent_per_month', price: 8, description: '' },
  { id: 'compliance-soc2', frameworkId: 'soc2', name: 'SOC 2 Type II', category: 'Compliance', unit: 'per_tenant_per_month', price: 5, description: '' },
];
const row = (name: string) => screen.getByText(name).closest('tr')!;

describe('ServicePricingPage compliance prices', () => {
  beforeEach(() => {
    vi.mocked(fetchServicePricing).mockResolvedValue(services);
    vi.mocked(updateSingleServicePricing).mockReset();
  });

  it('offers no delete for a framework price, but does for other services', async () => {
    render(<ServicePricingPage />);
    await waitFor(() => expect(screen.getByText('SOC 2 Type II')).toBeTruthy());
    expect(within(row('SOC 2 Type II')).queryByTitle('Delete Service')).toBeNull();
    expect(within(row('EDR')).getByTitle('Delete Service')).toBeTruthy();
  });

  it('refuses a framework price below $5 and keeps its category and unit fixed', async () => {
    render(<ServicePricingPage />);
    await waitFor(() => expect(screen.getByText('SOC 2 Type II')).toBeTruthy());
    fireEvent.click(within(row('SOC 2 Type II')).getByTitle('Edit Service'));

    const price = screen.getByPlaceholderText('0.00') as HTMLInputElement;
    expect(price.min).toBe('5');
    const [category, unit] = screen.getAllByRole('combobox') as HTMLSelectElement[];
    expect(category.disabled && unit.disabled).toBe(true);
    expect(unit.value).toBe('per_tenant_per_month');

    fireEvent.change(price, { target: { value: '3' } });
    fireEvent.submit(price.closest('form')!);
    await waitFor(() => expect(screen.getByText(/must be at least \$5\.00/)).toBeTruthy());
    expect(updateSingleServicePricing).not.toHaveBeenCalled();
  });
});
