/**
 * The app shell (App.tsx) owns the page's one <main> landmark. A screen that renders its own <main> nests a second
 * one, which screen readers and "Skip to main content" handle badly (the Partner portal and Partners screens did,
 * found 2026-11-05).
 */
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const dir = resolve(__dirname, '../../components');

describe('one main landmark', () => {
  it('no component renders a <main> element of its own', () => {
    const offenders = readdirSync(dir)
      .filter(f => f.endsWith('.tsx'))
      .filter(f => readFileSync(resolve(dir, f), 'utf8').split('\n')
        .some(line => /^\s*<main[\s>]/.test(line)));
    expect(offenders).toEqual([]);
  });
});
