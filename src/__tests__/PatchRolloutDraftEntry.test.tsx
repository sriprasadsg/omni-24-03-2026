/**
 * Phase 84 / PTCH-01, PTCH-06, D-11 (84-19): the two ways into the Start a rollout dialog from elsewhere: the Phase 83
 * vulnerability suggestion's Draft a rollout link and the OS Patches tab's Roll out in rings button. authFetch is mocked
 * with the 84-09 payloads.
 *
 * Value: protects=a vulnerability suggestion leads straight to a pre-filled Start dialog and the OS Patches list leads to
 * an empty one, and following either never stores, starts or schedules a rollout (only Start rollout inside the dialog
 * does); fails_when=the link says Open patching for someone who may start rollouts, says Draft a rollout for someone who
 * may not, the dialog is not open after the switch, the draft block or its removed-count line is missing, an unreadable
 * draft blocks the dialog, a viewer without start access gets a dialog, a POST to /api/patch-rollouts happens before the
 * Start button is pressed, or a one-shot intent reopens the dialog later; no_claim=the draft route itself
 * (backend/tests/test_patch_rollout_endpoints.py) and the dialog internals (PatchRolloutStartDialog.test.tsx).
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
import { PatchManagementDashboard } from '../../components/PatchManagementDashboard';
import { OsPatchesTab, OsAssetPatch } from '../../components/OsPatchesTab';
import { SuggestionBody, buildOpenViewHandlers } from '../../components/AutonomousOpsRowActions';
import type { OpenViewHandlers } from '../../components/AutonomousOpsRowActions';
import { UserContext } from '../../contexts/UserContext';
import type { AutonomousOpsRow } from '../../services/autonomousOpsApi';
import type { PendingPatch } from '../../services/patchRollouts/types';
import { flags, jsonRes, rolloutPage, card } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

const suggestionRow = (over: Partial<AutonomousOpsRow> = {}, kind: 'vulnerability' | 'file_change' = 'vulnerability'): AutonomousOpsRow => ({
  id: 'sugg-1', bucket: 'suggested', state: 'suggested', createdAt: '2026-11-05T10:00:00Z', actionLabel: 'Suggestion',
  classLine: 'Suggestion only', reasonText: 'Vulnerabilities were found.', ruleId: null, host: 'web-01', target: null,
  resultText: 'Suggested only.', controlEvent: null,
  suggestion: {
    kind, count: 2,
    items: kind === 'vulnerability' ? [{ cve: 'CVE-2026-1', package: 'openssl' }, { cve: 'CVE-2026-2', package: 'curl' }] : [{ path: '/etc/passwd' }],
    openView: kind === 'vulnerability' ? 'patchManagement' : 'fimMonitoring',
  },
  ...over,
});

// ------------------------------------------------------------------------------------------- the suggestion link

describe('Draft a rollout link on a vulnerability suggestion', () => {
  beforeEach(() => { mockFetch.mockReset(); });

  it('reads Draft a rollout with the full aria-label and opens the rollouts tab with the suggestion id', () => {
    const patchManagement = vi.fn();
    render(<SuggestionBody row={suggestionRow()} onOpenView={{ patchManagement, draftRollout: true }} />);
    const link = screen.getByRole('button', { name: 'Draft a rollout for the vulnerabilities on web-01' });
    expect(link).toHaveTextContent('Draft a rollout');
    expect(screen.queryByText('Open patching')).toBeNull();
    fireEvent.click(link);
    expect(patchManagement).toHaveBeenCalledTimes(1);
    expect(patchManagement).toHaveBeenCalledWith({ tab: 'rollouts', draft: 'sugg-1' });
  });

  it('following the link calls nothing on the server', () => {
    render(<SuggestionBody row={suggestionRow()} onOpenView={{ patchManagement: vi.fn(), draftRollout: true }} />);
    fireEvent.click(screen.getByRole('button', { name: /Draft a rollout/ }));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('without start access the link stays Open patching and sends no payload', () => {
    const patchManagement = vi.fn();
    render(<SuggestionBody row={suggestionRow()} onOpenView={{ patchManagement }} />);
    expect(screen.queryByText('Draft a rollout')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Open patching' }));
    expect(patchManagement).toHaveBeenCalledTimes(1);
    expect(patchManagement.mock.calls[0]).toEqual([]);
  });

  it('a viewer who cannot open Patching sees plain text, even when drafting is flagged', () => {
    render(<SuggestionBody row={suggestionRow()} onOpenView={{ draftRollout: true }} />);
    expect(screen.queryByRole('button', { name: /patching|Draft a rollout/ })).toBeNull();
    expect(screen.getByText('Open patching')).toBeInTheDocument();
  });

  it('a file change suggestion never offers a draft', () => {
    render(<SuggestionBody row={suggestionRow({}, 'file_change')} onOpenView={{ fimMonitoring: vi.fn(), patchManagement: vi.fn(), draftRollout: true }} />);
    expect(screen.queryByText('Draft a rollout')).toBeNull();
    expect(screen.getByRole('button', { name: 'Open file integrity' })).toBeInTheDocument();
  });

  it('the Showing x of y line keeps the plain Open patching link', () => {
    const row = suggestionRow();
    row.suggestion!.count = 14;
    const patchManagement = vi.fn();
    render(<SuggestionBody row={row} onOpenView={{ patchManagement, draftRollout: true }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }));
    const line = screen.getByText(/Showing 2 of 14/);
    fireEvent.click(within(line).getByRole('button', { name: 'Open patching' }));
    expect(patchManagement.mock.calls[0]).toEqual([]);
  });
});

describe('buildOpenViewHandlers', () => {
  it('returns undefined without a navigator', () => {
    expect(buildOpenViewHandlers(undefined, { canPatch: true, canFim: true, canDraft: true })).toBeUndefined();
  });

  it('adds draftRollout only when the viewer may open Patching and may start rollouts', () => {
    const go = vi.fn();
    expect(buildOpenViewHandlers(go, { canPatch: true, canFim: false, canDraft: true })?.draftRollout).toBe(true);
    expect(buildOpenViewHandlers(go, { canPatch: true, canFim: false, canDraft: false })?.draftRollout).toBeUndefined();
    expect(buildOpenViewHandlers(go, { canPatch: false, canFim: false, canDraft: true })?.draftRollout).toBeUndefined();
  });

  it('forwards the payload to the navigator and adds a target only for a screen the viewer may open', () => {
    const go = vi.fn();
    const handlers = buildOpenViewHandlers(go, { canPatch: true, canFim: false, canDraft: true }) as OpenViewHandlers;
    expect(handlers.fimMonitoring).toBeUndefined();
    handlers.patchManagement?.({ tab: 'rollouts', draft: 'x' });
    expect(go).toHaveBeenLastCalledWith('patchManagement', { tab: 'rollouts', draft: 'x' });
    handlers.patchManagement?.();
    expect(go).toHaveBeenLastCalledWith('patchManagement');
  });
});

// ------------------------------------------------------------------------------------------- OS Patches tab

const windowsAsset: OsAssetPatch = {
  agent_id: 'agent-win', hostname: 'EILT0197', os: 'Windows', os_version: '11', status: 'Online',
  pending_count: 1, last_checked: '2026-10-12T08:00:00Z', pending_updates: ['KB5034441'],
  pending_details: [{ id: 'KB5034441', title: '2026-10 Cumulative Update', severity: 'Critical' }],
};

describe('Roll out in rings on the OS Patches tab', () => {
  const tab = (props: Record<string, unknown> = {}) => render(
    <OsPatchesTab osPatches={[windowsAsset]} osPatchesMeta={null} osPatchesLoading={false}
      deployingAssetPatches={new Set()} onRefresh={vi.fn()} onApplyOsPatches={vi.fn()} {...props} />);

  it('shows the secondary button only with onRollOut, and pressing it calls the handler', () => {
    const onRollOut = vi.fn();
    tab({ onRollOut });
    const button = screen.getByRole('button', { name: 'Roll out in rings' });
    expect(button.className).toContain('min-h-10');
    fireEvent.click(button);
    expect(onRollOut).toHaveBeenCalledTimes(1);
  });

  it('shows no button without the prop, and leaves Deploy All alone', () => {
    const onApply = vi.fn();
    tab({ onApplyOsPatches: onApply });
    expect(screen.queryByText('Roll out in rings')).toBeNull();
    fireEvent.click(screen.getByText(/Deploy All/));
    expect(onApply).toHaveBeenCalledWith('agent-win', ['KB5034441']);
  });

  it('keeps Deploy All when the rollout button is present', () => {
    tab({ onRollOut: vi.fn() });
    expect(screen.getByText(/Deploy All/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Refresh/ })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------------------------------- the dashboard

describe('PatchManagementDashboard opens the Start dialog from an intent', () => {
  let pageFlags: ReturnType<typeof flags>;
  let draftReply: () => Promise<Response>;
  let patches: PendingPatch[];

  const patch = (id: string): PendingPatch => ({ patchId: id, title: `Title of ${id}`, os: 'windows', computers: 3 });
  const ringsPayload = { rings: [], readable: true, groups: [] };

  const posts = () => mockFetch.mock.calls.filter(c => /^\/api\/patch-rollouts(\?|$)/.test(String(c[0])) && c[1]?.method === 'POST');

  beforeEach(() => {
    pageFlags = flags();
    patches = [patch('KB5001'), patch('KB5002')];
    draftReply = () => Promise.resolve(jsonRes({
      name: 'Patches for CVE-2026-1 on web-01', patchIds: ['KB5001'], removedCount: 0, host: 'web-01', cves: ['CVE-2026-1'],
    }));
    mockFetch.mockReset();
    mockFetch.mockImplementation((url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://x');
      const method = init?.method ?? 'GET';
      if (u.pathname === '/api/patch-rollouts/rings') return Promise.resolve(jsonRes(ringsPayload));
      if (u.pathname === '/api/patch-rollouts/pending-patches') {
        return Promise.resolve(jsonRes({ items: patches, total: patches.length, offset: 0, limit: 50 }));
      }
      if (u.pathname === '/api/patch-rollouts/preflight') {
        return Promise.resolve(jsonRes({ rows: [], canStart: true, firstBlocker: null, nextWindowText: null }));
      }
      if (u.pathname === '/api/patch-rollouts/draft') return draftReply();
      if (u.pathname === '/api/patch-rollouts' && method === 'GET') {
        return Promise.resolve(jsonRes(rolloutPage([card({ id: 'R1', name: 'Existing' })], { flags: pageFlags })));
      }
      if (u.pathname === '/api/patches/os') return Promise.resolve(jsonRes({ assets: [windowsAsset], total_pending_os_patches: 1, scanned_at: '2026-10-12T08:00:00Z' }));
      return Promise.resolve(jsonRes([]));
    });
  });

  const dashboard = (props: Record<string, unknown> = {}) => render(
    <UserContext.Provider value={{
      currentUser: null, login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: () => true, enabledFeatures: [], serverLockedFeatures: {}, ...(props.user as object ?? {}),
    } as never}>
      <PatchManagementDashboard patches={[]} assets={[]} patchDeploymentJobs={[]} vulnerabilityScanJobs={[]}
        onSchedulePatchDeployment={vi.fn()} onScheduleVulnerabilityScan={vi.fn()} tenantId={null}
        {...Object.fromEntries(Object.entries(props).filter(([k]) => k !== 'user'))} />
    </UserContext.Provider>);

  const nameInput = () => screen.getByLabelText('Rollout name') as HTMLInputElement;
  const startInDialog = () => within(screen.getByRole('dialog')).getByRole('button', { name: /^(Start rollout|Starting\.\.\.)$/ });

  it('a draft intent selects the Rollouts tab and opens the dialog in draft state, then is consumed', async () => {
    const onIntentConsumed = vi.fn();
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed });
    const dialog = await screen.findByRole('dialog', { name: 'Start a rollout' });
    expect(await within(dialog).findByText(/Filled in from the vulnerabilities reported by web-01\./)).toBeInTheDocument();
    await waitFor(() => expect(nameInput().value).toBe('Patches for CVE-2026-1 on web-01'));
    await waitFor(() => expect(within(dialog).getByRole('checkbox', { name: /KB5001/ })).toBeChecked());
    expect(screen.getByRole('heading', { name: 'Rollouts' })).toBeInTheDocument();
    expect(onIntentConsumed).toHaveBeenCalled();
    expect(mockFetch.mock.calls.some(c => String(c[0]) === '/api/patch-rollouts/draft?suggestion=sugg-1')).toBe(true);
  });

  it('following the draft never stores, starts or schedules a rollout', async () => {
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed: vi.fn() });
    await screen.findByRole('dialog', { name: 'Start a rollout' });
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /KB5001/ })).toBeChecked());
    await waitFor(() => expect(startInDialog()).not.toBeDisabled());
    expect(posts()).toHaveLength(0);
  });

  it('a name for several vulnerabilities comes through from the server as is', async () => {
    draftReply = () => Promise.resolve(jsonRes({
      name: 'Patches for vulnerabilities on web-01', patchIds: ['KB5001', 'KB5002'], removedCount: 0, host: 'web-01', cves: ['CVE-1', 'CVE-2'],
    }));
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed: vi.fn() });
    await screen.findByRole('dialog', { name: 'Start a rollout' });
    await waitFor(() => expect(nameInput().value).toBe('Patches for vulnerabilities on web-01'));
  });

  it('with none of the suggested patches still pending: nothing ticked, the removed-count line, Start disabled', async () => {
    draftReply = () => Promise.resolve(jsonRes({
      name: 'Patches for CVE-2026-1 on web-01', patchIds: [], removedCount: 2, host: 'web-01', cves: ['CVE-2026-1'],
    }));
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed: vi.fn() });
    expect(await screen.findByText('2 patches are no longer needed and were removed.')).toBeInTheDocument();
    await screen.findByRole('checkbox', { name: /KB5001/ });
    expect(screen.getByText('0 selected')).toBeInTheDocument();
    expect(startInDialog()).toBeDisabled();
    expect(posts()).toHaveLength(0);
  });

  it('a draft that cannot be read opens the dialog without the block and with nothing ticked', async () => {
    draftReply = () => Promise.resolve(jsonRes({ detail: 'Suggestion not found.' }, 404));
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed: vi.fn() });
    await screen.findByRole('dialog', { name: 'Start a rollout' });
    await screen.findByRole('checkbox', { name: /KB5001/ });
    await waitFor(() => expect(mockFetch.mock.calls.some(c => String(c[0]).startsWith('/api/patch-rollouts/draft'))).toBe(true));
    expect(screen.queryByText(/Filled in from the vulnerabilities/)).toBeNull();
    expect(screen.getByText('0 selected')).toBeInTheDocument();
    expect(posts()).toHaveLength(0);
  });

  it('an intent without a draft opens an ordinary dialog and asks for no draft', async () => {
    dashboard({ intent: { tab: 'rollouts' }, onIntentConsumed: vi.fn() });
    await screen.findByRole('dialog', { name: 'Start a rollout' });
    await screen.findByRole('checkbox', { name: /KB5001/ });
    expect(screen.queryByText(/Filled in from the vulnerabilities/)).toBeNull();
    expect(mockFetch.mock.calls.some(c => String(c[0]).startsWith('/api/patch-rollouts/draft'))).toBe(false);
    expect(nameInput().value).toMatch(/^Rollout \d{1,2} /);
  });

  it('a viewer without start access gets the Rollouts tab and no dialog, and the intent is still consumed', async () => {
    pageFlags = flags({ canStart: false });
    const onIntentConsumed = vi.fn();
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed });
    await screen.findByText('Existing');
    await waitFor(() => expect(onIntentConsumed).toHaveBeenCalled());
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mockFetch.mock.calls.some(c => String(c[0]).startsWith('/api/patch-rollouts/draft'))).toBe(false);
  });

  it('closing the dialog does not bring it back, and Start rollout in the header opens a plain one', async () => {
    dashboard({ intent: { tab: 'rollouts', draft: 'sugg-1' }, onIntentConsumed: vi.fn() });
    const dialog = await screen.findByRole('dialog', { name: 'Start a rollout' });
    await within(dialog).findByText(/Filled in from the vulnerabilities/);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close without starting' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: 'Start rollout' }));
    await screen.findByRole('dialog', { name: 'Start a rollout' });
    expect(screen.queryByText(/Filled in from the vulnerabilities/)).toBeNull();
    expect(nameInput().value).toMatch(/^Rollout \d{1,2} /);
  });

  it('without an intent the dashboard opens on the Patches tab and no dialog', async () => {
    dashboard();
    await screen.findByRole('button', { name: /OS Patches/ });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Roll out in rings on the OS Patches tab switches to Rollouts and opens the dialog with nothing pre-filled', async () => {
    dashboard();
    fireEvent.click(await screen.findByRole('button', { name: /OS Patches/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Roll out in rings' }));
    await screen.findByRole('dialog', { name: 'Start a rollout' });
    expect(screen.getByRole('heading', { name: 'Rollouts' })).toBeInTheDocument();
    await screen.findByRole('checkbox', { name: /KB5001/ });
    expect(screen.queryByText(/Filled in from the vulnerabilities/)).toBeNull();
    expect(screen.getByText('0 selected')).toBeInTheDocument();
    expect(posts()).toHaveLength(0);
  });
});
