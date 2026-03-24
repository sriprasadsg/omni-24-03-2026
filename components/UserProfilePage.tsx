
import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { useUser } from '../contexts/UserContext';
// FIX: Added missing SaveIcon.
import { UserIcon, PencilIcon, SaveIcon, XIcon } from './icons';

interface UserProfilePageProps {
  onProfileUpdate: (updates: { name: string; avatar: string; }) => void;
}

const availableAvatars = [
    'https://i.pravatar.cc/150?u=super-admin',
    'https://i.pravatar.cc/150?u=alice-admin',
    'https://i.pravatar.cc/150?u=bob-secops',
    'https://i.pravatar.cc/150?u=charlie-devops',
    'https://i.pravatar.cc/150?u=eve-engineer',
    'https://i.pravatar.cc/150?u=generic-1',
    'https://i.pravatar.cc/150?u=generic-2',
    'https://i.pravatar.cc/150?u=generic-3',
];

export const UserProfilePage: React.FC<UserProfilePageProps> = ({ onProfileUpdate }) => {
    const { currentUser } = useUser();
    const [isEditing, setIsEditing] = useState(false);
    const [name, setName] = useState(currentUser?.name || '');
    const [avatar, setAvatar] = useState(currentUser?.avatar || '');

    useEffect(() => {
        if (currentUser) {
            setName(currentUser.name);
            setAvatar(currentUser.avatar);
        }
    }, [currentUser]);

    if (!currentUser) {
        return <div>Loading user profile...</div>;
    }

    const handleSave = () => {
        onProfileUpdate({ name, avatar });
        setIsEditing(false);
    };

    const handleCancel = () => {
        setName(currentUser.name);
        setAvatar(currentUser.avatar);
        setIsEditing(false);
    };

    return (
        <div className="container mx-auto max-w-4xl">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">My Profile</h2>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <div className="flex flex-col sm:flex-row items-center sm:items-start">
                    <div className="relative">
                        <img src={avatar} alt="User Avatar" className="w-32 h-32 rounded-full object-cover ring-4 ring-primary-500/50" />
                    </div>

                    <div className="mt-4 sm:mt-0 sm:ml-8 flex-1">
                        {isEditing ? (
                            <div className="space-y-4">
                                <div>
                                    <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Full Name</label>
                                    <input type="text" id="name" value={name} onChange={e => setName(e.target.value)}
                                        className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Choose Avatar</label>
                                    <div className="mt-2 flex flex-wrap gap-2">
                                        {availableAvatars.map(av => (
                                            <button key={av} onClick={() => setAvatar(av)} className={`w-12 h-12 rounded-full overflow-hidden ring-2 ${avatar === av ? 'ring-primary-500' : 'ring-transparent'}`}>
                                                <img src={av} alt="Avatar option" className="w-full h-full object-cover" />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div>
                                <h3 className="text-2xl font-bold text-gray-900 dark:text-white">{name}</h3>
                                <p className="text-md text-gray-500 dark:text-gray-400">{currentUser.email}</p>
                            </div>
                        )}
                        
                        <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
                            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-4 text-sm">
                                <div>
                                    <dt className="font-medium text-gray-500 dark:text-gray-400">Role</dt>
                                    <dd className="mt-1 text-gray-900 dark:text-gray-200">{currentUser.role}</dd>
                                </div>
                                <div>
                                    <dt className="font-medium text-gray-500 dark:text-gray-400">Tenant</dt>
                                    <dd className="mt-1 text-gray-900 dark:text-gray-200">{currentUser.tenantName}</dd>
                                </div>
                            </dl>
                        </div>
                    </div>
                </div>

                <div className="mt-6 flex justify-end space-x-3">
                    {isEditing ? (
                        <>
                            <button onClick={handleCancel} className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600">
                                <XIcon size={16} className="mr-2" />
                                Cancel
                            </button>
                            <button onClick={handleSave} className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                <SaveIcon size={16} className="mr-2" />
                                Save Changes
                            </button>
                        </>
                    ) : (
                        <button onClick={() => setIsEditing(true)} className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                            <PencilIcon size={16} className="mr-2" />
                            Edit Profile
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};
