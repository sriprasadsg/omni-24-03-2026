import React, { useState, useEffect, useCallback } from 'react';
import { CreditCard, Check, AlertCircle, Loader, Plus, Trash2, Star, X, Settings, PlusCircle, MinusCircle } from 'lucide-react';
import * as api from '../services/apiService';

type BuiltinGateway = 'stripe' | 'paypal' | 'razorpay' | 'square';
type PaymentGateway = BuiltinGateway | 'custom';

interface ConfiguredGateway {
    gateway: PaymentGateway;
    gatewayName: string;
    isActive: boolean;
    isCustom: boolean;
    webhookUrl?: string;
    createdAt: string;
    createdBy?: string;
}

interface CredentialPair { key: string; value: string }

const BUILTIN_META: Record<BuiltinGateway, { label: string; color: string; description: string }> = {
    stripe:   { label: 'Stripe',   color: 'indigo', description: 'Cards, Apple Pay, Google Pay & more' },
    paypal:   { label: 'PayPal',   color: 'blue',   description: 'PayPal balance, cards & BNPL' },
    razorpay: { label: 'Razorpay', color: 'violet', description: 'UPI, cards, netbanking (India)' },
    square:   { label: 'Square',   color: 'gray',   description: 'POS, cards & online payments' },
};

const BUILTIN_FIELDS: Record<BuiltinGateway, { label: string; key: string; placeholder: string }[]> = {
    stripe: [
        { label: 'Publishable Key', key: 'publishable_key', placeholder: 'pk_live_...' },
        { label: 'Secret Key',      key: 'secret_key',      placeholder: 'sk_live_...' },
        { label: 'Webhook Secret',  key: 'webhook_secret',  placeholder: 'whsec_...' },
    ],
    paypal: [
        { label: 'Client ID',     key: 'client_id',     placeholder: 'AY...' },
        { label: 'Client Secret', key: 'client_secret', placeholder: 'EL...' },
    ],
    razorpay: [
        { label: 'Key ID',     key: 'key_id',     placeholder: 'rzp_live_...' },
        { label: 'Key Secret', key: 'key_secret', placeholder: '...' },
    ],
    square: [
        { label: 'Access Token', key: 'access_token', placeholder: 'sq0atp-...' },
        { label: 'Location ID',  key: 'location_id',  placeholder: 'L...' },
    ],
};

const colorMap: Record<string, string> = {
    indigo: 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300',
    blue:   'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300',
    violet: 'bg-violet-50 dark:bg-violet-900/20 border-violet-200 dark:border-violet-700 text-violet-700 dark:text-violet-300',
    gray:   'bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300',
    orange: 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-700 text-orange-700 dark:text-orange-300',
};

// ── Add Gateway Modal ─────────────────────────────────────────────────────────

interface AddGatewayModalProps {
    existingTypes: PaymentGateway[];
    onClose: () => void;
    onSaved: () => void;
}

function AddGatewayModal({ existingTypes, onClose, onSaved }: AddGatewayModalProps) {
    const availableBuiltin = (Object.keys(BUILTIN_META) as BuiltinGateway[]).filter(g => !existingTypes.includes(g));
    // custom can always be added (multiple custom gateways are stored under 'custom' key — but we allow only one; if already present, hide it)
    const canAddCustom = !existingTypes.includes('custom');

    type Tab = BuiltinGateway | 'custom';
    const defaultTab: Tab = availableBuiltin.length > 0 ? availableBuiltin[0] : (canAddCustom ? 'custom' : 'stripe');
    const [selected, setSelected] = useState<Tab>(defaultTab);

    // Builtin credential state
    const [credentials, setCredentials] = useState<Record<string, string>>({});

    // Custom gateway state
    const [customName, setCustomName] = useState('');
    const [webhookUrl, setWebhookUrl] = useState('');
    const [pairs, setPairs] = useState<CredentialPair[]>([{ key: '', value: '' }]);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const addPair = () => setPairs(p => [...p, { key: '', value: '' }]);
    const removePair = (i: number) => setPairs(p => p.filter((_, idx) => idx !== i));
    const updatePair = (i: number, field: 'key' | 'value', val: string) =>
        setPairs(p => p.map((pair, idx) => idx === i ? { ...pair, [field]: val } : pair));

    const handleSave = async (e: React.SyntheticEvent) => {
        e.preventDefault();
        if (selected === 'custom' && !customName.trim()) {
            setError('Please enter a gateway name.');
            return;
        }
        setLoading(true);
        setError('');
        try {
            let creds: Record<string, string>;
            let body: Record<string, unknown>;

            if (selected === 'custom') {
                const validPairs = pairs.filter(p => p.key.trim());
                if (validPairs.length === 0) { setError('Add at least one credential field.'); setLoading(false); return; }
                creds = Object.fromEntries(validPairs.map(p => [p.key.trim(), p.value]));
                body = { gateway: 'custom', gateway_name: customName.trim(), webhook_url: webhookUrl.trim() || undefined, credentials: creds };
            } else {
                creds = credentials;
                body = { gateway: selected, credentials: creds };
            }

            const res = await api.authFetch('/api/payments/setup', {
                method: 'POST',
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const d = await res.json().catch(() => ({}));
                throw new Error(d.detail || 'Failed to configure gateway');
            }
            onSaved();
        } catch (err: any) {
            setError(err.message || 'An error occurred');
        } finally {
            setLoading(false);
        }
    };

    if (availableBuiltin.length === 0 && !canAddCustom) {
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-md">
                    <p className="text-gray-700 dark:text-gray-300">All supported gateways are already configured.</p>
                    <button onClick={onClose} className="mt-4 px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg text-sm">Close</button>
                </div>
            </div>
        );
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Add Payment Gateway</h2>
                    <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500">
                        <X size={18} />
                    </button>
                </div>

                <form onSubmit={handleSave} className="p-5 space-y-5 overflow-y-auto flex-1">
                    {/* Gateway type tabs */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Gateway Type</label>
                        <div className="grid grid-cols-2 gap-2.5">
                            {availableBuiltin.map(gw => (
                                <button key={gw} type="button"
                                    onClick={() => { setSelected(gw); setCredentials({}); setError(''); }}
                                    className={`p-3 border-2 rounded-lg text-left transition-all ${
                                        selected === gw
                                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                                    }`}>
                                    <div className="font-semibold text-sm text-gray-900 dark:text-white">{BUILTIN_META[gw].label}</div>
                                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{BUILTIN_META[gw].description}</div>
                                </button>
                            ))}
                            {canAddCustom && (
                                <button type="button"
                                    onClick={() => { setSelected('custom'); setError(''); }}
                                    className={`p-3 border-2 rounded-lg text-left transition-all ${
                                        selected === 'custom'
                                            ? 'border-orange-500 bg-orange-50 dark:bg-orange-900/20'
                                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                                    }`}>
                                    <div className="flex items-center gap-1.5 font-semibold text-sm text-gray-900 dark:text-white">
                                        <Settings size={13} className="text-orange-500" /> Custom / Other
                                    </div>
                                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Braintree, Adyen, Mollie, etc.</div>
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Builtin credential fields */}
                    {selected !== 'custom' && (
                        <div className="space-y-3">
                            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                                {BUILTIN_META[selected as BuiltinGateway].label} Credentials
                            </h3>
                            {BUILTIN_FIELDS[selected as BuiltinGateway].map(field => (
                                <div key={field.key}>
                                    <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{field.label}</label>
                                    <input type="password"
                                        value={credentials[field.key] || ''}
                                        onChange={e => setCredentials({ ...credentials, [field.key]: e.target.value })}
                                        placeholder={field.placeholder}
                                        required
                                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    />
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Custom gateway fields */}
                    {selected === 'custom' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                                    Gateway Name <span className="text-red-500">*</span>
                                </label>
                                <input type="text"
                                    value={customName}
                                    onChange={e => setCustomName(e.target.value)}
                                    placeholder="e.g. Braintree, Adyen, Mollie"
                                    required
                                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                                    Webhook URL <span className="text-gray-400 font-normal">(optional)</span>
                                </label>
                                <input type="url"
                                    value={webhookUrl}
                                    onChange={e => setWebhookUrl(e.target.value)}
                                    placeholder="https://yourdomain.com/webhooks/payment"
                                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                                />
                            </div>

                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
                                        API Credentials <span className="text-red-500">*</span>
                                    </label>
                                    <button type="button" onClick={addPair}
                                        className="flex items-center gap-1 text-xs text-orange-600 dark:text-orange-400 hover:underline">
                                        <PlusCircle size={13} /> Add field
                                    </button>
                                </div>
                                <div className="space-y-2">
                                    {pairs.map((pair, i) => (
                                        <div key={i} className="flex gap-2 items-center">
                                            <input type="text"
                                                value={pair.key}
                                                onChange={e => updatePair(i, 'key', e.target.value)}
                                                placeholder="Field name (e.g. api_key)"
                                                className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                                            />
                                            <input type="password"
                                                value={pair.value}
                                                onChange={e => updatePair(i, 'value', e.target.value)}
                                                placeholder="Value"
                                                className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                                            />
                                            <button type="button" onClick={() => removePair(i)}
                                                disabled={pairs.length === 1}
                                                className="text-gray-400 hover:text-red-500 disabled:opacity-30 flex-shrink-0">
                                                <MinusCircle size={17} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                                    All values are encrypted at rest. Add as many fields as your provider requires.
                                </p>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
                            <AlertCircle size={15} /> {error}
                        </div>
                    )}

                    <div className="flex justify-end gap-3 pt-1">
                        <button type="button" onClick={onClose}
                            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                            Cancel
                        </button>
                        <button type="submit" disabled={loading}
                            className={`px-5 py-2 text-sm disabled:bg-gray-400 text-white rounded-lg font-medium flex items-center gap-2 ${
                                selected === 'custom'
                                    ? 'bg-orange-500 hover:bg-orange-600'
                                    : 'bg-blue-600 hover:bg-blue-700'
                            }`}>
                            {loading && <Loader size={14} className="animate-spin" />}
                            {loading ? 'Saving…' : 'Add Gateway'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function PaymentSettings() {
    const [gateways, setGateways] = useState<ConfiguredGateway[]>([]);
    const [loadingGateways, setLoadingGateways] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 3500);
    };

    const loadGateways = useCallback(async () => {
        setLoadingGateways(true);
        try {
            const res = await api.authFetch('/api/payments/configured-gateways');
            if (res.ok) {
                const data = await res.json();
                setGateways(data.gateways || []);
            }
        } catch { /* silent */ } finally {
            setLoadingGateways(false);
        }
    }, []);

    useEffect(() => { loadGateways(); }, [loadGateways]);

    const handleActivate = async (gw: ConfiguredGateway) => {
        setActionLoading(`activate-${gw.gateway}`);
        try {
            const res = await api.authFetch(`/api/payments/gateways/${gw.gateway}/activate`, { method: 'POST' });
            if (!res.ok) throw new Error('Failed');
            showToast(`${gw.gatewayName} set as active gateway`);
            await loadGateways();
        } catch {
            showToast('Failed to activate gateway', false);
        } finally {
            setActionLoading(null);
        }
    };

    const handleDelete = async (gw: ConfiguredGateway) => {
        if (!confirm(`Remove ${gw.gatewayName} gateway? This cannot be undone.`)) return;
        setActionLoading(`delete-${gw.gateway}`);
        try {
            const res = await api.authFetch(`/api/payments/gateways/${gw.gateway}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('Failed');
            showToast(`${gw.gatewayName} removed`);
            await loadGateways();
        } catch {
            showToast('Failed to remove gateway', false);
        } finally {
            setActionLoading(null);
        }
    };

    const existingTypes = gateways.map(g => g.gateway);
    const canAddMore = existingTypes.length < 5; // 4 builtins + 1 custom slot

    return (
        <div className="p-6 max-w-3xl">
            {/* Toast */}
            {toast && (
                <div className={`fixed top-5 right-5 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-all ${toast.ok ? 'bg-green-600' : 'bg-red-600'}`}>
                    {toast.ok ? <Check size={15} /> : <AlertCircle size={15} />}
                    {toast.msg}
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <AddGatewayModal
                    existingTypes={existingTypes}
                    onClose={() => setShowModal(false)}
                    onSaved={() => { setShowModal(false); loadGateways(); showToast('Gateway added successfully'); }}
                />
            )}

            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Payment Settings</h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1 text-sm">
                        Manage payment gateways for subscriptions and billing
                    </p>
                </div>
                <button
                    onClick={() => setShowModal(true)}
                    disabled={!canAddMore}
                    title={!canAddMore ? 'All gateway slots are used' : undefined}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg font-medium text-sm transition-colors shadow-sm"
                >
                    <Plus size={16} />
                    Add Payment Gateway
                </button>
            </div>

            {/* Gateway list */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                {loadingGateways ? (
                    <div className="flex items-center justify-center gap-2 py-12 text-gray-500 dark:text-gray-400">
                        <Loader size={18} className="animate-spin" /> Loading gateways…
                    </div>
                ) : gateways.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
                        <div className="w-14 h-14 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
                            <CreditCard size={24} className="text-gray-400" />
                        </div>
                        <p className="text-gray-600 dark:text-gray-400 font-medium mb-1">No gateways configured</p>
                        <p className="text-sm text-gray-400 dark:text-gray-500 mb-5">
                            Add a payment gateway to enable subscriptions and billing.
                        </p>
                        <button onClick={() => setShowModal(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium">
                            <Plus size={15} /> Add Payment Gateway
                        </button>
                    </div>
                ) : (
                    <ul className="divide-y divide-gray-100 dark:divide-gray-700">
                        {gateways.map(gw => {
                            const isCustom = gw.isCustom || gw.gateway === 'custom';
                            const meta = !isCustom ? BUILTIN_META[gw.gateway as BuiltinGateway] : null;
                            const color = meta?.color ?? 'orange';
                            const displayName = gw.gatewayName || (meta?.label ?? gw.gateway);
                            const isActivating = actionLoading === `activate-${gw.gateway}`;
                            const isDeleting = actionLoading === `delete-${gw.gateway}`;

                            return (
                                <li key={gw.gateway} className="flex items-center gap-4 px-5 py-4">
                                    {/* Icon */}
                                    <div className={`w-10 h-10 rounded-lg border flex items-center justify-center flex-shrink-0 ${colorMap[color]}`}>
                                        {isCustom ? <Settings size={17} /> : <CreditCard size={18} />}
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-semibold text-gray-900 dark:text-white">{displayName}</span>
                                            {isCustom && (
                                                <span className="px-1.5 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-300 rounded text-xs font-medium">Custom</span>
                                            )}
                                            {gw.isActive && (
                                                <span className="flex items-center gap-1 px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full text-xs font-medium">
                                                    <Star size={10} fill="currentColor" /> Active
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
                                            {isCustom
                                                ? (gw.webhookUrl ? `Webhook: ${gw.webhookUrl}` : 'Custom integration — credentials stored securely')
                                                : meta?.description}
                                            {gw.createdAt && ` · Added ${new Date(gw.createdAt).toLocaleDateString()}`}
                                        </p>
                                    </div>

                                    {/* Actions */}
                                    <div className="flex items-center gap-2 flex-shrink-0">
                                        {!gw.isActive && (
                                            <button
                                                onClick={() => handleActivate(gw)}
                                                disabled={!!actionLoading}
                                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-blue-300 dark:border-blue-600 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-50"
                                            >
                                                {isActivating ? <Loader size={12} className="animate-spin" /> : <Star size={12} />}
                                                Set Active
                                            </button>
                                        )}
                                        <button
                                            onClick={() => handleDelete(gw)}
                                            disabled={!!actionLoading}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-red-200 dark:border-red-800 text-red-500 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
                                        >
                                            {isDeleting ? <Loader size={12} className="animate-spin" /> : <Trash2 size={12} />}
                                            Remove
                                        </button>
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>

            {/* Security note */}
            <div className="mt-5 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl">
                <h4 className="font-semibold text-blue-900 dark:text-blue-200 text-sm mb-1">Security Note</h4>
                <p className="text-xs text-blue-700 dark:text-blue-300">
                    All credentials are encrypted at rest. Only one gateway can be active at a time — it handles all new charges and subscriptions.
                    Custom gateways store credentials securely but require manual API integration for billing automation.
                </p>
            </div>
        </div>
    );
}
