/**
 * Phase 87 (PART-02, PART-04, PART-05, PART-08; 87-UI-SPEC section 2): the Partner portal page. The API
 * client and the CSV download are mocked. These cases cover the pool summary, the customers table in every
 * state of the contract, the viewer variant, the expired and expiring banners and the CSV export.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../../services/partnerApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/partnerApi')>('../../services/partnerApi');
  return {
    ...actual,
    fetchPartnerOverview: vi.fn(),
    fetchPartnerTeam: vi.fn(),
    createPartnerCustomer: vi.fn(),
    changeCustomerSeats: vi.fn(),
    fetchCustomerFeatures: vi.fn(),
    saveCustomerFeatures: vi.fn(),
    inviteColleague: vi.fn(),
    resendColleagueInvite: vi.fn(),
  };
});
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));
vi.mock('../../utils/csvExport', async () => {
  const actual = await vi.importActual<typeof import('../../utils/csvExport')>('../../utils/csvExport');
  return { ...actual, downloadCsv: vi.fn() };
});

import * as api from '../../services/partnerApi';
import type { PartnerCustomerRow, PartnerOverview } from '../../services/partnerApi';
import { showToast } from '../../utils/toast';
import { downloadCsv } from '../../utils/csvExport';
import { PartnerPortal } from '../../components/PartnerPortal';

const fetchPartnerOverview = api.fetchPartnerOverview as ReturnType<typeof vi.fn>;
const fetchPartnerTeam = api.fetchPartnerTeam as ReturnType<typeof vi.fn>;
const download = downloadCsv as ReturnType<typeof vi.fn>;
const toast = showToast as ReturnType<typeof vi.fn>;

const DAY = 24 * 60 * 60 * 1000;
const daysFromNow = (n: number) => new Date(Date.now() + n * DAY).toISOString();

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

const overview = (over: Partial<PartnerOverview> = {}, pool: Partial<PartnerOverview['pool']> = {}): PartnerOverview => ({
  partner: { name: 'Acme Retail' },
  role: 'admin',
  pool: { size: 100, handedOut: 40, free: 60, expiresAt: null, expired: false, ...pool },
  ceiling: ['view:assets'],
  unrestricted: false,
  customers: [customer()],
  ...over,
});

/** The Team panel (admin only) has its own table; the customers assertions look only inside the Customers section. */
const customersSection = () => screen.getByRole('heading', { name: 'Customers' }).closest('section') as HTMLElement;

const renderLoaded = async (data: PartnerOverview) => {
  fetchPartnerOverview.mockResolvedValue(data);
  fetchPartnerTeam.mockResolvedValue([]);
  const view = render(<PartnerPortal />);
  await screen.findByText('Seat pool');
  await waitFor(() => expect(document.querySelector('[data-skeleton]')).toBeNull());
  return view;
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchPartnerTeam.mockResolvedValue([]);
});
afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

describe('PartnerPortal header and loading (S4, S5)', () => {
  it('renders the title and both buttons disabled while the first load is in flight, with skeleton tiles and rows', () => {
    fetchPartnerOverview.mockReturnValue(new Promise(() => {}));
    const { container } = render(<PartnerPortal />);
    expect(screen.getByRole('heading', { level: 1, name: 'Partner portal' })).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Export CSV' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Create customer' }) as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelectorAll('.h-8.w-16').length).toBe(4);
    expect(container.querySelectorAll('tbody tr[data-skeleton]').length).toBe(4);
    expect(container.querySelectorAll('[aria-busy="true"]').length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector('[role="img"]')).toBeNull();
  });

  it('shows the portal error block with Try again and hides the summary and table, then recovers', async () => {
    fetchPartnerOverview.mockRejectedValueOnce(new Error('boom'));
    render(<PartnerPortal />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain("Couldn't load your customers. Check your connection and try again.");
    expect(screen.queryByText('Seat pool')).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Partner portal' })).toBeTruthy();
    fetchPartnerOverview.mockResolvedValue(overview());
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByText('Seat pool');
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('PartnerPortal seat pool summary (S4)', () => {
  it('shows the four tiles and a bar whose fill is handed out over size', async () => {
    const { container } = await renderLoaded(overview());
    expect(screen.getByText('Acme Retail')).toBeTruthy();
    expect(screen.getByText('Pool size').nextSibling?.textContent).toBe('100');
    expect(screen.getByText('Handed out').nextSibling?.textContent).toBe('40');
    expect(screen.getByText('40% of the pool')).toBeTruthy();
    expect(screen.getByText('Free').nextSibling?.textContent).toBe('60');
    expect(screen.getByText('Available to hand out')).toBeTruthy();
    expect(screen.getByText('Pool expires')).toBeTruthy();
    expect(screen.getAllByText('No expiry').length).toBe(2);
    expect(screen.getByText('Never')).toBeTruthy();
    const bar = container.querySelector('section[aria-labelledby] [role="img"]') as HTMLElement;
    expect(bar.getAttribute('aria-label')).toBe('40 of 100 seats handed out');
    expect((bar.firstElementChild as HTMLElement).style.width).toBe('40%');
  });

  it('renders a pool of 0 with an empty bar, and a seven-digit pool in a tabular-nums tile', async () => {
    const { container } = await renderLoaded(overview({ customers: [] }, { size: 0, handedOut: 0, free: 0 }));
    const bar = container.querySelector('section[aria-labelledby] [role="img"]') as HTMLElement;
    expect((bar.firstElementChild as HTMLElement).style.width).toBe('0%');
    expect(screen.getByText('Free').nextSibling?.textContent).toBe('0');
    cleanup();
    await renderLoaded(overview({}, { size: 1000000, handedOut: 1, free: 999999 }));
    const tile = screen.getByText('Pool size').nextSibling as HTMLElement;
    expect(tile.textContent).toBe('1,000,000');
    expect(tile.className).toContain('tabular-nums');
    expect(tile.className).toContain('text-3xl');
  });

  it('reads 1 day left at one day and 12 days left otherwise, with the info banner within 30 days', async () => {
    await renderLoaded(overview({}, { expiresAt: new Date(Date.now() + 0.5 * DAY).toISOString() }));
    expect(screen.getByText('1 day left')).toBeTruthy();
    expect(screen.getByText(/^Your seat pool expires on /)).toBeTruthy();
    cleanup();
    await renderLoaded(overview({}, { expiresAt: daysFromNow(11.5) }));
    expect(screen.getByText('12 days left')).toBeTruthy();
  });

  it('shows no banner for a distant expiry', async () => {
    await renderLoaded(overview({}, { expiresAt: daysFromNow(200) }));
    expect(screen.queryByText(/^Your seat pool expires on /)).toBeNull();
    expect(screen.queryByText(/days left/)).toBeTruthy();
  });

  it('with an expired pool shows the amber banner, Expired, and disables Create customer with aria-describedby', async () => {
    const expiresAt = '2026-01-05T23:59:59Z';
    await renderLoaded(overview({}, { expiresAt, expired: true, free: 0 }));
    const banner = screen.getByText(/^Your seat pool expired on/).closest('[role="status"]') as HTMLElement;
    expect(banner.textContent).toContain('Your seat pool expired on Jan 5, 2026.');
    expect(banner.textContent).toContain("You can't create customers or hand out seats until the platform administrator renews it. Your customers keep working with the seats they have.");
    expect(screen.getAllByText('Expired').length).toBeGreaterThan(0);
    expect(screen.getByText("Can't be handed out after expiry")).toBeTruthy();
    const create = screen.getAllByRole('button', { name: 'Create customer' })[0] as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    expect(create.getAttribute('aria-describedby')).toBe(banner.id);
  });

  it('with no free seats explains the disabled Create customer in words', async () => {
    await renderLoaded(overview({}, { free: 0, handedOut: 100 }));
    const create = screen.getAllByRole('button', { name: 'Create customer' })[0] as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    const reason = document.getElementById(create.getAttribute('aria-describedby') as string) as HTMLElement;
    expect(reason.textContent).toBe('You have no free seats. Ask the platform administrator for a larger pool.');
  });
});

describe('PartnerPortal customers table (S5)', () => {
  it('shows name, seats used with a mini bar, seats assigned, agents and licence expiry, name as plain text', async () => {
    const { container } = await renderLoaded(overview({
      customers: [customer({ name: 'Initech', seatsUsed: 5, seatsAssigned: 20, agentsOnline: 0, agentsTotal: 0, licenseExpiresAt: '2027-03-31T23:59:59Z' })],
    }));
    const row = screen.getByText('Initech').closest('tr') as HTMLElement;
    const cells = within(row).getAllByRole('cell');
    expect(cells[1].textContent).toBe('5');
    expect((cells[1].querySelector('[role="img"]')?.firstElementChild as HTMLElement).style.width).toBe('25%');
    expect(cells[2].textContent).toBe('20');
    expect(cells[3].textContent).toBe('0 online of 0');
    expect(cells[4].textContent).toContain('Mar 31, 2027');
    expect(container.querySelectorAll('a, [href]').length).toBe(0);
    expect(screen.getByText('Initech').closest('a')).toBeNull();
  });

  it('shows No expiry for a customer without one and Expired beside a past date', async () => {
    await renderLoaded(overview({
      customers: [customer({ id: 'a', name: 'Alpha' }), customer({ id: 'b', name: 'Beta', licenseExpiresAt: '2025-01-01T00:00:00Z' })],
    }));
    const alpha = screen.getByText('Alpha').closest('tr') as HTMLElement;
    expect(within(alpha).getByText('No expiry')).toBeTruthy();
    const beta = screen.getByText('Beta').closest('tr') as HTMLElement;
    expect(within(beta).getByText('Expired')).toBeTruthy();
  });

  it('shows used above assigned for an over-seated customer without inventing a warning', async () => {
    await renderLoaded(overview({ customers: [customer({ name: 'Crowded', seatsUsed: 12, seatsAssigned: 10 })] }));
    const row = screen.getByText('Crowded').closest('tr') as HTMLElement;
    const cells = within(row).getAllByRole('cell');
    expect(cells[1].textContent).toBe('12');
    expect(cells[2].textContent).toBe('10');
    expect((cells[1].querySelector('[role="img"]')?.firstElementChild as HTMLElement).style.width).toBe('100%');
    expect(within(row).queryByText(/over|exceed|warning|too many/i)).toBeNull();
  });

  it('orders customers by name, wraps long names and counts 1 customer / n customers', async () => {
    const long = 'Z'.repeat(100);
    await renderLoaded(overview({ customers: [customer({ id: 'z', name: long }), customer({ id: 'b', name: 'Beta' }), customer({ id: 'a', name: 'Alpha' })] }));
    const names = within(customersSection()).getAllByRole('row').slice(1).map(r => within(r).getAllByRole('cell')[0].textContent);
    expect(names).toEqual(['Alpha', 'Beta', long]);
    expect(screen.getByText(long).className).toContain('break-words');
    expect(screen.getByText('3 customers')).toBeTruthy();
    cleanup();
    await renderLoaded(overview());
    expect(screen.getByText('1 customer')).toBeTruthy();
  });

  it('renders the column headers and an Actions column for the admin only', async () => {
    await renderLoaded(overview());
    for (const h of ['Customer', 'Seats used', 'Seats assigned', 'Agents', 'Licence expires', 'Actions']) {
      expect(within(customersSection()).getByRole('columnheader', { name: h })).toBeTruthy();
    }
    expect(screen.getByRole('button', { name: 'Change seats for Globex' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Choose screens for Globex' })).toBeTruthy();
  });

  it('pages at 25 rows with Show more customers, and searches above 10 customers', async () => {
    const many = Array.from({ length: 30 }, (_, i) => customer({ id: `c${i}`, name: `Cust ${String(i).padStart(2, '0')}` }));
    await renderLoaded(overview({ customers: many }));
    expect(within(customersSection()).getAllByRole('row').length).toBe(26);
    fireEvent.click(screen.getByRole('button', { name: 'Show more customers' }));
    expect(within(customersSection()).getAllByRole('row').length).toBe(31);
    expect(screen.queryByRole('button', { name: 'Show more customers' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Search customers'), { target: { value: 'cust 07' } });
    expect(within(customersSection()).getAllByRole('row').length).toBe(2);
    fireEvent.change(screen.getByLabelText('Search customers'), { target: { value: 'nomatch' } });
    expect(screen.getByText('No customers match "nomatch".')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect((screen.getByLabelText('Search customers') as HTMLInputElement).value).toBe('');
  });

  it('has no search for 10 customers or fewer', async () => {
    await renderLoaded(overview());
    expect(screen.queryByLabelText('Search customers')).toBeNull();
  });

  it('shows the admin empty state with the action and the free-seat count', async () => {
    await renderLoaded(overview({ customers: [] }));
    expect(screen.getByRole('heading', { name: 'No customers yet' })).toBeTruthy();
    expect(screen.getByText('Create your first customer, give it some of your 60 free seats and invite its administrator.')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Create customer' }).length).toBe(2);
  });

  it('refreshes quietly (no skeleton) with Refresh customers', async () => {
    await renderLoaded(overview());
    fetchPartnerOverview.mockClear();
    fireEvent.click(screen.getByRole('button', { name: /Refresh customers/ }));
    expect(customersSection().querySelectorAll('tr[data-skeleton]').length).toBe(0);
    await waitFor(() => expect(fetchPartnerOverview).toHaveBeenCalledTimes(1));
    expect(screen.getByText('Globex')).toBeTruthy();
  });
});

describe('PartnerPortal viewer variant (PART-05, D-04)', () => {
  const viewer = () => overview({ role: 'viewer' });

  it('removes Create customer, row actions, the Team section and Invite colleague, keeps Export CSV and shows the read-only line', async () => {
    await renderLoaded(viewer());
    expect(screen.getByText('You have read-only access. Ask a partner administrator to make changes.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Create customer/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Change seats/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Choose screens/ })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'Actions' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Team' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Invite colleague/ })).toBeNull();
    expect(fetchPartnerTeam).not.toHaveBeenCalled();
  });

  it('shows the viewer empty state without an action', async () => {
    await renderLoaded(overview({ role: 'viewer', customers: [] }));
    expect(screen.getByText('Your customers appear here once a partner administrator creates them.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Create customer/ })).toBeNull();
  });
});

describe('PartnerPortal CSV export (PART-08, D-16)', () => {
  it('exports every customer in name order with the six columns, not only the filtered ones', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-02T12:00:00Z'));
    const rows = [
      customer({ id: 'b', name: 'Beta', seatsAssigned: 10, seatsUsed: 3, agentsOnline: 1, agentsTotal: 2, licenseExpiresAt: '2027-03-31T23:59:59Z' }),
      customer({ id: 'a', name: 'Alpha', seatsAssigned: 5, seatsUsed: 5, agentsOnline: 0, agentsTotal: 0, licenseExpiresAt: null }),
    ];
    await renderLoaded(overview({ customers: rows }));
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
    const [filename, csv] = download.mock.calls[0];
    expect(filename).toBe('partner-usage-acme-retail-2026-11-02.csv');
    expect(csv.split('\r\n')).toEqual([
      'Customer,Seats assigned,Seats used,Agents online,Agents total,Licence expires',
      'Alpha,5,5,0,0,',
      'Beta,10,3,1,2,2027-03-31',
    ]);
  });

  it('ignores the on-screen filter', async () => {
    const many = Array.from({ length: 12 }, (_, i) => customer({ id: `c${i}`, name: `Cust ${String(i).padStart(2, '0')}` }));
    await renderLoaded(overview({ customers: many }));
    fireEvent.change(screen.getByLabelText('Search customers'), { target: { value: 'cust 03' } });
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
    expect(download.mock.calls[0][1].split('\r\n').length).toBe(13);
  });

  it('guards a name that starts with = against spreadsheet formulas and quotes commas', async () => {
    await renderLoaded(overview({ customers: [customer({ name: '=HYPERLINK("x")' }), customer({ id: 'd', name: 'Doe, Inc' })] }));
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    const lines = download.mock.calls[0][1].split('\r\n');
    expect(lines.some((l: string) => l.startsWith(`"'=HYPERLINK(""x"")"`))).toBe(true);
    expect(lines.some((l: string) => l.startsWith('"Doe, Inc"'))).toBe(true);
  });

  it('downloads a header-only file for an empty customer list', async () => {
    await renderLoaded(overview({ customers: [] }));
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    expect(download.mock.calls[0][1]).toBe('Customer,Seats assigned,Seats used,Agents online,Agents total,Licence expires');
  });

  it('reads Exporting... and is disabled until the file is handed over, then recovers', async () => {
    let release: () => void = () => {};
    download.mockImplementationOnce(() => new Promise<void>(resolve => { release = resolve; }));
    await renderLoaded(overview());
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    const busy = await screen.findByRole('button', { name: 'Exporting...' });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { release(); });
    expect((await screen.findByRole('button', { name: 'Export CSV' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('toasts a red failure and recovers when the download throws', async () => {
    download.mockImplementationOnce(() => { throw new Error('blocked'); });
    await renderLoaded(overview());
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith("Couldn't export usage. Try again.", 'error'));
    expect((screen.getByRole('button', { name: 'Export CSV' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('falls back to a plain slug for a name with no letters or digits', async () => {
    await renderLoaded(overview({ partner: { name: '!!!' } }));
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    expect(download.mock.calls[0][0]).toMatch(/^partner-usage-partner-\d{4}-\d{2}-\d{2}\.csv$/);
  });
});

describe('PartnerPortal shows only the D-01 facts (PART-05, T-87-38)', () => {
  it('renders none of the forbidden words or any extra server field in the populated DOM', async () => {
    const leaky = { ...customer({ name: 'Globex' }), registrationKey: 'KEY-SECRET', alertCount: 77, assetCount: 88, findings: 99, users: ['u@x.io'], inviteLink: 'https://x/accept?token=TOK' };
    const { container } = await renderLoaded(overview({ customers: [leaky as unknown as PartnerCustomerRow] }));
    const text = container.textContent ?? '';
    expect(text).not.toMatch(/registrationKey|alert|asset|finding/i);
    expect(text).not.toContain('KEY-SECRET');
    expect(text).not.toContain('TOK');
    expect(text).not.toContain('77');
    expect(text).not.toContain('u@x.io');
    expect(container.innerHTML).not.toContain('KEY-SECRET');
    expect(container.querySelectorAll('[title]').length).toBeLessThanOrEqual(container.querySelectorAll('time[title]').length);
  });
});

describe('PartnerPortal dialogs follow the refreshed rows (87 WR-10)', () => {
  it('the seats dialog validates against the row a refusal refetched, not the one it opened with', async () => {
    await renderLoaded(overview({ customers: [customer({ name: 'Globex', seatsUsed: 10, seatsAssigned: 25 })] }));
    fireEvent.click(screen.getByRole('button', { name: 'Change seats for Globex' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('10 seats in use')).toBeTruthy();
    fetchPartnerOverview.mockResolvedValue(overview({ customers: [customer({ name: 'Globex', seatsUsed: 18, seatsAssigned: 25 })] }));
    (api.changeCustomerSeats as ReturnType<typeof vi.fn>).mockRejectedValue(
      new api.PartnerApiError("Globex uses 18 seats now. You can't set fewer.", 409, 'below_used'));
    fireEvent.change(within(dialog).getByLabelText('Seats'), { target: { value: '15' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save seats' }));
    expect(await within(dialog).findByText('18 seats in use')).toBeTruthy();
  });
});
