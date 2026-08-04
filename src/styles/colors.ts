// src/styles/colors.ts
// Semantic color tokens for Enterprise Omni-Agent AI Platform
// Inspired by Material Design and enterprise UI best practices.

export const colors = {
  // Primary brand colors
  primary: {
    DEFAULT: '#4F46E5', // Indigo 600
    light: '#6366F1',   // Indigo 500
    dark: '#4338CA',    // Indigo 700
    contrast: '#FFFFFF', // White for text on primary
  },
  // Secondary action colors (e.g., for accents or less prominent actions)
  secondary: {
    DEFAULT: '#06B6D4', // Cyan 600
    light: '#22D3EE',   // Cyan 500
    dark: '#0891B2',    // Cyan 700
    contrast: '#FFFFFF',
  },
  // Surface colors (backgrounds, cards, elevated elements)
  surface: {
    DEFAULT: '#FFFFFF', // White
    dim: '#F9FAFB',     // Gray 50 (light background)
    medium: '#F3F4F6',  // Gray 100 (subtle contrast)
    dark: '#1F2937',    // Gray 800 (dark mode surface)
    darker: '#111827',  // Gray 900 (dark mode background)
  },
  // Text colors for readability
  text: {
    primary: '#1F2937', // Gray 800
    secondary: '#4B5563', // Gray 600
    disabled: '#9CA3AF', // Gray 400
    onPrimary: '#FFFFFF',
    onSecondary: '#FFFFFF',
    onDark: '#F9FAFB', // Gray 50
  },
  // Status colors (success, warning, error, info)
  success: {
    DEFAULT: '#10B981', // Green 500
    light: '#34D399',   // Green 400
    dark: '#059669',    // Green 600
    contrast: '#FFFFFF',
  },
  warning: {
    DEFAULT: '#F59E0B', // Amber 500
    light: '#FBBF24',   // Amber 400
    dark: '#D97706',    // Amber 600
    contrast: '#FFFFFF',
  },
  error: {
    DEFAULT: '#EF4444', // Red 500
    light: '#F87171',   // Red 400
    dark: '#DC2626',    // Red 600
    contrast: '#FFFFFF',
  },
  info: {
    DEFAULT: '#3B82F6', // Blue 500
    light: '#60A5FA',   // Blue 400
    dark: '#2563EB',    // Blue 600
    contrast: '#FFFFFF',
  },
  // Border and divider colors
  border: {
    DEFAULT: '#D1D5DB', // Gray 300
    dark: '#4B5563',    // Gray 600 (dark mode)
  },
  // Interactive states
  hover: {
    primary: '#6366F1',
    secondary: '#22D3EE',
  },
  active: {
    primary: '#4338CA',
    secondary: '#0891B2',
  },
};
