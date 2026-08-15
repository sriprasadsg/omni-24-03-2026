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

  it('renders: section label, field label, helper text, unit suffix, and idle button label', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 14 });
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('14'));

    expect(screen.getByText('Remediation SLA')).toBeInTheDocument();
    expect(screen.getByText('At-Risk Window')).toBeInTheDocument();
    expect(screen.getByText(/flagged "at risk"/)).toBeInTheDocument();
    expect(screen.getByText('days')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save SLA Window' })).toBeInTheDocument();
  });

  it('fetch: settles the input to the resolved windowDays value', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 14 });
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('14'));
  });

  it('fetch: renders whatever windowDays the wrapper resolves with — 7 here is an ordinary resolved value, not a simulated failure (the wrapper is module-mocked, so its internal soft-fail catch in apiService.ts is not exercised by this test)', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 7 });
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('7'));
  });

  it('fetch: never renders blank when the resolved payload has no windowDays key', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({});
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('7'));
  });

  it('error: a rejected save shows the generic error toast, never the success toast, and never leaks role/status/path', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 14 });
    saveRemediationSlaWindow.mockRejectedValue(new Error('Failed to save remediation SLA window'));
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('14'));

    fireEvent.click(screen.getByRole('button', { name: 'Save SLA Window' }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith('Failed to save threshold — please try again', 'error')
    );
    expect(showToast).not.toHaveBeenCalledWith('SLA window updated', 'success');

    const toastCalls = showToast.mock.calls.map(args => String(args[0]));
    for (const message of toastCalls) {
      expect(message).not.toMatch(/admin|role|403|422|5\d\d|\/api\//i);
    }
  });

  it('validat: clamps the input to [1, 365] on change', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 14 });
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('14'));

    expect(input.min).toBe('1');
    expect(input.max).toBe('365');

    fireEvent.change(input, { target: { value: '999' } });
    expect(input.value).toBe('365');

    fireEvent.change(input, { target: { value: '0' } });
    expect(input.value).toBe('1');
  });

  it('validat: clearing the field then typing a new digit does not corrupt the value', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 200 });
    render(<RemediationSlaSettings />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('200'));

    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe('');

    fireEvent.change(input, { target: { value: '5' } });
    expect(input.value).toBe('5');
  });

  it('validat: an out-of-range held value (server response outside 1-365) shows the validation message and disables Save', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 400 });
    render(<RemediationSlaSettings />);

    await waitFor(() =>
      expect(screen.getByText('Must be between 1 and 365 days.')).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: 'Save SLA Window' })).toBeDisabled();
  });

  it('save: while a save is in flight, the button is disabled and reads "Saving..."', async () => {
    fetchRemediationSlaWindow.mockResolvedValue({ windowDays: 14 });
    let resolveSave: (() => void) | undefined;
    saveRemediationSlaWindow.mockImplementation(
      () => new Promise<void>(resolve => { resolveSave = resolve; })
    );
    render(<RemediationSlaSettings />);

    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('14'));

    fireEvent.click(screen.getByRole('button', { name: 'Save SLA Window' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled());

    resolveSave?.();
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('SLA window updated', 'success'));
  });
});
