/**
 * Automatic sign-out after inactivity: warn before the limit, sign out at it, only user input counts,
 * activity in another tab counts, and a tab coming back after the limit signs out at once.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ IDLE_TIMEOUT_MINUTES: 30, endSessionForInactivity: vi.fn() }));

import { IdleSignOut, LAST_ACTIVITY_KEY } from '../../components/IdleSignOut';

const LIMIT = 10_000;
const WARN = 4_000;

function setup() {
  const onSignOut = vi.fn();
  render(<IdleSignOut timeoutMs={LIMIT} warnMs={WARN} onSignOut={onSignOut} />);
  return onSignOut;
}
const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });
const warning = () => screen.queryByText('Still there?');

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
});
afterEach(() => vi.useRealTimers());

describe('IdleSignOut', () => {
  it('warns before the limit and keeps the session on "Stay signed in"', () => {
    const onSignOut = setup();
    advance(LIMIT - WARN - 1_000);
    expect(warning()).toBeNull();
    advance(2_000);
    expect(warning()).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Stay signed in' }));
    expect(warning()).toBeNull();
    advance(LIMIT - WARN - 1_000);
    expect(warning()).toBeNull();
    expect(onSignOut).not.toHaveBeenCalled();
  });

  it('signs out once at the limit', () => {
    const onSignOut = setup();
    advance(LIMIT + 3_000);
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('counts user input before the warning, but not while it shows', () => {
    const onSignOut = setup();
    advance(LIMIT - WARN - 1_000);
    fireEvent.keyDown(window, { key: 'a' });
    advance(LIMIT - WARN - 1_000);
    expect(warning()).toBeNull();
    advance(2_000);
    expect(warning()).not.toBeNull();
    fireEvent.pointerMove(window);
    advance(WARN);
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('treats activity in another tab as activity here', () => {
    const onSignOut = setup();
    advance(LIMIT - WARN + 1_000);
    expect(warning()).not.toBeNull();
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
    act(() => { window.dispatchEvent(new StorageEvent('storage', { key: LAST_ACTIVITY_KEY })); });
    expect(warning()).toBeNull();
    expect(onSignOut).not.toHaveBeenCalled();
  });

  it('signs out at once when a backgrounded tab comes back after the limit', () => {
    const onSignOut = setup();
    vi.setSystemTime(Date.now() + LIMIT * 3); // timers were throttled while hidden
    act(() => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('offers "Sign out now"', () => {
    const onSignOut = setup();
    advance(LIMIT - WARN + 1_000);
    fireEvent.click(screen.getByRole('button', { name: 'Sign out now' }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});
