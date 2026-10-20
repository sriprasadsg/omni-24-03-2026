import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Keyboard } from 'lucide-react';
import { AppView } from '../types';
import { Command } from './AICommandBar';
import { CommandPalette } from './CommandPalette';
import { IdleSignOut } from './IdleSignOut';
import { Modal } from './Modal';
import { useUser } from '../contexts/UserContext';
import { useVisibleNav, openNavItems } from '../hooks/useVisibleNav';
import { useNavMemory, navMemoryKey } from '../hooks/useNavMemory';
import { resolveHashView } from '../utils/viewAccess';
import { OPEN_SHORTCUTS_EVENT } from './UserMenu';

/** "g" then a key jumps to a page (only pages the user can open). */
export const GO_TO_KEYS: { key: string; view: AppView }[] = [
    { key: 'd', view: 'dashboard' },
    { key: 'a', view: 'agents' },
    { key: 'i', view: 'assetManagement' },
    { key: 'p', view: 'patchManagement' },
    { key: 's', view: 'security' },
    { key: 'c', view: 'compliance' },
    { key: 'r', view: 'reporting' },
    { key: ',', view: 'settings' },
];

const isTyping = (target: EventTarget | null) => {
    const el = target as HTMLElement | null;
    return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
};

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const MOD = isMac ? '⌘' : 'Ctrl';

const Keys: React.FC<{ keys: string[] }> = ({ keys }) => (
    <span className="flex items-center gap-1">
        {keys.map((k, i) => (
            <kbd key={i} className="min-w-[24px] h-6 px-1.5 grid place-items-center rounded-md font-mono text-[11px] text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-white/[0.06] ring-1 ring-inset ring-gray-200 dark:ring-white/10">{k}</kbd>
        ))}
    </span>
);

interface ShellServicesProps {
    currentView: AppView;
    /** The once-per-sign-in landing has run; before that the URL hash still decides where to land. */
    landed: boolean;
    isViewingTenant: boolean;
    isPaletteOpen: boolean;
    setPaletteOpen: (open: boolean) => void;
    onNavigate: (view: AppView) => void;
    onExecuteCommand: (command: Command) => void;
    onOpenSearch: () => void;
    onToggleSidebar: () => void;
    onSignOut: () => void;
}

/**
 * Shell-wide behaviour that every screen gets: the ⌘K command palette, keyboard shortcuts ("?" and
 * "g" sequences), deep links (the URL hash follows the page, so Back/Forward, refresh and shared links
 * work), recent-page memory and a screen-reader announcement on each page change.
 */
export const ShellServices: React.FC<ShellServicesProps> = ({
    currentView, landed, isViewingTenant, isPaletteOpen, setPaletteOpen, onNavigate, onExecuteCommand,
    onOpenSearch, onToggleSidebar, onSignOut,
}) => {
    const currentUser = useUser()?.currentUser;
    const groups = useVisibleNav(isViewingTenant);
    const pages = useMemo(() => openNavItems(groups), [groups]);
    const openViews = useMemo(() => new Map(pages.map(p => [p.view, p])), [pages]);
    const { pinned, recent, togglePin, recordVisit } = useNavMemory(navMemoryKey(currentUser));
    const [shortcutsOpen, setShortcutsOpen] = useState(false);
    const [announcement, setAnnouncement] = useState('');

    // Deep links: after landing, the hash names the current page. The first write replaces the entry
    // (no extra Back step); later pages push one, and App's hashchange listener handles Back/Forward.
    useEffect(() => {
        if (!landed || resolveHashView(currentView) !== currentView) return;
        const hash = window.location.hash.slice(1);
        if (hash && resolveHashView(hash) === currentView) return;
        const url = `${window.location.pathname}${window.location.search}#${currentView}`;
        if (hash) window.history.pushState(null, '', url);
        else window.history.replaceState(window.history.state, '', url);
    }, [currentView, landed]);

    // Remember the visit and tell screen readers where they are now.
    const label = openViews.get(currentView)?.label;
    useEffect(() => {
        if (!landed || !label) return;
        recordVisit(currentView);
        setAnnouncement(`${label} page`);
    }, [currentView, landed, label, recordVisit]);

    // The account menu opens the shortcut list too.
    useEffect(() => {
        const open = () => setShortcutsOpen(true);
        window.addEventListener(OPEN_SHORTCUTS_EVENT, open);
        return () => window.removeEventListener(OPEN_SHORTCUTS_EVENT, open);
    }, []);

    // "?" opens the shortcut list; "g" then a key jumps to a page.
    const pendingG = useRef(0);
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
            if (document.querySelector('[aria-modal="true"]')) return; // an open dialog owns the keyboard
            if (e.key === '?') {
                e.preventDefault();
                setShortcutsOpen(true);
                return;
            }
            if (pendingG.current && Date.now() - pendingG.current < 1200) {
                pendingG.current = 0;
                const target = GO_TO_KEYS.find(g => g.key === e.key.toLowerCase())?.view;
                if (target && openViews.has(target)) {
                    e.preventDefault();
                    onNavigate(target);
                }
                return;
            }
            if (e.key === 'g') pendingG.current = Date.now();
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [openViews, onNavigate]);

    const goTo = GO_TO_KEYS.filter(g => openViews.has(g.view));

    return (
        <>
            <div aria-live="polite" aria-atomic="true" className="sr-only">{announcement}</div>
            <IdleSignOut />

            <CommandPalette
                isOpen={isPaletteOpen}
                onClose={() => setPaletteOpen(false)}
                currentView={currentView}
                pages={pages}
                pinned={pinned}
                recent={recent}
                onNavigate={onNavigate}
                onTogglePin={togglePin}
                onExecuteCommand={onExecuteCommand}
                onOpenSearch={onOpenSearch}
                onShowShortcuts={() => setShortcutsOpen(true)}
                onToggleSidebar={onToggleSidebar}
                onSignOut={onSignOut}
            />

            <Modal
                isOpen={shortcutsOpen}
                onClose={() => setShortcutsOpen(false)}
                title="Keyboard shortcuts"
                icon={<Keyboard className="h-5 w-5 text-primary-500" />}
                size="md"
            >
                <div className="space-y-5 text-sm">
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400 mb-2">Anywhere</h3>
                        <ul className="divide-y divide-gray-100 dark:divide-white/[0.06]">
                            {[
                                { label: 'Command palette: pages, actions, AI', keys: [MOD, 'K'] },
                                { label: 'Search records', keys: [MOD, '/'] },
                                { label: 'This list', keys: ['?'] },
                                { label: 'Close a dialog', keys: ['Esc'] },
                            ].map(row => (
                                <li key={row.label} className="flex items-center justify-between gap-4 py-2 text-gray-700 dark:text-gray-300">
                                    {row.label}<Keys keys={row.keys} />
                                </li>
                            ))}
                        </ul>
                    </section>
                    {goTo.length > 0 && (
                        <section>
                            <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400 mb-2">Go to</h3>
                            <ul className="divide-y divide-gray-100 dark:divide-white/[0.06]">
                                {goTo.map(g => (
                                    <li key={g.key} className="flex items-center justify-between gap-4 py-2 text-gray-700 dark:text-gray-300">
                                        {openViews.get(g.view)!.label}<Keys keys={['G', g.key.toUpperCase()]} />
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        Pin the page you are on from the star in the header or with “Pin” in the command palette.
                    </p>
                </div>
            </Modal>
        </>
    );
};
