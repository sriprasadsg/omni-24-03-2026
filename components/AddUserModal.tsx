import React, { useState, useMemo, useEffect } from 'react';
import { Role, Tenant } from '../types';

interface AddUserModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (user: { name: string; email: string; role: string; tenantId: string; tenantName: string; }) => void;
    tenants: Tenant[];
    roles: Role[];
}

export const AddUserModal: React.FC<AddUserModalProps> = ({ isOpen, onClose, onSave, tenants, roles }) => {
    const availableTenants = useMemo(() => tenants.filter(t => t.id !== 'platform-admin'), [tenants]);

    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [selectedRole, setSelectedRole] = useState('');
    const [selectedTenantId, setSelectedTenantId] = useState('');
    
    useEffect(() => {
        if(isOpen) {
            const defaultRole = roles.find(r => r.name === 'Tenant Admin')?.name || roles[0]?.name || '';
            const defaultTenant = availableTenants[0]?.id || '';
            setSelectedRole(defaultRole);
            setSelectedTenantId(defaultTenant);
            setName('');
            setEmail('');
        }
    }, [isOpen, roles, availableTenants]);


    const isSuperAdminRole = selectedRole === 'Super Admin';
    const finalTenantId = isSuperAdminRole ? 'platform-admin' : selectedTenantId;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const tenant = tenants.find(t => t.id === finalTenantId);
        if (!name.trim() || !email.trim() || !selectedRole || !tenant) {
            alert("Please fill all fields correctly.");
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

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6 m-4" onClick={e => e.stopPropagation()}>
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Add New User</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
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
                            {roles.map(r => <option key={r.id} value={r.name}>{r.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label htmlFor="add-user-tenant" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Tenant</label>
                        <select id="add-user-tenant" value={selectedTenantId} onChange={e => setSelectedTenantId(e.target.value)} disabled={isSuperAdminRole} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm disabled:bg-gray-100 dark:disabled:bg-gray-700/50">
                            {isSuperAdminRole 
                                ? <option value="platform-admin">Platform</option>
                                : availableTenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)
                            }
                        </select>
                    </div>
                    <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                        <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add User</button>
                    </div>
                </form>
            </div>
        </div>
    );
};
