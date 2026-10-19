import React, { useCallback, useEffect, useState } from 'react';
import { ApiRole, RoleVisibility, fetchRoleVisibility, isBuiltInRole } from '../services/roleApi';
import { AlertTriangleIcon, ChevronDownIcon, EyeIcon, PencilIcon, PowerIcon } from './icons';

interface Props {
    role: ApiRole;
    tenantId?: string | null;
    refreshKey?: number;
    panelId: string;
}

const MARKER_BASE = 'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold shrink-0';

function Marker({ kind }: { kind: 'view' | 'manage' | 'switched-off' }) {
    if (kind === 'manage') {
        return (
            <span data-marker="manage" className={`${MARKER_BASE} bg-gray-800 text-white border border-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:border-gray-100`}>
                <PencilIcon size={12} aria-hidden="true" />Manage
            </span>
        );
    }
    if (kind === 'switched-off') {
        return (
            <span data-marker="switched-off" className={`${MARKER_BASE} bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-900/30`}>
                <PowerIcon size={12} aria-hidden="true" />Switched off
            </span>
        );
    }
    return (
        <span data-marker="view" className={`${MARKER_BASE} bg-transparent text-gray-600 border border-gray-300 dark:text-gray-300 dark:border-gray-600`}>
            <EyeIcon size={12} aria-hidden="true" />View
        </span>
    );
}

const CELL = 'flex items-center justify-between gap-2 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 min-w-0';
const GRID = 'grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-4 gap-y-2';

function basisLine(data: RoleVisibility): string {
    if (data.basis.kind === 'platform_role') return 'Platform role. Tenant screen switches do not narrow it.';
    if (data.basis.kind === 'no_tenant') return 'No tenant selected. Tenant screen switches do not narrow it.';
    return `Based on this role's permissions, narrowed by the screens switched on for ${data.basis.tenantName ?? data.basis.tenantId ?? 'this tenant'}.`;
}

export function RoleVisibilityPanel({ role, tenantId, refreshKey = 0, panelId }: Props) {
    const [data, setData] = useState<RoleVisibility | null>(null);
    const [error, setError] = useState(false);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState<Set<string>>(new Set());
    const [retry, setRetry] = useState(0);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(false);
        fetchRoleVisibility(role.id, tenantId ?? undefined)
            .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
            .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });
        return () => { cancelled = true; };
    }, [role.id, tenantId, refreshKey, retry]);

    const toggle = useCallback((id: string) => {
        setOpen(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    }, []);

    const shell = 'bg-gray-50 dark:bg-gray-900/40 border-t border-gray-200 dark:border-gray-700 p-6 min-w-0 flex flex-col gap-4';

    if (loading && !data) {
        return (
            <div id={panelId} role="region" aria-label={`What ${role.name} can see`} aria-busy="true" className={shell}>
                <div data-skeleton="header" className="h-6 w-3/5 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
                {[0, 1, 2].map(i => (
                    <div key={i} data-skeleton="group" className="h-10 rounded-lg bg-gray-200 dark:bg-gray-700 animate-pulse" />
                ))}
            </div>
        );
    }

    if (error || !data) {
        return (
            <div id={panelId} role="region" aria-label={`What ${role.name} can see`} aria-busy="false" className={shell}>
                <div className="flex items-center gap-2 text-red-600 dark:text-red-400" role="alert">
                    <AlertTriangleIcon size={16} aria-hidden="true" />
                    <span className="text-sm">Couldn't load what this role can see.</span>
                    <button type="button" onClick={() => setRetry(n => n + 1)} className="text-xs font-semibold text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white underline">
                        Try again
                    </button>
                </div>
            </div>
        );
    }

    const allOpen = data.groups.length > 0 && data.groups.every(g => open.has(g.id));
    const builtIn = isBuiltInRole(role);
    // Only a tenant basis is narrowed by switches, so only it has a switched-off section (UI-SPEC section 6).
    const showSwitchedOff = data.basis.kind === 'tenant';

    return (
        <div id={panelId} role="region" aria-label={`What ${role.name} can see`} aria-busy={loading} className={shell}>
            <h4 className="text-lg font-semibold text-gray-900 dark:text-white">
                {`${data.roleName || role.name} can see ${data.visibleCount} of ${data.totalCount} screens`}
            </h4>
            <p className="text-xs text-gray-500 dark:text-gray-400">{basisLine(data)}</p>
            {data.visibleCount === 0 ? (
                <div className="text-sm text-gray-600 dark:text-gray-400">
                    <p>This role can't see any screens yet.</p>
                    {!builtIn && <p>Edit the role to grant permissions.</p>}
                </div>
            ) : (
                <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap gap-2 min-w-0">
                            <span className="inline-flex items-center gap-1.5 text-xs"><Marker kind="view" /><span>View: can open the screen</span></span>
                            <span className="inline-flex items-center gap-1.5 text-xs"><Marker kind="manage" /><span>Manage: can also change data</span></span>
                            <span className="inline-flex items-center gap-1.5 text-xs"><Marker kind="switched-off" /><span>Switched off: granted, but off for this tenant</span></span>
                        </div>
                        <button
                            type="button"
                            onClick={() => setOpen(allOpen ? new Set() : new Set(data.groups.map(g => g.id)))}
                            className="text-xs font-semibold text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
                        >
                            {allOpen ? 'Collapse all' : 'Expand all'}
                        </button>
                    </div>
                    <div className="flex flex-col gap-2">
                        {data.groups.map(group => {
                            const isOpen = open.has(group.id);
                            const bodyId = `${panelId}-${group.id}`;
                            return (
                                <div key={group.id} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
                                    <button
                                        type="button"
                                        aria-expanded={isOpen}
                                        aria-controls={bodyId}
                                        onClick={() => toggle(group.id)}
                                        className="w-full flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-left focus:outline-none focus:ring-2 focus:ring-primary-500 rounded-lg"
                                    >
                                        <span className="text-xs font-semibold uppercase tracking-wider text-gray-900 dark:text-white">{group.title}</span>
                                        <span className="flex items-center gap-2 text-xs">
                                            <span className="font-normal text-gray-500 dark:text-gray-400">{`${group.visibleCount} of ${group.total}`}</span>
                                            {showSwitchedOff && group.switchedOff.length > 0 && (
                                                <span className="text-amber-700 dark:text-amber-300">{`+${group.switchedOff.length} switched off`}</span>
                                            )}
                                            <ChevronDownIcon size={14} aria-hidden="true" className={`motion-safe:transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                                        </span>
                                    </button>
                                    {isOpen && (
                                        <div id={bodyId} className="px-3 pb-3">
                                            {group.screens.length > 0 && (
                                                <div className={GRID}>
                                                    {group.screens.map(s => (
                                                        <div key={s.view} className={CELL}>
                                                            <span className="truncate text-sm text-gray-900 dark:text-gray-100" title={s.label}>{s.label}</span>
                                                            <Marker kind={s.access === 'manage' ? 'manage' : 'view'} />
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {showSwitchedOff && group.switchedOff.length > 0 && (
                                                <div className="border-t border-amber-200 dark:border-amber-900/30 pt-2 mt-2">
                                                    <p className="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-2">Switched off for this tenant</p>
                                                    <div className={GRID}>
                                                        {group.switchedOff.map(s => (
                                                            <div key={s.view} className={CELL}>
                                                                <span className="truncate text-sm text-gray-500 dark:text-gray-400" title={s.label}>{s.label}</span>
                                                                <Marker kind="switched-off" />
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </>
            )}
        </div>
    );
}
