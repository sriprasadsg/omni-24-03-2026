import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import Modal from '../Modal';

describe('Modal', () => {
  const mockOnClose = vi.fn();
  const mockOnConfirm = vi.fn();

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <Modal
        isOpen={false}
        onClose={mockOnClose}
        title="Test Modal"
        confirmLabel="Confirm"
        onConfirm={mockOnConfirm}
      />
    );
    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument();
  });

  it('renders correctly when isOpen is true', () => {
    render(
      <Modal
        isOpen={true}
        onClose={mockOnClose}
        title="Test Modal"
        description="This is a test modal."
        confirmLabel="Confirm"
        onConfirm={mockOnConfirm}
      />
    );
    expect(screen.getByText('Test Modal')).toBeInTheDocument();
    expect(screen.getByText('This is a test modal.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('calls onClose when Cancel button is clicked', () => {
    render(
      <Modal
        isOpen={true}
        onClose={mockOnClose}
        title="Test Modal"
        confirmLabel="Confirm"
        onConfirm={mockOnConfirm}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('calls onConfirm when Confirm button is clicked', () => {
    render(
      <Modal
        isOpen={true}
        onClose={mockOnClose}
        title="Test Modal"
        confirmLabel="Confirm"
        onConfirm={mockOnConfirm}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(mockOnConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', () => {
    render(
      <Modal
        isOpen={true}
        onClose={mockOnClose}
        title="Test Modal"
        confirmLabel="Confirm"
        onConfirm={mockOnConfirm}
      />
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('renders children content', () => {
    render(
      <Modal
        isOpen={true}
        onClose={mockOnClose}
        title="Test Modal"
        confirmLabel="Confirm"
        onConfirm={mockOnConfirm}
      >
        <div>Child Content Here</div>
      </Modal>
    );
    expect(screen.getByText('Child Content Here')).toBeInTheDocument();
  });
});