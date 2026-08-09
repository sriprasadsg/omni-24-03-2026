import React from 'react';
import { AlertTriangleIcon } from './icons';
import { Modal } from './Modal';

interface ConfirmationModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    isDestructive?: boolean;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
    isOpen,
    onClose,
    onConfirm,
    title,
    message,
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    isDestructive = false,
}) => {
    const footer = (
        <>
            <button
                type="button"
                onClick={onClose}
                className="inline-flex justify-center rounded-lg border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
                {cancelText}
            </button>
            <button
                type="button"
                onClick={() => { onConfirm(); onClose(); }}
                className={`inline-flex justify-center rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                    isDestructive
                        ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
                        : 'bg-primary-600 hover:bg-primary-700 focus:ring-primary-500'
                }`}
            >
                {confirmText}
            </button>
        </>
    );

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={title} size="md" footer={footer}>
            <div className="flex items-start gap-4">
                <div className={`flex-shrink-0 flex items-center justify-center h-10 w-10 rounded-full ${
                    isDestructive ? 'bg-red-100 dark:bg-red-900/50' : 'bg-blue-100 dark:bg-blue-900/50'
                }`}>
                    <AlertTriangleIcon
                        size={22}
                        className={isDestructive ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'}
                    />
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-300 pt-1.5">{message}</p>
            </div>
        </Modal>
    );
};
