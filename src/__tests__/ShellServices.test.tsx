/**
 * 2030 shell: deep links (the hash follows the page once landing has run), "g" shortcuts limited to
 * pages the user can open, the "?" shortcut sheet, page-change announcements and the System theme.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

vi.mock('../../services/geminiService', () => ({ getCommandFromQuery: vi.fn() }));
vi.mock('../../services/apiService', () => ({ authFetch: vi.fn(), fetchSupportUnreadCount: () => Promise.resolve(0), API_BASE: '/api', IDLE_TIMEOUT_MINUTES: 30, endSessionForInactivity: vi.fn() }));
vi.mock('../../services/socketService', () => ({ socketService: { on: vi.fn(), off: vi.fn() } }));

import { ShellServices } from '../../components/ShellServices';
import { Sidebar } from '../../components/Sidebar';
import { ThemeProvider, useTheme } from '../../contexts/ThemeProvider';
import { UserContext } from '../../contexts/UserContext';

const user = { id: 'u', name: 'T', email: 't@x', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: ['view:dashboard', 'view:agents', 'view:assets'] } as any;
const userCtx = { currentUser: user, hasPermission: (p: string) => user.permissions.includes(p) } as any;

function renderShell(props: Partial<React.ComponentProps<typeof ShellServices>> = {}) {
  const all = {
    currentView: 'dashboard' as any, landed: true, isViewingTenant: false, isPaletteOpen: false,
    setPaletteOpen: vi.fn(), onNavigate: vi.fn(), onExecuteCommand: vi.fn(), onOpenSearch: vi.fn(),
    onToggleSidebar: vi.fn(), onSignOut: vi.fn(), ...props,
  };
  const ui = (p: typeof all) => (
    <ThemeProvider><UserContext.Provider value={userCtx}><ShellServices {...p} /></UserContext.Provider></ThemeProvider>
  );
  const r = render(ui(all));
  return { ...all, rerender: (next: Partial<typeof all>) => r.rerender(ui({ ...all, ...next })) };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  localStorage.clear();
});

describe('deep links', () => {
  it('writes the page into the hash after landing: replace first, then push', () => {
    const before = window.history.length;
    const shell = renderShell({ currentView: 'dashboard' as any });
    expect(window.location.hash).toBe('#dashboard');
    expect(window.history.length).toBe(before);
    shell.rerender({ currentView: 'agents' as any });
    expect(window.location.hash).toBe('#agents');
    expect(window.history.length).toBe(before + 1);
  });

  it('leaves the hash alone until landing has run, and keeps an alias that already names the page', () => {
    window.history.replaceState(null, '', '/#assets');
    const shell = renderShell({ currentView: 'dashboard' as any, landed: false });
    expect(window.location.hash).toBe('#assets');
    shell.rerender({ currentView: 'assetManagement' as any, landed: true });
    expect(window.location.hash).toBe('#assets');
  });
});

describe('keyboard', () => {
  it('"g" then a key opens an allowed page and ignores a page the user cannot open', () => {
    const shell = renderShell();
    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 'i' });
    expect(shell.onNavigate).toHaveBeenCalledWith('assetManagement');
    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 's' });
    expect(shell.onNavigate).toHaveBeenCalledTimes(1);
  });

  it('ignores shortcuts typed into a field', () => {
    const shell = renderShell();
    const field = document.createElement('input');
    document.body.appendChild(field);
    fireEvent.keyDown(field, { key: 'g' });
    fireEvent.keyDown(field, { key: 'd' });
    fireEvent.keyDown(field, { key: '?' });
    expect(shell.onNavigate).not.toHaveBeenCalled();
    expect(screen.queryByText('Keyboard shortcuts')).toBeNull();
    field.remove();
  });

  it('"?" lists the shortcuts, with only the go-to pages this user can open', () => {
    renderShell();
    fireEvent.keyDown(window, { key: '?' });
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument();
    expect(screen.getByText('Assets')).toBeInTheDocument();
    expect(screen.queryByText('Security Overview')).toBeNull();
  });
});

describe('announcements and memory', () => {
  it('announces the page and remembers it as a recent visit', () => {
    const shell = renderShell({ currentView: 'dashboard' as any });
    shell.rerender({ currentView: 'agents' as any });
    expect(screen.getByText('Agents page')).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem('omni.nav.recent.t@x|tenant-a') ?? '[]')).toEqual(['agents', 'dashboard']);
  });

  it('shows a pinned page in the sidebar only while it is open to the user', () => {
    localStorage.setItem('omni.nav.pinned.t@x|tenant-a', JSON.stringify(['agents', 'settings']));
    render(
      <UserContext.Provider value={userCtx}>
        <Sidebar isOpen currentView="dashboard" setCurrentView={() => {}} isViewingTenant={false} onBackToTenants={() => {}} />
      </UserContext.Provider>,
    );
    const pinned = screen.getByRole('group', { name: 'Pinned pages' });
    expect(pinned.textContent).toContain('Agents');
    expect(pinned.textContent).not.toContain('Settings');
  });
});

describe('theme preference', () => {
  const Probe = () => {
    const { themePreference, setThemePreference, isDarkMode } = useTheme();
    return <button onClick={() => setThemePreference('system')}>{themePreference}:{String(isDarkMode)}</button>;
  };

  it('keeps an earlier light choice, and "system" follows the OS live', () => {
    localStorage.setItem('app-dark-mode', 'false');
    let listener: ((e: { matches: boolean }) => void) | undefined;
    const mql = { matches: true, addEventListener: (_: string, fn: any) => { listener = fn; }, removeEventListener: vi.fn() };
    const original = window.matchMedia;
    (window as any).matchMedia = vi.fn(() => mql);
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByRole('button')).toHaveTextContent('light:false');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('button')).toHaveTextContent('system:true');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    act(() => listener?.({ matches: false }));
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(localStorage.getItem('app-theme-preference')).toBe('system');
    (window as any).matchMedia = original;
  });
});
