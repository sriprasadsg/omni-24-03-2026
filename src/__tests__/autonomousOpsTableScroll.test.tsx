/**
 * Phase 86 / G-86-5: a structural check that each wide Autonomous Ops table has its own sideways scroll region.
 * jsdom has no layout, so this pins the structure (a labelled, focusable overflow-x-auto ancestor inside the
 * component's own section), not pixels. Without it, main's overflow-x-hidden clips the Action column of the
 * Going live Organizations table and the Refused / Would have done columns of the Statistics per-rule table.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../services/autonomousOpsGoLive', () => ({
  fetchGoLive: vi.fn(),
  recordGoLiveCheck: vi.fn(),
  setOrganizationShadow: vi.fn(),
  markTestOrganization: vi.fn(),
  clearTestOrganization: vi.fn(),
}));
vi.mock('../../services/autonomousOpsReporting', () => ({
  fetchAutonomousOpsStatistics: vi.fn(),
  downloadAutonomousOpsExport: vi.fn(),
  downloadAutonomousOpsReport: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { GoLiveOrganizations } from '../../components/autonomousOpsGoLive/GoLiveOrganizations';
import type { GoLiveOrganization } from '../../services/autonomousOpsGoLive';

const setMatches = (matches: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches, media: query, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
};

afterEach(() => { delete (window as unknown as { matchMedia?: unknown }).matchMedia; });

// ── the Going live Organizations table ───────────────────────────────────────────────────────────────────

const ACME: GoLiveOrganization = {
  id: 'acme-id', name: 'Acme', shadow: true, daysObserved: 5, wouldHaveDone: 18, canLift: false,
  reasons: [{ code: 'checks_missing', recorded: 3 }, { code: 'days_short', days: 5 }],
};
const BOLT: GoLiveOrganization = { id: 'bolt-id', name: 'Bolt', shadow: false, daysObserved: 12, wouldHaveDone: 40, canLift: false, reasons: [] };

const renderOrgs = () => render(
  <GoLiveOrganizations organizations={[ACME, BOLT]} masterShadow={false} testOrganization={null} onChanged={() => {}} />,
);

describe('Going live organizations table (G-86-5)', () => {
  it('sits in its own labelled, focusable overflow-x-auto region inside the Organizations section', () => {
    setMatches(true);
    const { container } = renderOrgs();
    const table = screen.getByRole('table', { name: 'Shadow mode by organization' });
    const scroller = table.closest('.overflow-x-auto');
    expect(scroller).not.toBeNull();
    expect(scroller).toBe(screen.getByRole('region', { name: 'Shadow mode by organization' }));
    expect(scroller).toHaveAttribute('tabindex', '0');
    const section = screen.getByRole('heading', { level: 3, name: 'Organizations' }).closest('section');
    expect(section).not.toBeNull();
    expect(section).not.toBe(scroller);
    expect(section!.contains(scroller)).toBe(true);
    expect(container.querySelectorAll('.overflow-x-auto')).toHaveLength(1);
  });

  it('keeps the Action header and every action button inside the scroll region', () => {
    setMatches(true);
    renderOrgs();
    const region = screen.getByRole('region', { name: 'Shadow mode by organization' });
    expect(within(region).getByRole('columnheader', { name: 'Action' })).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: 'Lift shadow mode' })).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: 'Turn shadow mode back on' })).toBeInTheDocument();
    expect(within(region).getAllByRole('button', { name: 'Use as test organization' })).toHaveLength(2);
  });

  it('adds no table and no scroll region in the card layout, so the cards add no extra tab stop', () => {
    setMatches(false);
    renderOrgs();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Shadow mode by organization' })).toBeNull();
    expect(screen.getByRole('list', { name: 'Shadow mode by organization' })).toBeInTheDocument();
  });
});
