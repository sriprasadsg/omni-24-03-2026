/**
 * styles/gloss.css (the glossy layer, 2026-11-17) must stay blur-free: blur rules live in index.css, where
 * GlassBlurOrder.test.ts guards the prefix order the minifier needs. And the solid-button sheen must carry
 * element specificity: Tailwind's reset sets `background-image: none` on every button, which beats a
 * zero-specificity :where() rule, so the sheen silently never showed.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const css = readFileSync(resolve(__dirname, '../../styles/gloss.css'), 'utf8');
const rules = css.replace(/\/\*[\s\S]*?\*\//g, '').split('}');

describe('gloss layer', () => {
  it('has no backdrop-filter (blur belongs in index.css)', () => {
    expect(css.replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/backdrop-filter\s*:/);
  });

  it('gives every rule that sets a button background-image element specificity', () => {
    // rules whose subject is a button: `button…`, `:is(button…` or `:where(button…`
    const buttonSheens = rules.filter(r => /^(?::(?:is|where)\()?button\b/.test(r.split('{')[0].trim()) && /background-image\s*:/.test(r));
    expect(buttonSheens.length).toBeGreaterThan(0);
    for (const rule of buttonSheens) {
      expect(rule.split('{')[0].trim(), 'selector').not.toMatch(/^:where\(/);
    }
  });
});
