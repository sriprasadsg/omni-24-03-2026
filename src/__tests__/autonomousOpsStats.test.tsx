/**
 * Phase 86 / ACTV-05, ACTV-07, D-05..D-08: the collapsed Statistics card on the Autonomous Ops screen.
 * The service is mocked; payloads follow the 86-01 contract.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';

vi.mock('../../services/autonomousOpsReporting', () => ({
  fetchAutonomousOpsStatistics: vi.fn(),
}));

import { fetchAutonomousOpsStatistics } from '../../services/autonomousOpsReporting';
import { StatsCard } from '../../components/autonomousOpsStats/StatsCard';
import { formatMinutes } from '../../components/autonomousOpsStats/reportingCopy';

const fetchStats = fetchAutonomousOpsStatistics as unknown as ReturnType<typeof vi.fn>;

const ZERO = { fired: 0, done: 0, approved: 0, denied: 0, undone: 0, failed: 0, refused: 0, wouldHaveDone: 0 };

function payload(totals: Partial<typeof ZERO>, minutes = 0, shadowOnly = false) {
  return {
    tenantId: 't1', days: 30, generatedAt: '2026-11-11T14:02:00Z', shadowOnly, canExport: true, rules: [],
    totals: { ...ZERO, ...totals },
    timeSaved: { minutes, estimate: true, perKind: [] },
  };
}

const renderCard = () => render(<StatsCard tenantId={null} days={30} onDaysChange={() => {}} refreshSignal={0} />);

beforeEach(() => { fetchStats.mockReset(); });

describe('the Statistics card summary line', () => {
  it('shows done, undone and the estimate for real decisions', async () => {
    fetchStats.mockResolvedValue(payload({ fired: 3, done: 2, undone: 1 }, 30));
    renderCard();
    expect(await screen.findByText('Last 30 days · 2 done · 1 undone · About 30 min saved (estimate)')).toBeInTheDocument();
  });

  it('says simulation only when nothing real happened but simulations did', async () => {
    fetchStats.mockResolvedValue(payload({ wouldHaveDone: 18 }, 0, true));
    renderCard();
    expect(await screen.findByText(
      'Last 30 days · Simulation only: 18 would have been done · Nothing was carried out')).toBeInTheDocument();
  });

  it('says there are no decisions for an empty period', async () => {
    fetchStats.mockResolvedValue(payload({}));
    renderCard();
    expect(await screen.findByText('Last 30 days · No decisions yet')).toBeInTheDocument();
  });

  it('says the statistics could not be loaded when the request fails', async () => {
    fetchStats.mockImplementation(() => Promise.reject(new Error('down')));
    renderCard();
    expect(await screen.findByText("Statistics couldn't be loaded")).toBeInTheDocument();
  });
});

describe('the Statistics card body', () => {
  it('starts collapsed and the toggle flips aria-expanded and shows the headline readout', async () => {
    fetchStats.mockResolvedValue(payload({ fired: 3, done: 2, undone: 1 }, 30));
    renderCard();
    await screen.findByText(/Last 30 days/);
    const toggle = screen.getByRole('button', { name: /Statistics/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Decisions')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.getByText('Undone')).toBeInTheDocument();
    expect(screen.getAllByText('Time saved').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Estimate').length).toBeGreaterThan(0);
    expect(screen.getAllByText('About 30 min').length).toBeGreaterThan(0);
  });
});

describe('formatMinutes', () => {
  it('follows the pinned examples', () => {
    expect(formatMinutes(0)).toBe('0 min');
    expect(formatMinutes(45)).toBe('About 45 min');
    expect(formatMinutes(338)).toBe('About 5 h 40 min');
    expect(formatMinutes(120)).toBe('About 2 h');
  });
});

// ---------------------------------------------------------------------------------------------------------
// 86-04 Task 1: period pills, simulation line, Time saved block and every card state
// ---------------------------------------------------------------------------------------------------------

const KINDS = [
  { kind: 'isolate_host', label: 'Isolate a host', counted: 2, minutesEach: 15, subtotal: 30 },
  { kind: 'answer_ticket', label: 'Answer a ticket', counted: 0, minutesEach: 8, subtotal: 0 },
];

function withKinds(totals: Partial<typeof ZERO>, minutes: number, shadowOnly = false, perKind = KINDS) {
  const p = payload(totals, minutes, shadowOnly);
  return { ...p, timeSaved: { minutes, estimate: true as const, perKind } };
}

const Harness: React.FC = () => {
  const [days, setDays] = React.useState<7 | 30 | 90>(30);
  return <StatsCard tenantId={null} days={days} onDaysChange={setDays} refreshSignal={0} />;
};

async function expandCard() {
  await screen.findByText(/Last \d+ days|couldn't be loaded/);
  const toggle = screen.getByRole('button', { name: /Statistics/ });
  fireEvent.click(toggle);
  return toggle;
}

describe('the period pills', () => {
  it('choose a period, call onDaysChange, refetch and show skeletons in place until the answer arrives', async () => {
    let release: (v: unknown) => void = () => {};
    fetchStats.mockImplementation((days: number) => (days === 7
      ? new Promise(resolve => { release = resolve; })
      : Promise.resolve({ ...withKinds({ fired: 3, done: 2, undone: 1 }, 30), days })));
    const { container } = render(<Harness />);
    await expandCard();
    const group = await screen.findByRole('group', { name: 'Statistics period' });
    expect(within(group).getByRole('button', { name: '30 days' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(group).getByRole('button', { name: '7 days' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(within(group).getByRole('button', { name: '7 days' }));
    expect(within(group).getByRole('button', { name: '7 days' })).toHaveAttribute('aria-pressed', 'true');
    expect(fetchStats).toHaveBeenLastCalledWith(7, null);
    await waitFor(() => expect(container.querySelector('[aria-busy="true"]')).not.toBeNull());
    expect(container.querySelectorAll('.h-20').length).toBe(4);
    expect(container.querySelector('.h-40')).not.toBeNull();
    await act(async () => { release({ ...withKinds({ fired: 1, done: 1 }, 15), days: 7 }); });
    await waitFor(() => expect(container.querySelector('[aria-busy="true"]')).toBeNull());
    expect(screen.getByText(/Last 7 days/)).toBeInTheDocument();
  });

  it('shows the Updated clock on the right of the controls row', async () => {
    fetchStats.mockResolvedValue(withKinds({ fired: 3, done: 2, undone: 1 }, 30));
    renderCard();
    await expandCard();
    expect(await screen.findByText(/^Updated /)).toBeInTheDocument();
  });
});

describe('the simulation line', () => {
  it('is the focus in shadow mode: real cells read zero and the line says nothing was carried out', async () => {
    fetchStats.mockResolvedValue(withKinds({ wouldHaveDone: 18 }, 0, true));
    renderCard();
    await expandCard();
    expect(await screen.findByText(
      'Simulation: 18 would have been done in this period. Nothing was carried out, and none of it is counted above.')).toBeInTheDocument();
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText('0 min').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Shadow mode is on, so nothing has been carried out and no time is counted.')).toBeInTheDocument();
  });

  it('says nothing would have been done when shadow mode is on and the count is zero', async () => {
    fetchStats.mockResolvedValue(withKinds({}, 0, true));
    renderCard();
    await expandCard();
    expect(await screen.findByText('Simulation: nothing would have been done in this period.')).toBeInTheDocument();
  });

  it('is absent for a live organization with no simulation rows, and the shadow sentence too', async () => {
    fetchStats.mockResolvedValue(withKinds({ fired: 3, done: 2, undone: 1 }, 30));
    renderCard();
    await expandCard();
    await screen.findByText('Show minutes per kind of action');
    expect(screen.queryByText(/^Simulation:/)).toBeNull();
    expect(screen.queryByText(/Shadow mode is on/)).toBeNull();
  });
});

describe('the empty and error states', () => {
  it('shows the empty card in place of the simulation line, time saved and rules', async () => {
    fetchStats.mockResolvedValue(withKinds({}, 0, false));
    renderCard();
    await expandCard();
    expect(await screen.findByRole('heading', { name: 'No decisions in the last 30 days' })).toBeInTheDocument();
    expect(screen.getByText(
      "Autonomous Ops hasn't made a decision in this period. Pick a longer period, or see Activity below for older entries.")).toBeInTheDocument();
    expect(screen.getByText('Last 30 days · No decisions yet')).toBeInTheDocument();
    expect(screen.queryByText('Show minutes per kind of action')).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText(/^Simulation:/)).toBeNull();
  });

  it('shows the red notice with Try again when the load fails, and Try again refetches', async () => {
    let up = false;
    fetchStats.mockImplementation(() => (up
      ? Promise.resolve(withKinds({ fired: 3, done: 2, undone: 1 }, 30))
      : Promise.reject(new Error('down'))));
    renderCard();
    await expandCard();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load statistics. Check your connection and try again.");
    expect(screen.getByText("Statistics couldn't be loaded")).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
    const calls = fetchStats.mock.calls.length;
    up = true;
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(fetchStats.mock.calls.length).toBeGreaterThan(calls));
    expect(await screen.findByText('Last 30 days · 2 done · 1 undone · About 30 min saved (estimate)')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows the collapsed skeleton under the title while the first load runs', () => {
    fetchStats.mockImplementation(() => new Promise(() => {}));
    const { container } = renderCard();
    expect(container.querySelector('.h-4.w-64')).not.toBeNull();
  });
});

describe('the Time saved block', () => {
  it('always shows the method and the figure with its Estimate chip', async () => {
    fetchStats.mockResolvedValue(withKinds({ fired: 12, done: 9, undone: 1 }, 338));
    renderCard();
    await expandCard();
    expect(await screen.findByRole('heading', { level: 3, name: /Time saved/ })).toBeInTheDocument();
    expect(screen.getAllByText('About 5 h 40 min').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Estimate').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/This is an estimate, not a measurement\. Each action that really ran and was not undone counts a fixed number of minutes/))
      .toBeInTheDocument();
    expect(screen.getByText(/These minutes are fixed in the product and can't be changed\./)).toBeInTheDocument();
  });

  it('opens a read-only table with every kind, including Counted 0 rows, and a Total equal to the subtotals', async () => {
    fetchStats.mockResolvedValue(withKinds({ fired: 3, done: 2, undone: 1 }, 30));
    renderCard();
    await expandCard();
    const disclosure = await screen.findByRole('button', { name: 'Show minutes per kind of action' });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('table', { name: 'Minutes per kind of action' })).toBeNull();
    fireEvent.click(disclosure);
    expect(screen.getByRole('button', { name: 'Hide minutes per kind of action' })).toHaveAttribute('aria-expanded', 'true');
    const table = screen.getByRole('table', { name: 'Minutes per kind of action' });
    for (const h of ['Kind of action', 'Counted', 'Minutes each', 'Subtotal']) {
      expect(within(table).getByRole('columnheader', { name: h })).toBeInTheDocument();
    }
    const answer = within(table).getByRole('row', { name: /Answer a ticket/ });
    expect(within(answer).getAllByRole('cell').map(c => c.textContent)).toEqual(['0', '8', '0 min']);
    const total = within(table).getByRole('row', { name: /^Total/ });
    expect(total).toHaveTextContent('30 min');
    expect(within(table).queryAllByRole('textbox')).toHaveLength(0);
    expect(within(table).queryAllByRole('spinbutton')).toHaveLength(0);
  });

  it('renders a hostile kind label as text', async () => {
    const hostile = [{ kind: 'x', label: '<img src=x onerror=alert(1)>', counted: 1, minutesEach: 5, subtotal: 5 }];
    fetchStats.mockResolvedValue(withKinds({ fired: 1, done: 1 }, 5, false, hostile));
    const { container } = renderCard();
    await expandCard();
    fireEvent.click(await screen.findByRole('button', { name: 'Show minutes per kind of action' }));
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });
});
