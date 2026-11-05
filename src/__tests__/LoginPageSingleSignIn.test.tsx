/**
 * One sign-in is one login call: the page hands its answer to App instead of App signing in again,
 * which opened a second session and logged a second sign-in every time (found 2026-11-05).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';

const { login } = vi.hoisted(() => ({ login: vi.fn() }));
vi.mock('../../services/apiService', () => ({
  SESSION_ENDED_KEY: 'omni.sessionEnded',
  IDLE_TIMEOUT_MINUTES: 30,
  fetchSsoProviders: () => Promise.resolve({ providers: [] }),
  login: (...a: unknown[]) => login(...a),
  LoginError: class LoginError extends Error {},
}));
vi.mock('@simplewebauthn/browser', () => ({ startAuthentication: vi.fn() }));

import { LoginPage } from '../../components/LoginPage';

beforeEach(() => {
  login.mockReset();
  (window as any).matchMedia ??= () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
  (window as any).IntersectionObserver ??= class { observe() {} unobserve() {} disconnect() {} };
});

describe('LoginPage sign-in', () => {
  it('calls login once and passes its answer to onLogin', async () => {
    const answer = { success: true, access_token: 't', user: { email: 'a@b.test', role: 'viewer' } };
    login.mockResolvedValue(answer);
    const onLogin = vi.fn().mockResolvedValue(true);
    const { container } = render(<LoginPage users={[]} onLogin={onLogin} />);
    fireEvent.change(container.querySelector('input[type="email"]')!, { target: { value: 'a@b.test' } });
    fireEvent.change(container.querySelector('input[type="password"]')!, { target: { value: 'Str0ng!pass' } });
    fireEvent.submit(container.querySelector('input[type="password"]')!.closest('form')!);
    await waitFor(() => expect(onLogin).toHaveBeenCalledTimes(1));
    expect(onLogin).toHaveBeenCalledWith(answer);
    expect(login).toHaveBeenCalledTimes(1);
    expect(login).toHaveBeenCalledWith('a@b.test', 'Str0ng!pass');
  });

  it('App applies that answer without signing in again', async () => {
    const { readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    const app = readFileSync(resolve(__dirname, '../../App.tsx'), 'utf8');
    const handler = app.slice(app.indexOf('const handleLogin = async'), app.indexOf('const handleSignup = async'));
    expect(handler).toContain('const handleLogin = async (data: Awaited<ReturnType<typeof api.login>>)');
    expect(handler).not.toContain('api.login(');
  });
});
