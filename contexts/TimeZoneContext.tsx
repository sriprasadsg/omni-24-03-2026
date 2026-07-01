
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

type TimeZoneContextType = {
    timeZone: string;
    setTimeZone: (tz: string) => void;
    availableTimeZones: string[];
};

const TimeZoneContext = createContext<TimeZoneContextType | undefined>(undefined);

export const TimeZoneProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    // ISO-8601 Timezones (simplified list)
    const availableTimeZones = [
        'UTC',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'Europe/London',
        'Europe/Paris',
        'Asia/Tokyo',
        'Asia/Kolkata',
        'Australia/Sydney'
    ];

    // Try to load from localStorage or default to system
    const [timeZone, setTimeZoneState] = useState<string>(() => {
        const saved = localStorage.getItem('omni-platform-timezone');
        if (saved && availableTimeZones.includes(saved)) return saved;
        try {
            const systemTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
            return systemTz;
        } catch {
            return 'UTC';
        }
    });

    const setTimeZone = (tz: string) => {
        setTimeZoneState(tz);
        localStorage.setItem('omni-platform-timezone', tz);
    };

    return (
        <TimeZoneContext.Provider value={{ timeZone, setTimeZone, availableTimeZones }}>
            {children}
        </TimeZoneContext.Provider>
    );
};

export const useTimeZone = () => {
    const context = useContext(TimeZoneContext);
    if (context === undefined) {
        throw new Error('useTimeZone must be used within a TimeZoneProvider');
    }
    return context;
};
