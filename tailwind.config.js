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
                'neon': '0 0 10px rgba(0, 210, 255, 0.5), 0 0 20px rgba(0, 210, 255, 0.3)',
                'glass': '0 8px 32px 0 rgba(31, 38, 135, 0.37)',
            }
        }
    },
    plugins: [],
}
