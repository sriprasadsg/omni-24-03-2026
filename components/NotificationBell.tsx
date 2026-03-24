

import React, { useState, useRef, useEffect } from 'react';
import { Notification, AppView } from '../types';
// FIX: Added missing BellIcon.
import { BellIcon, ShieldAlertIcon, ShieldZapIcon } from './icons';
import { useTimeZone } from '../contexts/TimeZoneContext';

interface NotificationBellProps {
    notifications: Notification[];
    onNotificationClick: (notification: Notification) => void;
    onMarkAllAsRead: () => void;
}

const getNotificationIcon = (linkTo: AppView): React.ReactNode => {
    switch (linkTo) {
        case 'patchManagement':
            return <ShieldAlertIcon className="text-orange-500" size={20} />;
        case 'security':
            return <ShieldZapIcon className="text-red-500" size={20} />;
        default:
            return <BellIcon className="text-gray-500" size={20} />;
    }
};

export const NotificationBell: React.FC<NotificationBellProps> = ({ notifications, onNotificationClick, onMarkAllAsRead }) => {
    const [isOpen, setIsOpen] = useState(false);
    const { timeZone } = useTimeZone();
    const menuRef = useRef<HTMLDivElement>(null);

    const unreadCount = notifications.filter(n => !n.isRead).length;

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleNotificationItemClick = (notification: Notification) => {
        onNotificationClick(notification);
        setIsOpen(false);
    };

    const handleMarkAll = () => {
        onMarkAllAsRead();
    }

    return (
        <div className="relative" ref={menuRef}>
            <button
                id="notifications-button"
                onClick={() => setIsOpen(!isOpen)}
                className="relative p-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none"
                aria-label="View notifications"
                aria-haspopup="true"
                aria-expanded={isOpen}
            >
                <BellIcon size={20} />
                {unreadCount > 0 && (
                    <span aria-live="polite" className="absolute top-1 right-1 flex h-4 w-4">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                        <span className="relative inline-flex items-center justify-center rounded-full h-4 w-4 bg-red-500 text-white text-[10px] font-bold">
                            {unreadCount}
                        </span>
                    </span>
                )}
            </button>

            {isOpen && (
                <div
                    className="absolute right-0 mt-2 w-80 sm:w-96 bg-white dark:bg-gray-800 rounded-lg shadow-lg ring-1 ring-black ring-opacity-5 z-50 flex flex-col max-h-[70vh]"
                    role="menu"
                    aria-orientation="vertical"
                    aria-labelledby="notifications-button"
                >
                    <div className="flex-shrink-0 flex justify-between items-center p-3 border-b border-gray-200 dark:border-gray-700">
                        <h3 className="font-semibold text-gray-800 dark:text-white">Notifications</h3>
                        {unreadCount > 0 && (
                            <button onClick={handleMarkAll} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                                Mark all as read
                            </button>
                        )}
                    </div>

                    {notifications.length > 0 ? (
                        <div className="flex-grow overflow-y-auto" role="none">
                            {notifications.map(notification => (
                                <button
                                    key={notification.id}
                                    onClick={() => handleNotificationItemClick(notification)}
                                    className="w-full text-left flex items-start p-3 hover:bg-gray-100 dark:hover:bg-gray-700 border-b border-gray-200 dark:border-gray-700 last:border-b-0"
                                    role="menuitem"
                                >
                                    {!notification.isRead && (
                                        <span className="flex-shrink-0 h-2.5 w-2.5 mt-2 mr-3 rounded-full bg-primary-500" aria-hidden="true"></span>
                                    )}
                                    <div className={`flex-shrink-0 mr-3 mt-1 ${notification.isRead ? 'ml-[22px]' : ''}`}>
                                        {getNotificationIcon(notification.linkTo)}
                                    </div>
                                    <div className="flex-1">
                                        <p className={`text-sm ${notification.isRead ? 'text-gray-600 dark:text-gray-400' : 'font-medium text-gray-800 dark:text-gray-200'}`}>
                                            {notification.message}
                                        </p>
                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                                            {new Date(notification.timestamp).toLocaleString(undefined, { timeZone })}
                                        </p>
                                    </div>
                                </button>
                            ))}
                        </div>
                    ) : (
                        <div className="flex-grow flex items-center justify-center p-8">
                            <p className="text-sm text-gray-500 dark:text-gray-400">You have no new notifications.</p>
                        </div>
                    )}

                    <div className="flex-shrink-0 text-center p-2 border-t border-gray-200 dark:border-gray-700">
                        <a href="#" onClick={(e) => { e.preventDefault(); alert("Feature not implemented."); }} className="text-sm font-medium text-primary-600 dark:text-primary-400 hover:underline">
                            View all notifications
                        </a>
                    </div>
                </div>
            )}
        </div>
    );
};
