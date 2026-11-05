/**
 * Modal focus (found 2026-11-05 on the Appoint partner dialog): a field with autoFocus keeps focus when the
 * dialog opens, instead of being blurred onto the Close button (which showed "Enter a partner name." before
 * anything was typed), and closing the dialog returns focus to the button that opened it.
 */
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import Modal from '../../components/Modal';

function Harness({ autoFocusField, onBlur }: { autoFocusField: boolean; onBlur?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open dialog</button>
      {open && (
        <Modal isOpen onClose={() => setOpen(false)} title="Dialog">
          <input aria-label="Name" autoFocus={autoFocusField} onBlur={onBlur} />
        </Modal>
      )}
    </>
  );
}

async function openWith(opener: HTMLElement) {
  opener.focus();
  fireEvent.click(opener);
  await act(async () => { await new Promise(r => setTimeout(r, 10)); });
}

describe('Modal focus', () => {
  it('keeps focus on an autoFocus field and never blurs it on open', async () => {
    const onBlur = vi.fn();
    render(<Harness autoFocusField onBlur={onBlur} />);
    await openWith(screen.getByText('Open dialog'));
    expect(document.activeElement).toBe(screen.getByLabelText('Name'));
    expect(onBlur).not.toHaveBeenCalled();
  });

  it('focuses the first focusable element when no field asks for focus', async () => {
    render(<Harness autoFocusField={false} />);
    await openWith(screen.getByText('Open dialog'));
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Close dialog' }));
  });

  it('returns focus to the opener on close, also when a field took focus on open', async () => {
    render(<Harness autoFocusField />);
    const opener = screen.getByText('Open dialog');
    await openWith(opener);
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Escape' });
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    expect(screen.queryByLabelText('Name')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});
