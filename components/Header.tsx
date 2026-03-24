

import React, { useContext } from 'react';
import { useTheme, ThemeId } from '../contexts/ThemeProvider';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { SunIcon, MoonIcon, BotIcon, HelpCircleIcon } from './icons';
import { User, Notification, AppView } from '../types';
import { UserMenu } from './UserMenu';
import NotificationCenter from './NotificationCenter';

interface HeaderProps {
    allUsers: User[];
    notifications: Notification[];
    onNotificationClick: (notification: Notification) => void;
    onMarkAllAsRead: () => void;
    onToggleSidebar: () => void;
    onOpenCommandBar: () => void;
    setCurrentView: (view: AppView) => void;
    onStartTour: () => void;
}

export const Header: React.FC<HeaderProps> = ({ allUsers, notifications, onNotificationClick, onMarkAllAsRead, onToggleSidebar, onOpenCommandBar, setCurrentView, onStartTour }) => {
    const { themeId, setThemeId, isDarkMode, toggleDarkMode } = useTheme();
    const { timeZone, setTimeZone, availableTimeZones } = useTimeZone();

    // Theme selector removed


    return (
        <header className="glass dark:glass shadow-sm z-50 sticky top-0 flex-shrink-0 border-b border-white/20 dark:border-white/5">
            <div className="w-full px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16">
                    <div className="flex items-center">
                        <button onClick={onToggleSidebar} className="p-2 -ml-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 md:hidden">
                            <svg className="h-6 w-6" stroke="currentColor" fill="none" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
                            </svg>
                        </button>
                        <div className="hidden md:flex items-center">
                            <BotIcon className="text-primary-500" size={28} />
                            <h1 className="text-xl font-bold ml-2 text-gray-800 dark:text-white">Omni-Agent AI</h1>
                        </div>
                    </div>
                    <div className="flex items-center space-x-2 sm:space-x-4">
                        <div className="hidden sm:block">
                            <select
                                value={timeZone}
                                onChange={(e) => setTimeZone(e.target.value)}
                                className="text-xs bg-gray-100 dark:bg-gray-700 border-none rounded-md px-2 py-1 text-gray-700 dark:text-gray-300 focus:ring-1 focus:ring-primary-500"
                                aria-label="Select Timezone"
                            >
                                {availableTimeZones.map(tz => (
                                    <option key={tz} value={tz}>{tz.replace('_', ' ')}</option>
                                ))}
                            </select>
                        </div>

                        {/* Theme Selector Removed - Enforced Enterprise Blue */}

                        <button
                            onClick={toggleDarkMode}
                            className={`p-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 ${isDarkMode ? 'text-yellow-400' : 'text-gray-500'}`}
                            aria-label="Toggle dark mode"
                        >
                            {isDarkMode ? <MoonIcon size={20} /> : <SunIcon size={20} />}
                        </button>

                        <button
                            onClick={onStartTour}
                            className="p-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                            aria-label="Start guided tour"
                        >
                            <HelpCircleIcon size={20} />
                        </button>

                        <button
                            onClick={onOpenCommandBar}
                            className="p-2 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 text-xs font-mono hidden sm:flex items-center"
                            aria-label="Open AI Command Bar"
                        >
                            <span className="mr-2 text-sm">AI Command</span>
                            <kbd className="px-2 py-1 text-xs font-semibold text-gray-800 bg-gray-100 border border-gray-200 rounded-lg dark:bg-gray-600 dark:text-gray-100 dark:border-gray-500">⌘K</kbd>
                        </button>

                        <NotificationCenter />

                        <div className="h-8 w-px bg-gray-200 dark:bg-gray-700 hidden sm:block"></div>

                        <UserMenu allUsers={allUsers} setCurrentView={setCurrentView} />
                    </div>
                </div>
            </div>
        </header>
    );
};
