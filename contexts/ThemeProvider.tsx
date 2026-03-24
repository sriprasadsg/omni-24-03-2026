import React, { createContext, useContext, useEffect, useState } from 'react';

export type ThemeId = 'enterprise-blue';

interface ThemeContextType {
    themeId: ThemeId;
    setThemeId: (id: ThemeId) => void;
    isDarkMode: boolean;
    toggleDarkMode: () => void;
}

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

    const [isDarkMode, setIsDarkMode] = useState(() => {
        const saved = localStorage.getItem('app-dark-mode');
        return saved ? JSON.parse(saved) : true; // Default to Dark Mode for Flash UI
    });

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

        // Persistence
        localStorage.setItem('app-theme', 'flash');
        localStorage.setItem('app-dark-mode', JSON.stringify(isDarkMode));

    }, [themeId, isDarkMode]);

    const toggleDarkMode = () => setIsDarkMode(prev => !prev);

    return (
        <ThemeContext.Provider value={{ themeId, setThemeId, isDarkMode, toggleDarkMode }}>
            {children}
        </ThemeContext.Provider>
    );
};
