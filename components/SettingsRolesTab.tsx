import React from 'react';
import { Role } from '../types';
import { PlusCircleIcon, PencilIcon, TrashIcon, ShieldLockIcon } from './icons';

interface Props {
    roles: Role[];
    canManageSettings: boolean;
    onEdit: (role: Role) => void;
    onDelete: (roleId: string) => void;
    onNew: () => void;
}

export function SettingsRolesTab({ roles, onEdit, onDelete, onNew }: Props) {
    return (
        <div>
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">Roles & Permissions</h3>
                <button onClick={onNew} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                    <PlusCircleIcon size={16} className="mr-1.5" />
                    New Custom Role
                </button>
            </div>
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
                        {roles.map(role => (
                            <tr key={role.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                    <div className="flex items-center">
                                        <span>{role.name}</span>
                                        <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-primary-100 text-primary-800 dark:bg-primary-900/50 dark:text-primary-300">
                                            {role.permissions.length}
                                        </span>
                                    </div>
                                </td>
                                <td className="px-4 py-3 text-xs max-w-sm">{role.description}</td>
                                <td className="px-4 py-3">
                                    <div className="flex items-center space-x-2">
                                        <button onClick={() => onEdit(role)} className="p-1.5 text-gray-500 hover:text-primary-600 disabled:text-gray-400 disabled:dark:text-gray-500 disabled:cursor-not-allowed" disabled={!role.isEditable} title={role.isEditable ? "Edit role" : "Built-in roles cannot be edited."}>
                                            <PencilIcon size={14} />
                                        </button>
                                        {role.isEditable ? (
                                            <button onClick={() => onDelete(role.id)} className="p-1.5 text-gray-500 hover:text-red-600" title="Delete role">
                                                <TrashIcon size={14} />
                                            </button>
                                        ) : (
                                            <span title="This built-in role cannot be deleted.">
                                                <ShieldLockIcon size={14} className="p-0.5 text-gray-400 dark:text-gray-500" />
                                            </span>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
