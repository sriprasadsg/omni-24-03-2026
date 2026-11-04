/**
 * Phase 87 (PART-01, PART-03, PART-07; 87-UI-SPEC section 1): the Super Admin Partners screen. The API
 * client is mocked; these cases cover every state in the contract (loading, empty, error, populated,
 * partial, zero-one-many, long text) and the customers disclosure.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return {
    ...actual,
    fetchPartners: vi.fn(),
    fetchPartnerCustomers: vi.fn(),
    fetchDirectCustomers: vi.fn(),
    appointPartner: vi.fn(),
    updatePartner: vi.fn(),
    suspendPartner: vi.fn(),
    reinstatePartner: vi.fn(),
    moveCustomer: vi.fn(),
  };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import * as api from '../../services/partnerApi';
import type { PartnerSummary, PartnerCustomerRow } from '../../services/partnerApi';
import { PartnersDashboard } from '../../components/PartnersDashboard';

const fetchPartners = api.fetchPartners as ReturnType<typeof vi.fn>;
const fetchPartnerCustomers = api.fetchPartnerCustomers as ReturnType<typeof vi.fn>;

const DAY = 24 * 60 * 60 * 1000;

const partner = (over: Partial<PartnerSummary> = {}): PartnerSummary => ({
  id: 'p1',
  name: 'Acme Resale',
  poolSize: 100,
  allocated: 40,
  free: 60,
  expiresAt: null,
  expired: false,
  screenCeiling: ['view:assets', 'screen:assetManagement'],
  unrestricted: false,
  status: 'active',
  customerCount: 2,
  ...over,
});

const customer = (over: Partial<PartnerCustomerRow> = {}): PartnerCustomerRow => ({
  id: 'c1',
  name: 'Globex',
  seatsAssigned: 25,
  seatsUsed: 10,
  agentsOnline: 4,
  agentsTotal: 9,
  licenseExpiresAt: null,
  ...over,
});

const row = (name: string) => screen.getByText(name).closest('tr') as HTMLElement;

beforeEach(() => {
  vi.clearAllMocks();
  fetchPartnerCustomers.mockResolvedValue([]);
});
afterEach(cleanup);

describe('PartnersDashboard header and loading', () => {
  it('renders the header at once and four skeleton rows with aria-busy while loading', () => {
    fetchPartners.mockReturnValue(new Promise(() => {}));
    const { container } = render(<PartnersDashboard />);
    expect(screen.getByRole('heading', { level: 1, name: 'Partners' })).toBeTruthy();
    expect(screen.getByText('Appoint partners, give each a pool of agent seats and set which screens they may sell.')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Appoint partner/ })).toBeTruthy();
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
    expect(container.querySelectorAll('tbody tr[data-skeleton]').length).toBe(4);
  });
});

describe('PartnersDashboard empty and error states', () => {
  it('shows the No partners yet empty state with the Appoint partner action', async () => {
    fetchPartners.mockResolvedValue([]);
    render(<PartnersDashboard />);
    expect(await screen.findByText('No partners yet')).toBeTruthy();
    expect(screen.getByText(/Appoint a partner to give a dealer or reseller its own pool of seats/)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Appoint partner' }).length).toBe(2);
  });

  it('shows a red alert with Try again and no table when the load fails, then recovers', async () => {
    fetchPartners.mockRejectedValueOnce(new Error('boom'));
    render(<PartnersDashboard />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't load partners. Check your connection and try again.");
    expect(screen.queryByRole('table')).toBeNull();
    fetchPartners.mockResolvedValueOnce([partner()]);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Acme Resale')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('PartnersDashboard populated table', () => {
  it('lists partners ordered by name with the pool bar, figures, status and count', async () => {
    fetchPartners.mockResolvedValue([
      partner({ id: 'p2', name: 'Zed Partners', allocated: 5, poolSize: 10, free: 5, customerCount: 1 }),
      partner({ id: 'p1', name: 'Acme Resale' }),
    ]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    const names = screen.getAllByRole('row').slice(1).map(r => r.querySelector('td')?.textContent ?? '');
    expect(names[0]).toContain('Acme Resale');
    expect(names[1]).toContain('Zed Partners');
    expect(screen.getByText('2 partners')).toBeTruthy();
    const acme = row('Acme Resale');
    expect(within(acme).getByText('40 of 100 handed out')).toBeTruthy();
    expect(within(acme).getByText('60 free')).toBeTruthy();
    expect(within(acme).getByRole('img', { name: '40 of 100 seats handed out' })).toBeTruthy();
    expect(within(acme).getByText('Active')).toBeTruthy();
    expect(within(acme).getByText('2 customers')).toBeTruthy();
    expect(within(acme).getByText('2 screens')).toBeTruthy();
    expect(within(row('Zed Partners')).getByText('1 customer')).toBeTruthy();
  });

  it('pluralises: 0 customers, 1 screen, and a singular partners count', async () => {
    fetchPartners.mockResolvedValue([partner({ customerCount: 0, screenCeiling: ['view:assets'] })]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    expect(screen.getByText('1 partner')).toBeTruthy();
    const acme = row('Acme Resale');
    expect(within(acme).getByText('0 customers')).toBeTruthy();
    expect(within(acme).getByText('1 screen')).toBeTruthy();
  });

  it('handles partial data: No expiry, All screens, dashes for missing figures', async () => {
    fetchPartners.mockResolvedValue([
      partner({ unrestricted: true, screenCeiling: ['all'] }),
      partner({ id: 'p2', name: 'Broken Data', customerCount: undefined as any, allocated: undefined as any }),
    ]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    const acme = row('Acme Resale');
    expect(within(acme).getByText('No expiry')).toBeTruthy();
    expect(within(acme).getByText('All screens')).toBeTruthy();
    expect(within(row('Broken Data')).getAllByText('—').length).toBeGreaterThanOrEqual(2);
  });

  it('shows the expiry date and the Expired chip for a lapsed pool, and a warning within 30 days', async () => {
    fetchPartners.mockResolvedValue([
      partner({ id: 'p1', name: 'Lapsed', expiresAt: new Date(Date.now() - 3 * DAY).toISOString(), expired: true }),
      partner({ id: 'p2', name: 'Soon', expiresAt: new Date(Date.now() + 5 * DAY).toISOString() }),
    ]);
    render(<PartnersDashboard />);
    await screen.findByText('Lapsed');
    expect(within(row('Lapsed')).getByText('Expired')).toBeTruthy();
    expect(within(row('Soon')).getByText(/Expires in \d+ days?/)).toBeTruthy();
  });

  it('renders a long partner name in full, wrapping, never truncated', async () => {
    const long = 'Very Long Partner Name '.repeat(8).trim();
    fetchPartners.mockResolvedValue([partner({ name: long })]);
    const { container } = render(<PartnersDashboard />);
    const cell = await screen.findByText(long);
    expect(cell.className).toContain('break-words');
    expect(container.innerHTML).not.toMatch(/truncate|line-clamp/);
  });

  it('shows a Suspended chip and Reinstate partner for a suspended partner', async () => {
    fetchPartners.mockResolvedValue([partner({ status: 'suspended' })]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    const acme = row('Acme Resale');
    expect(within(acme).getByText('Suspended')).toBeTruthy();
    expect(within(acme).getByRole('button', { name: 'Reinstate Acme Resale' })).toBeTruthy();
    expect(within(acme).queryByRole('button', { name: 'Suspend Acme Resale' })).toBeNull();
  });

  it('offers Edit partner, Show customers and Suspend partner per row, named for the partner', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    const acme = row('Acme Resale');
    expect(within(acme).getByRole('button', { name: 'Edit Acme Resale' })).toBeTruthy();
    expect(within(acme).getByRole('button', { name: 'Suspend Acme Resale' })).toBeTruthy();
    expect(within(acme).getByRole('button', { name: /Show customers/ })).toBeTruthy();
  });
});

describe('PartnersDashboard search and paging', () => {
  const many = (n: number) => Array.from({ length: n }, (_, i) => partner({ id: `p${i}`, name: `Partner ${String(i).padStart(3, '0')}` }));

  it('shows no search with 10 partners or fewer', async () => {
    fetchPartners.mockResolvedValue(many(10));
    render(<PartnersDashboard />);
    await screen.findByText('Partner 000');
    expect(screen.queryByLabelText('Search partners')).toBeNull();
  });

  it('shows search above 10 partners, filters by name, and the empty-match line clears', async () => {
    fetchPartners.mockResolvedValue(many(11));
    render(<PartnersDashboard />);
    await screen.findByText('Partner 000');
    const search = screen.getByLabelText('Search partners');
    fireEvent.change(search, { target: { value: 'partner 007' } });
    expect(screen.getByText('Partner 007')).toBeTruthy();
    expect(screen.queryByText('Partner 000')).toBeNull();
    fireEvent.change(search, { target: { value: 'nothing here' } });
    expect(screen.getByText('No partners match "nothing here".')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(screen.getByText('Partner 000')).toBeTruthy();
  });

  it('pages at 25 from 50 partners with Show more partners', async () => {
    fetchPartners.mockResolvedValue(many(60));
    render(<PartnersDashboard />);
    await screen.findByText('Partner 000');
    expect(screen.getAllByRole('row').length).toBe(1 + 25);
    fireEvent.click(screen.getByRole('button', { name: 'Show more partners' }));
    expect(screen.getAllByRole('row').length).toBe(1 + 50);
  });

  it('shows everything below 50 partners with no Show more button', async () => {
    fetchPartners.mockResolvedValue(many(49));
    render(<PartnersDashboard />);
    await screen.findByText('Partner 000');
    expect(screen.getAllByRole('row').length).toBe(1 + 49);
    expect(screen.queryByRole('button', { name: 'Show more partners' })).toBeNull();
  });
});

describe('PartnersDashboard customers disclosure', () => {
  it('toggles aria-expanded, loads the customers once, and shows only the D-01 facts', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    fetchPartnerCustomers.mockResolvedValue([
      customer(),
      customer({ id: 'c2', name: 'Initech', seatsAssigned: 5, seatsUsed: 5, agentsOnline: 0, agentsTotal: 0, licenseExpiresAt: '2026-12-01T23:59:59Z' }),
    ]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    const toggle = within(row('Acme Resale')).getByRole('button', { name: /Show customers/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(await screen.findByText('Globex')).toBeTruthy();
    expect(fetchPartnerCustomers).toHaveBeenCalledWith('p1');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(toggle.textContent).toContain('Hide customers');
    const controls = toggle.getAttribute('aria-controls') as string;
    expect(document.getElementById(controls)).toBeTruthy();
    for (const header of ['Customer', 'Seats used', 'Seats assigned', 'Agents online', 'Licence expires']) {
      expect(screen.getByRole('columnheader', { name: header })).toBeTruthy();
    }
    const globex = screen.getByText('Globex').closest('tr') as HTMLElement;
    expect(within(globex).getByText('4 of 9')).toBeTruthy();
    expect(within(globex).getByText('No expiry')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Move Globex' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Add an existing organization' })).toBeTruthy();
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('Globex')).toBeNull();
    fireEvent.click(toggle);
    await screen.findByText('Globex');
    expect(fetchPartnerCustomers).toHaveBeenCalledTimes(1);
  });

  it('refetches a partner collapsed during a change instead of showing its old customers (87 WR-08)', async () => {
    fetchPartners.mockResolvedValue([partner(), partner({ id: 'p2', name: 'Beta Resale' })]);
    fetchPartnerCustomers.mockResolvedValue([customer({ name: 'Old Co' })]);
    (api.suspendPartner as ReturnType<typeof vi.fn>).mockResolvedValue(partner({ status: 'suspended' }));
    render(<PartnersDashboard />);
    await screen.findByText('Beta Resale');
    const beta = within(row('Beta Resale')).getByRole('button', { name: /Show customers/ });
    fireEvent.click(beta);
    await screen.findByText('Old Co');
    fireEvent.click(beta); // collapsed while a change elsewhere moves seats
    fetchPartnerCustomers.mockResolvedValue([customer({ name: 'New Co' })]);
    fireEvent.click(within(row('Acme Resale')).getByRole('button', { name: 'Suspend Acme Resale' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Suspend partner' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(within(row('Beta Resale')).getByRole('button', { name: /Show customers/ }));
    expect(await screen.findByText('New Co')).toBeTruthy();
    expect(screen.queryByText('Old Co')).toBeNull();
  });

  it('keeps the partners on screen when the quiet reload after a change fails (87 WR-11)', async () => {
    fetchPartners.mockResolvedValueOnce([partner()]).mockRejectedValueOnce(new Error('offline'));
    (api.suspendPartner as ReturnType<typeof vi.fn>).mockResolvedValue(partner({ status: 'suspended' }));
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(within(row('Acme Resale')).getByRole('button', { name: 'Suspend Acme Resale' }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Suspend partner' }));
    expect(await screen.findByText(/Couldn't load partners/)).toBeTruthy();
    expect(screen.getByText('Acme Resale')).toBeTruthy();
  });

  it('says This partner has no customers yet. for an empty partner', async () => {
    fetchPartners.mockResolvedValue([partner({ customerCount: 0 })]);
    fetchPartnerCustomers.mockResolvedValue([]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(within(row('Acme Resale')).getByRole('button', { name: /Show customers/ }));
    expect(await screen.findByText('This partner has no customers yet.')).toBeTruthy();
  });

  it('shows a retryable error inside the disclosure when the customers fail to load', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    fetchPartnerCustomers.mockRejectedValueOnce(new Error('nope'));
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(within(row('Acme Resale')).getByRole('button', { name: /Show customers/ }));
    expect(await screen.findByText(/Couldn't load the customers/)).toBeTruthy();
    fetchPartnerCustomers.mockResolvedValueOnce([customer()]);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByText('Globex')).toBeTruthy());
  });

  it('shows an Expired chip beside a lapsed customer licence', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    fetchPartnerCustomers.mockResolvedValue([customer({ licenseExpiresAt: new Date(Date.now() - 2 * DAY).toISOString() })]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(within(row('Acme Resale')).getByRole('button', { name: /Show customers/ }));
    const globex = (await screen.findByText('Globex')).closest('tr') as HTMLElement;
    expect(within(globex).getByText('Expired')).toBeTruthy();
  });
});

describe('PartnersDashboard opens its dialogs and refetches after a success', () => {
  it('opens the Appoint a partner form from the header button', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(screen.getByRole('button', { name: 'Appoint partner' }));
    expect(await screen.findByRole('heading', { name: 'Appoint a partner' })).toBeTruthy();
  });

  it('opens Edit for the row, and Suspend then refetches the table after confirming', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    (api.suspendPartner as ReturnType<typeof vi.fn>).mockResolvedValue(partner({ status: 'suspended' }));
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(screen.getByRole('button', { name: 'Edit Acme Resale' }));
    expect(await screen.findByRole('heading', { name: 'Edit Acme Resale' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Edit Acme Resale' })).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Suspend Acme Resale' }));
    expect(await screen.findByRole('heading', { name: 'Suspend Acme Resale?' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Suspend partner', hidden: false }));
    await waitFor(() => expect(fetchPartners).toHaveBeenCalledTimes(2));
  });

  it('opens Move customer from the disclosure and Add an existing organization for the partner', async () => {
    fetchPartners.mockResolvedValue([partner()]);
    fetchPartnerCustomers.mockResolvedValue([customer()]);
    (api.fetchDirectCustomers as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(<PartnersDashboard />);
    await screen.findByText('Acme Resale');
    fireEvent.click(within(row('Acme Resale')).getByRole('button', { name: /Show customers/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Move Globex' }));
    expect(await screen.findByRole('heading', { name: 'Move Globex' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Move Globex' })).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Add an existing organization' }));
    expect(await screen.findByRole('heading', { name: 'Add an organization to Acme Resale' })).toBeTruthy();
  });
});
