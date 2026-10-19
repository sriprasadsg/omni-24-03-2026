/**
 * Account menu: sign-out goes through the app's logout (server revokes the session) and keeps the
 * user's saved preferences; Appearance sets the theme and table density; shortcuts open from here.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { UserMenu, OPEN_SHORTCUTS_EVENT } from '../../components/UserMenu';
import { ThemeProvider } from '../../contexts/ThemeProvider';
import { UserContext } from '../../contexts/UserContext';

const user = { id: 'u', name: 'Ava Chen', email: 'ava@x.test', role: 'Tenant Admin', tenantId: 't' } as any;

function renderMenu(logout = vi.fn()) {
  render(
    <ThemeProvider>
      <UserContext.Provider value={{ currentUser: user, logout } as any}>
        <UserMenu allUsers={[]} setCurrentView={vi.fn()} />
      </UserContext.Provider>
    </ThemeProvider>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Account and appearance' }));
  return logout;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = '';
});

describe('UserMenu', () => {
  it('signs out through the app and keeps saved preferences', () => {
    localStorage.setItem('omni.nav.pinned.ava@x.test|t', '["agents"]');
    const logout = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('omni.nav.pinned.ava@x.test|t')).toBe('["agents"]');
  });

  it('sets the theme and the table density from Appearance', () => {
    renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Light' }));
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(screen.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Compact' }));
    expect(document.documentElement.classList.contains('density-compact')).toBe(true);
    expect(localStorage.getItem('app-density')).toBe('compact');
    fireEvent.click(screen.getByRole('button', { name: 'Comfortable' }));
    expect(document.documentElement.classList.contains('density-compact')).toBe(false);
  });

  it('opens the keyboard shortcuts and closes on Escape', () => {
    const heard = vi.fn();
    window.addEventListener(OPEN_SHORTCUTS_EVENT, heard);
    renderMenu();
    fireEvent.click(screen.getByRole('button', { name: /Keyboard shortcuts/ }));
    expect(heard).toHaveBeenCalledTimes(1);
    window.removeEventListener(OPEN_SHORTCUTS_EVENT, heard);
    fireEvent.click(screen.getByRole('button', { name: 'Account and appearance' }));
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
  });
});
