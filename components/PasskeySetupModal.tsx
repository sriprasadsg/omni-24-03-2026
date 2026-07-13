import React, { useState } from 'react';
import { startRegistration } from '@simplewebauthn/browser';
import { XIcon, KeyIcon } from './icons';
import * as api from '../services/apiService';

interface PasskeySetupModalProps {
    onClose: () => void;
    onRegistered: () => void;
}

export const PasskeySetupModal: React.FC<PasskeySetupModalProps> = ({ onClose, onRegistered }) => {
    const [isRegistering, setIsRegistering] = useState(false);
    const [error, setError] = useState('');
    const [done, setDone] = useState(false);

    const handleRegister = async () => {
        setError('');
        setIsRegistering(true);
        try {
            const options = await api.passkeyRegisterOptions();
            const credential = await startRegistration({ optionsJSON: options });
            await api.passkeyRegisterVerify(credential);
            setDone(true);
            onRegistered();
        } catch (err: any) {
            console.error('Passkey registration error:', err);
            if (err?.name === 'NotAllowedError') {
                setError('Passkey creation was cancelled.');
            } else if (err?.name === 'InvalidStateError') {
                setError('A passkey for this account already exists on this device.');
            } else {
                setError('Could not register the passkey. Please try again.');
            }
        } finally {
            setIsRegistering(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-800 dark:text-white flex items-center gap-2">
                        <KeyIcon size={20} className="text-primary-500" />
                        Register a Passkey
                    </h3>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                        <XIcon size={20} />
                    </button>
                </div>

                {done ? (
                    <div className="space-y-4">
                        <p className="text-sm text-green-600 dark:text-green-400 font-medium">
                            ✓ Passkey registered. You can now sign in with it from the login page.
                        </p>
                        <button
                            onClick={onClose}
                            className="w-full px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                        >
                            Done
                        </button>
                    </div>
                ) : (
                    <div className="space-y-4">
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                            A passkey lets you sign in with your device's screen lock (Touch ID, Windows
                            Hello, or a hardware security key) instead of a password. Your browser will
                            prompt you to create one.
                        </p>

                        {error && (
                            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-md p-3">
                                {error}
                            </p>
                        )}

                        <div className="flex justify-end gap-3">
                            <button
                                onClick={onClose}
                                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleRegister}
                                disabled={isRegistering}
                                className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
                            >
                                {isRegistering ? 'Waiting for device…' : 'Create Passkey'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PasskeySetupModal;
