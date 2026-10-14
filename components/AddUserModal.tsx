import React, { useState, useMemo, useEffect } from 'react';
import { Role, Tenant } from '../types';
import { showToast } from '../utils/toast';
import { useUser } from '../contexts/UserContext';
import { isPlatformRoleName, isSuperAdminRoleName, PLATFORM_TENANT_ID, roleLabel } from '../utils/permissions';
import { Modal } from './Modal';

interface AddUserModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (user: { name: string; email: string; role: string; tenantId: string; tenantName: string; }) => void;
    tenants: Tenant[];
    roles: Role[];
}

export const AddUserModal: React.FC<AddUserModalProps> = ({ isOpen, onClose, onSave, tenants, roles }) => {
    const { currentUser } = useUser();
    const availableTenants = useMemo(() => tenants.filter(t => t.id !== PLATFORM_TENANT_ID), [tenants]);
    // Platform roles (spec C1) are offered only to a Platform Owner; the server enforces the same.
    const assignableRoles = useMemo(
        () => isSuperAdminRoleName(currentUser?.role) ? roles : roles.filter(r => !isPlatformRoleName(r.name)),
        [roles, currentUser]);

    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [selectedRole, setSelectedRole] = useState('');
    const [selectedTenantId, setSelectedTenantId] = useState('');

    useEffect(() => {
        if(isOpen) {
            const defaultRole = assignableRoles.find(r => r.name === 'Tenant Admin')?.name || assignableRoles[0]?.name || '';
            const defaultTenant = availableTenants[0]?.id || '';
            setSelectedRole(defaultRole);
            setSelectedTenantId(defaultTenant);
            setName('');
            setEmail('');
        }
    }, [isOpen, assignableRoles, availableTenants]);


    // A platform role lives only in the Platform tenant; a tenant role never does.
    const isPlatformRole = isPlatformRoleName(selectedRole);
    const finalTenantId = isPlatformRole ? PLATFORM_TENANT_ID : selectedTenantId;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const tenant = tenants.find(t => t.id === finalTenantId);
        if (!name.trim() || !email.trim() || !selectedRole || !tenant) {
            showToast("Please fill all fields correctly.", 'error');
            return;
        }

        onSave({
            name,
            email,
            role: selectedRole,
            tenantId: tenant.id,
            tenantName: tenant.name,
        });

        onClose(); // Close modal on save
    };

    const footer = (
        <>
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
            <button type="submit" form="add-user-form" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add User</button>
        </>
    );

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Add New User" size="md" footer={footer}>
            <form id="add-user-form" onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="add-user-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Full Name</label>
                    <input type="text" id="add-user-name" value={name} onChange={e => setName(e.target.value)} required className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
                </div>
                <div>
                    <label htmlFor="add-user-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
                    <input type="email" id="add-user-email" value={email} onChange={e => setEmail(e.target.value)} required className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
                </div>
                <div>
                    <label htmlFor="add-user-role" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Role</label>
                    <select id="add-user-role" value={selectedRole} onChange={e => setSelectedRole(e.target.value)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm">
                        {assignableRoles.map(r => <option key={r.id} value={r.name}>{roleLabel(r.name)}</option>)}
                    </select>
                </div>
                <div>
                    <label htmlFor="add-user-tenant" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Tenant</label>
                    <select id="add-user-tenant" value={selectedTenantId} onChange={e => setSelectedTenantId(e.target.value)} disabled={isPlatformRole} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50">
                        {isPlatformRole
                            ? <option value={PLATFORM_TENANT_ID}>Platform</option>
                            : availableTenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)
                        }
                    </select>
                </div>
            </form>
        </Modal>
    );
};
