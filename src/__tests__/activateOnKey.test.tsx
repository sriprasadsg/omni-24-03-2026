import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { activateOnKey } from '../../components/ui/a11y';

const Card = ({ onClick }: { onClick: () => void }) => (
  <div role="button" tabIndex={0} onKeyDown={activateOnKey} onClick={onClick}>
    Open asset
    <input aria-label="Note" />
  </div>
);

describe('activateOnKey', () => {
  it('clicks the element on Enter and on Space', () => {
    const onClick = vi.fn();
    render(<Card onClick={onClick} />);
    const card = screen.getByRole('button', { name: /Open asset/ });
    fireEvent.keyDown(card, { key: 'Enter' });
    fireEvent.keyDown(card, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('ignores other keys', () => {
    const onClick = vi.fn();
    render(<Card onClick={onClick} />);
    fireEvent.keyDown(screen.getByRole('button', { name: /Open asset/ }), { key: 'a' });
    expect(onClick).not.toHaveBeenCalled();
  });

  it('leaves keys typed in a control inside the element to that control', () => {
    const onClick = vi.fn();
    render(<Card onClick={onClick} />);
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Note' }), { key: 'Enter' });
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Note' }), { key: ' ' });
    expect(onClick).not.toHaveBeenCalled();
  });
});
