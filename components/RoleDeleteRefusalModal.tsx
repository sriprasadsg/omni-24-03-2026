import React, { useEffect, useRef } from 'react';
import { Modal } from './Modal';
import type { RoleInUseDetail } from '../services/roleApi';

interface Props {
    isOpen: boolean;
    roleName: string;
    detail: RoleInUseDetail | null;
    onClose: () => void;
    onGoToUsers: () => void;
}

const LIST = 'max-h-48 overflow-y-auto divide-y divide-slate-200 dark:divide-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg';

/** D-03 / D-15: the server refused the delete because users or sign-in mappings still hold the role. */
export function RoleDeleteRefusalModal({ isOpen, roleName, detail, onClose, onGoToUsers }: Props) {
    const headingRef = useRef<HTMLSpanElement>(null);
    useEffect(() => {
        if (!isOpen) return;
        // Modal moves focus to its first control on a 0ms timer; land on the heading after that.
        const t = window.setTimeout(() => headingRef.current?.focus(), 20);
        return () => window.clearTimeout(t);
    }, [isOpen]);

    if (!isOpen || !detail) return null;
    const holders = Array.isArray(detail.holders) ? detail.holders : [];
    const mappings = Array.isArray(detail.mappings) ? detail.mappings : [];
    const holderMore = Math.max(0, detail.holderCount - holders.length);
    const mappingMore = Math.max(0, detail.mappingCount - mappings.length);

    const footer = (
        <>
            <button
                type="button"
                onClick={onClose}
                className="inline-flex justify-center rounded-lg border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
                Close
            </button>
            <button
                type="button"
                onClick={() => { onGoToUsers(); onClose(); }}
                className="inline-flex justify-center rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
                Go to User Management
            </button>
        </>
    );

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            size="md"
            footer={footer}
            title={<span ref={headingRef} tabIndex={-1} className="outline-none">{`Can't delete "${roleName}" yet`}</span>}
        >
            <div className="space-y-4 text-sm font-normal text-slate-700 dark:text-slate-300">
                {detail.holderCount > 0 && (
                    <div className="space-y-2">
                        <p>{detail.holderCount === 1 ? '1 user still holds this role.' : `${detail.holderCount} users still hold this role.`}</p>
                        <p>Reassign them to another role, then delete it.</p>
                        <ul role="list" className={LIST}>
                            {holders.map((h, i) => {
                                const name = (h.name || '').trim();
                                return (
                                    <li key={`${h.email}-${i}`} className="px-3 py-2 min-w-0">
                                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{name || h.email}</p>
                                        {name && <p className="text-xs font-normal text-slate-500 dark:text-slate-400 truncate">{h.email}</p>}
                                    </li>
                                );
                            })}
                            {holderMore > 0 && <li className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{`and ${holderMore} more`}</li>}
                        </ul>
                    </div>
                )}
                {detail.mappingCount > 0 && (
                    <div className="space-y-2">
                        <p>{detail.mappingCount === 1 ? '1 sign-in mapping also uses it.' : `${detail.mappingCount} sign-in mappings also use it.`}</p>
                        <h3 className="text-xs font-semibold text-slate-900 dark:text-white">Sign-in mappings</h3>
                        <ul role="list" className={LIST}>
                            {mappings.map((m, i) => (
                                <li key={`${m.group}-${i}`} className="px-3 py-2 min-w-0">
                                    <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{m.group}</p>
                                    <p className="text-xs font-normal text-slate-500 dark:text-slate-400">{m.source}</p>
                                </li>
                            ))}
                            {mappingMore > 0 && <li className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{`and ${mappingMore} more`}</li>}
                        </ul>
                    </div>
                )}
            </div>
        </Modal>
    );
}
