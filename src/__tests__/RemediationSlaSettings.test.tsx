/**
 * Phase 62 (plan 62-01) RemediationSlaSettings behavior (SLA-03):
 *  1. Mounts, reads the tenant's at-risk window, edits it, saves it, and
 *     shows the success toast — the tracer's happy-path proof (Task 1).
 *  Further behaviors (renders / fetch soft-fail / error / validation)
 *  are added in Task 2.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const fetchRemediationSlaWindow = vi.fn();
const saveRemediationSlaWindow = vi.fn();
const showToast = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchRemediationSlaWindow: (...args: unknown[]) => fetchRemediationSlaWindow(...args),
  saveRemediationSlaWindow: (...args: unknown[]) => saveRemediationSlaWindow(...args),
}));

vi.mock('../../utils/toast', () => ({
  showToast: (...args: unknown[]) => showToast(...args),
}));

import { RemediationSlaSettings } from '../../components/RemediationSlaSettings';

describe('RemediationSlaSettings', () => {
  beforeEach(() => {
    fetchRemediationSlaWindow.mockReset();
    saveRemediationSlaWindow.mockReset();
    showToast.mockReset();
  });

  it('save: edits the at-risk window and persists it with a success toast', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 21 });
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('21'));

    saveRemediationSlaWindow.mockResolvedValue(undefined);
    fireEvent.change(input, { target: { value: '30' } });
    expect(input.value).toBe('30');

    const button = screen.getByRole('button', { name: /save sla window/i });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    await waitFor(() => expect(saveRemediationSlaWindow).toHaveBeenCalledTimes(1));
    expect(saveRemediationSlaWindow).toHaveBeenCalledWith(30);

    await waitFor(() => expect(showToast).toHaveBeenCalledWith('SLA window updated', 'success'));
  });
});
