/**
 * Phase 84 / PTCH-01, PTCH-04 (84-14 task 3): one rollout card, its ring strip and its halt block. The card renders
 * the 84-09 payload; nothing here reaches the network.
 *
 * Value: protects=each rollout shows where it is, ring by ring, and a halt says exactly why and what was put back in
 * the server's words; fails_when=a ring state loses its chip or detail line, the current ring is not marked, Review in
 * Needs your decision shows to someone who cannot open it, the halt block is not an alert or drops its second line, a
 * control renders without its prop, or a name is truncated or rendered as markup; no_claim=the server wording
 * (backend/tests/test_patch_rollout_views.py) and the Resume and Cancel dialogs (84-18).
 */
import React from 'react';
import { readFileSync } from 'node:fs';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { RolloutCard } from '../../components/patchRollouts/RolloutCard';
import { RING_STATE_CHIP, ROLLOUT_STATUS_CHIP } from '../../components/patchRollouts/rolloutCopy';
import type { RingState, RolloutStatus } from '../../services/patchRollouts/types';
import { HOUR, at, card, ring } from './_patchRolloutFixtures';

const HALT_SECOND_LINE =
  'A rollout halts on failure; reverts where supported. Rings that already passed keep the patches. Nothing further installs.';

const strip = () => screen.getByRole('list', { name: 'Rings' });
const blocks = () => within(strip()).getAllByRole('listitem');

describe('RolloutCard header', () => {
  it('is an article named by the rollout, focusable by id for the new-card focus', () => {
    render(<RolloutCard card={card({ id: 'R9', name: 'November security' })} />);
    const article = screen.getByRole('article', { name: 'November security' });
    expect(article.id).toBe('rollout-R9');
    expect(article.getAttribute('tabindex')).toBe('-1');
  });

  it('reads patches, computers and who started it, with the full time in the title', () => {
    const startedAt = at(-3 * HOUR);
    render(<RolloutCard card={card({ patchCount: 2, computerCount: 12, startedAt, startedBy: 'Asha' })} />);
    const meta = screen.getByText(/^2 patches · 12 computers · Started /);
    expect(meta.textContent).toMatch(/by Asha$/);
    expect(meta.querySelector('time')?.getAttribute('title')).toBeTruthy();
  });

  it('uses the singular at one patch and one computer', () => {
    render(<RolloutCard card={card({ patchCount: 1, computerCount: 1 })} />);
    expect(screen.getByText(/^1 patch · 1 computer · Started /)).toBeInTheDocument();
  });

  it('leaves out Started when the time is not known', () => {
    render(<RolloutCard card={card({ patchCount: 3, computerCount: 4, startedAt: null, startedBy: null })} />);
    expect(screen.getByText('3 patches · 4 computers')).toBeInTheDocument();
  });

  it.each(Object.keys(ROLLOUT_STATUS_CHIP) as RolloutStatus[])('the %s status chip carries its label', (status) => {
    render(<RolloutCard card={card({ status, halt: null })} />);
    const header = screen.getByRole('article').querySelector('header') as HTMLElement;
    expect(within(header).getByText(ROLLOUT_STATUS_CHIP[status].label)).toBeInTheDocument();
  });

  it('shows the Simulation chip only for a simulated rollout', () => {
    const { unmount } = render(<RolloutCard card={card({ simulation: true })} />);
    expect(screen.getByText('Simulation')).toBeInTheDocument();
    unmount();
    render(<RolloutCard card={card({ simulation: false })} />);
    expect(screen.queryByText('Simulation')).toBeNull();
  });

  it('a long rollout name wraps and is not rendered as markup', () => {
    const name = '<img src=x onerror=alert(1)> ' + 'Very-long-rollout-name-'.repeat(8);
    render(<RolloutCard card={card({ name })} />);
    const title = screen.getByRole('heading', { level: 3 });
    expect(title.textContent).toBe(name);
    expect(title.className).toContain('break-words');
    expect(title.querySelector('img')).toBeNull();
  });
});

describe('RolloutCard ring strip', () => {
  const ALL_STATES = Object.keys(RING_STATE_CHIP) as RingState[];

  it('renders one li per ring, each a min-w-[200px] flex-1 block, in an ordered list', () => {
    const rings = [0, 1, 2, 3].map(i => ring({ index: i, name: `Ring ${i}`, state: 'not_started', detail: `Detail ${i}` }));
    render(<RolloutCard card={card({ rings, currentRing: 0 })} />);
    expect(strip().tagName).toBe('OL');
    expect(blocks()).toHaveLength(4);
    for (const li of blocks()) {
      expect(li.className).toContain('min-w-[200px]');
      expect(li.className).toContain('flex-1');
    }
    expect(strip().className).toContain('flex-wrap');
  });

  it.each(ALL_STATES)('a ring in the %s state shows its chip and the server detail line', (state) => {
    render(<RolloutCard card={card({ rings: [ring({ name: 'Early', state, detail: `Server says ${state}` })], currentRing: 0 })} />);
    const block = blocks()[0];
    expect(within(block).getByText(RING_STATE_CHIP[state].label)).toBeInTheDocument();
    expect(within(block).getByText(`Server says ${state}`)).toBeInTheDocument();
    expect(within(block).getByText('Early')).toBeInTheDocument();
  });

  it('marks only the current ring aria-current="step"', () => {
    render(<RolloutCard card={card()} />);
    const marked = blocks().filter(li => li.getAttribute('aria-current') === 'step');
    expect(marked).toHaveLength(1);
    expect(within(marked[0]).getByText('Early')).toBeInTheDocument();
  });

  it('marks no ring when the rollout has finished', () => {
    render(<RolloutCard card={card({ status: 'completed', currentRing: null })} />);
    expect(blocks().some(li => li.hasAttribute('aria-current'))).toBe(false);
  });

  it('group names are mono and break-all; a ring with no group shows no group names', () => {
    render(<RolloutCard card={card({
      rings: [
        ring({ name: 'Early', groups: ['early-a', 'early-b-with-a-very-long-name-that-must-wrap'] }),
        ring({ index: 1, name: 'Broad', groups: [] }),
      ],
    })} />);
    const group = screen.getByText('early-b-with-a-very-long-name-that-must-wrap');
    expect(group.className).toContain('font-mono');
    expect(group.className).toContain('break-all');
    expect(within(blocks()[1]).queryByText(/./, { selector: '.font-mono' })).toBeNull();
  });

  it('a ring waiting for approval offers Review in Needs your decision only when the server says so and a handler exists', () => {
    const waiting = ring({ state: 'waiting_for_approval', detail: 'Waiting for your approval in Needs your decision.', decisionsLink: true });
    const onOpenView = vi.fn();
    const { unmount } = render(<RolloutCard card={card({ rings: [waiting], currentRing: 0 })} onOpenView={onOpenView} />);
    fireEvent.click(screen.getByRole('button', { name: /Review in Needs your decision/ }));
    expect(onOpenView).toHaveBeenCalledWith('autonomousOps');
    unmount();
    render(<RolloutCard card={card({ rings: [waiting], currentRing: 0 })} />);
    expect(screen.queryByText('Review in Needs your decision')).toBeNull();
  });

  it('without access it reads the server line instead of a link', () => {
    const waiting = ring({
      state: 'waiting_for_approval', decisionsLink: false,
      waitingText: 'Waiting for someone with access to Autonomous Ops.',
    });
    render(<RolloutCard card={card({ rings: [waiting], currentRing: 0 })} onOpenView={vi.fn()} />);
    expect(screen.getByText('Waiting for someone with access to Autonomous Ops.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Review in Needs your decision/ })).toBeNull();
  });

  it('a ring that is not waiting for approval never shows the link', () => {
    render(<RolloutCard card={card({ rings: [ring({ state: 'installing', decisionsLink: true })] })} onOpenView={vi.fn()} />);
    expect(screen.queryByText(/Review in Needs your decision/)).toBeNull();
  });

  it('renders no Show details control and no buttons when no extension is given', () => {
    render(<RolloutCard card={card()} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('Show details opens one ring at a time with aria-expanded, and the detail renders under the strip', () => {
    render(<RolloutCard card={card()} renderRingDetail={(r) => <div>DETAIL OF {r.name}</div>} />);
    const buttons = screen.getAllByRole('button', { name: /Show details/ });
    expect(buttons).toHaveLength(3);
    expect(buttons[0]).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(buttons[1]);
    expect(screen.getByText('DETAIL OF Early')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hide details/ })).toHaveAttribute('aria-expanded', 'true');
    expect(strip().contains(screen.getByText('DETAIL OF Early'))).toBe(false);
    fireEvent.click(screen.getAllByRole('button', { name: /Show details/ })[0]);
    expect(screen.queryByText('DETAIL OF Early')).toBeNull();
    expect(screen.getByText('DETAIL OF Canary')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Hide details/ }));
    expect(screen.queryByText('DETAIL OF Canary')).toBeNull();
  });
});

describe('RolloutCard halt block', () => {
  const halt = {
    ringName: 'Early',
    reason: '2 of 9 computers failed, more than the 20% limit.',
    reverts: ['Reverted on 3 computers.', '1 computer could not be reverted: Windows does not allow this update to be uninstalled. The patch is still installed on it.'],
  };

  it('is a red alert with the halt line, the mandatory second line and the server revert summary', () => {
    render(<RolloutCard card={card({ status: 'halted', halt })} />);
    const alert = screen.getByRole('alert');
    expect(within(alert).getByText('Halted at Early: 2 of 9 computers failed, more than the 20% limit.')).toBeInTheDocument();
    expect(within(alert).getByText(HALT_SECOND_LINE)).toBeInTheDocument();
    const lines = within(alert).getAllByRole('listitem').map(li => li.textContent);
    expect(lines).toEqual(halt.reverts);
  });

  it('shows no alert and no revert list when the rollout is not halted', () => {
    render(<RolloutCard card={card()} />);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(HALT_SECOND_LINE)).toBeNull();
  });

  it('leaves out the revert list when the server sent no lines, and wraps a long reason', () => {
    const reason = 'no heartbeat from ' + 'a-very-long-host-name-'.repeat(8) + ' within 30 minutes of the restart.';
    render(<RolloutCard card={card({ status: 'halted', halt: { ringName: 'Early', reason, reverts: [] } })} />);
    const alert = screen.getByRole('alert');
    expect(within(alert).queryByRole('list')).toBeNull();
    expect(within(alert).getByText(`Halted at Early: ${reason}`).className).toContain('break-words');
  });

  it('renders the actions the parent supplies inside the block, and nothing when none are given', () => {
    const { unmount } = render(<RolloutCard card={card({ status: 'halted', halt })} actions={<button type="button">Resume rollout</button>} />);
    expect(within(screen.getByRole('alert')).getByRole('button', { name: 'Resume rollout' })).toBeInTheDocument();
    unmount();
    render(<RolloutCard card={card({ status: 'halted', halt })} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('RolloutCard completed rollout', () => {
  it('a completed rollout with computers not reached shows the chip and the closes line', () => {
    render(<RolloutCard card={card({
      status: 'completed', currentRing: null, notReachedCount: 2,
      closedText: '2 computers were offline for the whole ring. They get the patches in a later window if they come back online. This rollout closes Mon 9 Nov.',
    })} />);
    expect(screen.getByText('2 not reached')).toBeInTheDocument();
    expect(screen.getByText(/This rollout closes Mon 9 Nov\.$/)).toBeInTheDocument();
  });

  it('uses the singular at one computer', () => {
    render(<RolloutCard card={card({ status: 'completed', currentRing: null, notReachedCount: 1, closedText: null })} />);
    expect(screen.getByText('1 not reached')).toBeInTheDocument();
  });

  it('after the rollout closes it reads the never-reached sentence and keeps no chip when nothing is left', () => {
    render(<RolloutCard card={card({
      status: 'completed', currentRing: null, notReachedCount: 0, neverReachedCount: 3, closedText: '3 computers were never reached.',
    })} />);
    expect(screen.getByText('3 computers were never reached.')).toBeInTheDocument();
    expect(screen.queryByText(/not reached$/)).toBeNull();
  });

  it('a running rollout shows no not-reached chip', () => {
    render(<RolloutCard card={card({ status: 'running', notReachedCount: 2 })} />);
    expect(screen.queryByText('2 not reached')).toBeNull();
  });
});

describe('rollout files render server text as text only', () => {
  it.each(['components/patchRollouts/RolloutCard.tsx', 'components/patchRollouts/RolloutsTab.tsx'])(
    '%s never sets inner HTML', (file) => {
      expect(readFileSync(file, 'utf8')).not.toContain('dangerouslySetInnerHTML');
    });
});
