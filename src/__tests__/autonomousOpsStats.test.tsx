/**
 * Phase 86 / ACTV-05, ACTV-07, D-05..D-08: the collapsed Statistics card on the Autonomous Ops screen.
 * The service is mocked; payloads follow the 86-01 contract.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

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

beforeEach(() => fetchStats.mockReset());

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
    fetchStats.mockRejectedValue(new Error('down'));
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
    expect(screen.getByText('Time saved')).toBeInTheDocument();
    expect(screen.getByText('Estimate')).toBeInTheDocument();
    expect(screen.getByText('About 30 min')).toBeInTheDocument();
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
