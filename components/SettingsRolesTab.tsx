import React, { useEffect, useState } from 'react';
import { ApiRole, RoleInUseDetail, RoleInUseError, deleteRole, fetchRoles, isBuiltInRole } from '../services/roleApi';
import { PlusCircleIcon, PencilIcon, TrashIcon, ShieldLockIcon, EyeIcon, ChevronRightIcon, LoaderIcon } from './icons';
import { RoleVisibilityPanel } from './RoleVisibilityPanel';
import { ConfirmationModal } from './ConfirmationModal';
import { RoleDeleteRefusalModal } from './RoleDeleteRefusalModal';
import { showToast } from '../utils/toast';

interface Props {
    roles: ApiRole[];
    tenantId?: string | null;
    canManageSettings?: boolean;
    canManageRBAC?: boolean;
    isSuperAdmin?: boolean;
    onEdit: (role: ApiRole) => void;
    onDelete: (roleId: string) => void;
    onNew: () => void;
    /** Switch the Settings tab to User Management (the delete-refused dialog's primary action). */
    onGoToUsers?: () => void;
}

const ICON_BTN = 'inline-flex items-center justify-center min-w-8 min-h-8 p-1.5 text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded';

export function SettingsRolesTab({ roles: seed, tenantId, canManageRBAC = false, isSuperAdmin = false, onEdit, onDelete, onNew, onGoToUsers }: Props) {
    const [openRoleId, setOpenRoleId] = useState<string | null>(null);
    const [roles, setRoles] = useState<ApiRole[]>(seed);
    const [confirmRole, setConfirmRole] = useState<ApiRole | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [refusal, setRefusal] = useState<{ roleName: string; detail: RoleInUseDetail } | null>(null);

    // D-01: the delete goes to the server; D-03: a role still in use is refused with who holds it.
    const runDelete = async (role: ApiRole) => {
        setDeletingId(role.id);
        try {
            await deleteRole(role.id, tenantId ?? undefined);
            setRoles(prev => prev.filter(r => r.id !== role.id));
            showToast(`Role "${role.name}" deleted.`, 'success');
            onDelete(role.id);
        } catch (e) {
            if (e instanceof RoleInUseError) {
                setRefusal({ roleName: role.name, detail: e.detail });
            } else {
                const msg = (e as Error)?.message || 'request failed';
                showToast(`Couldn't delete the role: ${msg}. Try again.`, 'error');
            }
        } finally {
            setDeletingId(null);
        }
    };

    // Seed from the parent, then refresh from the server for the selected tenant (D-17).
    // A failed or forbidden fetch keeps the seeded (or last good) list; the tab stays gated.
    useEffect(() => {
        let cancelled = false;
        setRoles(seed);
        fetchRoles(tenantId ?? undefined).then(list => { if (!cancelled && Array.isArray(list)) setRoles(list); }).catch(() => {});
        return () => { cancelled = true; };
    }, [tenantId, seed]);

    const hasCustom = roles.some(r => !isBuiltInRole(r));
    const needsTenant = isSuperAdmin && !tenantId;
    return (
        <div>
            <div className="flex justify-between items-center mb-1">
                <h3 className="text-lg font-semibold">Roles & Permissions</h3>
                {canManageRBAC && (
                    <button
                        onClick={onNew}
                        disabled={needsTenant}
                        title={needsTenant ? 'Select a tenant first: custom roles belong to one tenant.' : undefined}
                        className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <PlusCircleIcon size={16} className="mr-1.5" />
                        New Custom Role
                    </button>
                )}
            </div>
            {!hasCustom && (
                <p className="text-xs font-normal text-gray-500 dark:text-gray-400 mb-4">No custom roles yet. Built-in roles cannot be edited; create a custom role to tailor access.</p>
            )}
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-4 py-3">Role Name</th>
                            <th scope="col" className="px-4 py-3">Description</th>
                            <th scope="col" className="px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {roles.map(role => {
                            const isOpen = openRoleId === role.id;
                            const panelId = `role-visibility-${role.id}`;
                            const builtIn = isBuiltInRole(role);
                            return (
                                <React.Fragment key={role.id}>
                                    <tr className={`border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 ${deletingId === role.id ? 'opacity-60 pointer-events-none' : ''}`} aria-busy={deletingId === role.id || undefined}>
                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                            <div className="flex items-center min-w-0">
                                                <span className="truncate max-w-[16rem]" title={role.name}>{role.name}</span>
                                                {builtIn ? (
                                                    <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full border border-gray-300 text-gray-600 dark:border-gray-600 dark:text-gray-300 shrink-0">
                                                        <ShieldLockIcon size={12} aria-hidden="true" />Built-in
                                                    </span>
                                                ) : (
                                                    <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200 shrink-0">Custom</span>
                                                )}
                                                <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-primary-100 text-primary-800 dark:bg-primary-900/50 dark:text-primary-300">
                                                    {role.permissions.length}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-xs max-w-sm whitespace-normal break-words">{role.description}</td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center space-x-2">
                                                <button
                                                    type="button"
                                                    onClick={() => setOpenRoleId(isOpen ? null : role.id)}
                                                    aria-expanded={isOpen}
                                                    aria-controls={panelId}
                                                    aria-label={`What ${role.name} can see`}
                                                    className="inline-flex items-center gap-1 px-1.5 py-1 text-xs font-medium text-gray-600 hover:text-primary-600 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded"
                                                >
                                                    <ChevronRightIcon size={14} aria-hidden="true" className={`motion-safe:transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                                                    <EyeIcon size={14} aria-hidden="true" />
                                                    <span className="hidden sm:inline">What it can see</span>
                                                </button>
                                                {canManageRBAC && (
                                                    <button
                                                        type="button"
                                                        onClick={() => { if (!builtIn) onEdit(role); }}
                                                        aria-label={`Edit role ${role.name}`}
                                                        aria-disabled={builtIn ? 'true' : undefined}
                                                        className={`${ICON_BTN} ${builtIn ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed' : 'hover:text-primary-600'}`}
                                                        title={builtIn ? 'Built-in roles cannot be edited.' : 'Edit role'}
                                                    >
                                                        <PencilIcon size={14} />
                                                    </button>
                                                )}
                                                {canManageRBAC && (builtIn ? (
                                                    <span title="This built-in role cannot be deleted." className="inline-flex items-center justify-center min-w-8 min-h-8">
                                                        <ShieldLockIcon size={14} className="text-gray-400 dark:text-gray-500" />
                                                    </span>
                                                ) : (
                                                    <button type="button" onClick={() => setConfirmRole(role)} disabled={deletingId === role.id} aria-label={`Delete role ${role.name}`} className={`${ICON_BTN} hover:text-red-600`} title="Delete role">
                                                        {deletingId === role.id ? <LoaderIcon size={14} data-testid="role-delete-spinner" className="animate-spin" /> : <TrashIcon size={14} />}
                                                    </button>
                                                ))}
                                            </div>
                                        </td>
                                    </tr>
                                    {isOpen && (
                                        <tr className="border-b dark:border-gray-700">
                                            <td colSpan={3} className="p-0 min-w-0">
                                                <RoleVisibilityPanel role={role} tenantId={tenantId} panelId={panelId} />
                                            </td>
                                        </tr>
                                    )}
                                </React.Fragment>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            <ConfirmationModal
                isOpen={confirmRole !== null}
                onClose={() => setConfirmRole(null)}
                onConfirm={() => { if (confirmRole) void runDelete(confirmRole); }}
                title="Delete role"
                message={`Delete the custom role "${confirmRole?.name ?? ''}"? This can't be undone.`}
                confirmText="Delete role"
                cancelText="Keep role"
                isDestructive
            />
            <RoleDeleteRefusalModal
                isOpen={refusal !== null}
                roleName={refusal?.roleName ?? ''}
                detail={refusal?.detail ?? null}
                onClose={() => setRefusal(null)}
                onGoToUsers={() => onGoToUsers?.()}
            />
        </div>
    );
}
