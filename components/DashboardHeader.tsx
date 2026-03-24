
import React, { useState, useEffect } from 'react';
import { AppView } from '../types';
// FIX: Replaced non-existent CalendarDaysIcon with CalendarIcon.
import { CalendarIcon, RefreshCwIcon, FileTextIcon } from './icons';

interface DashboardHeaderProps {
    userName: string;
    setCurrentView: (view: AppView) => void;
}

export const DashboardHeader: React.FC<DashboardHeaderProps> = ({ userName, setCurrentView }) => {
    const [currentDate, setCurrentDate] = useState('');

    useEffect(() => {
        setCurrentDate(new Date().toLocaleDateString('en-US', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        }));
    }, []);

    return (
        <div>
            <div className="flex flex-col md:flex-row justify-between md:items-center space-y-4 md:space-y-0">
                <div>
                    <h2 className="text-3xl font-black text-gray-900 dark:text-white tracking-tight">
                        Welcome back, <span className="gradient-text">{(userName || 'User').split(' ')[0]}</span>
                    </h2>
                    <p className="text-sm font-medium text-gray-400 dark:text-gray-500 mt-1 flex items-center">
                        <CalendarIcon size={14} className="mr-2" />
                        {currentDate}
                    </p>
                </div>
                <div className="flex items-center space-x-3">
                    <button className="flex items-center px-4 py-2.5 text-sm font-bold text-gray-700 dark:text-gray-200 glass dark:glass rounded-xl shadow-lg border border-white/20 dark:border-white/5 hover:bg-white/40 dark:hover:bg-white/10 transition-all active:scale-95">
                        <CalendarIcon size={16} className="mr-2 text-primary-500" />
                        Last 24 Hours
                    </button>
                    <button className="p-2.5 text-gray-700 dark:text-gray-200 glass dark:glass rounded-xl shadow-lg border border-white/20 dark:border-white/5 hover:bg-white/40 dark:hover:bg-white/10 transition-all active:scale-95">
                        <RefreshCwIcon size={16} className="text-primary-500" />
                    </button>
                    <button
                        onClick={() => setCurrentView('reporting')}
                        className="flex items-center px-5 py-2.5 text-sm font-bold text-white bg-gradient-to-r from-primary-600 to-indigo-600 rounded-xl shadow-lg shadow-primary-500/20 hover:shadow-primary-500/40 transition-all active:scale-95">
                        <FileTextIcon size={18} className="mr-2" />
                        Generate Report
                    </button>
                </div>
            </div>
        </div>
    );
};
