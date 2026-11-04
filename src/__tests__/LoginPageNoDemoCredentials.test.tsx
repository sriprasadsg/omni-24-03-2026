/**
 * The sign-in page names no account. It used to list "Demo Credentials" (super@omni.ai and two tenant
 * accounts) on the production login page, which told anyone the Super Admin's sign-in name.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

describe('LoginPage', () => {
  it('shows no demo credentials and names no account', () => {
    const src = readFileSync(resolve(__dirname, '../../components/LoginPage.tsx'), 'utf8');
    expect(src).not.toMatch(/demo credentials/i);
    expect(src).not.toMatch(/super@omni\.ai|admin@acmecorp\.com|analyst@acmecorp\.com/);
  });
});
