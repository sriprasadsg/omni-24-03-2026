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

// ── platform-wide controls ──────────────────────────────────────────────────

describe('platform-wide stop (Super Admin)', () => {
  it('is not shown to a tenant admin', async () => {
    route({ status: () => jsonRes(statusPayload({ canStopPlatform: false })) });
    render(card(TENANT_ADMIN));
    await screen.findByText('Current level');
    expect(screen.queryByText('Platform-wide stop')).toBeNull();
    expect(screen.queryByRole('button', { name: /all organizations/ })).toBeNull();
  });

  it('presses Stop all organizations from inside a tenant and toasts', async () => {
    route({ status: () => jsonRes(statusPayload({ canStopPlatform: true })) });
    render(card(SUPER, { role: 'Super Admin', tenantId: 'tenant-a' }));
    expect(await screen.findByText('Platform-wide stop')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Stop all organizations' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Stop automatic actions for every organization?')).toBeInTheDocument();
    expect(dialog.textContent).toContain(
      'This halts new automatic decisions across the whole platform and holds back queued automatic instructions for all organizations. Only a platform administrator can resume it.',
    );
    fireEvent.change(within(dialog).getByLabelText('Reason (optional)'), { target: { value: 'Incident 42' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stop all organizations' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(posts('/api/platform/autonomous-ops/stop')).toHaveLength(1);
    expect(JSON.parse((posts('/api/platform/autonomous-ops/stop')[0][1] as RequestInit).body as string)).toEqual({ reason: 'Incident 42' });
    expect(mockToast).toHaveBeenCalledWith('Automatic actions stopped for every organization.', 'success');
  });

  it('resumes all organizations only with a typed reason, using the server canResumePlatform flag', async () => {
    route({
      status: () => jsonRes(statusPayload({
        canStopPlatform: true, canResumePlatform: true,
        stop: { tenant: null, platform: platformStopView({ by: 'Root Admin' }) },
      })),
    });
    render(card(SUPER, { role: 'Super Admin', tenantId: 'tenant-a' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Resume all organizations' }));
    expect(screen.queryByRole('button', { name: 'Stop all organizations' })).toBeNull();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Resume automatic actions for every organization?')).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: 'Resume all organizations' });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('Reason for resuming'), { target: { value: 'Incident closed' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(JSON.parse((posts('/api/platform/autonomous-ops/resume')[0][1] as RequestInit).body as string)).toEqual({ reason: 'Incident closed' });
    expect(mockToast).toHaveBeenCalledWith('Automatic actions resumed for every organization.', 'success');
  });

  it('in platform scope replaces the readout with the platform stop and the tenant stop count', async () => {
    route({});
    const { container } = render(card(SUPER, { role: 'Super Admin' }));
    expect(await screen.findByText('2 organizations stopped')).toBeInTheDocument();
    expect(screen.getByText('Each organization can also be stopped on its own.')).toBeInTheDocument();
    expect(screen.queryByText('Current level')).toBeNull();
    expect(container.querySelectorAll('dt')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Stop all organizations' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop automatic actions' })).toBeNull();
  });
});

// ── card states ─────────────────────────────────────────────────────────────

describe('card states', () => {
  const FORBIDDEN = ['truncate', 'font-medium', 'font-bold'];
  const noForbidden = (container: HTMLElement) => {
    for (const cls of FORBIDDEN) expect(container.querySelector(`.${cls}`)).toBeNull();
  };

  it('loading: four h-16 skeletons, one h-10 w-56 skeleton and aria-busy', async () => {
    route({ status: () => new Promise<Response>(() => {}) });
    const { container } = render(card(TENANT_ADMIN));
    await waitFor(() => expect(container.querySelector('[aria-busy="true"]')).not.toBeNull());
    expect(container.querySelectorAll('.h-16')).toHaveLength(4);
    expect(container.querySelectorAll('.h-10.w-56')).toHaveLength(1);
    expect(container.querySelector('.card')?.getAttribute('aria-busy')).toBe('true');
    noForbidden(container);
  });

  it('error: a role=alert block with Try again, Stop still available and Resume disabled', async () => {
    let fail = true;
    route({ status: () => (fail ? jsonRes({ detail: 'down' }, 503) : jsonRes(statusPayload())) });
    const { container } = render(card(TENANT_ADMIN));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load the current status. Stop is still available.");
    expect(screen.getByRole('button', { name: /Stop automatic actions/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Resume automatic actions/ })).toBeDisabled();
    noForbidden(container);

    fail = false;
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Current level')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('error: an analyst without the stop permission sees no Stop hint and no controls', async () => {
    route({ status: () => jsonRes({ detail: 'down' }, 503) });
    render(card(ANALYST));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load the current status.");
    expect(alert.textContent).not.toContain('Stop is still available');
    expect(screen.queryByRole('button', { name: /Stop automatic actions|Resume automatic actions/ })).toBeNull();
  });

  it('makes no request and renders nothing when disabled', async () => {
    route({});
    const { container } = render(card(ANALYST, { enabled: false }));
    await act(async () => { await Promise.resolve(); });
    expect(mockAuthFetch).not.toHaveBeenCalled();
    expect(container.querySelector('.card')).toBeNull();
  });

  it('populated: wraps long reasons and names, nothing truncated or in a forbidden weight', async () => {
    const long = 'y'.repeat(450);
    route({ status: () => jsonRes(stoppedTenant({ tenantName: 'T'.repeat(120), stop: { tenant: stopView({ reason: long }), platform: null } })) });
    const { container } = render(card(TENANT_ADMIN));
    const line = await screen.findByText(new RegExp(`Reason: ${long}`));
    expect(line.className).toContain('break-words');
    noForbidden(container);
  });

  it('uses the divider and a 40 px control row for the controls', async () => {
    route({});
    const { container } = render(card(TENANT_ADMIN));
    const stop = await screen.findByRole('button', { name: /Stop automatic actions/ });
    expect(stop.className).toContain('min-h-10');
    expect(stop.className).toContain('px-4');
    expect(stop.className).toContain('bg-red-600');
    expect(container.querySelector('.border-t.pt-6')).not.toBeNull();
  });

  it('renders the Resume button with the accent classes', async () => {
    route({ status: () => jsonRes(stoppedTenant()) });
    render(card(TENANT_ADMIN));
    const resume = await screen.findByRole('button', { name: /Resume automatic actions/ });
    expect(resume.className).toContain('bg-primary-600');
    expect(resume.className).toContain('min-h-10');
  });
});
