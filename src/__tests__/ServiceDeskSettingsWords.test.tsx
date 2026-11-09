/**
 * Phase 85 / DESK-02, DESK-04 (85-16): the words, the single staged Save, and the two confirm dialogs of the Service desk
 * card (85-UI-SPEC section 2 e, f and dialogs). authFetch and the toast are mocked; nothing here reaches a real API.
 * The summary, status line, readiness list and card states are in ServiceDeskSettings.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, within, act } from '@testing-library/react';

vi.mock('../../services/apiService', () => ({ API_BASE: '/api', authFetch: vi.fn() }));
vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { showToast } from '../../utils/toast';
import { wordProblem } from '../../components/serviceDesk/DeskWords';
import {
  BREAKER, header, jsonRes, mockAuthFetch, openCard, posts, putBodies, puts, saveButton, view,
} from './_serviceDeskSettingsHarness';

const mockToast = showToast as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => { mockAuthFetch.mockReset(); mockToast.mockReset(); });

const wordInput = () => screen.getByLabelText('Word or phrase') as HTMLInputElement;
const addWord = (text: string) => {
  fireEvent.change(wordInput(), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Add word' }));
};
const chips = () => within(screen.getByRole('list', { name: 'Extra words' })).getAllByRole('listitem').map(li => li.textContent);
const choose = (name: RegExp) => fireEvent.click(screen.getByRole('radio', { name }));
const dialogOf = async (title: string) => within(await screen.findByRole('dialog', { name: title }));

describe('Service desk words', () => {
  it('starts with the empty line, the counter and no list', async () => {
    await openCard();
    expect(screen.getByText('No extra words yet. The built-in rules still apply.')).toBeInTheDocument();
    expect(screen.getByText('0/50 words')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Extra words' })).toBeNull();
  });

  it('Add word and Enter both add a trimmed, lower-case chip, clear the field and count it', async () => {
    await openCard();
    addWord('  Payroll  ');
    fireEvent.change(wordInput(), { target: { value: 'Pay  Day' } });
    fireEvent.keyDown(wordInput(), { key: 'Enter' });
    expect(chips()).toEqual(['payroll', 'pay day']);
    expect(wordInput().value).toBe('');
    expect(screen.getByText('2/50 words')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('Remove {word} takes the chip off', async () => {
    await openCard({ words: ['payroll', 'bonus'] });
    fireEvent.click(screen.getByRole('button', { name: 'Remove payroll' }));
    expect(chips()).toEqual(['bonus']);
    expect(screen.getByText('1/50 words')).toBeInTheDocument();
  });

  it.each([
    ['nothing typed', '   ', 'Enter a word or phrase.'],
    ['one character', 'a', "Use 2 to 40 characters: letters, numbers, spaces and - ' & / ."],
    ['a character that is not allowed', 'pay*roll', "Use 2 to 40 characters: letters, numbers, spaces and - ' & / ."],
    ['41 characters', 'x'.repeat(41), "Use 2 to 40 characters: letters, numbers, spaces and - ' & / ."],
  ])('refuses %s with the inline message and never adds a chip', async (_n, text, message) => {
    await openCard({ words: ['bonus'] });
    addWord(text);
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(wordInput()).toHaveAttribute('aria-invalid', 'true');
    expect(chips()).toEqual(['bonus']);
  });

  it('refuses a word already on the list, whatever its case', async () => {
    await openCard({ words: ['payroll'] });
    addWord('PAYROLL');
    expect(await screen.findByRole('alert')).toHaveTextContent('payroll is already on the list.');
    expect(chips()).toEqual(['payroll']);
  });

  it('refuses the 51st word, and a long word the rule allows still wraps inside its chip', async () => {
    const fifty = Array.from({ length: 50 }, (_, i) => `word number ${i}`);
    await openCard({ words: fifty });
    expect(screen.getByText('50/50 words')).toBeInTheDocument();
    addWord('one more');
    expect(await screen.findByRole('alert')).toHaveTextContent('You can add up to 50 words.');
    expect(chips()).toHaveLength(50);
    expect(screen.getByText('word number 3')).toHaveClass('break-words');
  });

  it('clears the message when the person types again', async () => {
    await openCard();
    addWord('');
    await screen.findByRole('alert');
    fireEvent.change(wordInput(), { target: { value: 'pay' } });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows and hides the six built-in rules', async () => {
    await openCard();
    const toggle = screen.getByRole('button', { name: 'Show built-in rules' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    const hide = screen.getByRole('button', { name: 'Hide built-in rules' });
    expect(hide).toHaveAttribute('aria-expanded', 'true');
    const rules = document.getElementById(hide.getAttribute('aria-controls') as string) as HTMLElement;
    expect(within(rules).getAllByRole('listitem').map(li => li.textContent)).toEqual([
      'Tickets of type security, and the Security Concern and Access Request tray templates.',
      'Mentions of security, billing, legal or account access: unlocks, MFA resets, access grants, permission changes and suspected compromise.',
      'Asking for a person.',
      'Tickets with critical priority.',
      'Install Software and Hardware Request tickets go straight to a person; an article can\'t install software or ship hardware.',
      'How-to questions about resetting your own password can be answered.',
    ]);
    fireEvent.click(hide);
    expect(screen.queryByText('Asking for a person.')).toBeNull();
  });

  it('wordProblem mirrors the server rule for letters of any script, and its order', () => {
    expect(wordProblem('zahlung', [])).toBeNull();
    expect(wordProblem('Überweisung', [])).toBeNull();
    expect(wordProblem("o'brien & co/ltd.", [])).toBeNull();
    expect(wordProblem('x', ['x'])).toMatch(/^Use 2 to 40/); // shape is checked before the duplicate
    expect(wordProblem('ab', ['ab'])).toBe('ab is already on the list.');
  });
});

describe('Service desk Save', () => {
  it('is a quiet disabled button until something changes, then accent with Discard changes', async () => {
    await openCard();
    expect(saveButton()).toBeDisabled();
    expect(saveButton().className).not.toContain('bg-primary-600');
    expect(screen.queryByRole('button', { name: 'Discard changes' })).toBeNull();
    addWord('payroll');
    expect(saveButton()).toBeEnabled();
    expect(saveButton().className).toContain('bg-primary-600');
    expect(screen.getByRole('button', { name: 'Discard changes' })).toBeInTheDocument();
  });

  it('Discard changes puts the staged mode and words back', async () => {
    await openCard({ words: ['bonus'] });
    addWord('payroll');
    choose(/^Off/);
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(chips()).toEqual(['bonus']);
    expect((screen.getByRole('radio', { name: /^Drafts only/ }) as HTMLInputElement).checked).toBe(true);
    expect(saveButton()).toBeDisabled();
  });

  it('saves words alone straight away: only the words travel and the toast says saved', async () => {
    await openCard();
    addWord('payroll');
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Service desk settings saved.', 'success'));
    expect(putBodies()).toEqual([{ words: ['payroll'] }]);
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(saveButton()).toBeDisabled()); // the form now matches what the server returned
    expect(screen.getByText(/ · 1 extra word$/)).toBeInTheDocument();
  });

  it.each([
    ['Off', /^Off/, 'drafts', 'Service desk set to Off.'],
    ['Drafts only', /^Drafts only/, 'off', 'Service desk set to Drafts only.'],
  ])('saves %s without a dialog', async (_label, option, from, toast) => {
    await openCard({ mode: from, effectiveMode: from });
    choose(option);
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(toast, 'success'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(putBodies()).toEqual([{ mode: from === 'off' ? 'drafts' : 'off' }]);
  });

  it('shows a failed save as the red block with the server sentence, and keeps the staged form', async () => {
    await openCard({}, { put: () => jsonRes({ detail: 'Words must be 2 to 40 characters.' }, 422) });
    addWord('payroll');
    fireEvent.click(saveButton());
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't save service desk settings: Words must be 2 to 40 characters. Try again.");
    expect(alert.className).toContain('break-words');
    expect(chips()).toEqual(['payroll']);
    expect(saveButton()).toBeEnabled();
  });

  it('uses the connection sentence when the failure has no text', async () => {
    await openCard({}, { put: () => jsonRes({}, 500) });
    addWord('payroll');
    fireEvent.click(saveButton());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save service desk settings. Check your connection and try again.");
  });

  it('a 403 closes the form and toasts that the person may not change these settings', async () => {
    await openCard({}, { put: () => jsonRes({ detail: 'Forbidden' }, 403) });
    addWord('payroll');
    fireEvent.click(saveButton());
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith("You don't have permission to change these settings.", 'error'));
    expect(header()).toHaveAttribute('aria-expanded', 'false');
  });

  it('sends one request per click while a save is in flight', async () => {
    let release: (r: Response) => void = () => {};
    await openCard({}, { put: () => new Promise<Response>(resolve => { release = resolve; }) });
    addWord('payroll');
    fireEvent.click(saveButton());
    fireEvent.click(saveButton());
    expect(saveButton()).toHaveTextContent('Saving...');
    expect(puts()).toHaveLength(1);
    await act(async () => { release(jsonRes(view({ words: ['payroll'] }))); });
    await waitFor(() => expect(mockToast).toHaveBeenCalledTimes(1));
  });
});

describe('Post answers to requesters? dialog', () => {
  it('opens before anything is written, with Keep Drafts only in first focus', async () => {
    await openCard();
    choose(/^Post answers/);
    fireEvent.click(saveButton());
    const dialog = await dialogOf('Post answers to requesters?');
    expect(dialog.getByText(/^With Post answers on, a qualifying answer is shown to the person who raised the ticket, marked "AI-assisted answer from your IT knowledge base", with the articles it cites\./)).toBeInTheDocument();
    expect(dialog.getByText(/3 withdrawals in 24 hours drop this back to Drafts only\.$/)).toBeInTheDocument();
    expect(dialog.queryByRole('status')).toBeNull();
    await waitFor(() => expect(dialog.getByRole('button', { name: 'Keep Drafts only' })).toHaveFocus());
    expect(dialog.queryByRole('button', { name: 'Close dialog' })).toBeNull();
    expect(puts()).toHaveLength(0);
  });

  it('Keep Drafts only writes nothing and keeps the staged choice', async () => {
    await openCard();
    choose(/^Post answers/);
    fireEvent.click(saveButton());
    fireEvent.click((await dialogOf('Post answers to requesters?')).getByRole('button', { name: 'Keep Drafts only' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(puts()).toHaveLength(0);
    expect((screen.getByRole('radio', { name: /^Post answers/ }) as HTMLInputElement).checked).toBe(true);
  });

  it('adds the amber block naming the first blocker when the server lists one', async () => {
    await openCard({ posting: { posting: false, blockers: [{ code: 'stop' }, { code: 'shadow' }] } });
    choose(/^Post answers/);
    fireEvent.click(saveButton());
    const dialog = await dialogOf('Post answers to requesters?');
    expect(dialog.getByRole('status')).toHaveTextContent(
      'Answers will stay drafts for now: Automatic actions are stopped, so nothing is posted. Undo still works.',
    );
  });

  it('confirming sends mode post, toasts, closes and reveals the readiness list', async () => {
    await openCard({}, {
      put: (b) => jsonRes(view({
        mode: b.mode, effectiveMode: b.mode, posting: { posting: false, blockers: [{ code: 'level', level: 'suggest' }] },
      })),
    });
    choose(/^Post answers/);
    fireEvent.click(saveButton());
    fireEvent.click((await dialogOf('Post answers to requesters?')).getByRole('button', { name: 'Post answers' }));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Service desk set to Post answers.', 'success'));
    expect(putBodies()).toEqual([{ mode: 'post' }]);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(within(screen.getByRole('status', { name: 'Will answers be posted?' })).getByText('Drafts for now')).toBeInTheDocument();
  });

  it('shows Saving... on the accent button, ignores Esc while in flight, and sends once', async () => {
    let release: (r: Response) => void = () => {};
    await openCard({}, { put: () => new Promise<Response>(resolve => { release = resolve; }) });
    choose(/^Post answers/);
    fireEvent.click(saveButton());
    const dialog = await dialogOf('Post answers to requesters?');
    const confirm = dialog.getByRole('button', { name: 'Post answers' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(dialog.getByRole('button', { name: 'Saving...' })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(puts()).toHaveLength(1);
    await act(async () => { release(jsonRes(view({ mode: 'post', effectiveMode: 'post' }))); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('shows a refused save inside the dialog and keeps it open', async () => {
    await openCard({}, { put: () => jsonRes({ detail: 'Restore Post answers first.' }, 409) });
    choose(/^Post answers/);
    fireEvent.click(saveButton());
    const dialog = await dialogOf('Post answers to requesters?');
    fireEvent.click(dialog.getByRole('button', { name: 'Post answers' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent("Couldn't save service desk settings: Restore Post answers first. Try again.");
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Post answers' })).toBeEnabled();
  });
});

describe('Restore Post answers? dialog', () => {
  const BROKEN = { mode: 'drafts', breaker: BREAKER, canRestore: true };

  it('opens from the amber block, with Keep Drafts only in first focus, and writes nothing yet', async () => {
    await openCard(BROKEN);
    fireEvent.click(screen.getByRole('button', { name: 'Restore Post answers' }));
    const dialog = await dialogOf('Restore Post answers?');
    expect(dialog.getByText('Answers will be posted again as soon as every condition is met. If 3 more answers are withdrawn within 24 hours, the service desk drops to Drafts only again.')).toBeInTheDocument();
    await waitFor(() => expect(dialog.getByRole('button', { name: 'Keep Drafts only' })).toHaveFocus());
    expect(posts()).toHaveLength(0);
  });

  it('confirming restores, toasts, clears the breaker block and unlocks the option', async () => {
    await openCard(BROKEN);
    fireEvent.click(screen.getByRole('button', { name: 'Restore Post answers' }));
    fireEvent.click((await dialogOf('Restore Post answers?')).getByRole('button', { name: 'Restore Post answers' }));
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(
      'Post answers restored. Answers post again once every condition is met.', 'success',
    ));
    expect(posts()).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText(/^The service desk dropped to Drafts only\. 3 answers/)).toBeNull();
    expect(screen.getByRole('radio', { name: /^Post answers/ })).toBeEnabled();
  });

  it('shows Restoring... while in flight and ignores Esc', async () => {
    let release: (r: Response) => void = () => {};
    await openCard(BROKEN, { restore: () => new Promise<Response>(resolve => { release = resolve; }) });
    fireEvent.click(screen.getByRole('button', { name: 'Restore Post answers' }));
    const dialog = await dialogOf('Restore Post answers?');
    fireEvent.click(dialog.getByRole('button', { name: 'Restore Post answers' }));
    expect(dialog.getByRole('button', { name: 'Restoring...' })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await act(async () => { release(jsonRes(view({ mode: 'post', effectiveMode: 'post' }))); });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('shows a refusal inside the dialog', async () => {
    await openCard(BROKEN, { restore: () => jsonRes({ detail: 'Nothing to restore.' }, 409) });
    fireEvent.click(screen.getByRole('button', { name: 'Restore Post answers' }));
    const dialog = await dialogOf('Restore Post answers?');
    fireEvent.click(dialog.getByRole('button', { name: 'Restore Post answers' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent("Couldn't save service desk settings: Nothing to restore. Try again.");
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('Keep Drafts only closes it without a request', async () => {
    await openCard(BROKEN);
    fireEvent.click(screen.getByRole('button', { name: 'Restore Post answers' }));
    fireEvent.click((await dialogOf('Restore Post answers?')).getByRole('button', { name: 'Keep Drafts only' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(posts()).toHaveLength(0);
  });
});
