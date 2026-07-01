import React from 'react';
import { User, Role, Tenant } from '../types';
import { PlusCircleIcon, PencilIcon, TrashIcon, KeyIcon, SearchIcon, BuildingIcon } from './icons';
import { useUser } from '../contexts/UserContext';

interface Props {
    users: User[];
    roles: Role[];
    tenants: Tenant[];
    filteredUsers: User[];
    searchQuery: string;
    canManageRBAC: boolean;
    onSearchChange: (q: string) => void;
    onEditUser: (user: User) => void;
    onDeleteUser: (userId: string) => void;
    onResetPassword: (userId: string, userName: string) => void;
    onAddUser: () => void;
}

export function SettingsUsersTab({
    tenants, filteredUsers, searchQuery, canManageRBAC,
    onSearchChange, onEditUser, onDeleteUser, onResetPassword, onAddUser,
}: Props) {
    const { currentUser } = useUser();

    return (
        <div>
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 space-y-4 md:space-y-0">
                <div>
                    <h3 className="text-lg font-semibold text-gray-800 dark:text-white">User Management</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Manage user accounts, roles, and platform access across all tenants.</p>
                </div>
                <div className="flex items-center space-x-3 w-full md:w-auto">
                    <div className="relative flex-grow md:flex-initial">
                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <SearchIcon size={18} className="text-gray-400" />
                        </div>
                        <input
                            type="text"
                            placeholder="Search users, roles, or tenants..."
                            value={searchQuery}
                            onChange={(e) => onSearchChange(e.target.value)}
                            className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent sm:text-sm transition-all"
                        />
                    </div>
                    {canManageRBAC && (
                        <button onClick={onAddUser} className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 shadow-sm transition-colors">
                            <PlusCircleIcon size={18} className="mr-2" />
                            New User
                        </button>
                    )}
                </div>
            </div>
            <div className="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-4 py-3">User</th>
                            <th scope="col" className="px-4 py-3">Email</th>
                            {currentUser?.role === 'Super Admin' && <th scope="col" className="px-4 py-3">Tenant</th>}
                            <th scope="col" className="px-4 py-3">Role</th>
                            <th scope="col" className="px-4 py-3">Status</th>
                            <th scope="col" className="px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredUsers.length > 0 ? (
                            filteredUsers.map(user => {
                                const isCurrentUser = currentUser?.id === user.id;
                                const tenantName = user.tenantName || tenants.find(t => t.id === user.tenantId)?.name || 'Unknown';
                                return (
                                    <tr key={user.id} className={`border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 transition-opacity ${user.status === 'Disabled' ? 'opacity-50' : ''}`}>
                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                            <div className="flex items-center">
                                                {user.avatar
                                                    ? <img src={user.avatar} alt={user.name} className="h-8 w-8 rounded-full object-cover mr-3" />
                                                    : <span className="h-8 w-8 rounded-full bg-indigo-500 text-white flex items-center justify-center text-xs font-bold mr-3 flex-shrink-0">{(user.name || '?')[0].toUpperCase()}</span>}
                                                <span>{user.name}</span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-xs">{user.email}</td>
                                        {currentUser?.role === 'Super Admin' && (
                                            <td className="px-4 py-3 text-xs">
                                                <div className="flex items-center">
                                                    <BuildingIcon size={14} className="mr-1.5 text-gray-400" />
                                                    {tenantName}
                                                </div>
                                            </td>
                                        )}
                                        <td className="px-4 py-3">
                                            <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800 dark:bg-gray-900/50 dark:text-gray-300">{user.role}</span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${user.status === 'Active' ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
                                                {user.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center space-x-2">
                                                <button onClick={() => onEditUser(user)} disabled={isCurrentUser && user.role === 'Super Admin'} title={isCurrentUser && user.role === 'Super Admin' ? "Super Admin role cannot be changed." : "Edit user"} className="flex items-center px-2.5 py-1 text-xs font-medium text-primary-700 bg-primary-100 rounded-md hover:bg-primary-200 dark:bg-primary-900/50 dark:text-primary-300 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-not-allowed">
                                                    <PencilIcon size={12} className="mr-1.5" /> Edit
                                                </button>
                                                <button onClick={() => onResetPassword(user.id, user.name)} disabled={isCurrentUser} title={isCurrentUser ? "You cannot reset your own password here." : "Reset user password"} className="flex items-center px-2.5 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-md hover:bg-amber-200 dark:bg-amber-900/50 dark:text-amber-300 dark:hover:bg-amber-900 disabled:opacity-50 disabled:cursor-not-allowed">
                                                    <KeyIcon size={12} className="mr-1.5" /> Reset Password
                                                </button>
                                                <button onClick={() => onDeleteUser(user.id)} disabled={isCurrentUser} title={isCurrentUser ? "You cannot delete your own account." : "Delete user"} className="flex items-center px-2.5 py-1 text-xs font-medium text-red-700 bg-red-100 rounded-md hover:bg-red-200 dark:bg-red-900/50 dark:text-red-300 dark:hover:bg-red-900 disabled:opacity-50 disabled:cursor-not-allowed">
                                                    <TrashIcon size={12} className="mr-1.5" /> Delete
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })
                        ) : (
                            <tr>
                                <td colSpan={currentUser?.role === 'Super Admin' ? 6 : 5} className="px-4 py-12 text-center text-gray-500 dark:text-gray-400">
                                    <div className="flex flex-col items-center">
                                        <SearchIcon size={48} className="mb-4 opacity-20" />
                                        <p className="text-lg font-medium">No users found matching "{searchQuery}"</p>
                                        <button onClick={() => onSearchChange('')} className="mt-2 text-primary-600 hover:text-primary-500 font-medium">Clear search</button>
                                    </div>
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
