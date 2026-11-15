/**
 * Phase 86 / G-86-5: a structural check that each wide Autonomous Ops table has its own sideways scroll region.
 * jsdom has no layout, so this pins the structure (one overflow-x-auto ancestor inside the component's own
 * section), not pixels, and fakes the widths (setWidths) for the two states of review WR-07 / IN-06: while the
 * table fits, a plain wrapper with no landmark, tab stop or hint; while it is wider than its card, a region named
 * "Scrollable: <caption>" with a hint and a right-edge fade, a tab stop only for the Statistics table (no
 * focusable content of its own). Without the wrapper, main's overflow-x-hidden clips the Action column of the
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

import { SCROLL_HINT } from '../../components/AutonomousOpsScrollRegion';
import { GoLiveOrganizations } from '../../components/autonomousOpsGoLive/GoLiveOrganizations';
import { StatsRuleTable } from '../../components/autonomousOpsStats/StatsRuleTable';
import type { GoLiveOrganization } from '../../services/autonomousOpsGoLive';
import type { AutonomousOpsRuleStats, AutonomousOpsStatsTotals } from '../../services/autonomousOpsReporting';

const setMatches = (matches: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches, media: query, addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, onchange: null, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
};

/** jsdom has no layout: every element reports this content width and box width, as a card of that size would. */
const setWidths = (content: number, box: number) => {
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', { configurable: true, get: () => content });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => box });
};

afterEach(() => {
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
  delete (HTMLElement.prototype as unknown as { scrollWidth?: number }).scrollWidth;
  delete (HTMLElement.prototype as unknown as { clientWidth?: number }).clientWidth;
});

// ── the Going live Organizations table ───────────────────────────────────────────────────────────────────

const ACME: GoLiveOrganization = {
  id: 'acme-id', name: 'Acme', shadow: true, daysObserved: 5, wouldHaveDone: 18, canLift: false, testCandidate: true,
  reasons: [{ code: 'checks_missing', recorded: 3 }, { code: 'days_short', days: 5 }],
};
const BOLT: GoLiveOrganization = { id: 'bolt-id', name: 'Bolt', shadow: false, daysObserved: 12, wouldHaveDone: 40, canLift: false, testCandidate: true, reasons: [] };

const renderOrgs = () => render(
  <GoLiveOrganizations organizations={[ACME, BOLT]} masterShadow={false} testOrganization={null} onChanged={() => {}} />,
);

describe('Going live organizations table (G-86-5)', () => {
  it('is one plain overflow-x-auto wrapper, with no landmark, tab stop or hint, while the table fits (review IN-06)', () => {
    setMatches(true);
    setWidths(900, 900);
    const { container } = renderOrgs();
    const scroller = screen.getByRole('table', { name: 'Shadow mode by organization' }).closest('.overflow-x-auto');
    expect(scroller).not.toBeNull();
    expect(scroller!.getAttribute('role')).toBeNull();
    expect(scroller!.hasAttribute('tabindex')).toBe(false);
    expect(screen.queryByText(SCROLL_HINT)).toBeNull();
    expect(container.querySelector('[data-scroll-fade]')).toBeNull();
    expect(container.querySelectorAll('.overflow-x-auto')).toHaveLength(1);
  });

  it('becomes a named region with a hint and a right-edge fade inside the section while it is wider than its card (review WR-07)', () => {
    setMatches(true);
    setWidths(1200, 900);
    const { container } = renderOrgs();
    const region = screen.getByRole('region', { name: 'Scrollable: Shadow mode by organization' });
    expect(screen.getByRole('table', { name: 'Shadow mode by organization' }).closest('.overflow-x-auto')).toBe(region);
    expect(region.hasAttribute('tabindex')).toBe(false);   // its own buttons are the tab stops
    expect(screen.getByText(SCROLL_HINT)).toBeTruthy();
    expect(container.querySelector('[data-scroll-fade]')).not.toBeNull();
    const section = screen.getByRole('heading', { level: 3, name: 'Organizations' }).closest('section');
    expect(section).not.toBeNull();
    expect(section).not.toBe(region);
    expect(section!.contains(region)).toBe(true);
    expect(container.querySelectorAll('.overflow-x-auto')).toHaveLength(1);
  });

  it('keeps the Action header and every action button inside the scroll region', () => {
    setMatches(true);
    setWidths(1200, 900);
    renderOrgs();
    const region = screen.getByRole('region', { name: 'Scrollable: Shadow mode by organization' });
    expect(within(region).getByRole('columnheader', { name: 'Action' })).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: 'Lift shadow mode' })).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: 'Turn shadow mode back on' })).toBeInTheDocument();
    expect(within(region).getAllByRole('button', { name: 'Use as test organization' })).toHaveLength(2);
  });

  it('adds no table and no scroll region in the card layout, so the cards add no extra tab stop', () => {
    setMatches(false);
    renderOrgs();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Scrollable: Shadow mode by organization' })).toBeNull();
    expect(screen.getByRole('list', { name: 'Shadow mode by organization' })).toBeInTheDocument();
  });

  it('stacks the card dl in one column below sm and two from sm, with the simulation cell spanning the row', () => {
    setMatches(false);
    renderOrgs();
    const card = within(screen.getByRole('list', { name: 'Shadow mode by organization' })).getAllByRole('listitem')[0];
    const dl = card.querySelector('dl');
    expect(dl).not.toBeNull();
    const classes = (dl!.getAttribute('class') ?? '').split(/\s+/);
    expect(classes).toContain('grid-cols-1');
    expect(classes).toContain('sm:grid-cols-2');
    expect(classes).not.toContain('grid-cols-2');
    const sim = Array.from(dl!.querySelectorAll('dt')).find(d => d.textContent === 'Would have done (simulation)');
    expect(sim).toBeDefined();
    expect((sim!.parentElement!.getAttribute('class') ?? '').split(/\s+/)).toContain('col-span-full');
    expect(Array.from(dl!.querySelectorAll('dt')).map(d => d.textContent)).toEqual([
      'Shadow mode', 'Days observed', 'Would have done (simulation)',
    ]);
  });
});

// ── the Statistics per-rule table ────────────────────────────────────────────────────────────────────────

const ZERO: AutonomousOpsStatsTotals = { fired: 0, done: 0, approved: 0, denied: 0, undone: 0, failed: 0, refused: 0, wouldHaveDone: 0 };
const rule = (id: string, name: string, counts: Partial<AutonomousOpsStatsTotals>): AutonomousOpsRuleStats => ({ id, name, ...ZERO, ...counts });
const sumTotals = (rules: AutonomousOpsRuleStats[]): AutonomousOpsStatsTotals => {
  const totals = { ...ZERO };
  for (const r of rules) for (const k of Object.keys(ZERO) as Array<keyof AutonomousOpsStatsTotals>) totals[k] += r[k];
  return totals;
};
const THREE = [
  rule('r.charlie', 'Charlie rule', { fired: 2, done: 1, undone: 1 }),
  rule('r.bravo', 'Bravo rule', { fired: 5, done: 4, approved: 1, denied: 1, failed: 1, refused: 2 }),
  rule('r.alpha', 'Alpha rule', { fired: 2, done: 2, wouldHaveDone: 3 }),
];
const SIXTEEN = Array.from({ length: 16 }, (_, i) => rule(`r.gen${i}`, `Generated rule ${i}`, { fired: 16 - i }));
const CAPTION = 'Decisions by rule, last 30 days';
const renderRules = (rules: AutonomousOpsRuleStats[]) => render(<StatsRuleTable rules={rules} totals={sumTotals(rules)} days={30} />);

describe('Statistics per-rule table (G-86-5)', () => {
  it('is a plain wrapper with no landmark, tab stop or hint while the table fits (review IN-06)', () => {
    setMatches(true);
    setWidths(900, 900);
    const { container } = renderRules(THREE);
    const scroller = screen.getByRole('table', { name: CAPTION }).closest('.overflow-x-auto');
    expect(scroller).not.toBeNull();
    expect(scroller!.getAttribute('role')).toBeNull();
    expect(scroller!.hasAttribute('tabindex')).toBe(false);
    expect(screen.queryByText(SCROLL_HINT)).toBeNull();
    expect(container.querySelectorAll('.overflow-x-auto')).toHaveLength(1);
  });

  it('becomes a focusable, named region with a hint while it is wider than its card (review WR-07, IN-06)', () => {
    setMatches(true);
    setWidths(1200, 900);
    const { container } = renderRules(THREE);
    const region = screen.getByRole('region', { name: `Scrollable: ${CAPTION}` });
    expect(screen.getByRole('table', { name: CAPTION }).closest('.overflow-x-auto')).toBe(region);
    expect(region.getAttribute('tabindex')).toBe('0');   // no focusable content of its own
    expect(screen.getByText(SCROLL_HINT)).toBeTruthy();
    expect(container.querySelector('[data-scroll-fade]')).not.toBeNull();
  });

  it('keeps the Refused and simulation headers and the All rules footer inside the scroll region', () => {
    setMatches(true);
    setWidths(1200, 900);
    renderRules(THREE);
    const region = screen.getByRole('region', { name: `Scrollable: ${CAPTION}` });
    expect(within(region).getByRole('columnheader', { name: 'Refused' })).toBeInTheDocument();
    expect(within(region).getByRole('columnheader', { name: /Would have done \(simulation\)/ })).toBeInTheDocument();
    expect(within(region).getByRole('rowheader', { name: 'All rules' })).toBeInTheDocument();
  });

  it('keeps Show all and What the columns mean outside the scroll region', () => {
    setMatches(true);
    setWidths(1200, 900);
    renderRules(SIXTEEN);
    const region = screen.getByRole('region', { name: `Scrollable: ${CAPTION}` });
    const showAll = screen.getByRole('button', { name: 'Show all 16 rules' });
    const glossary = screen.getByRole('button', { name: 'What the columns mean' });
    expect(region.contains(showAll)).toBe(false);
    expect(region.contains(glossary)).toBe(false);
  });

  it('adds no table and no scroll region in the card layout', () => {
    setMatches(false);
    renderRules(THREE);
    expect(screen.queryByRole('table', { name: CAPTION })).toBeNull();
    expect(screen.queryByRole('region', { name: `Scrollable: ${CAPTION}` })).toBeNull();
  });
});
