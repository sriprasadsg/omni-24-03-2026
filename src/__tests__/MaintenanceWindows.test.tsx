/**
 * Phase 84 / PTCH-05, D-01, D-02: the maintenance window calls, the add, edit and delete dialogs (84-12 task 1)
 * and the reworked Settings panel (task 2). authFetch is mocked, so the payloads follow the 84-05 contract.
 *
 * Value: protects=a window is never saved with a bad day, time or zone, weekdays go out as ISO numbers (Monday 1
 * to Sunday 7), and a failed save or delete shows the server's sentence; fails_when=a day toggle sends 0-6, a
 * past-midnight window loses its "next day" line, the first window can be saved without a zone, or Esc closes a
 * dialog while its request is in flight; no_claim=the server rules (backend/tests/test_maintenance_windows.py).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import {
  fetchWindows, createWindow, updateWindow, deleteWindow, fetchTimeZone, saveTimeZone, fetchWindowStatus,
  fetchChangeWindows,
} from '../../services/patchRollouts/windows';
import { WindowDialog, DeleteWindowDialog } from '../../components/patchRollouts/MaintenanceWindowDialog';
import type { MaintenanceWindow } from '../../services/patchRollouts/types';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function win(over: Partial<MaintenanceWindow> = {}): MaintenanceWindow {
  return {
    id: 'w1', name: 'Weekly patching', recurrence: 'weekly', startTime: '22:00', endTime: '02:00',
    daysOfWeek: [6, 7], startsAt: null, endsAt: null, scheduleText: '22:00 to 02:00 the next day',
    nextText: 'Next: Sat 7 Nov, 22:00', openNow: false, ...over,
  };
}

beforeEach(() => {
  mockFetch.mockReset();
  mockToast.mockReset();
});

describe('window calls', () => {
  it('fetchWindows reads the list from the maintenance route', async () => {
    mockFetch.mockResolvedValue(jsonRes([win()]));
    const rows = await fetchWindows();
    expect(rows).toHaveLength(1);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/maintenance/windows');
  });

  it('createWindow posts the body and returns the stored window', async () => {
    mockFetch.mockResolvedValue(jsonRes({ success: true, window: win() }, 201));
    const stored = await createWindow({ name: 'Weekly patching', recurrence: 'weekly', daysOfWeek: [6, 7] });
    expect(stored.id).toBe('w1');
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe('/api/maintenance/windows');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body).daysOfWeek).toEqual([6, 7]);
  });

  it('updateWindow puts to the window id and deleteWindow deletes it', async () => {
    mockFetch.mockResolvedValueOnce(jsonRes({ success: true, window: win({ name: 'New' }) }));
    const stored = await updateWindow('w1', { name: 'New', recurrence: 'daily', startTime: '01:00', endTime: '02:00' });
    expect(stored.name).toBe('New');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/maintenance/windows/w1');
    expect(mockFetch.mock.calls[0][1].method).toBe('PUT');
    mockFetch.mockResolvedValueOnce(jsonRes({ success: true }));
    await deleteWindow('w1');
    expect(mockFetch.mock.calls[1][0]).toBe('/api/maintenance/windows/w1');
    expect(mockFetch.mock.calls[1][1].method).toBe('DELETE');
  });

  it('the time zone, status and Change Management reads use their routes', async () => {
    mockFetch.mockResolvedValueOnce(jsonRes({ timeZone: 'Asia/Kolkata' }));
    expect(await fetchTimeZone()).toBe('Asia/Kolkata');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/maintenance/time-zone');
    mockFetch.mockResolvedValueOnce(jsonRes({ timeZone: 'Europe/Paris' }));
    expect(await saveTimeZone('Europe/Paris')).toBe('Europe/Paris');
    expect(mockFetch.mock.calls[1][1].method).toBe('PUT');
    expect(JSON.parse(mockFetch.mock.calls[1][1].body)).toEqual({ timeZone: 'Europe/Paris' });
    mockFetch.mockResolvedValueOnce(jsonRes({ state: 'open', text: 'Open until 02:00 (Asia/Kolkata).', timeZone: 'Asia/Kolkata' }));
    expect((await fetchWindowStatus()).state).toBe('open');
    expect(mockFetch.mock.calls[2][0]).toBe('/api/maintenance/status');
    mockFetch.mockResolvedValueOnce(jsonRes([]));
    await fetchChangeWindows();
    expect(mockFetch.mock.calls[3][0]).toBe('/api/changes/maintenance-windows');
  });

  it('a non-2xx answer becomes an Error carrying the server detail', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'A window can be up to 24 hours long.' }, 422));
    await expect(createWindow({ name: 'x', recurrence: 'daily' })).rejects.toThrow('A window can be up to 24 hours long.');
  });
});

function openDialog(over: Partial<React.ComponentProps<typeof WindowDialog>> = {}) {
  const onClose = vi.fn();
  const onSaved = vi.fn();
  render(<WindowDialog isOpen window={null} timeZone="Asia/Kolkata" onClose={onClose} onSaved={onSaved} {...over} />);
  return { onClose, onSaved };
}

const type = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('WindowDialog', () => {
  it('a Weekly window with no day says so and Save stays disabled', () => {
    openDialog();
    type('Window name', 'Weekly patching');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'weekly' } });
    type('Starts at', '22:00');
    type('Ends at', '02:00');
    expect(screen.getByRole('alert').textContent).toContain('Choose at least one day.');
    expect(screen.getByRole('button', { name: 'Save window' })).toBeDisabled();
  });

  it('a Daily 22:00 to 02:00 window explains the next day and its length', () => {
    openDialog();
    type('Window name', 'Nightly');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'daily' } });
    type('Starts at', '22:00');
    type('Ends at', '02:00');
    expect(screen.getByText('Ends the next day at 02:00.')).toBeInTheDocument();
    expect(screen.getByText('Runs 4 h 0 min in Asia/Kolkata.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save window' })).toBeEnabled();
  });

  it('equal times, a window over 24 hours and a one-time end before the start are refused inline', () => {
    openDialog();
    type('Window name', 'Odd');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'daily' } });
    type('Starts at', '10:00');
    type('Ends at', '10:00');
    expect(screen.getByRole('alert').textContent).toContain("The window can't start and end at the same time.");
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'none' } });
    type('Starts', '2026-11-10T22:00');
    type('Ends', '2026-11-10T21:00');
    expect(screen.getByRole('alert').textContent).toContain('The end must be after the start.');
    type('Ends', '2026-11-12T22:00');
    expect(screen.getByRole('alert').textContent).toContain('A window can be up to 24 hours long.');
    expect(screen.getByRole('button', { name: 'Save window' })).toBeDisabled();
  });

  it('Saturday and Sunday are sent as ISO weekdays 6 and 7, and monthly is not offered', async () => {
    const { onSaved } = openDialog();
    mockFetch.mockResolvedValue(jsonRes({ success: true, window: win() }, 201));
    type('Window name', 'Weekend');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'weekly' } });
    type('Starts at', '22:00');
    type('Ends at', '02:00');
    fireEvent.click(screen.getByRole('button', { name: 'Sunday' }));
    fireEvent.click(screen.getByRole('button', { name: 'Saturday' }));
    expect(screen.getByRole('button', { name: 'Saturday' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('option', { name: /monthly/i })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Save window' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.daysOfWeek).toEqual([6, 7]);
    expect(body.recurrence).toBe('weekly');
    expect(body.startTime).toBe('22:00');
    expect(body.timeZone).toBeUndefined();
    expect(mockToast).toHaveBeenCalledWith('Window "Weekend" saved.', 'success');
  });

  it('with no stored zone the Time zone field is shown, required, and sent with the first window', async () => {
    const { onSaved } = openDialog({ timeZone: null });
    mockFetch.mockResolvedValue(jsonRes({ success: true, window: win() }, 201));
    type('Window name', 'First');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'daily' } });
    type('Starts at', '01:00');
    type('Ends at', '03:00');
    expect(screen.getByRole('button', { name: 'Save window' })).toBeDisabled();
    type('Time zone', 'Mars/Olympus');
    expect(screen.getByRole('alert').textContent).toContain('Choose a time zone from the list, for example Asia/Kolkata.');
    expect(screen.getByRole('button', { name: 'Save window' })).toBeDisabled();
    type('Time zone', 'Asia/Kolkata');
    fireEvent.click(screen.getByRole('button', { name: 'Save window' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(mockFetch.mock.calls[0][1].body).timeZone).toBe('Asia/Kolkata');
  });

  it('a save failure shows the server sentence, and the fallback when there is none', async () => {
    openDialog();
    mockFetch.mockResolvedValueOnce(jsonRes({ detail: 'You can keep up to 50 maintenance windows. Delete one first.' }, 422));
    type('Window name', 'Nightly');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'daily' } });
    type('Starts at', '01:00');
    type('Ends at', '03:00');
    fireEvent.click(screen.getByRole('button', { name: 'Save window' }));
    await waitFor(() => expect(screen.getByText(/Couldn't save the window: You can keep up to 50/)).toBeInTheDocument());
    mockFetch.mockRejectedValueOnce(new Error('network'));
    fireEvent.click(screen.getByRole('button', { name: 'Save window' }));
    await waitFor(() =>
      expect(screen.getByText("Couldn't save the window. Check your connection and try again.")).toBeInTheDocument());
  });

  it('an edit puts to the window id with its stored values filled in', async () => {
    const { onSaved } = openDialog({ window: win() });
    expect(screen.getByText('Edit maintenance window')).toBeInTheDocument();
    expect(screen.getByLabelText('Window name')).toHaveValue('Weekly patching');
    expect(screen.getByRole('button', { name: 'Saturday' })).toHaveAttribute('aria-pressed', 'true');
    mockFetch.mockResolvedValue(jsonRes({ success: true, window: win({ name: 'Renamed' }) }));
    type('Window name', 'Renamed');
    fireEvent.click(screen.getByRole('button', { name: 'Save window' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][0]).toBe('/api/maintenance/windows/w1');
    expect(mockFetch.mock.calls[0][1].method).toBe('PUT');
  });

  it('has no bare Cancel button, and Esc does not close while the request is in flight', async () => {
    const { onClose } = openDialog();
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    let release: (r: Response) => void = () => {};
    mockFetch.mockReturnValue(new Promise<Response>(r => { release = r; }));
    type('Window name', 'Nightly');
    fireEvent.change(screen.getByLabelText('Repeats'), { target: { value: 'daily' } });
    type('Starts at', '01:00');
    type('Ends at', '03:00');
    fireEvent.click(screen.getByRole('button', { name: 'Save window' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    release(jsonRes({ success: true, window: win() }, 201));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Saving...' })).toBeNull());
  });

  it('Close without saving closes the dialog', () => {
    const { onClose } = openDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Close without saving' }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe('DeleteWindowDialog', () => {
  const openDelete = (isLast: boolean) => {
    const onClose = vi.fn();
    const onDeleted = vi.fn();
    render(<DeleteWindowDialog isOpen window={win()} isLast={isLast} onClose={onClose} onDeleted={onDeleted} />);
    return { onClose, onDeleted };
  };

  it('asks first, puts focus on Keep window and deletes with a red button', async () => {
    const { onDeleted } = openDelete(false);
    expect(screen.getByText('Delete this window?')).toBeInTheDocument();
    expect(screen.getByText(/"Weekly patching" will be removed\./)).toBeInTheDocument();
    expect(screen.queryByText(/This is the last window/)).toBeNull();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Keep window' })).toHaveFocus());
    mockFetch.mockResolvedValue(jsonRes({ success: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete window' }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE');
    expect(mockToast).toHaveBeenCalledWith('Window "Weekly patching" deleted.', 'success');
  });

  it('the only window adds the amber last-window block', () => {
    openDelete(true);
    const block = screen.getByText('This is the last window. Nobody can start a rollout until you add another.');
    expect(block).toBeInTheDocument();
    expect(within(block.closest('[role="status"]') as HTMLElement).getByText(/last window/)).toBeInTheDocument();
  });

  it('shows Deleting... while it works and an error when it fails', async () => {
    openDelete(false);
    let release: (r: Response) => void = () => {};
    mockFetch.mockReturnValue(new Promise<Response>(r => { release = r; }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete window' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Deleting...' })).toBeDisabled());
    release(jsonRes({ detail: 'Maintenance window not found' }, 404));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain("Couldn't delete the window: Maintenance window not found"));
  });
});
