import React, { useState, useRef, useEffect } from 'react';
import { useUser } from '../contexts/UserContext';
import { User, AppView } from '../types';
import { ChevronDownIcon, CheckIcon, LogOutIcon, UserIcon as ProfileIcon } from './icons';

interface UserMenuProps {
    allUsers: User[];
    setCurrentView: (view: AppView) => void;
}

export const UserMenu: React.FC<UserMenuProps> = ({ allUsers, setCurrentView }) => {
    const { currentUser, logout } = useUser();
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    if (!currentUser) return null;

    return (
        <div className="relative" ref={menuRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center space-x-2 p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700"
            >
                {currentUser.avatar ? (
                    <img className="h-8 w-8 rounded-full object-cover" src={currentUser.avatar} alt="User" />
                ) : (
                    <div className="h-8 w-8 rounded-full bg-primary-500 flex items-center justify-center text-white font-bold">
                        {(currentUser.name || currentUser.email || 'U').charAt(0).toUpperCase()}
                    </div>
                )}
                <div className="hidden md:flex flex-col items-start">
                    <span className="text-sm font-medium text-gray-800 dark:text-white">{currentUser.name || currentUser.email}</span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">{currentUser.role}</span>
                </div>
                <ChevronDownIcon size={16} className="hidden md:block text-gray-500 dark:text-gray-400" />
            </button>

            {isOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg ring-1 ring-black ring-opacity-5 py-1 z-50">
                    <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{currentUser.name || currentUser.email}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{currentUser.email}</p>
                    </div>
                    <div className="mt-1 pt-1">
                        <button
                            onClick={() => {
                                setCurrentView('profile');
                                setIsOpen(false);
                            }}
                            className="w-full text-left flex items-center px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                        >
                            <ProfileIcon className="mr-3" />
                            My Profile
                        </button>
                        <button
                            onClick={() => {
                                // Clear all storage
                                localStorage.clear();
                                sessionStorage.clear();
                                // Navigate to login page
                                const link = document.createElement('a');
                                link.href = '/';
                                link.click();
                            }}
                            className="w-full text-left flex items-center px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/50"
                        >
                            <LogOutIcon className="mr-3" />
                            Logout
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
