

import React, { useContext, useState } from 'react';
import { useTheme, ThemeId } from '../contexts/ThemeProvider';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { SunIcon, MoonIcon, BotIcon, HelpCircleIcon, InfoIcon } from './icons';
import { User, Notification, AppView } from '../types';
import { UserMenu } from './UserMenu';
import NotificationCenter from './NotificationCenter';
import ToastContainer from './ToastContainer';
import { FeatureHelpModal } from './FeatureHelpModal';
import { NAV_GROUPS, catalogueFor } from '../utils/catalogueAccess';
import { AppView as View } from '../types';

const ICON_BUTTON = 'grid place-items-center h-9 w-9 rounded-xl text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.07] transition-colors';

interface HeaderProps {
    allUsers: User[];
    onToggleSidebar: () => void;
    onOpenCommandBar: () => void;
    onOpenSearch?: () => void;
    setCurrentView: (view: AppView) => void;
    onStartTour: () => void;
    currentView?: string;
}

export const Header: React.FC<HeaderProps> = ({ allUsers, onToggleSidebar, onOpenCommandBar, onOpenSearch, setCurrentView, onStartTour, currentView = 'dashboard' }) => {
    const { themeId, setThemeId, isDarkMode, toggleDarkMode } = useTheme();
    const { timeZone, setTimeZone, availableTimeZones } = useTimeZone();
    const [isHelpOpen, setIsHelpOpen] = useState(false);

    // Theme selector removed


    return (
        <>
        <header className="z-50 flex-shrink-0 glass-panel rounded-2xl">
            <div className="flex items-center justify-between gap-3 h-14 px-3 sm:px-4">
                <div className="flex items-center gap-2 min-w-0">
                    <button onClick={onToggleSidebar} className={`${ICON_BUTTON} -ml-1`} aria-label="Toggle navigation">
                        <svg className="h-5 w-5" stroke="currentColor" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h10M4 18h16" />
                        </svg>
                    </button>
                    {(() => {
                        const entry = catalogueFor(currentView as View);
                        const group = NAV_GROUPS.find(g => g.items.some(i => i.view === currentView));
                        return (
                            <nav aria-label="Breadcrumb" className="hidden sm:flex items-center gap-2 min-w-0 text-sm">
                                {group && <span className="truncate text-gray-500 dark:text-gray-400">{group.title}</span>}
                                {group && <span aria-hidden="true" className="text-gray-300 dark:text-gray-600">/</span>}
                                <span className="truncate font-semibold text-gray-900 dark:text-white">{entry?.label ?? 'Omni-Agent AI'}</span>
                            </nav>
                        );
                    })()}
                </div>

                <button
                    onClick={onOpenCommandBar}
                    className="group hidden md:flex items-center gap-3 flex-1 max-w-md h-10 px-3.5 rounded-xl text-sm text-gray-500 dark:text-gray-400 bg-gray-900/[0.04] dark:bg-white/[0.04] border border-gray-900/[0.06] dark:border-white/[0.08] hover:border-primary-500/40 dark:hover:border-primary-400/40 hover:shadow-[0_0_0_4px_rgb(34_211_238/0.08)] transition-all"
                    aria-label="Open AI Command Bar"
                >
                    <span aria-hidden="true" className="grid place-items-center h-6 w-6 rounded-lg bg-gradient-to-br from-primary-400 to-blue-500 text-white shadow-[0_0_12px_-2px_rgb(34_211_238/0.7)]">
                        <BotIcon size={14} />
                    </span>
                    <span className="flex-1 text-left truncate">Ask AI or run a command…</span>
                    <kbd className="font-mono text-[11px] px-1.5 py-0.5 rounded-md text-gray-500 dark:text-gray-400 border border-gray-900/10 dark:border-white/10">⌘K</kbd>
                </button>

                <div className="flex items-center gap-1">
                    {onOpenSearch && (
                        <button onClick={onOpenSearch} className={`${ICON_BUTTON} hidden sm:grid`} aria-label="Open Global Search" title="Search (⌘/)">
                            <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true">
                                <circle cx="11" cy="11" r="7" /><path strokeLinecap="round" d="m20 20-3.5-3.5" />
                            </svg>
                        </button>
                    )}
                    <button onClick={onOpenCommandBar} className={`${ICON_BUTTON} md:hidden`} aria-label="Open AI Command Bar (compact)">
                        <BotIcon size={17} />
                    </button>
                    <div className="hidden lg:block">
                        <select
                            value={timeZone}
                            onChange={(e) => setTimeZone(e.target.value)}
                            className="h-9 max-w-[8.5rem] text-xs rounded-xl px-2.5 text-gray-600 dark:text-gray-300 bg-transparent border border-gray-900/[0.08] dark:border-white/[0.08] focus:outline-none focus:ring-2 focus:ring-primary-500/50 cursor-pointer"
                            aria-label="Select Timezone"
                        >
                            {availableTimeZones.map(tz => (
                                <option key={tz} value={tz}>{tz.replace('_', ' ')}</option>
                            ))}
                        </select>
                    </div>
                    <button onClick={toggleDarkMode} className={ICON_BUTTON} aria-label="Toggle dark mode" title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}>
                        {isDarkMode ? <MoonIcon size={17} /> : <SunIcon size={17} />}
                    </button>
                    <button onClick={onStartTour} className={`${ICON_BUTTON} hidden sm:grid`} aria-label="Start guided tour">
                        <HelpCircleIcon size={17} />
                    </button>
                    <button onClick={() => setIsHelpOpen(true)} className={ICON_BUTTON} aria-label="Feature help" title="What does this page do?">
                        <InfoIcon size={17} />
                    </button>
                    <NotificationCenter />
                    <div aria-hidden="true" className="h-6 w-px mx-1 bg-gray-900/10 dark:bg-white/10 hidden sm:block" />
                    <UserMenu allUsers={allUsers} setCurrentView={setCurrentView} />
                </div>
            </div>
        </header>
        <ToastContainer />
        <FeatureHelpModal
            isOpen={isHelpOpen}
            onClose={() => setIsHelpOpen(false)}
            featureKey={currentView}
        />
        </>
    );
};
