import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pin, PinOff, Keyboard, LogOut, Laptop, Sun, Moon, PanelLeft, Search, Sparkles, CornerDownLeft, History } from 'lucide-react';
import { AppView } from '../types';
import { Command } from './AICommandBar';
import { getCommandFromQuery } from '../services/geminiService';
import { useTheme, ThemePreference } from '../contexts/ThemeProvider';
import { NavItem } from '../hooks/useVisibleNav';
import { rankItems } from '../utils/commandSearch';

type PageItem = NavItem & { group: string };

interface Entry {
    id: string;
    section: string;
    label: string;
    detail?: string;
    icon: React.ReactNode;
    keywords?: string[];
    pinned?: boolean;
    run: () => void;
}

interface CommandPaletteProps {
    isOpen: boolean;
    onClose: () => void;
    currentView: AppView;
    pages: PageItem[];          // open pages of the visible menu
    pinned: AppView[];
    recent: AppView[];
    onNavigate: (view: AppView) => void;
    onTogglePin: (view: AppView) => void;
    onExecuteCommand: (command: Command) => void;
    onOpenSearch: () => void;
    onShowShortcuts: () => void;
    onToggleSidebar: () => void;
    onSignOut: () => void;
}

const ICON = 'h-4 w-4';

/**
 * ⌘K: jump to any page you can open, run a shell action, or hand the query to the AI assistant.
 * Pages and actions match locally and instantly; the AI is the last row, never the only path.
 */
export const CommandPalette: React.FC<CommandPaletteProps> = ({
    isOpen, onClose, currentView, pages, pinned, recent, onNavigate, onTogglePin, onExecuteCommand,
    onOpenSearch, onShowShortcuts, onToggleSidebar, onSignOut,
}) => {
    const { themePreference, setThemePreference } = useTheme();
    const [query, setQuery] = useState('');
    const [active, setActive] = useState(0);
    const [aiState, setAiState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null });
    const inputRef = useRef<HTMLInputElement>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const returnFocusRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
        if (!isOpen) return;
        returnFocusRef.current = document.activeElement as HTMLElement | null;
        setQuery('');
        setActive(0);
        setAiState({ loading: false, error: null });
        const id = requestAnimationFrame(() => inputRef.current?.focus());
        return () => {
            cancelAnimationFrame(id);
            returnFocusRef.current?.focus?.();
        };
    }, [isOpen]);

    const byView = useMemo(() => new Map(pages.map(p => [p.view, p])), [pages]);
    const currentPage = byView.get(currentView);

    const go = (view: AppView) => { onClose(); onNavigate(view); };
    const pageEntry = (section: string) => (p: PageItem): Entry => ({
        id: `${section}-${p.view}`, section, label: p.label, detail: p.group, icon: p.icon,
        pinned: pinned.includes(p.view), run: () => go(p.view),
    });

    const actions: Entry[] = useMemo(() => {
        const theme = (pref: ThemePreference, label: string, icon: React.ReactNode): Entry => ({
            id: `theme-${pref}`, section: 'Actions', label, icon, keywords: ['theme', 'appearance', 'mode', pref],
            detail: themePreference === pref ? 'Current' : undefined,
            run: () => { setThemePreference(pref); onClose(); },
        });
        const list: Entry[] = [];
        if (currentPage) {
            const isPinned = pinned.includes(currentPage.view);
            list.push({
                id: 'pin-current', section: 'Actions', label: `${isPinned ? 'Unpin' : 'Pin'} “${currentPage.label}”`,
                icon: isPinned ? <PinOff className={ICON} /> : <Pin className={ICON} />, keywords: ['pin', 'favourite', 'favorite', 'bookmark'],
                run: () => { onTogglePin(currentPage.view); onClose(); },
            });
        }
        list.push(
            { id: 'search-data', section: 'Actions', label: 'Search records…', detail: '⌘/', icon: <Search className={ICON} />, keywords: ['find', 'data', 'global'], run: () => { onClose(); onOpenSearch(); } },
            { id: 'shortcuts', section: 'Actions', label: 'Keyboard shortcuts', detail: '?', icon: <Keyboard className={ICON} />, keywords: ['keys', 'help', 'hotkeys'], run: () => { onClose(); onShowShortcuts(); } },
            { id: 'sidebar', section: 'Actions', label: 'Collapse or expand the sidebar', icon: <PanelLeft className={ICON} />, keywords: ['menu', 'navigation', 'toggle'], run: () => { onToggleSidebar(); onClose(); } },
            theme('system', 'Theme: match system', <Laptop className={ICON} />),
            theme('dark', 'Theme: dark', <Moon className={ICON} />),
            theme('light', 'Theme: light', <Sun className={ICON} />),
            { id: 'sign-out', section: 'Actions', label: 'Sign out', icon: <LogOut className={ICON} />, keywords: ['logout', 'log out', 'exit'], run: () => { onClose(); onSignOut(); } },
        );
        return list;
    }, [currentPage, pinned, themePreference, setThemePreference, onClose, onTogglePin, onOpenSearch, onShowShortcuts, onToggleSidebar, onSignOut]);

    const askAI = async (text: string) => {
        setAiState({ loading: true, error: null });
        try {
            const commands = await getCommandFromQuery(text);
            // The model answers with a view name; only follow it to a page this user can open.
            const usable = commands.filter(c => c.name !== 'navigateToView' || byView.has(c.args?.view));
            if (usable.length === 0) {
                setAiState({ loading: false, error: commands.length ? 'The assistant suggested a page you can’t open.' : 'The assistant couldn’t turn that into an action. Try a page name.' });
                return;
            }
            onClose();
            usable.forEach(c => onExecuteCommand(c));
        } catch {
            setAiState({ loading: false, error: 'The AI assistant isn’t reachable right now. Page and action search still work.' });
        }
    };

    const entries: Entry[] = useMemo(() => {
        const q = query.trim();
        if (!q) {
            const pinnedPages = pinned.map(v => byView.get(v)).filter((p): p is PageItem => !!p).map(pageEntry('Pinned'));
            const recentPages = recent.filter(v => v !== currentView && !pinned.includes(v))
                .map(v => byView.get(v)).filter((p): p is PageItem => !!p).slice(0, 5).map(pageEntry('Recent'));
            return [...pinnedPages, ...recentPages, ...actions];
        }
        const matchedPages = rankItems(q, pages, 8).map(pageEntry('Pages'));
        const matchedActions = rankItems(q, actions, 4);
        const ai: Entry = {
            id: 'ask-ai', section: 'Ask AI', label: `Ask AI: “${q}”`, icon: <Sparkles className={ICON} />,
            run: () => { void askAI(q); },
        };
        return [...matchedPages, ...matchedActions, ai];
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query, pages, pinned, recent, currentView, actions, byView]);

    useEffect(() => { setActive(0); }, [query]);
    useEffect(() => {
        const row = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
        row?.scrollIntoView?.({ block: 'nearest' });
    }, [active]);

    if (!isOpen) return null;

    const onKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, entries.length - 1)); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
        else if (e.key === 'Home') { e.preventDefault(); setActive(0); }
        else if (e.key === 'End') { e.preventDefault(); setActive(entries.length - 1); }
        else if (e.key === 'Enter') { e.preventDefault(); if (!aiState.loading) entries[active]?.run(); }
        else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
        else if (e.key === 'Tab') { e.preventDefault(); } // focus stays in the palette
    };

    const listId = 'command-palette-list';
    let lastSection = '';

    return (
        <div className="fixed inset-0 z-[70] flex justify-center items-start px-4 pt-[12vh] bg-black/50 backdrop-blur-sm fade-in" onMouseDown={onClose}>
            <div
                role="dialog"
                aria-modal="true"
                aria-label="Command palette"
                className="w-full max-w-xl glass-strong rounded-3xl overflow-hidden slide-up"
                onMouseDown={e => e.stopPropagation()}
                onKeyDown={onKeyDown}
            >
                <div className="flex items-center gap-3 px-4 h-14 border-b border-gray-900/[0.06] dark:border-white/[0.08]">
                    <Search className="h-[18px] w-[18px] text-primary-600 dark:text-primary-400 flex-shrink-0" aria-hidden="true" />
                    <input
                        ref={inputRef}
                        value={query}
                        onChange={e => { setQuery(e.target.value); setAiState({ loading: false, error: null }); }}
                        placeholder="Go to a page, run a command or ask AI…"
                        role="combobox"
                        aria-expanded="true"
                        aria-controls={listId}
                        aria-activedescendant={entries[active] ? `cp-${entries[active].id}` : undefined}
                        aria-autocomplete="list"
                        className="flex-1 bg-transparent text-[15px] text-gray-900 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 outline-none focus-visible:outline-none"
                        style={{ outline: 'none' }}
                    />
                    <kbd className="hidden sm:inline font-mono text-[11px] px-1.5 py-0.5 rounded-md text-gray-500 dark:text-gray-400 border border-gray-900/10 dark:border-white/10">esc</kbd>
                </div>

                {/* Under the input, not after the last row: a long list would scroll it out of sight. */}
                {aiState.error && (
                    <p role="alert" className="mx-3 mt-3 px-3 py-2 rounded-xl text-xs text-amber-800 dark:text-amber-300 bg-amber-500/10 ring-1 ring-inset ring-amber-500/20">{aiState.error}</p>
                )}

                <div ref={listRef} id={listId} role="listbox" aria-label="Results" className="max-h-[min(60vh,440px)] overflow-y-auto p-2">
                    {entries.map((entry, index) => {
                        const heading = entry.section !== lastSection ? entry.section : null;
                        lastSection = entry.section;
                        const isActive = index === active;
                        return (
                            <React.Fragment key={entry.id}>
                                {heading && (
                                    <div role="presentation" className="px-3 pt-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                                        {heading === 'Recent' && <History className="h-3 w-3" aria-hidden="true" />}
                                        {heading}
                                    </div>
                                )}
                                <div
                                    id={`cp-${entry.id}`}
                                    role="option"
                                    aria-selected={isActive}
                                    data-index={index}
                                    onMouseMove={() => setActive(index)}
                                    onClick={() => !aiState.loading && entry.run()}
                                    className={`flex items-center gap-3 px-3 h-11 rounded-xl cursor-pointer select-none transition-colors ${isActive
                                        ? 'bg-primary-500/10 text-gray-900 dark:text-white ring-1 ring-inset ring-primary-500/25'
                                        : 'text-gray-700 dark:text-gray-300'}`}
                                >
                                    <span className={`grid place-items-center h-7 w-7 flex-shrink-0 rounded-lg [&_svg]:h-4 [&_svg]:w-4 ${isActive ? 'text-primary-600 dark:text-primary-400 bg-primary-500/10' : 'text-gray-500 dark:text-gray-400 bg-gray-900/[0.04] dark:bg-white/[0.05]'}`}>
                                        {entry.id === 'ask-ai' && aiState.loading ? <span className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" /> : entry.icon}
                                    </span>
                                    <span className="flex-1 truncate text-sm font-medium">{entry.label}</span>
                                    {entry.pinned && <Pin className="h-3.5 w-3.5 text-primary-500 flex-shrink-0" aria-label="Pinned" />}
                                    {entry.detail && <span className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[40%]">{entry.detail}</span>}
                                    {isActive && <CornerDownLeft className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" aria-hidden="true" />}
                                </div>
                            </React.Fragment>
                        );
                    })}
                </div>

                <div className="hidden sm:flex items-center gap-4 px-4 h-10 border-t border-gray-900/[0.06] dark:border-white/[0.08] text-[11px] text-gray-500 dark:text-gray-400">
                    <span><kbd className="font-mono">↑↓</kbd> move</span>
                    <span><kbd className="font-mono">↵</kbd> open</span>
                    <span><kbd className="font-mono">?</kbd> all shortcuts</span>
                    <span className="ml-auto">{pages.length} pages available</span>
                </div>
            </div>
        </div>
    );
};
