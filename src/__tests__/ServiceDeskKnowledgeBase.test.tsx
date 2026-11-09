/**
 * Phase 85 / DESK-06, DESK-07 (85-21): the Knowledge Base screen's Help desk side of 85-UI-SPEC section 6 - the Help desk
 * switch and chips, the filter pill, the readiness note and the client calls. authFetch and the toast are mocked; the
 * payloads follow 85-15-SUMMARY.md. Nothing here reaches a real API.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, render } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import { ArticleEditDialog } from '../../components/serviceDesk/ArticleEditDialog';
import { DIALOGS, KB, TOASTS, VALIDATION, fill } from '../../components/serviceDesk/serviceDeskCopy';
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

// ------------------------------------------------------------------------------------------ Add starter IT articles

describe('Add starter IT articles', () => {
  const STARTERS = '/api/knowledge/helpdesk/starters';
  const open = async (flags = kbFlags()) => {
    serve({ [`GET ${LIST}`]: () => docList([kbDoc()], flags), [`POST ${STARTERS}`]: jsonRes({ added: 4, existing: 0, addedKeys: [] }) });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: KB.addStarters }));
    return screen.findByRole('dialog');
  };

  it('opens a dialog that names the topics and puts focus on Close without adding', async () => {
    const dialog = await open();
    expect(screen.getByRole('heading', { name: DIALOGS.starters.title })).toBeInTheDocument();
    expect(dialog).toHaveTextContent(fill(DIALOGS.starters.body, { n: 4 }));
    await waitFor(() => expect(screen.getByRole('button', { name: DIALOGS.starters.keep })).toHaveFocus());
    expect(screen.queryByRole('button', { name: /^Cancel$/ })).toBeNull();
  });

  it('adds the articles with one request, says Adding... meanwhile, toasts the plural and reads the list again', async () => {
    const answer = deferred<Response>();
    serve({ [`GET ${LIST}`]: () => docList([kbDoc()]), [`POST ${STARTERS}`]: () => answer.promise });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: KB.addStarters }));
    fireEvent.click(await screen.findByRole('button', { name: DIALOGS.starters.confirm }));
    fireEvent.click(await screen.findByRole('button', { name: DIALOGS.starters.pending }));
    expect(screen.getByRole('button', { name: DIALOGS.starters.pending })).toBeDisabled();
    answer.resolve(jsonRes({ added: 4, existing: 0, addedKeys: ['password_reset', 'vpn', 'printer', 'agent_tray'] }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(fill(TOASTS.startersAdded, { n: 4 }), 'success'));
    expect(calls('POST', STARTERS)).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls('GET', LIST)).toHaveLength(2);
  });

  it('toasts the singular when one starter was added and the none-to-add words when nothing was', async () => {
    for (const [added, text] of [[1, TOASTS.startersAddedOne], [0, TOASTS.startersNone]] as const) {
      mockFetch.mockReset(); vi.mocked(showToast).mockReset();
      serve({ [`GET ${LIST}`]: () => docList([kbDoc()], kbFlags({ starterMissing: 1 })), [`POST ${STARTERS}`]: jsonRes({ added, existing: 4 - added, addedKeys: [] }) });
      const out = await renderKb();
      fireEvent.click(await screen.findByRole('button', { name: KB.addStarters }));
      fireEvent.click(await screen.findByRole('button', { name: DIALOGS.starters.confirm }));
      await waitFor(() => expect(showToast).toHaveBeenCalledWith(text, 'success'));
      out.unmount();
    }
    expect(TOASTS.startersAddedOne.startsWith('Added 1 starter article.')).toBe(true);
  });

  it('keeps the dialog open with a red block when the server refuses', async () => {
    serve({ [`GET ${LIST}`]: () => docList([kbDoc()]), [`POST ${STARTERS}`]: jsonRes({ detail: 'Try later.' }, 500) });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: KB.addStarters }));
    fireEvent.click(await screen.findByRole('button', { name: DIALOGS.starters.confirm }));
    expect(await screen.findByRole('alert')).toHaveTextContent(fill(KB.starterFailed, { message: 'Try later' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: DIALOGS.starters.confirm })).not.toBeDisabled();
  });

  it('replaces the button with Starter IT articles added when none is missing, and shows nothing without permission', async () => {
    serve({ [`GET ${LIST}`]: () => docList([kbDoc()], kbFlags({ starterMissing: 0 })) });
    await renderKb();
    expect(await screen.findByText(KB.startersAdded)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: KB.addStarters })).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------ the article dialog

describe('Edit article', () => {
  const DETAIL = { id: 'kb-1', title: 'Printer fix', content: 'Turn it off and on.', tags: ['it', 'printer'], helpdesk: true, starterKey: null, max: 30 };
  const openEdit = async (detail: Record<string, any> = DETAIL, listDoc: Record<string, any> = {}) => {
    serve({
      [`GET ${LIST}`]: () => docList([kbDoc({ helpdesk: true, ...listDoc })], kbFlags({ helpdeskCount: 1 })),
      [`GET ${PATCH_1}`]: jsonRes(detail),
      [`PATCH ${PATCH_1}`]: jsonRes({ id: 'kb-1' }),
    });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: /^Edit article/ }));
    await screen.findByRole('dialog');
  };
  const title = () => screen.getByLabelText(KB.fieldTitle) as HTMLInputElement;
  const content = () => screen.getByLabelText(new RegExp(`^${KB.fieldContent}`)) as HTMLTextAreaElement;
  const save = () => screen.getByRole('button', { name: KB.saveArticle });

  it('loads the stored text, shows the counter from the server limit and the Help desk checkbox with its helper', async () => {
    await openEdit();
    await waitFor(() => expect(content().value).toBe('Turn it off and on.'));
    expect(title().value).toBe('Printer fix');
    expect(screen.getByLabelText(KB.fieldTags)).toHaveValue('it, printer');
    expect(screen.getByText(fill(KB.contentCounter, { n: 19, max: 30 }))).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: KB.helpdeskCheckbox })).toBeChecked();
    expect(screen.getByText(KB.helpdeskHelper)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: KB.articleDialogEdit })).toBeInTheDocument();
    expect(content().className).toContain('min-h-72');
  });

  it('says Loading article... while the text arrives and offers Try again when it cannot load', async () => {
    serve({ [`GET ${LIST}`]: () => docList([kbDoc()]), [`GET ${PATCH_1}`]: jsonRes({ detail: 'x' }, 500) });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: /^Edit article/ }));
    expect(await screen.findByText(KB.articleLoadFailed)).toBeInTheDocument();
    serve({ [`GET ${LIST}`]: () => docList([kbDoc()]), [`GET ${PATCH_1}`]: jsonRes(DETAIL) });
    fireEvent.click(screen.getByRole('button', { name: KB.tryAgain }));
    await waitFor(() => expect(content().value).toBe('Turn it off and on.'));
  });

  it('shows the blue replace-the-wording block on a starter copy only', async () => {
    await openEdit({ ...DETAIL, starterKey: 'vpn' }, { starterKey: 'vpn' });
    expect(await screen.findByText(KB.starterCopyNote)).toBeInTheDocument();
  });

  it('keeps Save article off until something changes, then sends only what changed and reads the list again', async () => {
    await openEdit();
    await waitFor(() => expect(content().value).not.toBe(''));
    expect(save()).toBeDisabled();
    fireEvent.change(title(), { target: { value: 'Printer fix v2' } });
    expect(save()).not.toBeDisabled();
    fireEvent.click(save());
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(TOASTS.articleSaved, 'success'));
    expect(calls('PATCH', PATCH_1)).toHaveLength(1);
    expect(bodyOf(calls('PATCH', PATCH_1)[0])).toEqual({ title: 'Printer fix v2' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls('GET', LIST)).toHaveLength(2);
  });

  it('sends the Help desk mark and the tags when they change', async () => {
    await openEdit();
    await waitFor(() => expect(content().value).not.toBe(''));
    fireEvent.click(screen.getByRole('checkbox', { name: KB.helpdeskCheckbox }));
    fireEvent.change(screen.getByLabelText(KB.fieldTags), { target: { value: 'it, printer, floor 2' } });
    fireEvent.click(save());
    await waitFor(() => expect(calls('PATCH', PATCH_1)).toHaveLength(1));
    expect(bodyOf(calls('PATCH', PATCH_1)[0])).toEqual({ helpdesk: false, tags: ['it', 'printer', 'floor 2'] });
  });

  it('refuses an empty title, empty text and text over the limit in plain words without sending anything', async () => {
    await openEdit();
    await waitFor(() => expect(content().value).not.toBe(''));
    fireEvent.change(title(), { target: { value: '   ' } });
    fireEvent.click(save());
    expect(screen.getByText(VALIDATION.titleEmpty)).toBeInTheDocument();
    fireEvent.change(title(), { target: { value: 'Printer fix' } });
    fireEvent.change(content(), { target: { value: '  ' } });
    fireEvent.click(save());
    expect(screen.getByText(VALIDATION.contentEmpty)).toBeInTheDocument();
    fireEvent.change(content(), { target: { value: 'x'.repeat(31) } });
    fireEvent.click(save());
    expect(screen.getByText(fill(VALIDATION.contentTooLong, { max: 30 }))).toBeInTheDocument();
    expect(calls('PATCH', PATCH_1)).toHaveLength(0);
  });

  it('shows Saving... while it saves, then the red block with the server message when it fails', async () => {
    const answer = deferred<Response>();
    serve({
      [`GET ${LIST}`]: () => docList([kbDoc({ helpdesk: true })], kbFlags({ helpdeskCount: 1 })),
      [`GET ${PATCH_1}`]: jsonRes(DETAIL),
      [`PATCH ${PATCH_1}`]: () => answer.promise,
    });
    await renderKb();
    fireEvent.click(await screen.findByRole('button', { name: /^Edit article/ }));
    await waitFor(() => expect(content().value).not.toBe(''));
    fireEvent.change(title(), { target: { value: 'New title' } });
    fireEvent.click(save());
    expect(await screen.findByRole('button', { name: KB.saving })).toBeDisabled();
    answer.resolve(jsonRes({ detail: 'Change at least one field.' }, 422));
    expect(await screen.findByRole('alert')).toHaveTextContent(fill(KB.saveFailed, { message: 'Change at least one field' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(save()).not.toBeDisabled();
  });

  it('throws the edits away with Close without saving', async () => {
    await openEdit();
    await waitFor(() => expect(content().value).not.toBe(''));
    fireEvent.change(title(), { target: { value: 'Changed' } });
    fireEvent.click(screen.getByRole('button', { name: KB.closeWithoutSaving }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls('PATCH', PATCH_1)).toHaveLength(0);
  });

  it('offers no Edit article on a platform reference row', async () => {
    serve({ [`GET ${LIST}`]: () => docList([kbDoc({ tenantId: 'global' })]) });
    await renderKb();
    await screen.findByText('Printer fix');
    expect(screen.queryByRole('button', { name: /^Edit article/ })).toBeNull();
  });
});

describe('Write article (create mode)', () => {
  const NEW = '/api/knowledge/helpdesk/articles';

  it('opens with the gap question as the title and Help desk ticked, and saves with the group id', async () => {
    serve({ [`POST ${NEW}`]: jsonRes({ id: 'kb-9', title: 'T', helpdesk: true, gapsWritten: 3 }) });
    const onSaved = vi.fn();
    render(<ArticleEditDialog mode="write" initialTitle="How do I reset my VPN?" gapGroupId="g-1" onClose={vi.fn()} onSaved={onSaved} />);
    expect(screen.getByRole('heading', { name: KB.articleDialogWrite })).toBeInTheDocument();
    expect((screen.getByLabelText(KB.fieldTitle) as HTMLInputElement).value).toBe('How do I reset my VPN?');
    expect(screen.getByRole('checkbox', { name: KB.helpdeskCheckbox })).toBeChecked();
    expect(screen.queryByText(KB.starterCopyNote)).toBeNull();
    fireEvent.change(screen.getByLabelText(new RegExp(`^${KB.fieldContent}`)), { target: { value: 'Open the VPN app and choose Reset.' } });
    fireEvent.click(screen.getByRole('button', { name: KB.saveArticle }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(bodyOf(calls('POST', NEW)[0])).toEqual({
      title: 'How do I reset my VPN?', content: 'Open the VPN app and choose Reset.', tags: [], helpdesk: true, gapGroupId: 'g-1',
    });
    expect(showToast).toHaveBeenCalledWith(TOASTS.articleSavedGap, 'success');
    expect(calls('GET', '/api/knowledge/docs/kb-9')).toHaveLength(0);
  });

  it('toasts the plain saved words when the article answers no gap', async () => {
    serve({ [`POST ${NEW}`]: jsonRes({ id: 'kb-9', title: 'T', helpdesk: true, gapsWritten: 0 }) });
    const onSaved = vi.fn();
    render(<ArticleEditDialog mode="write" initialTitle="Title" onClose={vi.fn()} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText(new RegExp(`^${KB.fieldContent}`)), { target: { value: 'Text' } });
    fireEvent.click(screen.getByRole('button', { name: KB.saveArticle }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(TOASTS.articleSaved, 'success'));
    expect(bodyOf(calls('POST', NEW)[0])).not.toHaveProperty('gapGroupId');
  });
});
