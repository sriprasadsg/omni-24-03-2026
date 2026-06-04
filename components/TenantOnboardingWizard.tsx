import React, { useState } from 'react';
import { addTenant, addUser, generateApiKey } from '../services/apiService';
import { CheckIcon, CogIcon, XIcon, CopyIcon, ChevronRightIcon, UsersIcon, KeyIcon, ServerIcon, BuildingIcon } from './icons';

interface Props {
    isOpen: boolean;
    onClose: () => void;
    onComplete: (tenant: any) => void;
}

type Step = 'tenant' | 'user' | 'apikey' | 'done';

const STEPS: { id: Step; label: string; icon: React.ReactNode }[] = [
    { id: 'tenant', label: 'Organization', icon: <BuildingIcon size={16} /> },
    { id: 'user',   label: 'Admin User',   icon: <UsersIcon size={16} /> },
    { id: 'apikey', label: 'API Key',       icon: <KeyIcon size={16} /> },
    { id: 'done',   label: 'Done',          icon: <CheckIcon size={16} /> },
];

const TIERS = ['Free', 'Starter', 'Pro', 'Enterprise'] as const;

function StepIndicator({ current }: { current: Step }) {
    const idx = STEPS.findIndex(s => s.id === current);
    return (
        <div className="flex items-center mb-8">
            {STEPS.map((step, i) => {
                const past = i < idx;
                const active = i === idx;
                return (
                    <React.Fragment key={step.id}>
                        <div className={`flex items-center gap-2 text-xs font-medium ${active ? 'text-primary-600 dark:text-primary-400' : past ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                            <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 ${active ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400' : past ? 'border-green-500 bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400' : 'border-gray-300 dark:border-gray-600 text-gray-400'}`}>
                                {past ? <CheckIcon size={12} /> : i + 1}
                            </span>
                            <span className="hidden sm:inline">{step.label}</span>
                        </div>
                        {i < STEPS.length - 1 && <div className={`flex-1 h-0.5 mx-2 ${i < idx ? 'bg-green-400' : 'bg-gray-200 dark:bg-gray-700'}`} />}
                    </React.Fragment>
                );
            })}
        </div>
    );
}

export const TenantOnboardingWizard: React.FC<Props> = ({ isOpen, onClose, onComplete }) => {
    const [step, setStep] = useState<Step>('tenant');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [createdTenant, setCreatedTenant] = useState<any>(null);
    const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    // Step 1 form
    const [tenantName, setTenantName] = useState('');
    const [tier, setTier] = useState<string>('Starter');

    // Step 2 form
    const [adminName, setAdminName] = useState('');
    const [adminEmail, setAdminEmail] = useState('');

    const reset = () => {
        setStep('tenant'); setBusy(false); setError(null);
        setCreatedTenant(null); setCreatedApiKey(null);
        setTenantName(''); setTier('Starter');
        setAdminName(''); setAdminEmail('');
    };

    const handleClose = () => { reset(); onClose(); };

    const handleCreateTenant = async () => {
        if (!tenantName.trim()) { setError('Organization name is required'); return; }
        setBusy(true); setError(null);
        try {
            const tenant = await addTenant({ name: tenantName.trim(), subscriptionTier: tier });
            setCreatedTenant(tenant);
            setStep('user');
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to create organization');
        } finally { setBusy(false); }
    };

    const handleCreateUser = async () => {
        if (!adminName.trim() || !adminEmail.trim()) { setError('Name and email are required'); return; }
        setBusy(true); setError(null);
        try {
            await addUser({ name: adminName.trim(), email: adminEmail.trim(), role: 'Admin', tenantId: createdTenant?.id, tenantName: tenantName.trim() });
            setStep('apikey');
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to create user');
        } finally { setBusy(false); }
    };

    const handleSkipUser = () => { setError(null); setStep('apikey'); };

    const handleGenerateKey = async () => {
        setBusy(true); setError(null);
        try {
            const result = await generateApiKey(createdTenant?.id, `${tenantName}-agent-key`, 'wizard');
            setCreatedApiKey(result.key || result.api_key || result.value || JSON.stringify(result));
            setStep('done');
            onComplete(createdTenant);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to generate API key');
        } finally { setBusy(false); }
    };

    const handleSkipKey = () => { setError(null); setStep('done'); onComplete(createdTenant); };

    const copyKey = () => {
        if (!createdApiKey) return;
        navigator.clipboard.writeText(createdApiKey).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={handleClose}>
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="flex justify-between items-center p-6 border-b border-gray-200 dark:border-gray-700">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white">New Tenant Setup</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Guided onboarding for a new organization</p>
                    </div>
                    <button onClick={handleClose} className="p-1.5 rounded-full text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">
                        <XIcon size={18} />
                    </button>
                </div>

                <div className="p-6">
                    <StepIndicator current={step} />

                    {error && (
                        <div className="mb-4 px-4 py-2.5 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300">
                            {error}
                        </div>
                    )}

                    {/* ── Step 1: Tenant ── */}
                    {step === 'tenant' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Organization Name <span className="text-red-500">*</span></label>
                                <input type="text" value={tenantName} onChange={e => setTenantName(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && handleCreateTenant()}
                                    placeholder="Acme Corp" autoFocus
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Subscription Tier</label>
                                <div className="grid grid-cols-2 gap-2">
                                    {TIERS.map(t => (
                                        <button key={t} onClick={() => setTier(t)}
                                            className={`py-2 px-4 text-sm font-medium rounded-lg border transition-colors ${tier === t ? 'bg-primary-600 text-white border-primary-600' : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'}`}>
                                            {t}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <button onClick={handleCreateTenant} disabled={busy || !tenantName.trim()}
                                className="w-full flex items-center justify-center gap-2 py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50">
                                {busy ? <CogIcon size={16} className="animate-spin" /> : <ChevronRightIcon size={16} />}
                                Create Organization
                            </button>
                        </div>
                    )}

                    {/* ── Step 2: Admin User ── */}
                    {step === 'user' && (
                        <div className="space-y-4">
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Tenant <span className="font-semibold text-primary-600 dark:text-primary-400">{createdTenant?.name || tenantName}</span> created.
                                Add a first admin user (optional).
                            </p>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Full Name</label>
                                <input type="text" value={adminName} onChange={e => setAdminName(e.target.value)}
                                    placeholder="Jane Doe" autoFocus
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500 outline-none" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Email</label>
                                <input type="email" value={adminEmail} onChange={e => setAdminEmail(e.target.value)}
                                    placeholder="admin@acmecorp.com"
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-primary-500 outline-none" />
                            </div>
                            <div className="flex gap-3">
                                <button onClick={handleSkipUser} className="flex-1 py-2.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700">
                                    Skip for now
                                </button>
                                <button onClick={handleCreateUser} disabled={busy || !adminName.trim() || !adminEmail.trim()}
                                    className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 text-sm">
                                    {busy ? <CogIcon size={16} className="animate-spin" /> : <ChevronRightIcon size={16} />}
                                    Create User
                                </button>
                            </div>
                        </div>
                    )}

                    {/* ── Step 3: API Key ── */}
                    {step === 'apikey' && (
                        <div className="space-y-4">
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Generate an API key for the Omni-Agent to authenticate heartbeats from
                                <span className="font-semibold text-primary-600 dark:text-primary-400"> {createdTenant?.name || tenantName}</span>.
                            </p>
                            <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 text-sm space-y-1">
                                <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300"><ServerIcon size={15} className="text-primary-500" /><span>Agent authentication via bearer token</span></div>
                                <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300"><KeyIcon size={15} className="text-amber-500" /><span>Key shown once — save it securely</span></div>
                            </div>
                            <div className="flex gap-3">
                                <button onClick={handleSkipKey} className="flex-1 py-2.5 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-50 dark:hover:bg-gray-700">
                                    Skip
                                </button>
                                <button onClick={handleGenerateKey} disabled={busy}
                                    className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 text-sm">
                                    {busy ? <CogIcon size={16} className="animate-spin" /> : <KeyIcon size={16} />}
                                    Generate Key
                                </button>
                            </div>
                        </div>
                    )}

                    {/* ── Step 4: Done ── */}
                    {step === 'done' && (
                        <div className="space-y-4 text-center">
                            <div className="w-14 h-14 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto">
                                <CheckIcon size={28} className="text-green-600 dark:text-green-400" />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Setup Complete!</h3>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                    <span className="font-medium text-primary-600 dark:text-primary-400">{createdTenant?.name || tenantName}</span> is ready.
                                </p>
                            </div>
                            {createdApiKey && (
                                <div className="text-left p-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-1 font-medium uppercase tracking-wide">API Key (save this now)</p>
                                    <div className="flex items-center gap-2">
                                        <code className="flex-1 text-xs font-mono text-gray-800 dark:text-gray-200 break-all">{createdApiKey}</code>
                                        <button onClick={copyKey} className="flex-shrink-0 p-1.5 rounded text-gray-500 hover:text-primary-600 hover:bg-gray-100 dark:hover:bg-gray-600">
                                            {copied ? <CheckIcon size={14} className="text-green-500" /> : <CopyIcon size={14} />}
                                        </button>
                                    </div>
                                </div>
                            )}
                            <button onClick={handleClose}
                                className="w-full py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 text-sm">
                                Close
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
