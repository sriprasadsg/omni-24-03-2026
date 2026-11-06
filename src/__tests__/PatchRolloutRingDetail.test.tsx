/**
 * Phase 84 / PTCH-02, PTCH-03 (84-18): the ring detail disclosure under a rollout card. The component renders the
 * payload of the 84-09 views (health rows, failure-rate and soak lines, hosts) as React text; the Rollouts tab wires it
 * behind Show details.
 *
 * Value: protects=the operator can see which signal held or halted a ring and on which computer, and the missing,
 * waiting and not-checked cases never read as a pass; fails_when=a row without data reads Passed, Not checked reads
 * Passed, an empty watched list reads No data, the table orders problems below healthy computers, more than 25 rows
 * show at once, a name or a result is cut off, server text is rendered as markup, or two rings are open at once;
 * no_claim=the sentences themselves (backend/tests/test_patch_rollout_views.py) and layout at a real width
 * (checked by a person once the UI is published).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { RingDetail } from '../../components/patchRollouts/RingDetail';
import { RolloutsTab } from '../../components/patchRollouts/RolloutsTab';
import { UserContext } from '../../contexts/UserContext';
import type { HealthRow, HostRow, RingView } from '../../services/patchRollouts/types';
import { card, host, jsonRes, ring, rolloutPage } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
beforeEach(() => { mockFetch.mockReset(); });

const health = (): HealthRow[] => [
  { signal: 'install', state: 'passed', text: '3 of 3 computers installed without an error.' },
  { signal: 'inventory', state: 'passed', text: '3 of 3 computers no longer list these patches.' },
  { signal: 'heartbeat', state: 'passed', text: '3 of 3 computers sent a heartbeat after restarting.' },
  { signal: 'services', state: 'passed', text: 'Omni Agent and SQL Server are running on 3 of 3 computers.' },
];
const withHealth = (over: Partial<Record<HealthRow['signal'], Partial<HealthRow>>>): HealthRow[] =>
  health().map(row => ({ ...row, ...(over[row.signal] ?? {}) }));

const show = (over: Partial<RingView> = {}) => render(<RingDetail ring={ring({ health: health(), ...over })} />);
const row = (title: string) => {
  const term = screen.getByText(title, { selector: 'dt' });
  return term.parentElement as HTMLElement;
};
const tableNames = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)
  .map(r => within(r).getAllByRole('cell')[0].querySelector('p')?.textContent ?? '');
const hosts = (n: number): HostRow[] => Array.from({ length: n }, (_, i) => host({
  agentId: `a${i}`, hostname: `host-${String(i).padStart(2, '0')}`,
}));

describe('RingDetail health rows', () => {
  it('shows the four health rows in order, each with a chip and the server text', () => {
    show();
    const titles = screen.getAllByRole('term').map(t => t.textContent);
    expect(titles).toEqual(['Install result', 'Inventory after install', 'Heartbeat after restart', 'Services']);
    expect(within(row('Install result')).getByText('Passed')).toBeInTheDocument();
    expect(within(row('Install result')).getByText('3 of 3 computers installed without an error.')).toBeInTheDocument();
    expect(within(row('Services')).getByText('Omni Agent and SQL Server are running on 3 of 3 computers.')).toBeInTheDocument();
  });

  it('keeps the fixed order and the four titles when the server sends the rows in another order', () => {
    show({ health: [...health()].reverse() });
    expect(screen.getAllByRole('term').map(t => t.textContent))
      .toEqual(['Install result', 'Inventory after install', 'Heartbeat after restart', 'Services']);
  });

  it('an empty watched-services list reads Only the agent service is checked and is not No data', () => {
    show({ health: withHealth({ services: { state: 'agent_only', text: 'Only the agent service is checked.' } }) });
    const services = row('Services');
    expect(within(services).getByText('Only the agent service is checked.')).toBeInTheDocument();
    expect(within(services).getByText('Passed')).toBeInTheDocument();
    expect(within(services).queryByText('No data')).toBeNull();
  });

  it('before a ring starts every signal is an amber Waiting chip that says what it waits for', () => {
    show({ health: [] });
    for (const title of ['Install result', 'Inventory after install', 'Heartbeat after restart', 'Services']) {
      expect(within(row(title)).getByText('Waiting')).toBeInTheDocument();
    }
    expect(within(row('Install result')).getByText('Waiting for the install result.')).toBeInTheDocument();
    expect(within(row('Heartbeat after restart')).getByText('Waiting for the heartbeat after the restart.')).toBeInTheDocument();
    expect(screen.queryByText('Passed')).toBeNull();
  });

  it('a signal that is not in yet shows Waiting with the server text', () => {
    show({ health: withHealth({ heartbeat: { state: 'waiting', text: 'Waiting for the heartbeat after the restart.' } }) });
    expect(within(row('Heartbeat after restart')).getByText('Waiting')).toBeInTheDocument();
    expect(within(row('Heartbeat after restart')).getByText('Waiting for the heartbeat after the restart.')).toBeInTheDocument();
  });

  it('a missing signal shows the red No data chip and the sentence that says the ring halts', () => {
    const text = 'No data for the heartbeat after the restart counts as a failure, so the ring halts.';
    show({ health: withHealth({ heartbeat: { state: 'no_data', text } }) });
    expect(within(row('Heartbeat after restart')).getByText('No data')).toBeInTheDocument();
    expect(within(row('Heartbeat after restart')).getByText(text)).toBeInTheDocument();
    expect(within(row('Heartbeat after restart')).queryByText('Passed')).toBeNull();
  });

  it('a No data row with no server text still says the ring halts', () => {
    show({ health: withHealth({ heartbeat: { state: 'no_data', text: '' } }) });
    expect(within(row('Heartbeat after restart')).getByText(
      'No data for the heartbeat after the restart counts as a failure, so the ring halts.')).toBeInTheDocument();
  });

  it('a failed signal shows the red Failed chip', () => {
    show({ health: withHealth({ install: { state: 'failed', text: '2 of 3 computers installed without an error.' } }) });
    expect(within(row('Install result')).getByText('Failed')).toBeInTheDocument();
    expect(within(row('Install result')).getByText('2 of 3 computers installed without an error.')).toBeInTheDocument();
  });

  it('DEV-2: Not checked shows the outline chip with the server text and is never shown as Passed', () => {
    const text = "Omni Agent and SQL Server can't be checked on 2 of 3 computers until their agent is updated.";
    show({ health: withHealth({ services: { state: 'not_checked', text } }) });
    const services = row('Services');
    expect(within(services).getByText('Not checked')).toBeInTheDocument();
    expect(within(services).getByText(text)).toBeInTheDocument();
    expect(within(services).queryByText('Passed')).toBeNull();
  });

  it('keeps the singular form the server wrote at one computer', () => {
    show({ health: withHealth({ install: { state: 'passed', text: '1 of 1 computer installed without an error.' } }) });
    expect(screen.getByText('1 of 1 computer installed without an error.')).toBeInTheDocument();
  });

  it('shows the failure-rate and soak lines from the payload', () => {
    show({
      failureRateText: '1 of 9 computers failed (11%). The ring halts above 20% once 5 computers have reported. Below 5 computers, any failure halts.',
      soakText: 'Soaks 24 hours after the last install or restart.',
    });
    expect(screen.getByText(/1 of 9 computers failed \(11%\)/)).toBeInTheDocument();
    expect(screen.getByText('Soaks 24 hours after the last install or restart.')).toBeInTheDocument();
  });

  it('shows the canary and below-minimum failure lines as the server wrote them', () => {
    const { unmount } = show({ failureRateText: 'Any failure halts the rollout.' });
    expect(screen.getByText('Any failure halts the rollout.')).toBeInTheDocument();
    unmount();
    show({ failureRateText: '0 of 3 computers failed. Fewer than 5 computers have reported, so any failure halts.' });
    expect(screen.getByText(/Fewer than 5 computers have reported, so any failure halts\./)).toBeInTheDocument();
  });
});

describe('RingDetail computers', () => {
  it('shows the four columns with their minimum widths (800px in all)', () => {
    show({ hosts: [host()], hostTotal: 1 });
    const heads = within(screen.getByRole('table')).getAllByRole('columnheader');
    expect(heads.map(h => h.textContent)).toEqual(['Computer', 'State', 'Result', 'Changed']);
    expect(heads[0].className).toContain('min-w-[200px]');
    expect(heads[1].className).toContain('min-w-[150px]');
    expect(heads[2].className).toContain('min-w-[300px]');
    expect(heads[3].className).toContain('min-w-[150px]');
  });

  it('the table scrolls inside its own region at lg and wider, and stacked cards take over below lg', () => {
    const { container } = show({ hosts: [host()], hostTotal: 1 });
    const table = screen.getByRole('table');
    expect(table.closest('div')?.className).toContain('overflow-x-auto');
    expect(table.closest('div')?.className).toContain('hidden');
    expect(table.closest('div')?.className).toContain('lg:block');
    const cards = container.querySelector('ul.lg\\:hidden');
    expect(cards).not.toBeNull();
    const terms = within(cards as HTMLElement).getAllByRole('term').map(t => t.textContent);
    expect(terms).toEqual(['Computer', 'State', 'Result', 'Changed']);
  });

  it('orders problems first, then Waiting, then the rest by name', () => {
    show({
      hosts: [
        host({ agentId: '1', hostname: 'b-healthy', state: 'healthy' }),
        host({ agentId: '2', hostname: 'z-waiting', state: 'waiting', result: 'Waiting for the next window.' }),
        host({ agentId: '3', hostname: 'y-failed', state: 'failed', result: 'KB1 failed to install: disk full.' }),
        host({ agentId: '4', hostname: 'a-healthy', state: 'healthy' }),
        host({ agentId: '5', hostname: 'c-stuck', state: 'not_reverted', result: 'Not reverted: this computer\'s agent doesn\'t support it yet. The patch is still installed.' }),
        host({ agentId: '6', hostname: 'd-installed', state: 'installed' }),
      ],
      hostTotal: 6,
    });
    expect(tableNames()).toEqual(['c-stuck', 'y-failed', 'z-waiting', 'a-healthy', 'b-healthy', 'd-installed']);
  });

  it('shows the state chip and the server Result for every state, never claiming a revert that did not happen', () => {
    show({
      hosts: [
        host({ agentId: '1', hostname: 'h1', state: 'failed', result: 'No heartbeat from this computer within 30 minutes of the restart, so the ring halts.' }),
        host({ agentId: '2', hostname: 'h2', state: 'not_reverted', result: "Not reverted: Windows doesn't allow this update to be uninstalled. The patch is still installed." }),
        host({ agentId: '3', hostname: 'h3', state: 'not_reached', result: 'Offline for the whole ring, so nothing was installed. It gets the patches in a later window if it comes back online.' }),
        host({ agentId: '4', hostname: 'h4', state: 'left_out', result: 'In "October patches" at the time this rollout started.' }),
        host({ agentId: '5', hostname: 'h5', state: 'reverted', result: 'Reverted 2 patches at 14:30.' }),
      ],
      hostTotal: 5,
    });
    const table = within(screen.getByRole('table'));
    expect(table.getByText('No heartbeat from this computer within 30 minutes of the restart, so the ring halts.')).toBeInTheDocument();
    expect(table.getByText("Not reverted: Windows doesn't allow this update to be uninstalled. The patch is still installed.")).toBeInTheDocument();
    expect(table.getByText(/Offline for the whole ring/)).toBeInTheDocument();
    expect(table.getByText('In "October patches" at the time this rollout started.')).toBeInTheDocument();
    for (const label of ['Failed', 'Not reverted', 'Not reached', 'Left out', 'Reverted']) {
      expect(table.getByText(label)).toBeInTheDocument();
    }
  });

  it('before a ring starts every computer shows Waiting', () => {
    show({
      state: 'not_started', health: [],
      hosts: [host({ agentId: '1', hostname: 'w1', state: 'waiting', result: 'Waiting for the next window.', changedAt: null }),
        host({ agentId: '2', hostname: 'w2', state: 'waiting', result: 'Waiting for the next window.', changedAt: null })],
      hostTotal: 2,
    });
    expect(within(screen.getByRole('table')).getAllByText('Waiting')).toHaveLength(2);
  });

  it('shows the operating system under the name and a dash for a computer that has not changed', () => {
    show({ hosts: [host({ hostname: 'web-01', os: 'Ubuntu 22.04', changedAt: null })], hostTotal: 1 });
    const cell = within(screen.getByRole('table')).getAllByRole('cell')[0];
    expect(within(cell).getByText('web-01')).toBeInTheDocument();
    expect(within(cell).getByText('Ubuntu 22.04')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).getAllByRole('cell')[3].textContent).toBe('—');
  });

  it('pages at 25 rows, then Show more computers adds the rest', () => {
    show({ hosts: hosts(30), hostTotal: 30 });
    expect(tableNames()).toHaveLength(25);
    fireEvent.click(screen.getByRole('button', { name: 'Show more computers' }));
    expect(tableNames()).toHaveLength(30);
    expect(screen.queryByRole('button', { name: 'Show more computers' })).toBeNull();
  });

  it('shows no Show more computers control at 25 or fewer', () => {
    show({ hosts: hosts(25), hostTotal: 25 });
    expect(screen.queryByRole('button', { name: 'Show more computers' })).toBeNull();
  });

  it('says how many of the ring\'s computers are listed when the server sent only the first page', () => {
    show({ hosts: hosts(3), hostTotal: 120 });
    expect(screen.getByText('Showing 3 of 120 computers.')).toBeInTheDocument();
  });

  it('a ring with no computers says so instead of showing an empty table', () => {
    show({ hosts: [], hostTotal: 0 });
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.getByText('No computers are in this ring.')).toBeInTheDocument();
  });

  it('wraps long names, results and patch ids instead of cutting them off', () => {
    const long = 'a-very-long-computer-name-'.repeat(8);
    const result = 'KB5039999999999999999999999999999999 failed to install: '.repeat(4);
    show({ hosts: [host({ hostname: long, state: 'failed', result })], hostTotal: 1 });
    const table = within(screen.getByRole('table'));
    expect(table.getByText(long).className).toContain('break-words');
    expect(table.getByText(result.trim()).className).toContain('break-words');
    expect(table.getByText(long).className).not.toContain('truncate');
    expect(table.getByText(result.trim()).className).not.toContain('truncate');
  });

  it('renders server text as text, never as markup', () => {
    const { container } = show({
      hosts: [host({ hostname: '<img src=x onerror=alert(1)>', result: '<b>done</b>' })], hostTotal: 1,
      failureRateText: '<script>alert(1)</script>',
      health: withHealth({ install: { state: 'passed', text: '<i>3 of 3</i>' } }),
    });
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('i')).toBeNull();
    expect(screen.getAllByText('<img src=x onerror=alert(1)>').length).toBeGreaterThan(0);
  });
});

describe('RingDetail on the Rollouts tab', () => {
  const ctx = { currentUser: { role: 'Admin' }, hasPermission: () => true } as any;
  const serve = (...cards: ReturnType<typeof card>[]) => mockFetch.mockImplementation((url: string) => Promise.resolve(
    url.startsWith('/api/patch-rollouts')
      ? jsonRes(rolloutPage(cards))
      : jsonRes({})));
  const open = () => render(<UserContext.Provider value={ctx}><RolloutsTab /></UserContext.Provider>);

  it('opens the detail of one ring behind Show details and shows that ring\'s evidence', async () => {
    serve(card({
      rings: [
        ring({ index: 0, name: 'Canary', health: health() }),
        ring({ index: 1, name: 'Early', state: 'checking_health', health: withHealth({ heartbeat: { state: 'waiting', text: 'Waiting for the heartbeat after the restart.' } }) }),
      ],
    }));
    open();
    const buttons = await screen.findAllByRole('button', { name: /Show details/ });
    expect(buttons[0]).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(buttons[1]);
    await waitFor(() => expect(screen.getByText('Install result', { selector: 'dt' })).toBeInTheDocument());
    expect(screen.getByText('Waiting for the heartbeat after the restart.', { selector: 'dd *, dd' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hide details/ })).toHaveAttribute('aria-expanded', 'true');
  });

  it('opening a second ring closes the first, so one ring\'s detail is open at a time', async () => {
    serve(card({
      rings: [
        ring({ index: 0, name: 'Canary', health: health(), failureRateText: 'Canary line.' }),
        ring({ index: 1, name: 'Early', health: health(), failureRateText: 'Early line.' }),
      ],
    }));
    open();
    const buttons = await screen.findAllByRole('button', { name: /Show details/ });
    fireEvent.click(buttons[0]);
    expect(screen.getByText('Canary line.')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Show details/ })[0]);
    expect(screen.getByText('Early line.')).toBeInTheDocument();
    expect(screen.queryByText('Canary line.')).toBeNull();
    expect(screen.getAllByRole('term').filter(t => t.textContent === 'Install result')).toHaveLength(1);
  });
});
