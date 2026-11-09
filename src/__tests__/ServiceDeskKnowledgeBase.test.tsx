/**
 * Phase 85 / DESK-06, DESK-07 (85-21): the Knowledge Base screen's Help desk side of 85-UI-SPEC section 6 - the Help desk
 * switch and chips, the filter pill, the readiness note and the client calls. authFetch and the toast are mocked; the
 * payloads follow 85-15-SUMMARY.md. Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import { KB, fill } from '../../components/serviceDesk/serviceDeskCopy';
import {
  addStarters, createArticle, dismissGap, fetchArticle, fetchGaps, fetchStarterStatus, patchArticle, restoreGap,
} from '../../services/serviceDesk/knowledgeApi';
import {
  bodyOf, calls, deferred, docList, jsonRes, kbDoc, kbFlags, mockFetch, renderKb, serve,
} from './_serviceDeskKnowledgeHarness';

const LIST = '/api/knowledge/docs';
const PATCH_1 = '/api/knowledge/docs/kb-1';

beforeEach(() => { mockFetch.mockReset(); vi.mocked(showToast).mockReset(); });

// ------------------------------------------------------------------------------------------ the client calls

describe('knowledgeApi', () => {
  it('sends each call to its route with the method the server expects', async () => {
    mockFetch.mockResolvedValue(jsonRes({}));
    await fetchArticle('kb 1');
    await patchArticle('kb-1', { helpdesk: true });
    await createArticle({ title: 'T', content: 'C', tags: [], helpdesk: true, gapGroupId: 'g-1' });
    await fetchStarterStatus();
    await addStarters();
    await fetchGaps();
    await fetchGaps(true);
    await dismissGap('g-1');
    await restoreGap('g-1');
    const seen = mockFetch.mock.calls.map(([u, init]) => `${init?.method ?? 'GET'} ${u}`);
    expect(seen).toEqual([
      'GET /api/knowledge/docs/kb%201', 'PATCH /api/knowledge/docs/kb-1', 'POST /api/knowledge/helpdesk/articles',
      'GET /api/knowledge/helpdesk/starters', 'POST /api/knowledge/helpdesk/starters', 'GET /api/knowledge/helpdesk/gaps',
      'GET /api/knowledge/helpdesk/gaps?dismissed=true', 'POST /api/knowledge/helpdesk/gaps/g-1/dismiss',
      'POST /api/knowledge/helpdesk/gaps/g-1/restore',
    ]);
    expect(bodyOf(mockFetch.mock.calls[1])).toEqual({ helpdesk: true });
    expect(bodyOf(mockFetch.mock.calls[2])).toMatchObject({ gapGroupId: 'g-1', helpdesk: true });
  });

  it('throws the server status and message for a refused call', async () => {
    mockFetch.mockResolvedValue(jsonRes({ detail: 'Nope.' }, 403));
    await expect(patchArticle('kb-1', { helpdesk: true })).rejects.toMatchObject({ status: 403, detail: 'Nope.' });
  });
});

// ------------------------------------------------------------------------------------------ rows, chips and switch

describe('document rows', () => {
  const rows = () => docList([
    kbDoc({ id: 'kb-1', title: 'Printer fix' }),
    kbDoc({ id: 'kb-2', title: 'Starter VPN', helpdesk: true, starterKey: 'vpn' }),
    kbDoc({ id: 'kb-3', title: 'OWASP guide', tenantId: 'global' }),
  ], kbFlags({ helpdeskCount: 1 }));

  it('gives a tenant row the switch, and a platform row the chip and the shared-reference line with no switch', async () => {
    serve({ [`GET ${LIST}`]: rows() });
    await renderKb();
    await screen.findByText('Printer fix');
    expect(screen.getByRole('switch', { name: 'Help desk: Printer fix' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch', { name: 'Help desk: Starter VPN' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByRole('switch', { name: 'Help desk: OWASP guide' })).toBeNull();
    expect(screen.getAllByRole('switch')).toHaveLength(2);
    expect(screen.getByText(KB.chipPlatformReference)).toBeInTheDocument();
    expect(screen.getByText(KB.sharedReference)).toBeInTheDocument();
    expect(screen.getByText(KB.chipStarterCopy)).toBeInTheDocument();
    expect(screen.getAllByText(KB.chipHelpDesk).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Delete')).toHaveLength(3);
  });

  it('shows the words On and Off beside each switch', async () => {
    serve({ [`GET ${LIST}`]: rows() });
    await renderKb();
    await screen.findByText('Printer fix');
    expect(screen.getAllByText(KB.switchOn)).toHaveLength(1);
    expect(screen.getAllByText(KB.switchOff)).toHaveLength(1);
  });

  it('renders no desk controls for someone who cannot manage articles', async () => {
    serve({ [`GET ${LIST}`]: docList([kbDoc({ helpdesk: true })], kbFlags({ canManageArticles: false, helpdeskCount: 0, starterMissing: 0 })) });
    await renderKb();
    await screen.findByText('Printer fix');
    expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByText(/^Help desk \(/)).toBeNull();
    expect(screen.queryByText(KB.noHelpdeskArticles)).toBeNull();
    expect(screen.queryByText(KB.startersAdded)).toBeNull();
    expect(screen.queryByText(/Edit article/)).toBeNull();
  });

  it('wraps a long title instead of cutting it off', async () => {
    const long = 'A very long article title '.repeat(8).trim();
    serve({ [`GET ${LIST}`]: docList([kbDoc({ title: long })]) });
    await renderKb();
    expect((await screen.findByText(long)).className).toContain('break-words');
  });
});

describe('the Help desk switch', () => {
  it('saves once, stays disabled while it runs, then toasts the title and shows the new state and count', async () => {
    const answer = deferred<Response>();
    serve({
      [`GET ${LIST}`]: docList([kbDoc()]),
      [`PATCH ${PATCH_1}`]: () => answer.promise,
    });
    await renderKb();
    const toggle = await screen.findByRole('switch', { name: 'Help desk: Printer fix' });
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeDisabled());
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    answer.resolve(jsonRes({ id: 'kb-1', helpdesk: true }));
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    expect(toggle).not.toBeDisabled();
    expect(calls('PATCH', PATCH_1)).toHaveLength(1);
    expect(bodyOf(calls('PATCH', PATCH_1)[0])).toEqual({ helpdesk: true });
    expect(showToast).toHaveBeenCalledWith(fill(KB.toggleOn, { title: 'Printer fix' }), 'success');
    expect(screen.getByRole('button', { name: fill(KB.filterHelpDesk, { k: 1 }) })).toBeInTheDocument();
  });

  it('toasts the off words when a marked article is switched off', async () => {
    serve({
      [`GET ${LIST}`]: docList([kbDoc({ helpdesk: true })], kbFlags({ helpdeskCount: 1 })),
      [`PATCH ${PATCH_1}`]: jsonRes({ id: 'kb-1', helpdesk: false }),
    });
    await renderKb();
    fireEvent.click(await screen.findByRole('switch', { name: 'Help desk: Printer fix' }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(fill(KB.toggleOff, { title: 'Printer fix' }), 'success'));
    expect(bodyOf(calls('PATCH', PATCH_1)[0])).toEqual({ helpdesk: false });
  });

  it('keeps the old state and says why in a red line when the server refuses', async () => {
    serve({
      [`GET ${LIST}`]: docList([kbDoc()]),
      [`PATCH ${PATCH_1}`]: jsonRes({ detail: 'The article is over 20000 characters. Shorten it.' }, 422),
    });
    await renderKb();
    const toggle = await screen.findByRole('switch', { name: 'Help desk: Printer fix' });
    fireEvent.click(toggle);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(fill(KB.toggleFailed, { message: 'The article is over 20000 characters. Shorten it' }));
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(toggle).not.toBeDisabled();
    expect(showToast).not.toHaveBeenCalled();
  });

  it('words a refusal with no message for the platform organization in plain words', async () => {
    serve({
      [`GET ${LIST}`]: docList([kbDoc()]),
      [`PATCH ${PATCH_1}`]: jsonRes({}, 403),
    });
    await renderKb();
    fireEvent.click(await screen.findByRole('switch', { name: 'Help desk: Printer fix' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The service desk isn\'t available for the platform organization');
  });
});

// ------------------------------------------------------------------------------------------ filter and readiness

describe('the Help desk filter and the readiness note', () => {
  it('filters the list to marked articles with the Help desk pill', async () => {
    serve({ [`GET ${LIST}`]: docList([
      kbDoc({ id: 'kb-1', title: 'Printer fix', helpdesk: true }), kbDoc({ id: 'kb-2', title: 'Old runbook' }),
    ], kbFlags({ helpdeskCount: 1 })) });
    await renderKb();
    await screen.findByText('Old runbook');
    expect(screen.getByRole('button', { name: fill(KB.filterAll, { total: 2 }) })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: fill(KB.filterHelpDesk, { k: 1 }) }));
    expect(screen.getByText('Printer fix')).toBeInTheDocument();
    expect(screen.queryByText('Old runbook')).toBeNull();
  });

  it('says there is nothing to show when no article is marked and the pill is chosen', async () => {
    serve({ [`GET ${LIST}`]: docList([kbDoc()]) });
    await renderKb();
    await screen.findByText('Printer fix');
    fireEvent.click(screen.getByRole('button', { name: fill(KB.filterHelpDesk, { k: 0 }) }));
    expect(screen.getByText(KB.filterHelpDeskEmpty)).toBeInTheDocument();
  });

  it('warns in amber that every ticket goes to a person when no article is marked and the desk is on', async () => {
    serve({ [`GET ${LIST}`]: docList([kbDoc()]) });
    await renderKb();
    const note = await screen.findByText(KB.noHelpdeskArticles);
    expect(note.closest('[role="status"]')).not.toBeNull();
  });

  it('does not warn when the desk is off, and says how many are marked', async () => {
    serve({ [`GET ${LIST}`]: docList([kbDoc()], kbFlags({ deskOff: true })) });
    await renderKb();
    await screen.findByText('Printer fix');
    expect(screen.queryByText(KB.noHelpdeskArticles)).toBeNull();
    expect(screen.getByText(fill(KB.readiness, { k: 0 }))).toBeInTheDocument();
  });

  it('reads the singular when one article is marked and the plural otherwise', async () => {
    serve({ [`GET ${LIST}`]: docList([kbDoc({ helpdesk: true })], kbFlags({ helpdeskCount: 1 })) });
    const first = await renderKb();
    expect(await screen.findByText(/^1 article is marked Help desk\./)).toBeInTheDocument();
    first.unmount();
    serve({ [`GET ${LIST}`]: docList([kbDoc({ helpdesk: true })], kbFlags({ helpdeskCount: 3 })) });
    await renderKb();
    expect(await screen.findByText(fill(KB.readiness, { k: 3 }))).toBeInTheDocument();
  });
});
