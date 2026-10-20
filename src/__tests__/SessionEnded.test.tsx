/**
 * When a session ends on its own the login screen says why, once, without the red error styling.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  SESSION_ENDED_KEY: 'omni.sessionEnded',
  IDLE_TIMEOUT_MINUTES: 30,
  fetchSsoProviders: () => Promise.resolve({ providers: [] }),
}));
vi.mock('@simplewebauthn/browser', () => ({ startAuthentication: vi.fn() }));

import { LoginPage } from '../../components/LoginPage';

const NOTICE = /Your session ended, so you were signed out/;

beforeEach(() => {
  sessionStorage.clear();
  // jsdom has neither; the login page's reveal animation asks for both.
  (window as any).matchMedia ??= () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
  (window as any).IntersectionObserver ??= class { observe() {} unobserve() {} disconnect() {} };
});

describe('session-ended notice', () => {
  it('shows once after the session ended, then is forgotten', () => {
    sessionStorage.setItem('omni.sessionEnded', '1');
    const first = render(<LoginPage users={[]} />);
    expect(screen.getByRole('status')).toHaveTextContent(NOTICE);
    expect(sessionStorage.getItem('omni.sessionEnded')).toBeNull();
    first.unmount();
    render(<LoginPage users={[]} />);
    expect(screen.queryByText(NOTICE)).toBeNull();
  });

  it('names inactivity when the idle timer ended the session', () => {
    sessionStorage.setItem('omni.sessionEnded', 'idle');
    render(<LoginPage users={[]} />);
    expect(screen.getByRole('status')).toHaveTextContent('signed out after 30 minutes without activity');
  });

  it('stays hidden on an ordinary visit to the login page', () => {
    render(<LoginPage users={[]} />);
    expect(screen.queryByText(NOTICE)).toBeNull();
  });
});
