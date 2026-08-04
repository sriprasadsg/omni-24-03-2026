// src/styles/typography.ts
// Typography scale and styles for Enterprise Omni-Agent AI Platform

export const typography = {
  // Font families (assuming a standard sans-serif stack)
  fontFamily: {
    sans: [
      'Inter',
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      '"Noto Sans"',
      'sans-serif',
      '"Apple Color Emoji"',
      '"Segoe UI Emoji"',
      '"Segoe UI Symbol"',
      '"Noto Color Emoji"',
    ].join(','),
    mono: [
      'Menlo',
      'Monaco',
      'Consolas',
      '"Liberation Mono"',
      '"Courier New"',
      'monospace',
    ].join(','),
  },
  // Font sizes (in rem for accessibility)
  fontSize: {
    'xs': '0.75rem',    // 12px
    'sm': '0.875rem',   // 14px
    'base': '1rem',      // 16px (body)
    'lg': '1.125rem',   // 18px
    'xl': '1.25rem',    // 20px
    '2xl': '1.5rem',     // 24px
    '3xl': '1.875rem',   // 30px
    '4xl': '2.25rem',    // 36px
    '5xl': '3rem',       // 48px
  },
  // Line heights
  lineHeight: {
    'xs': '1rem',
    'sm': '1.25rem',
    'base': '1.5rem',
    'lg': '1.75rem',
    'xl': '1.75rem',
    '2xl': '2rem',
    '3xl': '2.25rem',
    '4xl': '2.5rem',
    '5xl': '1',
  },
  // Font weights
  fontWeight: {
    'light': 300,
    'normal': 400,
    'medium': 500,
    'semibold': 600,
    'bold': 700,
  },
};
