/**
 * Phase 84 / PTCH-01, D-09, D-10 (84-17): the start and rings calls and the Rollout rings card on the Rollouts tab.
 * authFetch is mocked with the 84-09 payloads (GET and PUT /api/patch-rollouts/rings).
 *
 * Value: protects=an operator builds the rings from the agent groups with every limit checked on screen before the
 * server is asked, sees the saved rings in one line, and never overwrites rings the page could not read without
 * being told; fails_when=a limit is accepted that the server refuses, the Canary ring can be renamed, moved or
 * removed, a group sits in two rings, Save is enabled when nothing changed or the form is invalid, a failed save
 * loses the operator's edits, or the card renders for a person without canManageRings; no_claim=the ring checks the
 * server repeats (backend/tests/test_patch_rollout_endpoints.py) and the start dialog (PatchRolloutStartDialog).
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
import { fetchRings, saveRings } from '../../services/patchRollouts/rings';
import { fetchDraft, fetchPendingPatches, postPreflight, startRollout } from '../../services/patchRollouts/start';
import { RingsSettings } from '../../components/patchRollouts/RingsSettings';
import type { RingsSettings as RingsData } from '../../services/patchRollouts/types';
import { jsonRes } from './_patchRolloutFixtures';

const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
const toast = showToast as unknown as ReturnType<typeof vi.fn>;

const groups = [
  { id: 'g1', name: 'canary-hosts', computers: 3, ring: 'Canary' },
  { id: 'g2', name: 'servers', computers: 1, ring: 'Pilot' },
  { id: 'g3', name: 'laptops', computers: 12, ring: null },
];
const ringOf = (key: string, name: string, groupIds: string[], over = {}) =>
  ({ key, name, groupIds, soakHours: 24, failPct: 10, minSample: 10, ...over });
const savedRings = (over: Partial<RingsData> = {}): RingsData => ({
  rings: [ringOf('canary', 'Canary', ['g1']), ringOf('ring-a', 'Pilot', ['g2']), ringOf('ring-b', 'Everyone else', [])],
  readable: true, groups, ...over,
});
const EMPTY: RingsData = { rings: [], readable: true, groups };

const SUMMARY = 'Canary (canary-hosts) -> Pilot (servers) -> Everyone else · 24-hour soak';
const NOT_SET = 'No rings set up yet · Canary needs a group before a rollout can start';
const LOAD_ERROR = "Couldn't load rollout rings. Check your connection and try again.";
const UNREADABLE = "Your rollout rings couldn't be read, so no rollout can start until they load.";
const NO_GROUPS = 'You have no agent groups yet. Create one in Agent Groups, then pick it here.';

let current: RingsData;
let putBody: { rings: Array<Record<string, unknown>> } | null;
let putStatus = 200;
let putDetail: string | undefined;

function serve(data: RingsData) {
  current = data;
  putBody = null;
  putStatus = 200;
  putDetail = undefined;
  mockFetch.mockReset();
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === 'PUT') {
      putBody = JSON.parse(String(init.body));
      if (putStatus !== 200) return Promise.resolve(jsonRes(putDetail === undefined ? {} : { detail: putDetail }, putStatus));
      current = { ...current, rings: putBody.rings.map((r, i) => ({ key: `k${i}`, ...(r as object) })) as RingsData['rings'] };
      return Promise.resolve(jsonRes(current));
    }
    return Promise.resolve(jsonRes(current));
  });
}

const open = async () => {
  fireEvent.click(await screen.findByRole('button', { name: 'Rollout rings' }));
};
const form = () => screen.getByRole('region', { name: 'Rollout rings' });
const block = (n: number) => within(form()).getAllByRole('group', { name: /^Ring \d/ })[n];
const saveBtn = () => screen.getByRole('button', { name: /^(Save rings|Saving\.\.\.)$/ });

beforeEach(() => { mockFetch.mockReset(); toast.mockReset(); });

// ------------------------------------------------------------------------------------------- calls

describe('start and rings calls', () => {
  it('fetchRings and saveRings use /rings and send the viewed organization', async () => {
    serve(savedRings());
    await fetchRings('tenant_x');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/rings?tenantId=tenant_x');
    mockFetch.mockClear();
    await saveRings(savedRings().rings);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/rings');
    expect(mockFetch.mock.calls[0][1]).toMatchObject({ method: 'PUT' });
    expect(JSON.parse(String(mockFetch.mock.calls[0][1].body)).rings).toHaveLength(3);
  });

  it('a failed rings call carries the status and the server sentence', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'A rollout needs 2 to 4 rings.' }, 422));
    await expect(saveRings([])).rejects.toMatchObject({ status: 422, detail: 'A rollout needs 2 to 4 rings.' });
    mockFetch.mockResolvedValue(jsonRes({}, 500));
    await expect(fetchRings()).rejects.toMatchObject({ status: 500, detail: '' });
  });

  it('fetchPendingPatches pages and searches', async () => {
    mockFetch.mockResolvedValue(jsonRes({ items: [], total: 0, offset: 50, limit: 50 }));
    await fetchPendingPatches({ offset: 50, limit: 50, search: 'KB 50', tenantId: 'tenant_x' });
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/pending-patches?search=KB+50&offset=50&limit=50&tenantId=tenant_x');
  });

  it('postPreflight sends the ids and startRollout sends the name and ids', async () => {
    mockFetch.mockResolvedValue(jsonRes({ rows: [], canStart: true, firstBlocker: null, nextWindowText: null }));
    await postPreflight(['KB1', 'KB2']);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/preflight');
    expect(mockFetch.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    expect(JSON.parse(String(mockFetch.mock.calls[0][1].body))).toEqual({ patchIds: ['KB1', 'KB2'] });
    mockFetch.mockClear();
    mockFetch.mockResolvedValue(jsonRes({ id: 'R1', name: 'Nov', simulation: false }, 201));
    await startRollout({ name: 'Nov', patchIds: ['KB1'] }, 'tenant_x');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts?tenantId=tenant_x');
    expect(JSON.parse(String(mockFetch.mock.calls[0][1].body))).toEqual({ name: 'Nov', patchIds: ['KB1'] });
  });

  it('startRollout errors carry the code and the rows of a 409 and a 422', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'One or more of these computers are already in another rollout.', code: 'already_in_rollout' }, 409));
    await expect(startRollout({ name: 'a', patchIds: ['KB1'] })).rejects.toMatchObject({ status: 409, code: 'already_in_rollout' });
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Add a maintenance window first.', rows: [{ check: 'window' }] }, 422));
    await expect(startRollout({ name: 'a', patchIds: ['KB1'] })).rejects.toMatchObject({ status: 422, rows: [{ check: 'window' }] });
  });

  it('fetchDraft asks for the suggestion', async () => {
    mockFetch.mockResolvedValue(jsonRes({ name: 'n', patchIds: [], removedCount: 0, host: 'h', cves: [] }));
    await fetchDraft('s 1', 'tenant_x');
    expect(mockFetch.mock.calls[0][0]).toBe('/api/patch-rollouts/draft?suggestion=s+1&tenantId=tenant_x');
  });
});

// ------------------------------------------------------------------------------------------- the card

describe('RingsSettings card', () => {
  it('is not rendered without canManageRings and makes no call', () => {
    serve(savedRings());
    const { container } = render(<RingsSettings canManageRings={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('collapsed: a button with aria-expanded and aria-controls under an h2, and the one-line summary', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    const button = await screen.findByRole('button', { name: 'Rollout rings' });
    expect(screen.getByRole('heading', { level: 2, name: 'Rollout rings' })).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button.getAttribute('aria-controls')).toBeTruthy();
    expect(await screen.findByText(SUMMARY)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save rings' })).toBeNull();
  });

  it('loading: an h-4 w-64 summary skeleton while collapsed and three h-16 skeletons with aria-busy while expanded', async () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    const { container } = render(<RingsSettings canManageRings />);
    expect(container.querySelector('.h-4.w-64')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Rollout rings' }));
    expect(container.querySelectorAll('.h-16')).toHaveLength(3);
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('nothing saved: the not-set summary, and the form starts with the Canary ring and a last ring', async () => {
    serve(EMPTY);
    render(<RingsSettings canManageRings />);
    expect(await screen.findByText(NOT_SET)).toBeInTheDocument();
    await open();
    expect(within(form()).getAllByRole('group', { name: /^Ring \d/ })).toHaveLength(2);
    expect(saveBtn()).toBeDisabled();
  });

  it('a load failure shows the red alert with Try again, which reads again', async () => {
    mockFetch.mockResolvedValue(jsonRes({}, 500));
    render(<RingsSettings canManageRings />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(LOAD_ERROR);
    serve(savedRings());
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(SUMMARY)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('unreadable settings: the blue block says no rollout can start until they load', async () => {
    serve(savedRings({ rings: [], readable: false }));
    render(<RingsSettings canManageRings />);
    expect(await screen.findByText(UNREADABLE)).toBeInTheDocument();
  });

  it('populated: one block per ring with name, groups, soak and, except on Canary, the failure limit', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    expect(within(form()).getAllByRole('group', { name: /^Ring \d/ })).toHaveLength(3);
    const canary = block(0);
    expect(within(canary).queryByRole('textbox')).toBeNull();
    expect(within(canary).getByText('Any failure halts the rollout.')).toBeInTheDocument();
    expect(within(canary).queryByText(/Halt when more than/)).toBeNull();
    const pilot = block(1);
    expect(within(pilot).getByRole('textbox')).toHaveValue('Pilot');
    expect(within(pilot).getByText(/Halt when more than/)).toBeInTheDocument();
    expect(within(pilot).getByLabelText('Soak after the last install or restart')).toHaveValue(24);
    expect(within(canary).getByRole('checkbox', { name: 'canary-hosts (3 computers)' })).toBeChecked();
  });

  it('the form says changes apply to later rollouts and that a computer in two rings joins the earlier one', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    expect(screen.getByText(/Changes apply to rollouts you start afterwards; a running rollout keeps the rings it started with\./)).toBeInTheDocument();
    expect(screen.getAllByText('A computer in groups from two rings joins the earlier ring.').length).toBeGreaterThan(0);
  });

  it('group rows read (1 computer) and (n computers), a group of another ring is disabled with (in Ring)', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    const canary = block(0);
    expect(within(canary).getByRole('checkbox', { name: 'servers (in Pilot)' })).toBeDisabled();
    const pilot = block(1);
    expect(within(pilot).getByRole('checkbox', { name: 'servers (1 computer)' })).toBeChecked();
    expect(within(pilot).getByRole('checkbox', { name: 'laptops (12 computers)' })).not.toBeDisabled();
  });

  it('the Canary name cannot be edited, moved or removed', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    const canary = block(0);
    expect(within(canary).queryByRole('button', { name: /Move Canary/ })).toBeNull();
    expect(within(canary).queryByRole('button', { name: /Remove ring Canary/ })).toBeNull();
    expect(within(canary).getByText('Canary')).toBeInTheDocument();
  });

  it('move buttons are disabled at the ends and move a ring earlier or later', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    expect(screen.getByRole('button', { name: 'Move Pilot earlier' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Everyone else later' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Move Pilot later' }));
    expect(within(block(1)).getByRole('textbox')).toHaveValue('Everyone else');
    expect(within(block(2)).getByRole('textbox')).toHaveValue('Pilot');
    expect(saveBtn()).not.toBeDisabled();
  });

  it('Add ring appends a ring, is hidden at four rings, and a ring can be removed down to two', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    fireEvent.click(screen.getByRole('button', { name: 'Add ring' }));
    expect(within(form()).getAllByRole('group', { name: /^Ring \d/ })).toHaveLength(4);
    expect(screen.queryByRole('button', { name: 'Add ring' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Remove ring Everyone else' }));
    fireEvent.click(screen.getByRole('button', { name: /^Remove ring Ring/ }));
    expect(within(form()).getAllByRole('group', { name: /^Ring \d/ })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: /^Remove ring/ }).every(b => (b as HTMLButtonElement).disabled)).toBe(true);
  });

  it('ring names are capped at 40 characters', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    expect(within(block(1)).getByRole('textbox')).toHaveAttribute('maxlength', '40');
  });

  // ---- validation: each sentence exactly as the contract words it

  it('Canary with no group: Pick at least one group for the Canary ring.', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    fireEvent.click(within(block(0)).getByRole('checkbox', { name: 'canary-hosts (3 computers)' }));
    expect(within(block(0)).getByRole('alert')).toHaveTextContent('Pick at least one group for the Canary ring.');
    expect(saveBtn()).toBeDisabled();
  });

  it('an empty ring name: Enter a ring name.', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: '   ' } });
    expect(within(block(1)).getByRole('alert')).toHaveTextContent('Enter a ring name.');
    expect(saveBtn()).toBeDisabled();
  });

  it('two rings with the same name: Ring names must be different.', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    fireEvent.change(within(block(2)).getByRole('textbox'), { target: { value: 'pilot' } });
    expect(within(block(2)).getByRole('alert')).toHaveTextContent('Ring names must be different.');
  });

  it('soak outside 1 to 168 hours: Enter hours between 1 and 168.', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    for (const bad of ['0', '169', '', 'abc']) {
      fireEvent.change(within(block(1)).getByLabelText('Soak after the last install or restart'), { target: { value: bad } });
      expect(within(block(1)).getByRole('alert')).toHaveTextContent('Enter hours between 1 and 168.');
    }
    fireEvent.change(within(block(1)).getByLabelText('Soak after the last install or restart'), { target: { value: '168' } });
    expect(within(block(1)).queryByRole('alert')).toBeNull();
  });

  it('a failure share outside 1 to 50: Enter a percentage between 1 and 50.', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    const input = within(block(1)).getByLabelText('Failure limit percentage for Pilot');
    fireEvent.change(input, { target: { value: '51' } });
    expect(within(block(1)).getByRole('alert')).toHaveTextContent('Enter a percentage between 1 and 50.');
    fireEvent.change(input, { target: { value: '0' } });
    expect(within(block(1)).getByRole('alert')).toHaveTextContent('Enter a percentage between 1 and 50.');
    fireEvent.change(input, { target: { value: '50' } });
    expect(within(block(1)).queryByRole('alert')).toBeNull();
  });

  it('a minimum outside 1 to 100: Enter a number between 1 and 100.', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    const input = within(block(1)).getByLabelText('Computers that must have reported for Pilot');
    fireEvent.change(input, { target: { value: '101' } });
    expect(within(block(1)).getByRole('alert')).toHaveTextContent('Enter a number between 1 and 100.');
    fireEvent.change(input, { target: { value: '1' } });
    expect(within(block(1)).queryByRole('alert')).toBeNull();
  });

  it('the last ring may have no group; a middle ring may not', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    expect(within(block(2)).queryByRole('alert')).toBeNull();
    fireEvent.click(within(block(1)).getByRole('checkbox', { name: 'servers (1 computer)' }));
    expect(within(block(1)).getByRole('alert')).toHaveTextContent('Pick at least one group for every ring except the last.');
    expect(saveBtn()).toBeDisabled();
  });

  it('with no agent groups a blue block links to Open agent groups', async () => {
    serve({ rings: [], readable: true, groups: [] });
    const onOpenAgentGroups = vi.fn();
    render(<RingsSettings canManageRings onOpenAgentGroups={onOpenAgentGroups} />);
    await open();
    expect(screen.getByText(NO_GROUPS)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open agent groups' }));
    expect(onOpenAgentGroups).toHaveBeenCalledTimes(1);
  });

  // ---- dirty, save, discard

  it('Save is disabled when clean, accent when dirty, and Discard changes puts the saved rings back', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    expect(saveBtn()).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Discard changes' })).toBeNull();
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    expect(saveBtn()).not.toBeDisabled();
    expect(saveBtn().className).toMatch(/bg-primary-600/);
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(within(block(1)).getByRole('textbox')).toHaveValue('Pilot');
    expect(saveBtn()).toBeDisabled();
  });

  it('Save sends the rings with their keys, shows Saving..., toasts, and the summary follows', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    fireEvent.change(within(block(1)).getByLabelText('Soak after the last install or restart'), { target: { value: '48' } });
    fireEvent.click(saveBtn());
    expect(saveBtn()).toHaveTextContent('Saving...');
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Rollout rings saved.', 'success'));
    expect(putBody?.rings).toHaveLength(3);
    expect(putBody?.rings[1]).toMatchObject({ key: 'ring-a', name: 'Servers', groupIds: ['g2'], soakHours: 48, failPct: 10, minSample: 10 });
    expect(putBody?.rings[0]).toMatchObject({ key: 'canary', name: 'Canary', groupIds: ['g1'] });
    await waitFor(() => expect(saveBtn()).toBeDisabled());
  });

  it('onSaved is called after a save so the list can read again', async () => {
    serve(savedRings());
    const onSaved = vi.fn();
    render(<RingsSettings canManageRings onSaved={onSaved} />);
    await open();
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    fireEvent.click(saveBtn());
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it('a failed save shows the red block with the server message and keeps the edits', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    putStatus = 422; putDetail = 'A group can be in only one ring.';
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    fireEvent.click(saveBtn());
    expect(await screen.findByText("Couldn't save rollout rings: A group can be in only one ring. Try again.")).toBeInTheDocument();
    expect(within(block(1)).getByRole('textbox')).toHaveValue('Servers');
    expect(saveBtn()).not.toBeDisabled();
  });

  it('a failed save with no message shows the fallback', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    putStatus = 500;
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    fireEvent.click(saveBtn());
    expect(await screen.findByText("Couldn't save rollout rings. Check your connection and try again.")).toBeInTheDocument();
  });

  it('a 403 closes the form and toasts that the person may not change rings', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    putStatus = 403;
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    fireEvent.click(saveBtn());
    await waitFor(() => expect(toast).toHaveBeenCalledWith("You don't have permission to change rollout rings.", 'error'));
    expect(screen.getByRole('button', { name: 'Rollout rings' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('works while rollouts are stopped: the card has no stop logic of its own', async () => {
    serve(savedRings());
    render(<RingsSettings canManageRings />);
    await open();
    fireEvent.change(within(block(1)).getByRole('textbox'), { target: { value: 'Servers' } });
    expect(saveBtn()).not.toBeDisabled();
  });

  it('the expanded state can be controlled, so the Start dialog can open the card', async () => {
    serve(savedRings());
    const onExpandedChange = vi.fn();
    const view = render(<RingsSettings canManageRings expanded={false} onExpandedChange={onExpandedChange} />);
    const button = await screen.findByRole('button', { name: 'Rollout rings' });
    fireEvent.click(button);
    expect(onExpandedChange).toHaveBeenCalledWith(true);
    expect(button).toHaveAttribute('aria-expanded', 'false');
    view.rerender(<RingsSettings canManageRings expanded onExpandedChange={onExpandedChange} />);
    expect(screen.getByRole('button', { name: 'Rollout rings' })).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByRole('button', { name: 'Add ring' })).toBeInTheDocument();
  });

  it('long group names are mono with break-all and the summary wraps', async () => {
    serve(savedRings({ groups: [{ id: 'g1', name: 'a'.repeat(80), computers: 2, ring: 'Canary' }, ...groups.slice(1)] }));
    render(<RingsSettings canManageRings />);
    await open();
    const name = within(block(0)).getByText('a'.repeat(80));
    expect(name.className).toMatch(/font-mono/);
    expect(name.className).toMatch(/break-all/);
  });

  it('renders server text as text only', async () => {
    serve(savedRings({ groups: [{ id: 'g1', name: '<img src=x onerror=alert(1)>', computers: 1, ring: 'Canary' }, ...groups.slice(1)] }));
    const { container } = render(<RingsSettings canManageRings />);
    await open();
    expect(container.querySelector('img')).toBeNull();
    expect(within(block(0)).getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
  });
});
