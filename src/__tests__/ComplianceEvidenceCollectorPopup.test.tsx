/**
 * Compliance Evidence Collector: a computer's row opens a popup listing the evidence collected for it.
 *  1. The computer's name opens the popup, which lists each control with its status and the check behind it.
 *  2. Failing controls come first.
 *  3. "Show evidence" reveals the evidence text as plain text.
 *  4. A computer with no evidence says so.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

const authFetch = vi.fn();

vi.mock('../../services/apiService', () => ({
  authFetch: (...args: unknown[]) => authFetch(...args),
  runAgentComplianceScan: vi.fn(),
}));

import { ComplianceEvidenceStatusDashboard } from '../../components/ComplianceEvidenceStatusDashboard';
import type { Agent } from '../../types';

const agents = [
  { id: 'a1', hostname: 'EILT0197', assetId: 'asset-EILT0197', capabilities: ['compliance_enforcement'] },
  { id: 'a2', hostname: 'NEW-PC', assetId: 'asset-NEW-PC', capabilities: [] },
] as unknown as Agent[];

const records = [
  { assetId: 'asset-EILT0197', controlId: 'A.8.24', status: 'Compliant', checkName: 'BitLocker Drive Encryption',
    lastUpdated: '2026-11-16T14:38:40Z',
    evidence: [{ name: 'System Check: BitLocker Drive Encryption', uploadedAt: '2026-11-16T14:38:40Z', systemGenerated: true,
                 content: '# System Compliance Evidence\n**Result:** Pass\n<b>System drive is BitLocker protected</b>' }] },
  { assetId: 'asset-EILT0197', controlId: 'PCI-6.2', status: 'Non-Compliant', checkName: 'Windows Automatic Updates',
    lastUpdated: '2026-11-16T14:38:40Z', evidence: [] },
];

describe('Compliance Evidence Collector popup', () => {
  beforeEach(() => {
    authFetch.mockReset();
    authFetch.mockResolvedValue({ ok: true, json: async () => records });
  });

  it("opens from the computer's name and lists each control with its status and check", async () => {
    render(<ComplianceEvidenceStatusDashboard agents={agents} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Show evidence for EILT0197' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('A.8.24')).toBeTruthy();
    expect(within(dialog).getByText('BitLocker Drive Encryption')).toBeTruthy();
    expect(within(dialog).getByText('PCI-6.2')).toBeTruthy();
    expect(within(dialog).getByText('Windows Automatic Updates')).toBeTruthy();
    expect(within(dialog).getByText(/^2 controls with evidence · last collected /)).toBeTruthy();
  });

  it('lists failing controls first', async () => {
    render(<ComplianceEvidenceStatusDashboard agents={agents} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Show evidence for EILT0197' }));
    const rows = within(await screen.findByRole('dialog')).getAllByTestId('evidence-control');
    expect(rows.map(r => r.getAttribute('data-control'))).toEqual(['PCI-6.2', 'A.8.24']);
  });

  it('reveals the evidence text as plain text', async () => {
    render(<ComplianceEvidenceStatusDashboard agents={agents} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Show evidence for EILT0197' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Show evidence for A.8.24' }));
    const text = within(dialog).getByText(/System drive is BitLocker protected/);
    expect(text.textContent).toContain('<b>System drive is BitLocker protected</b>');   // shown as text, not HTML
    expect(dialog.querySelector('b')).toBeNull();
  });

  it('says so when a computer has no evidence yet', async () => {
    render(<ComplianceEvidenceStatusDashboard agents={agents} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Show evidence for NEW-PC' }));
    expect(within(await screen.findByRole('dialog')).getByText('No evidence has been collected for this computer yet.')).toBeTruthy();
  });
});
