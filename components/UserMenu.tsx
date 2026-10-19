import React, { useState, useRef, useEffect } from 'react';
import { Laptop, Sun, Moon, Rows3, Rows4, Keyboard } from 'lucide-react';
import { useUser } from '../contexts/UserContext';
import { useTheme, ThemePreference, Density } from '../contexts/ThemeProvider';
import { User, AppView } from '../types';
import { ChevronDownIcon, LogOutIcon, UserIcon as ProfileIcon } from './icons';

interface UserMenuProps {
    allUsers: User[];
    setCurrentView: (view: AppView) => void;
}

/** Event the shell listens for to open the keyboard-shortcut sheet. */
export const OPEN_SHORTCUTS_EVENT = 'omni:open-shortcuts';

function Segmented<T extends string>({ label, value, options, onChange }: {
    label: string; value: T; options: { value: T; label: string; icon: React.ReactNode }[]; onChange: (v: T) => void;
}) {
    return (
        <div>
            <p className="px-1 pb-1.5 text-[11px] font-medium text-gray-500 dark:text-gray-400">{label}</p>
            <div role="group" aria-label={label} className="grid gap-0.5 p-0.5 rounded-xl bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
                {options.map(o => (
                    <button
                        key={o.value}
                        onClick={() => onChange(o.value)}
                        aria-pressed={value === o.value}
                        className={`flex items-center justify-center gap-1.5 h-8 rounded-[10px] text-xs font-medium transition-colors ${value === o.value
                            ? 'bg-white dark:bg-white/10 text-gray-900 dark:text-white shadow-sm'
                            : 'text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200'}`}
                    >
                        <span aria-hidden="true" className="[&_svg]:h-3.5 [&_svg]:w-3.5">{o.icon}</span>{o.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

const ITEM = 'w-full flex items-center gap-3 h-9 px-3 rounded-xl text-sm transition-colors';

export const UserMenu: React.FC<UserMenuProps> = ({ allUsers, setCurrentView }) => {
    const { currentUser, logout } = useUser();
    const { themePreference, setThemePreference, density, setDensity } = useTheme();
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);
    const buttonRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!isOpen) return;
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) setIsOpen(false);
        };
        const handleKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') { setIsOpen(false); buttonRef.current?.focus(); }
        };
        document.addEventListener('mousedown', handleClickOutside);
        document.addEventListener('keydown', handleKey);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleKey);
        };
    }, [isOpen]);

    if (!currentUser) return null;

    return (
        <div className="relative" ref={menuRef}>
            <button
                ref={buttonRef}
                onClick={() => setIsOpen(!isOpen)}
                aria-expanded={isOpen}
                aria-haspopup="true"
                aria-label="Account and appearance"
                className="flex items-center gap-2 p-1 rounded-full hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.07] transition-colors"
            >
                {currentUser.avatar ? (
                    <img className="h-8 w-8 rounded-full object-cover" src={currentUser.avatar} alt="" />
                ) : (
                    <div className="h-8 w-8 rounded-full bg-primary-600 flex items-center justify-center text-white font-semibold">
                        {(currentUser.name || currentUser.email || 'U').charAt(0).toUpperCase()}
                    </div>
                )}
                <div className="hidden md:flex flex-col items-start leading-tight">
                    <span className="text-sm font-medium text-gray-800 dark:text-white whitespace-nowrap">{currentUser.name || currentUser.email}</span>
                    <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">{currentUser.role}</span>
                </div>
                <ChevronDownIcon size={16} className={`hidden md:block text-gray-500 dark:text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Solid, not glass: inside the blurred header a backdrop blur can only blur the header,
                so the page text behind showed through the menu. */}
            {isOpen && (
                <div className="absolute right-0 mt-2 w-72 rounded-2xl p-2 z-50 slide-up bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.08] shadow-2xl">
                    <div className="px-3 py-2.5">
                        <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{currentUser.name || currentUser.email}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{currentUser.email}</p>
                    </div>
                    <button
                        onClick={() => { setCurrentView('profile'); setIsOpen(false); }}
                        className={`${ITEM} text-gray-700 dark:text-gray-200 hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.06]`}
                    >
                        <ProfileIcon size={16} className="text-gray-500 dark:text-gray-400" />
                        My Profile
                    </button>
                    <button
                        onClick={() => { setIsOpen(false); window.dispatchEvent(new Event(OPEN_SHORTCUTS_EVENT)); }}
                        className={`${ITEM} text-gray-700 dark:text-gray-200 hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.06]`}
                    >
                        <Keyboard className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                        Keyboard shortcuts
                        <kbd className="ml-auto font-mono text-[11px] px-1.5 rounded-md text-gray-500 dark:text-gray-400 ring-1 ring-inset ring-gray-200 dark:ring-white/10">?</kbd>
                    </button>

                    <div className="my-2 mx-1 space-y-3 p-3 rounded-xl bg-gray-900/[0.02] dark:bg-white/[0.02] ring-1 ring-inset ring-gray-900/[0.05] dark:ring-white/[0.05]">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Appearance</p>
                        <Segmented<ThemePreference>
                            label="Theme"
                            value={themePreference}
                            onChange={setThemePreference}
                            options={[
                                { value: 'system', label: 'System', icon: <Laptop /> },
                                { value: 'light', label: 'Light', icon: <Sun /> },
                                { value: 'dark', label: 'Dark', icon: <Moon /> },
                            ]}
                        />
                        <Segmented<Density>
                            label="Table density"
                            value={density}
                            onChange={setDensity}
                            options={[
                                { value: 'comfortable', label: 'Comfortable', icon: <Rows3 /> },
                                { value: 'compact', label: 'Compact', icon: <Rows4 /> },
                            ]}
                        />
                    </div>

                    {/* Sign out through the app so the server revokes the session and its refresh cookie;
                        clearing storage alone left both alive and also wiped every saved preference. */}
                    <button
                        onClick={() => { setIsOpen(false); logout(); }}
                        className={`${ITEM} text-red-600 dark:text-red-400 hover:bg-red-500/10`}
                    >
                        <LogOutIcon size={16} />
                        Sign out
                    </button>
                </div>
            )}
        </div>
    );
};
