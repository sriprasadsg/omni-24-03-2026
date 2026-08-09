import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
}

export default function Modal({ isOpen, onClose, title, description, children, confirmLabel, onConfirm }: ModalProps) {
  if (!isOpen) return null;

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-[90%] max-w-md bg-gray-800 rounded-xl shadow-2xl border border-gray-700">
        <div className="p-6">
          <h2 className="text-lg font-semibold mb-2 text-white">{title}</h2>
          {description && <p className="text-gray-400 mb-6">{description}</p>}
          {children}
          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white px-4 py-2 rounded transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              className={`bg-cyan-600 hover:bg-cyan-500 text-white font-medium px-4 py-2 rounded`}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}