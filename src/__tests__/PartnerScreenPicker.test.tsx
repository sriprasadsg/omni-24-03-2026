/**
 * Phase 87 (PART-06, D-10, D-19): the status chips and the screen picker that refuses to offer a screen
 * outside the partner's ceiling.
 */
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import featureSwitches from '../../shared/tenant-feature-switches.json';
import { PartnerScreenPicker } from '../../components/PartnerScreenPicker';
import { PartnerStatusChip, PoolExpiryChip, StaffStatusChip, daysUntil, formatDay } from '../../components/PartnerStatusChip';

const NOW = new Date('2026-11-02T12:00:00Z');
const inDays = (n: number) => new Date(NOW.getTime() + n * 24 * 60 * 60 * 1000).toISOString();
const START = ['view:dashboard', 'view:profile', 'screen:dashboard'];

const ALL_SWITCHES = featureSwitches.groups.flatMap(g => g.features.map(f => f.permission));
const TICKABLE_TOTAL = ALL_SWITCHES.filter(p => p !== 'screen:dashboard').length;

describe('PartnerStatusChip', () => {
  it('shows Active and Suspended with a 12px decorative icon', () => {
    const active = render(<PartnerStatusChip kind="active" />);
    expect(screen.getByText('Active')).toBeTruthy();
    const icon = active.container.querySelector('svg');
    expect(icon?.getAttribute('aria-hidden')).toBe('true');
    expect(icon?.getAttribute('width')).toBe('12');
    active.unmount();
    render(<PartnerStatusChip kind="suspended" />);
    expect(screen.getByText('Suspended')).toBeTruthy();
  });
});

describe('PoolExpiryChip', () => {
  it('reads Expired for a date in the past', () => {
    render(<PoolExpiryChip expiresAt={inDays(-2)} now={NOW} />);
    expect(screen.getByText('Expired')).toBeTruthy();
  });

  it('reads Expires in 3 days three days ahead and 1 day when it is one', () => {
    const three = render(<PoolExpiryChip expiresAt={inDays(3)} now={NOW} />);
    expect(screen.getByText('Expires in 3 days')).toBeTruthy();
    three.unmount();
    render(<PoolExpiryChip expiresAt={inDays(1)} now={NOW} />);
    expect(screen.getByText('Expires in 1 day')).toBeTruthy();
  });

  it('shows nothing beyond 30 days, at exactly 30 days it still warns, and nothing with no date', () => {
    expect(render(<PoolExpiryChip expiresAt={inDays(31)} now={NOW} />).container.textContent).toBe('');
    expect(render(<PoolExpiryChip expiresAt={null} now={NOW} />).container.textContent).toBe('');
    expect(render(<PoolExpiryChip now={NOW} />).container.textContent).toBe('');
    expect(render(<PoolExpiryChip expiresAt="not a date" now={NOW} />).container.textContent).toBe('');
    expect(render(<PoolExpiryChip expiresAt={inDays(30)} now={NOW} />).container.textContent).toBe('Expires in 30 days');
  });
});

describe('StaffStatusChip', () => {
  it.each([
    ['active', 'Active'],
    ['invited', 'Invited'],
    ['invite_expired', 'Invite expired'],
  ] as const)('shows %s as %s', (status, text) => {
    render(<StaffStatusChip status={status} />);
    expect(screen.getByText(text)).toBeTruthy();
  });
});

describe('date helpers', () => {
  it('counts whole days ahead, rounding up, and is null without a usable date', () => {
    expect(daysUntil(inDays(3), NOW)).toBe(3);
    expect(daysUntil(inDays(-2), NOW)).toBe(-2);
    expect(daysUntil(null, NOW)).toBeNull();
    expect(daysUntil('nope', NOW)).toBeNull();
  });

  it('formats a day as Mon D, YYYY', () => {
    expect(formatDay('2026-11-15T12:00:00Z')).toBe('Nov 15, 2026');
    expect(formatDay(null)).toBe('');
  });
});

/** The picker is controlled: this keeps its value so a click can be followed by the next one. */
const Harness: React.FC<{
  mode: 'ceiling' | 'customer';
  ceiling?: string[];
  unrestricted?: boolean;
  initial: string[];
  kept?: string[];
  disabled?: boolean;
  onChange?: (next: string[]) => void;
}> = ({ initial, onChange, ...rest }) => {
  const [value, setValue] = useState(initial);
  return (
    <>
      <PartnerScreenPicker
        {...rest}
        value={value}
        onChange={next => {
          setValue(next);
          onChange?.(next);
        }}
      />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </>
  );
};

const current = (): string[] => JSON.parse(screen.getByTestId('value').textContent ?? '[]');
const box = (name: string) => screen.getByRole('checkbox', { name }) as HTMLInputElement;

describe('PartnerScreenPicker, customer mode (D-10, D-19)', () => {
  const CEILING = ['view:assets', 'screen:assetManagement'];
  const VALUE = [...START, 'view:compliance'];

  it('offers only switches inside the ceiling as tickable', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} />);
    expect(box('Asset Management').disabled).toBe(false);
    expect(box('Asset Management').checked).toBe(false);
    expect(box('Assets').disabled).toBe(false);
    expect(screen.queryByRole('checkbox', { name: 'Tracing & APM' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: 'Security Operations' })).toBeNull();
  });

  it('shows Overview checked and disabled with Always included', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} />);
    expect(box('Overview').checked).toBe(true);
    expect(box('Overview').disabled).toBe(true);
    expect(screen.getByText('Always included')).toBeTruthy();
  });

  it("shows a kept screen outside the ceiling checked and disabled with the kept sentence", () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} kept={['view:compliance']} />);
    expect(box('Compliance Management').checked).toBe(true);
    expect(box('Compliance Management').disabled).toBe(true);
    expect(screen.getByText("Kept from before. You can't add it again.")).toBeTruthy();
  });

  it('treats a held screen outside the ceiling as kept even when the caller did not list it', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} />);
    expect(box('Compliance Management').disabled).toBe(true);
  });

  it('ticking a child ticks its parent, and unticking the parent unticks its children', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} />);
    fireEvent.click(box('Assets'));
    expect(box('Assets').checked).toBe(true);
    expect(box('Asset Management').checked).toBe(true);
    expect(current()).toEqual(expect.arrayContaining(['screen:assetManagement', 'view:assets', ...VALUE]));
    fireEvent.click(box('Asset Management'));
    expect(box('Assets').checked).toBe(false);
    expect(current()).toEqual(VALUE);
  });

  it('never removes a screen it does not show', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={[...VALUE, 'agent:legacy_thing']} />);
    fireEvent.click(screen.getByRole('button', { name: 'Select all screens' }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear all screens' }));
    expect(current()).toEqual([...VALUE, 'agent:legacy_thing']);
  });

  it('Select all screens ticks tickable rows only and the count line follows', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} />);
    expect(screen.getByText('1 screen selected')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Select all screens' }));
    expect(current().sort()).toEqual([...VALUE, 'view:assets', 'screen:assetManagement'].sort());
    expect(screen.getByText('3 screens selected')).toBeTruthy();
    expect(box('Compliance Management').checked).toBe(true);
  });

  it('Clear all screens unticks tickable rows but keeps the always-included and kept ones', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={[...VALUE, 'view:assets', 'screen:assetManagement']} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clear all screens' }));
    expect(current().sort()).toEqual([...VALUE].sort());
    expect(screen.getByText('1 screen selected')).toBeTruthy();
  });

  it('keeps a child disabled with what it needs when its parent is outside the ceiling', () => {
    render(<Harness mode="customer" ceiling={['screen:assetManagement']} initial={START} />);
    expect(box('Assets').disabled).toBe(true);
    expect(screen.getByText('Needs Asset Management.')).toBeTruthy();
    expect(screen.queryByRole('checkbox', { name: 'Asset Management' })).toBeNull();
  });

  it('keeps the parent of a kept screen on', () => {
    render(<Harness mode="customer" ceiling={['view:compliance']} initial={[...START, 'view:compliance', 'screen:compliance']} />);
    expect(box('Compliance').disabled).toBe(true);
    expect(box('Compliance Management').checked).toBe(true);
    expect(box('Compliance Management').disabled).toBe(true);
    expect(screen.getByText('Needed by a screen kept from before.')).toBeTruthy();
  });

  it('offers every switch when the ceiling is unrestricted', () => {
    render(<Harness mode="customer" unrestricted ceiling={['all']} initial={START} />);
    expect(box('Tracing & APM').disabled).toBe(false);
    expect(box('Security Operations').disabled).toBe(false);
    expect(box('Overview').disabled).toBe(true);
  });

  it('shows the empty-ceiling message and no checkbox when nothing is available to sell and nothing is kept', () => {
    render(<Harness mode="customer" ceiling={[]} initial={START} />);
    expect(screen.getByText("Your platform administrator hasn't made any screens available to sell yet. Ask them to set your screen list.")).toBeTruthy();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('lists only the kept screens, without the empty message, when the ceiling is empty but the customer holds some', () => {
    render(<Harness mode="customer" ceiling={[]} initial={[...START, 'view:compliance']} />);
    expect(screen.queryByText(/hasn't made any screens available/)).toBeNull();
    expect(box('Compliance Management').disabled).toBe(true);
  });

  it('disables every control while the form is busy', () => {
    render(<Harness mode="customer" ceiling={CEILING} initial={VALUE} disabled />);
    for (const checkbox of screen.getAllByRole('checkbox')) expect((checkbox as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Select all screens' }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('PartnerScreenPicker, ceiling mode (Super Admin)', () => {
  it('makes every switch tickable except Overview and counts n of total', () => {
    render(<Harness mode="ceiling" initial={[]} />);
    expect(box('Tracing & APM').disabled).toBe(false);
    expect(box('Compliance Management').disabled).toBe(false);
    expect(box('Overview').disabled).toBe(true);
    expect(screen.getByText(`0 of ${TICKABLE_TOTAL} selected`)).toBeTruthy();
  });

  it('ticks, selects all and clears, reporting each change', () => {
    const onChange = vi.fn();
    render(<Harness mode="ceiling" initial={[]} onChange={onChange} />);
    fireEvent.click(box('Tracing & APM'));
    expect(onChange).toHaveBeenLastCalledWith(['view:tracing']);
    expect(screen.getByText(`1 of ${TICKABLE_TOTAL} selected`)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Select all screens' }));
    expect(screen.getByText(`${TICKABLE_TOTAL} of ${TICKABLE_TOTAL} selected`)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Clear all screens' }));
    expect(screen.getByText(`0 of ${TICKABLE_TOTAL} selected`)).toBeTruthy();
    expect(current()).toEqual([]);
  });

  it('groups the checklist as Manage Tenant does', () => {
    render(<Harness mode="ceiling" initial={[]} />);
    for (const group of featureSwitches.groups) {
      const fieldset = screen.getByRole('group', { name: group.name });
      expect(within(fieldset).getAllByRole('checkbox').length).toBeGreaterThan(0);
    }
  });
});
