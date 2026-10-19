/** @type {import('tailwindcss').Config} */

// Spatial Glass (2030) design system — design-system/omni-agent-2030/MASTER.md.
// One cool "space" neutral ramp replaces Tailwind's gray and slate (the app uses
// both, ~14,600 times across 305 files), so every surface, border and text tone
// moves to the new system without per-component edits. Values live in index.css
// as CSS variables, next to the primary (electric cyan) ramp.
const scale = (name) =>
    Object.fromEntries(
        ['50', '100', '200', '300', '400', '500', '600', '700', '800', '900', '950']
            .map((step) => [step, `rgb(var(--${name}-${step}) / <alpha-value>)`]),
    );

export default {
    content: [
        "./index.html",
        "./components/**/*.{js,ts,jsx,tsx}",
        "./pages/**/*.{js,ts,jsx,tsx}",
        "./*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class',
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
                mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
            },
            colors: {
                primary: scale('primary'),
                gray: scale('space'),
                slate: scale('space'),
                secondary: scale('space'),
                // Legacy aliases kept so older components still resolve to the new system.
                flash: {
                    cyan: 'rgb(var(--primary-400) / <alpha-value>)',
                    blue: 'rgb(var(--primary-600) / <alpha-value>)',
                    violet: 'rgb(var(--space-700) / <alpha-value>)',
                    dark: 'rgb(var(--space-950) / <alpha-value>)',
                    panel: 'var(--glass-bg)',
                },
            },
            borderRadius: {
                lg: '0.625rem',
                xl: '0.875rem',
                '2xl': '1.25rem',
                '3xl': '1.75rem',
            },
            boxShadow: {
                neon: '0 0 0 1px rgb(var(--primary-400) / 0.35), 0 0 24px -4px rgb(var(--primary-400) / 0.45)',
                'neon-sm': '0 0 12px -2px rgb(var(--primary-400) / 0.4)',
                glass: 'var(--glass-shadow)',
                card: 'var(--card-shadow)',
                'card-hover': 'var(--card-shadow-hover)',
                'inner-top': 'inset 0 1px 0 rgb(255 255 255 / 0.06)',
            },
            keyframes: {
                blink: {
                    '0%, 100%': { opacity: '1' },
                    '50%': { opacity: '0' },
                },
                float: {
                    '0%, 100%': { transform: 'translateY(0px)' },
                    '50%': { transform: 'translateY(-6px)' },
                },
                shimmer: {
                    '0%': { backgroundPosition: '-200% 0' },
                    '100%': { backgroundPosition: '200% 0' },
                },
                scaleIn: {
                    '0%': { opacity: '0', transform: 'scale(0.96)' },
                    '100%': { opacity: '1', transform: 'scale(1)' },
                },
                riseIn: {
                    '0%': { opacity: '0', transform: 'translateY(8px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
            },
            animation: {
                blink: 'blink 1s step-end infinite',
                float: 'float 3s ease-in-out infinite',
                shimmer: 'shimmer 1.6s infinite',
                'scale-in': 'scaleIn 0.28s cubic-bezier(0.16, 1, 0.3, 1)',
                'rise-in': 'riseIn 0.36s cubic-bezier(0.16, 1, 0.3, 1) both',
            },
            backgroundImage: {
                'glass-gradient': 'linear-gradient(135deg, rgb(255 255 255 / 0.10), rgb(255 255 255 / 0.04))',
                'neon-gradient': 'linear-gradient(135deg, rgb(var(--primary-600)), rgb(var(--primary-400)))',
                'neon-gradient-h': 'linear-gradient(to right, rgb(var(--primary-600)), rgb(var(--primary-400)))',
                'flash-gradient': 'linear-gradient(135deg, rgb(var(--space-950)) 0%, rgb(var(--space-900)) 100%)',
                'card-gradient': 'linear-gradient(135deg, rgb(255 255 255 / 0.06), rgb(255 255 255 / 0.02))',
                'success-gradient': 'linear-gradient(135deg, #10b981, #059669)',
                'danger-gradient': 'linear-gradient(135deg, #ef4444, #dc2626)',
                'warning-gradient': 'linear-gradient(135deg, #f59e0b, #d97706)',
            },
        },
    },
    plugins: [],
};
