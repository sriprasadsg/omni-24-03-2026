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
                sans: ['Outfit', 'sans-serif'],
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
                    'cyan': '#00d2ff',
                    'blue': '#3a7bd5',
                    'violet': '#7f00ff',
                    'dark': '#0a0a1f',
                    'panel': 'rgba(20, 20, 40, 0.6)',
                }
            },
            backgroundImage: {
                'glass-gradient': 'linear-gradient(135deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.05))',
                'neon-gradient': 'linear-gradient(to right, #00d2ff, #3a7bd5)',
                'flash-gradient': 'linear-gradient(135deg, #0a0a1f 0%, #141428 100%)',
            },
            boxShadow: {
                'neon':    '0 0 12px rgba(0, 210, 255, 0.5), 0 0 30px rgba(0, 210, 255, 0.2)',
                'neon-sm': '0 0 6px rgba(0, 210, 255, 0.4)',
                'glass':   '0 8px 32px 0 rgba(31, 38, 135, 0.37)',
                'card':    '0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.08)',
                'card-hover': '0 4px 24px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,210,255,0.12)',
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
                'neon-gradient':     'linear-gradient(135deg, #00d2ff, #7f00ff)',
                'neon-gradient-h':   'linear-gradient(to right, #00d2ff, #3a7bd5)',
                'flash-gradient':    'linear-gradient(135deg, #080818 0%, #10103a 100%)',
                'card-gradient':     'linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))',
                'success-gradient':  'linear-gradient(135deg, #10b981, #059669)',
                'danger-gradient':   'linear-gradient(135deg, #ef4444, #dc2626)',
                'warning-gradient':  'linear-gradient(135deg, #f59e0b, #d97706)',
            },
        }
    },
    plugins: [],
}
