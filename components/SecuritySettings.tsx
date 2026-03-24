
import React, { useState, useEffect } from 'react';
import { ShieldCheckIcon, ShieldAlertIcon, KeyIcon, SmartphoneIcon, ShieldLockIcon, CheckIcon, AlertTriangleIcon, CopyIcon, GlobeIcon } from './icons';
import * as apiService from '../services/apiService';

export const SecuritySettings: React.FC = () => {
    const [mfaStatus, setMfaStatus] = useState<{ enabled: boolean; enrolled_at: string | null; backup_codes_remaining: number } | null>(null);
    const [ssoProviders, setSsoProviders] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [setupStep, setSetupStep] = useState<'idle' | 'enrolling' | 'verifying'>('idle');
    const [setupData, setSetupData] = useState<{ secret: string; qr_base64: string; qr_uri: string } | null>(null);
    const [verificationCode, setVerificationCode] = useState('');
    const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        loadSecurityInfo();
    }, []);

    const loadSecurityInfo = async () => {
        setLoading(true);
        try {
            const [status, sso] = await Promise.all([
                apiService.fetchMfaStatus(),
                apiService.fetchSsoProviders()
            ]);
            setMfaStatus(status);
            setSsoProviders(sso.providers || []);
        } catch (err) {
            console.error('Failed to load security info:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleStartSetup = async () => {
        setError(null);
        try {
            const data = await apiService.setupMfa();
            setSetupData(data);
            setSetupStep('enrolling');
        } catch (err) {
            setError('Failed to initiate MFA setup.');
        }
    };

    const handleVerifySetup = async () => {
        setError(null);
        try {
            const result = await apiService.verifyMfaSetup(verificationCode);
            if (result.success) {
                setBackupCodes(result.backup_codes);
                setSetupStep('verifying');
                loadSecurityInfo();
            }
        } catch (err: any) {
            setError(err.message || 'MFA verification failed.');
        }
    };

    const handleDisableMfa = async () => {
        const code = prompt('Please enter your MFA code to confirm disabling MFA:');
        if (!code) return;

        try {
            await apiService.disableMfa(code);
            loadSecurityInfo();
            alert('MFA has been disabled.');
        } catch (err) {
            alert('Failed to disable MFA. Please ensure your code is correct.');
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500">Loading security settings...</div>;

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2">
            <div>
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-1">Security & Identity</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">Manage multi-factor authentication and single sign-on settings.</p>
            </div>

            {/* MFA Section */}
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div className="flex items-center gap-4">
                        <div className={`p-3 rounded-xl ${mfaStatus?.enabled ? 'bg-green-100 dark:bg-green-900/30 text-green-600' : 'bg-primary-100 dark:bg-primary-900/30 text-primary-600'}`}>
                            {mfaStatus?.enabled ? <ShieldCheckIcon size={24} /> : <ShieldAlertIcon size={24} />}
                        </div>
                        <div>
                            <h4 className="text-base font-bold text-gray-900 dark:text-white">Multi-Factor Authentication (TOTP)</h4>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                {mfaStatus?.enabled 
                                    ? `Enabled since ${new Date(mfaStatus.enrolled_at!).toLocaleDateString()}` 
                                    : 'Add an extra layer of security to your account using an authenticator app.'}
                            </p>
                        </div>
                    </div>
                    {!mfaStatus?.enabled && setupStep === 'idle' && (
                        <button onClick={handleStartSetup} className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-semibold hover:bg-primary-700 transition-colors shadow-sm">
                            Setup Authenticator
                        </button>
                    )}
                    {mfaStatus?.enabled && (
                        <button onClick={handleDisableMfa} className="px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50 rounded-lg text-sm font-semibold hover:bg-red-100 transition-colors">
                            Disable MFA
                        </button>
                    )}
                </div>

                <div className="p-6 bg-gray-50/50 dark:bg-gray-800/50">
                    {setupStep === 'enrolling' && setupData && (
                        <div className="max-w-md mx-auto space-y-6 text-center animate-in zoom-in-95">
                            <h5 className="font-bold text-gray-900 dark:text-white">Enroll Authenticator App</h5>
                            <p className="text-xs text-gray-600 dark:text-gray-400">Scan this QR code with Google Authenticator, Authy, or Microsoft Authenticator.</p>
                            
                            <div className="bg-white p-4 rounded-xl inline-block border-4 border-white shadow-lg">
                                <img src={`data:image/png;base64,${setupData.qr_base64}`} alt="MFA QR Code" className="w-48 h-48" />
                            </div>

                            <div className="text-left bg-white dark:bg-gray-900 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                                <p className="text-[10px] uppercase font-bold text-gray-400 mb-1">Manual Secret</p>
                                <div className="flex items-center justify-between">
                                    <code className="text-sm font-mono text-primary-600 dark:text-primary-400 tracking-wider">{setupData.secret}</code>
                                    <button onClick={() => navigator.clipboard.writeText(setupData.secret)} className="text-gray-400 hover:text-primary-500"><CopyIcon size={14} /></button>
                                </div>
                            </div>

                            <div className="space-y-4">
                                <input 
                                    type="text" 
                                    placeholder="Enter 6-digit code" 
                                    maxLength={6}
                                    value={verificationCode}
                                    onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                                    className="w-full text-center text-2xl tracking-[1em] font-mono py-3 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 focus:border-primary-500 outline-none transition-all dark:text-white"
                                />
                                {error && <p className="text-xs text-red-500 flex items-center justify-center gap-1"><AlertTriangleIcon size={14} /> {error}</p>}
                                <div className="flex gap-3">
                                    <button onClick={() => setSetupStep('idle')} className="flex-1 py-2 text-sm text-gray-500 hover:text-gray-700 font-semibold">Cancel</button>
                                    <button onClick={handleVerifySetup} disabled={verificationCode.length !== 6} className="flex-grow py-2 bg-primary-600 text-white rounded-lg text-sm font-semibold hover:bg-primary-700 disabled:opacity-50">Verify & Activate</button>
                                </div>
                            </div>
                        </div>
                    )}

                    {setupStep === 'verifying' && backupCodes && (
                        <div className="max-w-md mx-auto space-y-6 animate-in zoom-in-95">
                            <div className="text-center">
                                <div className="inline-flex p-3 bg-green-100 dark:bg-green-900/30 text-green-600 rounded-full mb-4"><CheckIcon size={32} /></div>
                                <h5 className="font-bold text-gray-900 dark:text-white text-lg">MFA Activated!</h5>
                                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">Keep these backup codes in a safe place. Each code can be used once if you lose access to your authenticator app.</p>
                            </div>

                            <div className="grid grid-cols-2 gap-2 bg-white dark:bg-gray-900 p-4 rounded-xl border border-gray-200 dark:border-gray-700 font-mono text-sm text-gray-700 dark:text-gray-300">
                                {backupCodes.map((code, i) => <div key={i}>{code}</div>)}
                            </div>

                            <button onClick={() => setSetupStep('idle')} className="w-full py-3 bg-primary-600 text-white rounded-xl font-bold hover:bg-primary-700">I Have Saved These Codes</button>
                        </div>
                    )}

                    {setupStep === 'idle' && mfaStatus?.enabled && (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            <div className="bg-white dark:bg-gray-900 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                                <div className="flex items-center gap-3 text-primary-500 mb-2">
                                    <ShieldLockIcon size={18} />
                                    <span className="text-xs font-bold uppercase tracking-wider">Device Status</span>
                                </div>
                                <p className="text-sm font-semibold dark:text-white">Active Device</p>
                                <p className="text-[10px] text-gray-500">Authenticator Application</p>
                            </div>
                            <div className="bg-white dark:bg-gray-900 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                                <div className="flex items-center gap-3 text-amber-500 mb-2">
                                    <KeyIcon size={18} />
                                    <span className="text-xs font-bold uppercase tracking-wider">Recovery</span>
                                </div>
                                <p className="text-sm font-semibold dark:text-white">{mfaStatus.backup_codes_remaining} Codes Left</p>
                                <p className="text-[10px] text-gray-500">Unused backup recovery codes</p>
                            </div>
                        </div>
                    )}

                    {setupStep === 'idle' && !mfaStatus?.enabled && (
                        <div className="flex flex-col items-center justify-center py-8 text-center">
                            <SmartphoneIcon size={48} className="text-gray-300 mb-4" />
                            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">No multi-factor authentication device is currently enrolled. We highly recommend enabling MFA for all accounts.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* SSO Section */}
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-4">
                        <div className="p-3 rounded-xl bg-blue-100 dark:bg-blue-900/30 text-blue-600">
                            <GlobeIcon size={24} />
                        </div>
                        <div>
                            <h4 className="text-base font-bold text-gray-900 dark:text-white">Single Sign-On (SSO) Providers</h4>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Connect your corporate identity provider for seamless access.</p>
                        </div>
                    </div>
                </div>
                <div className="p-6 bg-gray-50/50 dark:bg-gray-800/50">
                    {ssoProviders.length > 0 ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {ssoProviders.map(provider => (
                                <div key={provider.id} className="flex items-center justify-between bg-white dark:bg-gray-900 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center font-bold text-primary-600">
                                            {provider.name[0]}
                                        </div>
                                        <div>
                                            <p className="text-sm font-bold dark:text-white">{provider.name}</p>
                                            <p className="text-[10px] text-green-500 flex items-center gap-1"><CheckIcon size={10} /> Active Integration</p>
                                        </div>
                                    </div>
                                    <span className="px-2 py-1 text-[10px] bg-gray-100 dark:bg-gray-800 text-gray-500 rounded uppercase font-bold tracking-tight">External</span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-8 text-center">
                            <GlobeIcon size={48} className="text-gray-300 mb-4" />
                            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">No external SSO providers are currently configured for your tenant.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
