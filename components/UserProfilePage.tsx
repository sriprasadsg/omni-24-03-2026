
import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { useUser } from '../contexts/UserContext';
import { UserIcon, PencilIcon, SaveIcon, XIcon, ShieldCheckIcon, ShieldAlertIcon, KeyIcon } from './icons';
import MFASetupWizard from './MFASetupWizard';
import PasskeySetupModal from './PasskeySetupModal';
import { authFetch, listPasskeys, deletePasskey } from '../services/apiService';

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

    // MFA state
    const [mfaEnabled, setMfaEnabled] = useState<boolean>(false);
    const [mfaBackupRemaining, setMfaBackupRemaining] = useState<number>(0);
    const [showMfaSetup, setShowMfaSetup] = useState(false);
    const [showDisableMfa, setShowDisableMfa] = useState(false);
    const [disableCode, setDisableCode] = useState('');
    const [disableError, setDisableError] = useState('');
    const [disableLoading, setDisableLoading] = useState(false);

    // Passkey state
    const [passkeys, setPasskeys] = useState<any[]>([]);
    const [showPasskeySetup, setShowPasskeySetup] = useState(false);
    const [passkeyError, setPasskeyError] = useState('');

    const refreshPasskeys = () => {
        listPasskeys().then(setPasskeys).catch(() => setPasskeys([]));
    };

    useEffect(() => {
        if (currentUser) {
            setName(currentUser.name);
            setAvatar(currentUser.avatar);
        }
    }, [currentUser]);

    useEffect(() => {
        authFetch('/api/mfa/status')
            .then(r => r.json())
            .then(d => {
                setMfaEnabled(d.enabled ?? false);
                setMfaBackupRemaining(d.backup_codes_remaining ?? 0);
            })
            .catch(() => {});
        refreshPasskeys();
    }, []);

    const handleRemovePasskey = async (credentialId: string) => {
        setPasskeyError('');
        try {
            await deletePasskey(credentialId);
            refreshPasskeys();
        } catch (e: any) {
            setPasskeyError(e.message || 'Failed to remove passkey');
        }
    };

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

    const handleDisableMfa = async () => {
        if (!disableCode) { setDisableError('Enter your account password to confirm'); return; }
        setDisableLoading(true); setDisableError('');
        try {
            const r = await authFetch('/api/mfa/disable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: disableCode }),
            });
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || 'Failed to disable MFA');
            setMfaEnabled(false);
            setShowDisableMfa(false);
            setDisableCode('');
        } catch (e: any) {
            setDisableError(e.message);
        } finally {
            setDisableLoading(false);
        }
    };

    return (
        <div className="container mx-auto max-w-4xl space-y-6">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">My Profile</h2>

            {/* Profile card */}
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

            {/* Security card */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">Security</h3>

                <div className="flex items-center justify-between py-4 border-b border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-3">
                        {mfaEnabled
                            ? <ShieldCheckIcon size={24} className="text-green-500" />
                            : <ShieldAlertIcon size={24} className="text-amber-500" />
                        }
                        <div>
                            <p className="text-sm font-medium text-gray-900 dark:text-white">Two-Factor Authentication (TOTP)</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                {mfaEnabled
                                    ? `Enabled — ${mfaBackupRemaining} backup code${mfaBackupRemaining !== 1 ? 's' : ''} remaining`
                                    : 'Not enabled — your account is less secure without 2FA'}
                            </p>
                        </div>
                    </div>

                    {mfaEnabled ? (
                        <button
                            onClick={() => { setShowDisableMfa(v => !v); setDisableCode(''); setDisableError(''); }}
                            className="px-4 py-2 text-sm font-medium text-red-600 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                            {showDisableMfa ? 'Cancel' : 'Disable 2FA'}
                        </button>
                    ) : (
                        <button
                            onClick={() => setShowMfaSetup(true)}
                            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                        >
                            Enable 2FA
                        </button>
                    )}
                </div>

                {/* Passkeys */}
                <div className="py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <KeyIcon size={24} className={passkeys.length > 0 ? 'text-green-500' : 'text-gray-400'} />
                            <div>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">Passkeys (WebAuthn)</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    {passkeys.length > 0
                                        ? `${passkeys.length} passkey${passkeys.length !== 1 ? 's' : ''} registered`
                                        : 'Sign in with Touch ID, Windows Hello, or a security key'}
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={() => setShowPasskeySetup(true)}
                            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                        >
                            Register a new passkey
                        </button>
                    </div>

                    {passkeyError && <p className="mt-2 text-xs text-red-500">{passkeyError}</p>}

                    {passkeys.length > 0 && (
                        <ul className="mt-4 divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded-lg">
                            {passkeys.map((pk) => (
                                <li key={pk.credential_id} className="flex items-center justify-between px-4 py-3">
                                    <div>
                                        <p className="text-sm text-gray-900 dark:text-gray-200 font-mono">
                                            {String(pk.credential_id).slice(0, 16)}…
                                        </p>
                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                            Added {pk.created_at ? new Date(pk.created_at).toLocaleDateString() : 'unknown'}
                                            {pk.last_used_at ? ` · last used ${new Date(pk.last_used_at).toLocaleDateString()}` : ' · never used'}
                                            {pk.transports?.length ? ` · ${pk.transports.join(', ')}` : ''}
                                        </p>
                                    </div>
                                    <button
                                        onClick={() => handleRemovePasskey(pk.credential_id)}
                                        className="px-3 py-1.5 text-xs font-medium text-red-600 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                                    >
                                        Remove
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>

                {/* Inline disable form */}
                {showDisableMfa && (
                    <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg space-y-3">
                        <p className="text-sm text-red-700 dark:text-red-300 font-medium">Enter your account password to confirm disabling 2FA:</p>
                        <input
                            type="password"
                            value={disableCode}
                            onChange={e => setDisableCode(e.target.value)}
                            placeholder="Password"
                            className="block w-64 px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md text-sm"
                        />
                        {disableError && <p className="text-xs text-red-500">{disableError}</p>}
                        <button
                            onClick={handleDisableMfa}
                            disabled={disableLoading || !disableCode}
                            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
                        >
                            {disableLoading ? 'Disabling...' : 'Confirm Disable'}
                        </button>
                    </div>
                )}
            </div>

            {/* Passkey Setup Modal overlay */}
            {showPasskeySetup && (
                <PasskeySetupModal
                    onClose={() => setShowPasskeySetup(false)}
                    onRegistered={refreshPasskeys}
                />
            )}

            {/* MFA Setup Wizard overlay */}
            {showMfaSetup && (
                <MFASetupWizard
                    onClose={() => setShowMfaSetup(false)}
                    onEnabled={() => {
                        setMfaEnabled(true);
                        setMfaBackupRemaining(8);
                    }}
                />
            )}
        </div>
    );
};
