/**
 * Phase 77 (ACC-08, D-08): a 403 or a window focus re-reads permissions. The 403 signal is a
 * leading-plus-trailing 15 s debounce so a burst of denials never storms /api/auth/me and the last
 * denial is never left without a refresh.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  PERMISSION_DENIED_EVENT,
  PERMISSION_DENIED_WINDOW_MS,
  shouldSignalPermissionDenied,
  notifyPermissionDenied,
  _resetPermissionDeniedForTests,
  samePermissionSet,
  lostAccess,
} from '../../utils/permissionRefresh';
import type { User } from '../../types';

const mk = (permissions: string[]): User =>
  ({ id: 'u1', name: 'U', email: 'u@x.test', role: 'Custom', tenantId: 't1', permissions }) as unknown as User;

describe('shouldSignalPermissionDenied', () => {
  it('signals only a plain 403 outside /api/auth/', () => {
    expect(shouldSignalPermissionDenied('/api/assets', 403, null)).toBe(true);
    expect(shouldSignalPermissionDenied('/api/auth/me', 403, null)).toBe(false);
    expect(shouldSignalPermissionDenied('/api/assets', 403, '1')).toBe(false);
    expect(shouldSignalPermissionDenied('/api/assets', 404, null)).toBe(false);
    expect(shouldSignalPermissionDenied('/api/assets', 500, null)).toBe(false);
  });
});

describe('notifyPermissionDenied (leading plus trailing debounce)', () => {
  let events: number;
  const onEvent = () => { events += 1; };
  beforeEach(() => {
    vi.useFakeTimers();
    events = 0;
    _resetPermissionDeniedForTests();
    window.addEventListener(PERMISSION_DENIED_EVENT, onEvent);
  });
  afterEach(() => {
    window.removeEventListener(PERMISSION_DENIED_EVENT, onEvent);
    _resetPermissionDeniedForTests();
    vi.useRealTimers();
  });

  it('uses the omni:permission-denied event and a 15 s window', () => {
    expect(PERMISSION_DENIED_EVENT).toBe('omni:permission-denied');
    expect(PERMISSION_DENIED_WINDOW_MS).toBe(15000);
  });

  it('a single call dispatches exactly one event and no trailing event', () => {
    notifyPermissionDenied();
    expect(events).toBe(1);
    vi.advanceTimersByTime(PERMISSION_DENIED_WINDOW_MS + 1000);
    expect(events).toBe(1);
  });

  it('a burst dispatches once at once and once more at the end of the window', () => {
    notifyPermissionDenied();
    vi.advanceTimersByTime(5000);
    notifyPermissionDenied();
    vi.advanceTimersByTime(5000);
    notifyPermissionDenied();
    expect(events).toBe(1);
    vi.advanceTimersByTime(4999);
    expect(events).toBe(1);
    vi.advanceTimersByTime(1);
    expect(events).toBe(2);
    vi.advanceTimersByTime(60000);
    expect(events).toBe(2);
  });

  it('a new call after the window starts a new window and dispatches immediately', () => {
    notifyPermissionDenied();
    notifyPermissionDenied();
    vi.advanceTimersByTime(PERMISSION_DENIED_WINDOW_MS);
    expect(events).toBe(2);
    notifyPermissionDenied();
    expect(events).toBe(3);
  });
});

describe('authFetch 403 signal', () => {
  let events: number;
  const onEvent = () => { events += 1; };
  beforeEach(() => {
    vi.useFakeTimers();
    events = 0;
    _resetPermissionDeniedForTests();
    window.addEventListener(PERMISSION_DENIED_EVENT, onEvent);
  });
  afterEach(() => {
    window.removeEventListener(PERMISSION_DENIED_EVENT, onEvent);
    _resetPermissionDeniedForTests();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('dispatches once on a 403 from /api/assets and nothing on /api/auth/me', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 403 })));
    const { authFetch } = await import('../../services/apiService');
    const res = await authFetch('/api/assets');
    expect(res.status).toBe(403);
    expect(events).toBe(1);
    _resetPermissionDeniedForTests();
    events = 0;
    await authFetch('/api/auth/me');
    expect(events).toBe(0);
  });
});

describe('samePermissionSet', () => {
  it('is order-insensitive and detects differences', () => {
    expect(samePermissionSet(['a', 'b'], ['b', 'a'])).toBe(true);
    expect(samePermissionSet(['a'], ['a', 'b'])).toBe(false);
  });
});

describe('lostAccess', () => {
  it('is true only when the view was allowed before and is denied after', () => {
    const withItam = mk(['view:itam']);
    const without = mk(['view:dashboard']);
    expect(lostAccess('itam', withItam, without)).toBe(true);
    expect(lostAccess('itam', without, withItam)).toBe(false);
    expect(lostAccess('dashboard', mk(['view:dashboard', 'view:itam']), without)).toBe(false);
  });
});
