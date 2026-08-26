/** @type {import('tailwindcss').Config} */
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
                sans: ['Plus Jakarta Sans', 'sans-serif'],
            },
            colors: {
                'primary': {
                    '50': 'var(--primary-50)',
                    '100': 'var(--primary-100)',
                    '200': 'var(--primary-200)',
                    '300': 'var(--primary-300)',
                    '400': 'var(--primary-400)',
                    '500': 'var(--primary-500)',
                    '600': 'var(--primary-600)',
                    '700': 'var(--primary-700)',
                    '800': 'var(--primary-800)',
                    '900': 'var(--primary-900)',
                    '950': 'var(--primary-950)',
                },
                'secondary': {
                    '50': '#f8fafc',
                    '100': '#f1f5f9',
                    '200': '#e2e8f0',
                    '300': '#cbd5e1',
                    '400': '#94a3b8',
                    '500': '#64748b',
                    '600': '#475569',
                    '700': '#334155',
                    '800': '#1e293b',
                    '900': '#0f172a',
                    '950': '#020617',
                },
                'flash': {
                    'cyan': '#0ea5e9',
                    'blue': '#0369a1',
                    'violet': '#334155',
                    'dark': '#0b1220',
                    'panel': 'rgba(15, 23, 42, 0.6)',
                }
            },
            boxShadow: {
                'neon':    '0 0 12px rgba(3, 105, 161, 0.4), 0 0 30px rgba(3, 105, 161, 0.15)',
                'neon-sm': '0 0 6px rgba(3, 105, 161, 0.3)',
                'glass':   '0 8px 32px 0 rgba(15, 23, 42, 0.25)',
                'card':    '0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.08)',
                'card-hover': '0 4px 24px rgba(0,0,0,0.12), 0 0 0 1px rgba(3,105,161,0.12)',
                'inner-top': 'inset 0 1px 0 rgba(255,255,255,0.06)',
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
                    '0%':   { backgroundPosition: '-200% 0' },
                    '100%': { backgroundPosition: '200% 0' },
                },
                scaleIn: {
                    '0%':   { opacity: '0', transform: 'scale(0.95)' },
                    '100%': { opacity: '1', transform: 'scale(1)' },
                },
            },
            animation: {
                blink:    'blink 1s step-end infinite',
                float:    'float 3s ease-in-out infinite',
                shimmer:  'shimmer 1.6s infinite',
                'scale-in': 'scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
            },
            backgroundImage: {
                'glass-gradient':    'linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05))',
                'neon-gradient':     'linear-gradient(135deg, #0369a1, #0ea5e9)',
                'neon-gradient-h':   'linear-gradient(to right, #0369a1, #0ea5e9)',
                'flash-gradient':    'linear-gradient(135deg, #0b1220 0%, #111c30 100%)',
                'card-gradient':     'linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))',
                'success-gradient':  'linear-gradient(135deg, #10b981, #059669)',
                'danger-gradient':   'linear-gradient(135deg, #ef4444, #dc2626)',
                'warning-gradient':  'linear-gradient(135deg, #f59e0b, #d97706)',
            },
        }
    },
    plugins: [],
}
