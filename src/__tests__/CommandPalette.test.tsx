/**
 * 2030 shell: the ⌘K palette navigates locally and instantly; the AI is a fallback row that may only
 * send the user to a page they can open. Pinned/recent memory survives storage that throws.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, renderHook } from '@testing-library/react';

const getCommandFromQuery = vi.fn();
vi.mock('../../services/geminiService', () => ({ getCommandFromQuery: (q: string) => getCommandFromQuery(q) }));

import { CommandPalette } from '../../components/CommandPalette';
import { ThemeProvider } from '../../contexts/ThemeProvider';
import { rankItems, scoreItem } from '../../utils/commandSearch';
import { useNavMemory } from '../../hooks/useNavMemory';

const page = (view: string, label: string, group = 'Infrastructure & Assets') =>
  ({ view, label, group, icon: null, permission: 'view:x' }) as any;
const PAGES = [
  page('dashboard', 'Overview', 'Dashboards & Insights'),
  page('agents', 'Agents'),
  page('assetManagement', 'Assets'),
  page('itam', 'IT Asset Management'),
  page('assetIntelligence', 'Asset Intelligence'),
  page('patchManagement', 'Patching'),
];

function renderPalette(over: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  const props = {
    isOpen: true, onClose: vi.fn(), currentView: 'dashboard' as any, pages: PAGES, pinned: [], recent: [],
    onNavigate: vi.fn(), onTogglePin: vi.fn(), onExecuteCommand: vi.fn(), onOpenSearch: vi.fn(),
    onShowShortcuts: vi.fn(), onToggleSidebar: vi.fn(), onSignOut: vi.fn(), ...over,
  };
  render(<ThemeProvider><CommandPalette {...props} /></ThemeProvider>);
  return props;
}

const input = () => screen.getByRole('combobox');
const options = () => screen.getAllByRole('option').map(o => o.textContent ?? '');

beforeEach(() => {
  getCommandFromQuery.mockReset();
  localStorage.clear();
});

describe('commandSearch', () => {
  it('ranks the exact page above longer pages that merely contain the word', () => {
    expect(rankItems('assets', PAGES).map(p => p.label)[0]).toBe('Assets');
  });
  it('ignores a "go to" prefix and needs every word to match', () => {
    expect(rankItems('go to patching', PAGES).map(p => p.label)).toEqual(['Patching']);
    expect(rankItems('asset intel', PAGES).map(p => p.label)).toEqual(['Asset Intelligence']);
  });
  it('lists only name matches when a name matches, and the whole group when only the group does', () => {
    expect(rankItems('asset', PAGES).map(p => p.label)).toEqual(['Assets', 'Asset Intelligence', 'IT Asset Management']);
    expect(rankItems('infrastructure', PAGES).map(p => p.view).sort()).toEqual(['agents', 'assetIntelligence', 'assetManagement', 'itam', 'patchManagement']);
  });
  it('accepts in-order letters and rejects what does not match at all', () => {
    expect(scoreItem('ptch', PAGES[5])).toBeGreaterThan(0);
    expect(rankItems('kubernetes', PAGES)).toEqual([]);
  });
});

describe('CommandPalette', () => {
  it('opens a page from the keyboard without calling the AI', () => {
    const props = renderPalette();
    fireEvent.change(input(), { target: { value: 'assets' } });
    expect(options()[0]).toContain('Assets');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(props.onNavigate).toHaveBeenCalledWith('assetManagement');
    expect(props.onClose).toHaveBeenCalled();
    expect(getCommandFromQuery).not.toHaveBeenCalled();
  });

  it('moves the selection with the arrow keys', () => {
    const props = renderPalette();
    fireEvent.change(input(), { target: { value: 'asset' } });
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(props.onNavigate).toHaveBeenCalledTimes(1);
    expect((props.onNavigate as ReturnType<typeof vi.fn>).mock.calls[0][0]).not.toBe(rankItems('asset', PAGES)[0].view);
  });

  it('lists pinned and recent pages only when they are still open to the user', () => {
    renderPalette({ pinned: ['patchManagement', 'settings'] as any, recent: ['agents', 'tenantManagement'] as any });
    expect(screen.getByText('Pinned')).toBeInTheDocument();
    expect(screen.getByText('Recent')).toBeInTheDocument();
    const rows = options();
    expect(rows.some(r => r.includes('Patching'))).toBe(true);
    expect(rows.some(r => r.includes('Agents'))).toBe(true);
    expect(rows.some(r => /settings|tenant/i.test(r) && !r.includes('Theme'))).toBe(false);
  });

  it('always offers "Ask AI" as the last row for a typed query', () => {
    renderPalette();
    fireEvent.change(input(), { target: { value: 'which hosts need patches' } });
    expect(options().at(-1)).toContain('Ask AI');
  });

  it('refuses an AI answer that points at a page the user cannot open', async () => {
    getCommandFromQuery.mockResolvedValue([{ name: 'navigateToView', args: { view: 'settings' } }]);
    const props = renderPalette();
    fireEvent.change(input(), { target: { value: 'open settings please' } });
    fireEvent.keyDown(input(), { key: 'End' });
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(await screen.findByRole('alert')).toHaveTextContent('page you can’t open');
    expect(props.onExecuteCommand).not.toHaveBeenCalled();
  });

  it('runs an AI answer that names an open page', async () => {
    getCommandFromQuery.mockResolvedValue([{ name: 'navigateToView', args: { view: 'agents' } }]);
    const props = renderPalette();
    fireEvent.change(input(), { target: { value: 'show me my endpoints' } });
    fireEvent.keyDown(input(), { key: 'End' });
    fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(props.onExecuteCommand).toHaveBeenCalledWith({ name: 'navigateToView', args: { view: 'agents' } }));
  });

  it('says the AI is unreachable without breaking page search', async () => {
    getCommandFromQuery.mockRejectedValue(new Error('down'));
    renderPalette();
    fireEvent.change(input(), { target: { value: 'zzz' } });
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t reachable');
    fireEvent.change(input(), { target: { value: 'agents' } });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(options()[0]).toContain('Agents');
  });

  it('pins the current page from the actions list', () => {
    const props = renderPalette({ currentView: 'agents' as any });
    fireEvent.click(screen.getByText('Pin “Agents”'));
    expect(props.onTogglePin).toHaveBeenCalledWith('agents');
  });
});

describe('useNavMemory', () => {
  it('keeps pins and recents per user and puts the newest visit first', () => {
    const { result } = renderHook(() => useNavMemory('ava@x|t1'));
    act(() => result.current.togglePin('agents' as any));
    act(() => result.current.recordVisit('dashboard' as any));
    act(() => result.current.recordVisit('agents' as any));
    expect(result.current.pinned).toEqual(['agents']);
    expect(result.current.recent).toEqual(['agents', 'dashboard']);
    const other = renderHook(() => useNavMemory('bo@x|t2'));
    expect(other.result.current.pinned).toEqual([]);
    act(() => result.current.togglePin('agents' as any));
    expect(result.current.pinned).toEqual([]);
  });

  it('still works when storage throws', () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    const { result } = renderHook(() => useNavMemory('ava@x|t1'));
    act(() => result.current.recordVisit('agents' as any));
    expect(result.current.pinned).toEqual([]);
    get.mockRestore();
    set.mockRestore();
  });
});
