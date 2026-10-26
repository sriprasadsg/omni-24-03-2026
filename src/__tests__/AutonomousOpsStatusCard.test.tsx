/**
 * Phase 81 / ACTV-01, GATE-06, D-11, D-14, D-22, D-25: the Autonomous Ops status card, the Resume
 * dialog and the Super Admin platform-wide controls. authFetch is mocked; payloads follow 81-09.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({
  API_BASE: '/api',
  authFetch: vi.fn(),
}));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import {
  mockAuthFetch, jsonRes, statusPayload, platformStatusPayload, stopView, platformStopView, stoppedTenant,
  route, posts, card, TENANT_ADMIN, SECURITY_ANALYST, ANALYST, SUPER,
} from './_autonomousOpsCardHarness';

const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.mockReset();
});

// ── readout and notices ─────────────────────────────────────────────────────

describe('status card readout', () => {
  it('shows the four cells with their labels, values and helper lines', async () => {
    route({});
    const { container } = render(card(TENANT_ADMIN));
    await screen.findByText('Current level');
    expect(screen.getByText('Highest level allowed')).toBeInTheDocument();
    expect(screen.getByText('Shadow mode')).toBeInTheDocument();
    expect(container.querySelectorAll('dt')).toHaveLength(4);
    expect(screen.getAllByText('Automatic within limits')).toHaveLength(2);
    expect(screen.getByText(
      'Low-risk actions run on their own and can be undone. Riskier actions need your approval.',
    )).toBeInTheDocument();
    expect(screen.getByText('Set by a platform administrator.')).toBeInTheDocument();
    expect(screen.getByText('Off: actions are live')).toBeInTheDocument();
    expect(screen.getByText('Actions allowed by the level above are carried out.')).toBeInTheDocument();
    expect(screen.getByText('Not stopped')).toBeInTheDocument();
  });

  it('labels Off and Suggest only with their helper lines', async () => {
    route({ status: () => jsonRes(statusPayload({ level: 'suggest', maxLevel: 'suggest' })) });
    const first = render(card(ANALYST));
    expect(await screen.findAllByText('Suggest only')).toHaveLength(2);
    expect(screen.getByText('Autonomous Ops suggests actions. Every action needs your approval.')).toBeInTheDocument();
    first.unmount();

    route({ status: () => jsonRes(statusPayload({ level: 'off', maxLevel: 'suggest' })) });
    render(card(ANALYST));
    expect(await screen.findByText('Off')).toBeInTheDocument();
    expect(screen.getByText('Nothing is decided or recorded.')).toBeInTheDocument();
  });

  it('shows shadow mode as a simulation, saying whether it is set for the deployment or the organization', async () => {
    route({ status: () => jsonRes(statusPayload({ shadow: { effective: true, source: 'deployment' } })) });
    const first = render(card(ANALYST));
    const chip = await screen.findByText('On: simulation only');
    expect(chip.closest('span')?.className).toContain('border-dashed');
    expect(screen.getByText(/Autonomous Ops records what it would have done. Nothing is carried out./)).toBeInTheDocument();
    expect(screen.getByText(/Set for the whole deployment\./)).toBeInTheDocument();
    first.unmount();

    route({ status: () => jsonRes(statusPayload({ shadow: { effective: true, source: 'tenant' } })) });
    render(card(ANALYST));
    expect(await screen.findByText(/Set for this organization\./)).toBeInTheDocument();
    expect(screen.queryByText(/Set for the whole deployment\./)).toBeNull();
  });

  it('shows the circuit-breaker notice with the level it was lowered from', async () => {
    route({ status: () => jsonRes(statusPayload({ level: 'suggest', previousLevel: 'undoable_auto' })) });
    render(card(ANALYST));
    expect(await screen.findByText(
      'Lowered from Automatic within limits after several automatic actions in a row were undone or failed. A person with manage access can restore it.',
    )).toBeInTheDocument();
  });

  it('shows the Suggest-only notice when the setting could not be read', async () => {
    route({ status: () => jsonRes(statusPayload({ level: 'suggest', levelReadable: false })) });
    render(card(ANALYST));
    expect(await screen.findByText(
      "This organization's setting couldn't be read, so it is treated as Suggest only. Every action needs approval.",
    )).toBeInTheDocument();
  });

  it('shows the platform organization as Off with no controls', async () => {
    route({
      status: () => jsonRes(statusPayload({
        platformTenant: true, eligible: false, level: 'off', maxLevel: 'off', canStop: false,
      })),
    });
    render(card(TENANT_ADMIN));
    expect(await screen.findByText('Autonomous Ops is not available for the platform organization.')).toBeInTheDocument();
    expect(screen.getAllByText('Off')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /Stop automatic actions|Resume automatic actions/ })).toBeNull();
  });

  it('says the screen is not switched on for an organization that is not eligible', async () => {
    route({ status: () => jsonRes(statusPayload({ eligible: false })) });
    render(card(ANALYST));
    expect(await screen.findByText(
      "This screen isn't switched on for this organization, so nothing is decided or recorded for it.",
    )).toBeInTheDocument();
  });

  it('lays the readout out as 1, 2 and 4 columns', async () => {
    route({});
    const { container } = render(card(ANALYST));
    await screen.findByText('Current level');
    const grid = container.querySelector('dl') as HTMLElement;
    expect(grid.className).toContain('grid-cols-1');
    expect(grid.className).toContain('sm:grid-cols-2');
    expect(grid.className).toContain('xl:grid-cols-4');
  });
});

// ── controls ────────────────────────────────────────────────────────────────

describe('stop and resume controls', () => {
  it('renders Resume (and no Stop) when the server says canResume', async () => {
    route({ status: () => jsonRes(stoppedTenant()) });
    render(card(TENANT_ADMIN));
    expect(await screen.findByRole('button', { name: /Resume automatic actions/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Stop automatic actions/ })).toBeNull();
    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByText(/Stopped by Dana Admin on Oct 25, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Reason: Investigating a bad rule/)).toBeInTheDocument();
  });

  it('explains who can resume when the viewer cannot', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null }, canResume: false })) });
    const a = render(card(SECURITY_ANALYST));
    expect(await screen.findByText('Only an administrator with manage access can resume this.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resume automatic actions|Stop automatic actions/ })).toBeNull();
    a.unmount();

    // a tenant admin looking at a stop a Super Admin pressed, and at a platform-wide stop
    const b = render(card(TENANT_ADMIN));
    expect(await screen.findByText('Only a platform administrator can resume this.')).toBeInTheDocument();
    b.unmount();

    route({ status: () => jsonRes(statusPayload({ stop: { tenant: null, platform: platformStopView() }, canResume: false })) });
    render(card(SECURITY_ANALYST));
    expect(await screen.findByText('Only a platform administrator can resume this.')).toBeInTheDocument();
    expect(screen.getByText(/Stopped by Platform administrator on/)).toBeInTheDocument();
  });

  it('gives an analyst with no control access no controls and no helper line', async () => {
    route({ status: () => jsonRes(statusPayload({ stop: { tenant: stopView(), platform: null }, canStop: false })) });
    render(card(ANALYST));
    await screen.findByText('Stopped');
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByText(/can resume this/)).toBeNull();
  });

  it('gives Platform Support no controls even if the permission list names them', async () => {
    route({ status: () => jsonRes(statusPayload({ canStop: false })) });
    render(card(SUPER, { role: 'Platform Support', tenantId: 'tenant-a' }));
    await screen.findByText('Current level');
    expect(screen.queryByRole('button')).toBeNull();
  });
});

// ── Resume dialog ───────────────────────────────────────────────────────────

describe('Resume dialog', () => {
  async function openResume(statusOver: Record<string, unknown> = {}) {
    route({ status: () => jsonRes(stoppedTenant(statusOver)) });
    render(card(TENANT_ADMIN));
    fireEvent.click(await screen.findByRole('button', { name: /Resume automatic actions/ }));
    return await screen.findByRole('dialog');
  }

  it('shows who stopped it, requires a typed reason and never submits from the keyboard', async () => {
    const dialog = await openResume();
    expect(within(dialog).getByText('Resume automatic actions?')).toBeInTheDocument();
    expect(dialog.textContent).toContain('Stopped by Dana Admin on Oct 25, 2026');
    expect(dialog.textContent).toContain('Reason: Investigating a bad rule');
    expect(dialog.textContent).toContain(
      'Actions that were held back during the stop were cancelled and will not run. New decisions can start again.',
    );
    const field = within(dialog).getByLabelText('Reason for resuming') as HTMLTextAreaElement;
    expect(field.getAttribute('aria-required')).toBe('true');
    expect(field.maxLength).toBe(500);
    await waitFor(() => expect(document.activeElement).toBe(field));

    const confirm = within(dialog).getByRole('button', { name: 'Resume automatic actions' });
    expect(confirm).toBeDisabled();

    // Enter on an empty field shows the validation message
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Enter a reason to resume.');

    // whitespace only counts as empty
    fireEvent.change(field, { target: { value: '   ' } });
    expect(confirm).toBeDisabled();
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Enter a reason to resume.');

    // no shortcut submit, even with text
    fireEvent.change(field, { target: { value: 'Rule fixed' } });
    expect(confirm).toBeEnabled();
    fireEvent.keyDown(field, { key: 'Enter', ctrlKey: true });
    fireEvent.keyDown(field, { key: 'Enter', metaKey: true });
    expect(posts('/api/autonomous-ops/resume')).toHaveLength(0);
    expect(within(dialog).getByText('10/500')).toBeInTheDocument();
  });

  it('resumes with the trimmed reason once, closes, toasts and refetches the status', async () => {
    let release: (r: Response) => void = () => {};
    const dialog = await openResume();
    route({
      status: () => jsonRes(statusPayload()),
      resume: () => new Promise<Response>(r => { release = r; }),
    });
    const field = within(dialog).getByLabelText('Reason for resuming');
    fireEvent.change(field, { target: { value: '  Rule fixed  ' } });
    const confirm = within(dialog).getByRole('button', { name: 'Resume automatic actions' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Resuming...' })).toBeDisabled());
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeEnabled();
    expect(posts('/api/autonomous-ops/resume')).toHaveLength(1);
    expect(JSON.parse((posts('/api/autonomous-ops/resume')[0][1] as RequestInit).body as string)).toEqual({ reason: 'Rule fixed' });

    await act(async () => { release(jsonRes(statusPayload())); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Automatic actions resumed.', 'success');
    await waitFor(() => expect(screen.getByText('Not stopped')).toBeInTheDocument());
  });

  it('adds the shadow clause when shadow mode is on', async () => {
    const dialog = await openResume({ shadow: { effective: true, source: 'tenant' } });
    expect(dialog.textContent).toContain('New decisions can start again in shadow mode, so nothing is carried out.');
  });

  it('closes with an error toast when a platform administrator pressed the stop meanwhile (403)', async () => {
    const dialog = await openResume();
    route({
      status: () => jsonRes(stoppedTenant({ canResume: false })),
      resume: () => jsonRes({ detail: 'Forbidden' }, 403),
    });
    fireEvent.change(within(dialog).getByLabelText('Reason for resuming'), { target: { value: 'Rule fixed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume automatic actions' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Only a platform administrator can resume this stop.', 'error');
  });

  it('keeps the dialog open with the typed reason and the server message on any other failure', async () => {
    const dialog = await openResume();
    route({
      status: () => jsonRes(stoppedTenant()),
      resume: () => jsonRes({ detail: 'Storage is busy.' }, 503),
    });
    const field = within(dialog).getByLabelText('Reason for resuming') as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: 'Rule fixed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume automatic actions' }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't resume automatic actions: Storage is busy. Try again.");
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(field.value).toBe('Rule fixed');
    expect(within(dialog).getByRole('button', { name: 'Resume automatic actions' })).toBeEnabled();
  });

  it('falls back to the connection message when the server sent none', async () => {
    const dialog = await openResume();
    mockAuthFetch.mockImplementation(async (url: string) => {
      if (url.split('?')[0] === '/api/autonomous-ops/resume') throw new Error('network down');
      return jsonRes(stoppedTenant());
    });
    fireEvent.change(within(dialog).getByLabelText('Reason for resuming'), { target: { value: 'Rule fixed' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Resume automatic actions' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      "Couldn't resume automatic actions. Check your connection and try again.",
    );
  });
});

// ── Stop dialog failures ────────────────────────────────────────────────────

describe('Stop dialog failures', () => {
  it('a 409 closes the dialog with an info toast naming who stopped it', async () => {
    route({ stop: () => jsonRes({ detail: 'Already stopped.', by: 'Sam Responder' }, 409) });
    render(card(SECURITY_ANALYST));
    fireEvent.click(await screen.findByRole('button', { name: /Stop automatic actions/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stop automatic actions' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mockToast).toHaveBeenCalledWith('Automatic actions were already stopped by Sam Responder.', 'info');
  });

  it('keeps the dialog open with the typed reason and the server message on failure', async () => {
    route({ stop: () => jsonRes({ detail: 'Storage is busy.' }, 503) });
    render(card(SECURITY_ANALYST));
    fireEvent.click(await screen.findByRole('button', { name: /Stop automatic actions/ }));
    const dialog = await screen.findByRole('dialog');
    const field = within(dialog).getByLabelText('Reason (optional)') as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: 'Looks wrong' } });
    fireEvent.keyDown(field, { key: 'Enter', ctrlKey: true });
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent(
      "Couldn't stop automatic actions: Storage is busy. Try again. If it keeps failing, ask a platform administrator to use the platform-wide stop.",
    );
    expect(field.value).toBe('Looks wrong');
    expect(field.maxLength).toBe(500);
    expect(within(dialog).getByText('11/500')).toBeInTheDocument();
  });
});

