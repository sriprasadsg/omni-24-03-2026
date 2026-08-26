

import React, { useContext, useState } from 'react';
import { useTheme, ThemeId } from '../contexts/ThemeProvider';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { SunIcon, MoonIcon, BotIcon, HelpCircleIcon, InfoIcon } from './icons';
import { User, Notification, AppView } from '../types';
import { UserMenu } from './UserMenu';
import NotificationCenter from './NotificationCenter';
import ToastContainer from './ToastContainer';
import { FeatureHelpModal } from './FeatureHelpModal';

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
        <header className="z-50 sticky top-0 flex-shrink-0" style={{
            background: 'rgba(8,8,24,0.8)',
            backdropFilter: 'blur(20px) saturate(160%)',
            WebkitBackdropFilter: 'blur(20px) saturate(160%)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            boxShadow: '0 1px 0 rgba(255,255,255,0.04)',
        }}>
            <div className="w-full px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-14">
                    <div className="flex items-center">
                        <button onClick={onToggleSidebar}
                            className="p-2 -ml-1.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-all md:hidden">
                            <svg className="h-5 w-5" stroke="currentColor" fill="none" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
                            </svg>
                        </button>
                        <div className="hidden md:flex items-center gap-2.5">
                            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                                style={{ background: 'linear-gradient(135deg, rgba(14,165,233,0.2), rgba(3,105,161,0.2))', border: '1px solid rgba(14,165,233,0.3)' }}>
                                <BotIcon className="text-primary-400" size={18} />
                            </div>
                            <h1 className="text-[15px] font-semibold text-gradient tracking-tight">Omni-Agent AI</h1>
                        </div>
                    </div>
                    <div className="flex items-center gap-1 sm:gap-2">
                        <div className="hidden sm:block">
                            <select
                                value={timeZone}
                                onChange={(e) => setTimeZone(e.target.value)}
                                className="text-[11px] rounded-lg px-2.5 py-1.5 text-slate-400 focus:outline-none focus:ring-1 focus:ring-primary-500/50 cursor-pointer"
                                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
                                aria-label="Select Timezone"
                            >
                                {availableTimeZones.map(tz => (
                                    <option key={tz} value={tz}>{tz.replace('_', ' ')}</option>
                                ))}
                            </select>
                        </div>

                        <button
                            onClick={toggleDarkMode}
                            className="p-2 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-all"
                            aria-label="Toggle dark mode"
                        >
                            {isDarkMode ? <MoonIcon size={17} /> : <SunIcon size={17} />}
                        </button>

                        <button
                            onClick={onStartTour}
                            className="p-2 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-all"
                            aria-label="Start guided tour"
                        >
                            <HelpCircleIcon size={17} />
                        </button>

                        {onOpenSearch && (
                            <button
                                onClick={onOpenSearch}
                                className="p-2 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 text-xs font-mono hidden sm:flex items-center"
                                aria-label="Open Global Search"
                            >
                                <span className="mr-2 text-sm">Search</span>
                                <kbd className="px-2 py-1 text-xs font-semibold text-gray-800 bg-gray-100 border border-gray-200 rounded-lg dark:bg-gray-600 dark:text-gray-100 dark:border-gray-500">⌘/</kbd>
                            </button>
                        )}
                        <button
                            onClick={onOpenCommandBar}
                            className="p-2 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 text-xs font-mono hidden sm:flex items-center"
                            aria-label="Open AI Command Bar"
                        >
                            <span className="mr-2 text-sm">AI Command</span>
                            <kbd className="px-2 py-1 text-xs font-semibold text-gray-800 bg-gray-100 border border-gray-200 rounded-lg dark:bg-gray-600 dark:text-gray-100 dark:border-gray-500">⌘K</kbd>
                        </button>

                        <button
                            onClick={() => setIsHelpOpen(true)}
                            className="p-2 rounded-xl text-slate-400 hover:text-primary-400 hover:bg-primary-500/10 transition-all"
                            aria-label="Feature help"
                            title="What does this page do?"
                        >
                            <InfoIcon size={17} />
                        </button>

                        <NotificationCenter />

                        <div className="h-8 w-px bg-gray-200 dark:bg-gray-700 hidden sm:block"></div>

                        <UserMenu allUsers={allUsers} setCurrentView={setCurrentView} />
                    </div>
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
