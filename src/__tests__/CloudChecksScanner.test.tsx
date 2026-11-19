/**
 * Cloud Checks: an account with no imported scanner results shows its checks as not checked, never as passed.
 *
 * Value: protects=the pass rate counts only checks that were really evaluated, a provider with nothing checked
 * shows "Not checked" instead of 0 %, and a SKIP row says why; fails_when=the pass rate divides by unchecked rows,
 * a provider card shows a percentage for zero checked rows, or the not-checked reason is hidden; no_claim=the
 * server's SKIP decision (backend/tests/test_cloud_checks_expansion.py).
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import CloudChecksScanner from '../../components/CloudChecksScanner';

const jsonRes = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response;

const NOT_CHECKED = 'Not checked: no scanner results have been imported for this account yet.';

function stubFetch(summary: unknown, results: unknown[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.startsWith('/api/cloud-checks/summary')) return jsonRes(summary);
    if (url.startsWith('/api/cloud-checks/results')) return jsonRes(results);
    if (url.startsWith('/api/cloud-accounts')) return jsonRes([]);
    return jsonRes([]);
  }));
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('CloudChecksScanner', () => {
  it('counts only checked rows in the pass rate and says how many were not checked', async () => {
    stubFetch({ total: 10, pass: 1, fail: 1, notChecked: 8, passPct: 50, bySeverity: {},
      byProvider: { aws: { pass: 1, fail: 1 } }, byService: {}, coverage: 1 }, []);
    render(<CloudChecksScanner />);
    expect(await screen.findByText('1 / 2 checked')).toBeTruthy();
    expect(screen.getByText('8 not checked')).toBeTruthy();
  });

  it('shows Not checked for a provider with nothing evaluated and the reason on a SKIP row', async () => {
    stubFetch({ total: 1, pass: 0, fail: 0, notChecked: 1, passPct: 0, bySeverity: {},
      byProvider: { aws: { pass: 0, fail: 0 } }, byService: {}, coverage: 0 },
      [{ checkId: 'aws-1', checkName: 'S3 Block Public Access', provider: 'aws', service: 's3', severity: 'high',
        result: 'SKIP', detail: NOT_CHECKED, accountId: 'a1', checked_at: '2026-11-19T10:00:00Z' }]);
    render(<CloudChecksScanner />);
    expect(await screen.findByText('Not checked')).toBeTruthy();
    expect(screen.getByText('—')).toBeTruthy();
    expect(screen.getByText(NOT_CHECKED)).toBeTruthy();
  });
});
