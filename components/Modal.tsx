import React, { useEffect, useRef, useCallback, useId } from 'react';
import { createPortal } from 'react-dom';
import { XIcon } from './icons';

/**
 * Shared modal primitive. Replaces the 100+ hand-rolled modal shells across the
 * app, each of which reimplemented (inconsistently) the backdrop, centering,
 * z-index, escape/backdrop close, scroll-lock, focus handling and dialog a11y.
 *
 * Behaviour:
 *   - Rendered in a portal on document.body (escapes overflow/stacking contexts)
 *   - role="dialog" aria-modal, labelled by the title when provided
 *   - Escape closes (opt-out via closeOnEsc)
 *   - Backdrop click closes (opt-out via closeOnBackdrop)
 *   - Body scroll locked while open
 *   - Focus moved into the dialog on open, trapped on Tab, restored on close
 *
 * Theme: works in light and dark. Panels standardise on the slate ramp to end
 * the gray/slate drift.
 */

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl';

const SIZE_MAP: Record<ModalSize, string> = {
    sm:  'max-w-sm',
    md:  'max-w-md',
    lg:  'max-w-lg',
    xl:  'max-w-xl',
    '2xl': 'max-w-2xl',
    '3xl': 'max-w-3xl',
};

const FOCUSABLE =
    'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

export interface ModalProps {
    isOpen: boolean;
    onClose: () => void;
    /** Optional heading rendered in the standard header row. */
    title?: React.ReactNode;
    /** Optional element left of the title (e.g. an icon). */
    icon?: React.ReactNode;
    /** Optional footer region (typically action buttons). */
    footer?: React.ReactNode;
    size?: ModalSize;
    /** Show the top-right close button (default true). */
    showClose?: boolean;
    closeOnBackdrop?: boolean;
    closeOnEsc?: boolean;
    /** Extra classes for the panel. */
    className?: string;
    /** Extra classes for the scrollable body region. */
    bodyClassName?: string;
    children?: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({
    isOpen,
    onClose,
    title,
    icon,
    footer,
    size = 'lg',
    showClose = true,
    closeOnBackdrop = true,
    closeOnEsc = true,
    className = '',
    bodyClassName = '',
    children,
}) => {
    const panelRef = useRef<HTMLDivElement>(null);
    const lastFocusedRef = useRef<HTMLElement | null>(null);
    const titleId = useId();

    // Escape + focus-trap key handling
    const onKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (e.key === 'Escape' && closeOnEsc) {
            e.stopPropagation();
            onClose();
            return;
        }
        if (e.key !== 'Tab') return;
        const nodes = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
        if (!nodes || nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }, [onClose, closeOnEsc]);

    // Lock body scroll, move focus in, restore focus on close
    useEffect(() => {
        if (!isOpen) return;
        lastFocusedRef.current = document.activeElement as HTMLElement | null;
        const prevOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';

        // Focus the first focusable element (or the panel itself)
        const t = window.setTimeout(() => {
            const focusable = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
            (focusable ?? panelRef.current)?.focus();
        }, 0);

        return () => {
            window.clearTimeout(t);
            document.body.style.overflow = prevOverflow;
            lastFocusedRef.current?.focus?.();
        };
    }, [isOpen]);

    if (!isOpen) return null;

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
            role="dialog"
            aria-modal="true"
            aria-labelledby={title ? titleId : undefined}
            onMouseDown={e => { if (closeOnBackdrop && e.target === e.currentTarget) onClose(); }}
            onKeyDown={onKeyDown}
        >
            <div
                ref={panelRef}
                tabIndex={-1}
                className={`w-full ${SIZE_MAP[size]} max-h-[90vh] flex flex-col bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-2xl outline-none animate-scale-in ${className}`}
            >
                {(title || showClose) && (
                    <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3 border-b border-slate-200 dark:border-slate-800 flex-shrink-0">
                        <div className="flex items-center gap-3 min-w-0">
                            {icon}
                            {title && (
                                <h2 id={titleId} className="text-slate-900 dark:text-white font-semibold text-lg truncate">
                                    {title}
                                </h2>
                            )}
                        </div>
                        {showClose && (
                            <button
                                type="button"
                                onClick={onClose}
                                aria-label="Close dialog"
                                className="flex-shrink-0 -mr-1.5 -mt-1 p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
                            >
                                <XIcon size={18} />
                            </button>
                        )}
                    </div>
                )}

                <div className={`px-6 py-4 overflow-y-auto flex-1 ${bodyClassName}`}>
                    {children}
                </div>

                {footer && (
                    <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-800 flex-shrink-0">
                        {footer}
                    </div>
                )}
            </div>
        </div>,
        document.body,
    );
};

export default Modal;
