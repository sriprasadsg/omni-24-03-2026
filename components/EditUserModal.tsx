import React, { useState, useEffect } from 'react';
import { User, Role } from '../types';
import { useUser } from '../contexts/UserContext';
import { isPlatformRoleName, isSuperAdminRoleName, PLATFORM_TENANT_ID, roleLabel } from '../utils/permissions';
import { Modal } from './Modal';

interface EditUserModalProps {
    user: User;
    roles: Role[];
    onClose: () => void;
    onSave: (userId: string, updates: { role?: string; status?: 'Active' | 'Disabled' }) => void;
}

export const EditUserModal: React.FC<EditUserModalProps> = ({ user, roles, onClose, onSave }) => {
    const { currentUser } = useUser();
    const [selectedRole, setSelectedRole] = useState(user.role);
    const [selectedStatus, setSelectedStatus] = useState<'Active' | 'Disabled'>(user.status);

    useEffect(() => {
        setSelectedRole(user.role);
        setSelectedStatus(user.status);
    }, [user]);

    const handleSave = () => {
        const updates: { role?: string; status?: 'Active' | 'Disabled' } = {};
        if (selectedRole !== user.role) {
            updates.role = selectedRole;
        }
        if (selectedStatus !== user.status) {
            updates.status = selectedStatus;
        }
        if (Object.keys(updates).length > 0) {
            onSave(user.id, updates);
        }
        onClose();
    };

    const isCurrentUser = currentUser?.id === user.id;
    const isOwnerAccount = isSuperAdminRoleName(user.role);
    // Platform accounts take only platform roles and tenant accounts only tenant roles (spec C1);
    // platform roles are offered only to a Platform Owner.
    const inPlatformTenant = user.tenantId === PLATFORM_TENANT_ID;
    const roleOptions = roles.filter(r => isPlatformRoleName(r.name) === inPlatformTenant
        && (!inPlatformTenant || isSuperAdminRoleName(currentUser?.role)));

    const footer = (
        <>
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
            <button type="button" onClick={handleSave} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Save Changes</button>
        </>
    );

    return (
        <Modal isOpen={true} onClose={onClose} title={`Edit User: ${user.name}`} size="md" footer={footer}>
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{user.email}</p>
                    </div>
                    <div>
                        <label htmlFor="role" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Role</label>
                        <select
                            id="role"
                            value={selectedRole}
                            onChange={(e) => setSelectedRole(e.target.value)}
                            disabled={isCurrentUser && isOwnerAccount}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50"
                        >
                            {!roleOptions.some(r => r.name === user.role) && <option value={user.role}>{roleLabel(user.role)}</option>}
                            {roleOptions.map(r => <option key={r.id} value={r.name}>{roleLabel(r.name)}</option>)}
                        </select>
                         {isCurrentUser && isOwnerAccount && <p className="text-xs text-gray-400 mt-1">You cannot change your own Platform Owner role.</p>}
                    </div>
                     <div>
                        <label htmlFor="status" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Status</label>
                        <select
                            id="status"
                            value={selectedStatus}
                            onChange={(e) => setSelectedStatus(e.target.value as 'Active' | 'Disabled')}
                            disabled={isCurrentUser}
                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50"
                        >
                            <option value="Active">Active</option>
                            <option value="Disabled">Disabled</option>
                        </select>
                        {isCurrentUser && <p className="text-xs text-gray-400 mt-1">You cannot disable your own account.</p>}
                    </div>
                </div>
        </Modal>
    );
};
