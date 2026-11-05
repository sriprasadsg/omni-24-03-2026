/**
 * The build's CSS minifier keeps only the last of `backdrop-filter` and `-webkit-backdrop-filter` in a rule. With
 * the standard one first, the built .glass, .glass-strong and .glass-panel kept only the Safari prefix, so Chrome,
 * Edge and Firefox drew no blur and the phone menu was see-through (found 2026-11-05). The prefix must come first.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const css = readFileSync(resolve(__dirname, '../../index.css'), 'utf8');

describe('glass blur declarations', () => {
  it('puts -webkit-backdrop-filter before backdrop-filter in every rule that has both', () => {
    const rules = css.split('}').filter(r => /-webkit-backdrop-filter\s*:/.test(r) && /(^|[^-])backdrop-filter\s*:/m.test(r.replace(/-webkit-backdrop-filter/g, '')));
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) {
      const prefixed = rule.search(/-webkit-backdrop-filter\s*:/);
      const standard = rule.search(/(^|[^-])backdrop-filter\s*:/m);
      expect(prefixed, rule.trim().split('\n')[0]).toBeLessThan(standard);
    }
  });
});
