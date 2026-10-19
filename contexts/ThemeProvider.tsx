import React, { createContext, useContext, useEffect, useState } from 'react';

export type ThemeId = 'enterprise-blue';
/** 'system' follows the OS light/dark setting live; the other two pin a mode. */
export type ThemePreference = 'system' | 'light' | 'dark';

interface ThemeContextType {
    themeId: ThemeId;
    setThemeId: (id: ThemeId) => void;
    isDarkMode: boolean;
    toggleDarkMode: () => void;
    themePreference: ThemePreference;
    setThemePreference: (preference: ThemePreference) => void;
}

const PREFERENCE_KEY = 'app-theme-preference';

const systemPrefersDark = () => {
    try {
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch {
        return true;
    }
};

// Storage can throw (private windows, blocked site data); the theme must still work.
const readStorage = (key: string): string | null => {
    try { return localStorage.getItem(key); } catch { return null; }
};
const writeStorage = (key: string, value: string) => {
    try { localStorage.setItem(key, value); } catch { /* keep the in-memory theme */ }
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const useTheme = () => {
    const context = useContext(ThemeContext);
    if (!context) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
};

interface ThemeProviderProps {
    children: React.ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {

    const [themeId, setThemeId] = useState<ThemeId>('enterprise-blue'); // Keeping ID for compatibility

    // Dark stays the default (Spatial Glass is dark first); an earlier explicit toggle is kept.
    const [themePreference, setThemePreference] = useState<ThemePreference>(() => {
        const saved = readStorage(PREFERENCE_KEY);
        if (saved === 'system' || saved === 'light' || saved === 'dark') return saved;
        const legacy = readStorage('app-dark-mode');
        return legacy === 'false' ? 'light' : 'dark';
    });
    const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);
    const isDarkMode = themePreference === 'system' ? systemDark : themePreference === 'dark';

    // Follow the OS setting while the preference is 'system'.
    useEffect(() => {
        if (themePreference !== 'system') return;
        let query: MediaQueryList;
        try { query = window.matchMedia('(prefers-color-scheme: dark)'); } catch { return; }
        const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
        setSystemDark(query.matches);
        query.addEventListener?.('change', onChange);
        return () => query.removeEventListener?.('change', onChange);
    }, [themePreference]);

    useEffect(() => {
        const root = document.documentElement;

        // Remove old theme classes
        root.classList.remove('theme-enterprise-blue');

        // Add flash styling
        root.classList.add('theme-flash');

        // Toggle Dark Mode class
        if (isDarkMode) {
            root.classList.add('dark');
        } else {
            root.classList.remove('dark');
        }

        // Persistence (app-dark-mode kept so a rollback to an older build keeps the user's mode)
        writeStorage('app-theme', 'flash');
        writeStorage('app-dark-mode', JSON.stringify(isDarkMode));
        writeStorage(PREFERENCE_KEY, themePreference);

    }, [themeId, isDarkMode, themePreference]);

    // The header toggle pins the opposite of what is showing.
    const toggleDarkMode = () => setThemePreference(isDarkMode ? 'light' : 'dark');

    return (
        <ThemeContext.Provider value={{ themeId, setThemeId, isDarkMode, toggleDarkMode, themePreference, setThemePreference }}>
            {children}
        </ThemeContext.Provider>
    );
};
