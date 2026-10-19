
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
        <div className="fade-in">
            <div className="flex flex-col md:flex-row justify-between md:items-center gap-4">
                <div>
                    <h2 className="text-[30px] font-semibold tracking-[-0.03em] text-slate-900 dark:text-white">
                        Good day, <span className="text-gradient">{(userName || 'User').split(' ')[0]}</span>
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1.5">
                        <CalendarIcon size={13} />
                        {currentDate}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button className="flex items-center gap-2 h-10 px-4 text-sm font-medium text-slate-700 dark:text-slate-200 glass rounded-xl transition-all hover:border-primary-500/30 active:scale-[0.98]">
                        <CalendarIcon size={15} className="text-primary-500" />
                        Last 24 Hours
                    </button>
                    <button aria-label="Refresh" className="grid place-items-center h-10 w-10 glass rounded-xl transition-all hover:border-primary-500/30 active:scale-[0.98]">
                        <RefreshCwIcon size={15} className="text-primary-500" />
                    </button>
                    <button
                        onClick={() => setCurrentView('reporting')}
                        className="flex items-center gap-2 h-10 px-5 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 transition-all active:scale-[0.98]">
                        <FileTextIcon size={15} />
                        Generate Report
                    </button>
                </div>
            </div>
        </div>
    );
};
