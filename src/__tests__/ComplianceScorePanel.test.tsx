/**
 * Compliance score panel: says how much of each framework was assessed.
 *  1. The overall score carries "N of M controls assessed".
 *  2. Each framework row carries "N of M assessed".
 *  3. A framework with no evidence reads "Not assessed", never 0%.
 *  4. A payload cached before the counts existed still renders, without them.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const fetchComplianceScore = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchComplianceScore: (...args: unknown[]) => fetchComplianceScore(...args),
}));

import { ComplianceScorePanel } from '../../components/ComplianceScorePanel';

const iso = {
  framework_id: 'iso27001', framework_name: 'ISO 27001', short_name: 'ISO 27001', score: 72.5,
  passing: 10, failing: 4, partial: 1, total_controls: 15, framework_controls: 93,
};
const hipaa = {
  framework_id: 'hipaa', framework_name: 'HIPAA', short_name: 'HIPAA', score: 0,
  passing: 0, failing: 0, partial: 0, total_controls: 0, framework_controls: 49,
};
const payload = {
  overall_score: 72.5, assessed_controls: 15, catalogue_controls: 142,
  computed_at: new Date().toISOString(), tenant_id: 't1', frameworks: [iso, hipaa],
};

describe('ComplianceScorePanel coverage', () => {
  beforeEach(() => { fetchComplianceScore.mockReset(); });

  it('shows how many controls the overall score covers', async () => {
    fetchComplianceScore.mockResolvedValue(payload);
    render(<ComplianceScorePanel />);
    expect(await screen.findByText('15 of 142 controls assessed')).toBeTruthy();
  });

  it('shows how many controls each framework score covers', async () => {
    fetchComplianceScore.mockResolvedValue(payload);
    render(<ComplianceScorePanel />);
    expect(await screen.findByText('15 of 93 assessed')).toBeTruthy();
    expect(screen.getByText('0 of 49 assessed')).toBeTruthy();
  });

  it('marks a framework with no evidence as not assessed instead of 0%', async () => {
    fetchComplianceScore.mockResolvedValue(payload);
    render(<ComplianceScorePanel />);
    expect(await screen.findByText('Not assessed')).toBeTruthy();
    expect(screen.queryByText('0%')).toBeNull();
    expect(screen.getAllByText('72.5%').length).toBe(2);       // overall and the ISO row
  });

  it('renders a payload cached before the counts existed', async () => {
    const { assessed_controls: _a, catalogue_controls: _c, ...old } = payload;
    fetchComplianceScore.mockResolvedValue({
      ...old,
      frameworks: [{ ...iso, framework_controls: undefined }],
    });
    render(<ComplianceScorePanel />);
    expect((await screen.findAllByText('72.5%')).length).toBe(2);
    expect(screen.queryByText(/controls assessed/)).toBeNull();
    expect(screen.queryByText(/ assessed$/)).toBeNull();
  });
});
