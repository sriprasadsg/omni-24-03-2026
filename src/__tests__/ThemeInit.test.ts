/**
 * public/theme-init.js runs before React and must reach the same decision as ThemeProvider, or the
 * page flashes one theme and then switches.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const script = readFileSync(resolve(__dirname, '../../public/theme-init.js'), 'utf8');
const run = () => new Function(script)();
const html = document.documentElement;
const originalMatchMedia = window.matchMedia;

function osPrefersDark(dark: boolean) {
  (window as any).matchMedia = () => ({ matches: dark });
}

beforeEach(() => {
  localStorage.clear();
  html.className = 'dark';
  document.head.innerHTML = '<meta name="theme-color" content="#060a14">';
});
afterEach(() => { (window as any).matchMedia = originalMatchMedia; });

describe('theme-init.js', () => {
  it('defaults to dark, like the provider', () => {
    run();
    expect(html.classList.contains('dark')).toBe(true);
  });

  it('honours a saved light preference and the legacy dark-mode flag', () => {
    localStorage.setItem('app-theme-preference', 'light');
    run();
    expect(html.classList.contains('dark')).toBe(false);
    expect(document.querySelector('meta[name="theme-color"]')!.getAttribute('content')).toBe('#f3f6fa');
    localStorage.clear();
    localStorage.setItem('app-dark-mode', 'false');
    html.className = 'dark';
    run();
    expect(html.classList.contains('dark')).toBe(false);
  });

  it('follows the OS when the preference is system, and applies compact density', () => {
    localStorage.setItem('app-theme-preference', 'system');
    localStorage.setItem('app-density', 'compact');
    osPrefersDark(false);
    run();
    expect(html.classList.contains('dark')).toBe(false);
    expect(html.classList.contains('density-compact')).toBe(true);
    osPrefersDark(true);
    run();
    expect(html.classList.contains('dark')).toBe(true);
  });
});
