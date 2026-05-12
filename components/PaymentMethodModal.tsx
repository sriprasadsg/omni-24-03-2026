import React, { useState, useEffect } from 'react';
import { X, CreditCard, Loader, CheckCircle, AlertCircle } from 'lucide-react';
import * as api from '../services/apiService';
import { API_BASE } from '../services/apiService';

interface PaymentMethodModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (gateway: string) => Promise<void>;
    onAddMethod: (paymentMethodId: string) => Promise<void>;
    mode: 'upgrade' | 'add_method';
    planName: string;
    price: number | null;
}

interface ConfiguredGateway {
    gateway: string;
    createdAt: string;
}

export const PaymentMethodModal: React.FC<PaymentMethodModalProps> = ({
    isOpen,
    onClose,
    onConfirm,
    mode,
    planName,
    price
}) => {
    const [gateways, setGateways] = useState<ConfiguredGateway[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedGateway, setSelectedGateway] = useState<string | null>(null);
    const [confirming, setConfirming] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [stripeConfigured, setStripeConfigured] = useState(false);

    useEffect(() => {
        if (isOpen) {
            fetchGateways();
            fetchStripeConfig();
        }
    }, [isOpen]);

    const fetchStripeConfig = async () => {
        try {
            const res = await api.authFetch(`${API_BASE}/billing/stripe-config`);
            if (res.ok) {
                const data = await res.json();
                setStripeConfigured(data.configured === true);
            }
        } catch (_) {}
    };

    const fetchGateways = async () => {
        try {
            setLoading(true);
            const response = await api.authFetch('/api/payments/configured-gateways');
            const data = await response.json();
            if (data.success) {
                setGateways(data.gateways);
                if (data.gateways.length === 1) setSelectedGateway(data.gateways[0].gateway);
            } else {
                setError('Failed to load payment methods.');
            }
        } catch (err) {
            console.error(err);
            setError('Network error loading payment methods.');
        } finally {
            setLoading(false);
        }
    };

    const handleConfirm = async () => {
        if (!selectedGateway) return;
        setConfirming(true);
        setError(null);
        try {
            await onConfirm(selectedGateway);
        } catch (err: any) {
            setError(err.message || 'Failed to process subscription.');
            setConfirming(false);
        }
    };

    const handleAddMethod = async (e: React.FormEvent) => {
        e.preventDefault();
        setConfirming(true);
        setError(null);
        try {
            if (!stripeConfigured) {
                throw new Error('Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY in the backend .env file.');
            }
            // Redirect to Stripe Checkout hosted page for secure card tokenisation
            const res = await api.authFetch(`${API_BASE}/billing/stripe/checkout`, {
                method: 'POST',
                body: JSON.stringify({ price_id: 'setup' }),
            });
            if (!res.ok) throw new Error('Failed to create Stripe checkout session.');
            const data = await res.json();
            if (data.checkout_url) {
                window.location.href = data.checkout_url;
                return;
            }
            throw new Error('No checkout URL returned from server.');
        } catch (err: any) {
            setError(err.message || 'Failed to add payment method.');
            setConfirming(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6 relative">
                <button
                    onClick={onClose}
                    disabled={confirming}
                    className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                    <X className="w-5 h-5" />
                </button>

                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                    {mode === 'add_method' ? 'Add Payment Method' : `Upgrade to ${planName}`}
                </h2>

                {mode === 'upgrade' && price != null && (
                    <div className="mb-6 text-gray-600 dark:text-gray-400">
                        <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                            ${price}/mo
                        </span>
                    </div>
                )}

                {loading ? (
                    <div className="flex justify-center py-8">
                        <Loader className="w-8 h-8 animate-spin text-blue-600" />
                    </div>
                ) : error ? (
                    <div className="bg-red-50 dark:bg-red-900/20 p-4 rounded-lg text-red-700 dark:text-red-300 mb-4">
                        {error}
                    </div>
                ) : mode === 'add_method' ? (
                    <form onSubmit={handleAddMethod} className="space-y-4">
                        {stripeConfigured ? (
                            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 text-sm text-blue-700 dark:text-blue-300">
                                You will be redirected to Stripe's secure checkout to add your card details.
                            </div>
                        ) : (
                            <div className="flex items-start gap-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
                                <AlertCircle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                                <div className="text-sm text-yellow-700 dark:text-yellow-300">
                                    <p className="font-semibold mb-1">Stripe not configured</p>
                                    <p>Set <code className="bg-yellow-100 dark:bg-yellow-900 px-1 rounded">STRIPE_SECRET_KEY</code> and <code className="bg-yellow-100 dark:bg-yellow-900 px-1 rounded">STRIPE_PUBLISHABLE_KEY</code> in the backend <code className="bg-yellow-100 dark:bg-yellow-900 px-1 rounded">.env</code> file to enable payments.</p>
                                </div>
                            </div>
                        )}
                        <button
                            type="submit"
                            disabled={confirming || !stripeConfigured}
                            className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-all"
                        >
                            {confirming ? <Loader className="w-5 h-5 animate-spin" /> : <CreditCard className="w-5 h-5" />}
                            {confirming ? 'Redirecting…' : 'Continue to Stripe'}
                        </button>
                    </form>
                ) : gateways.length === 0 ? (
                    <div className="text-center py-6">
                        <AlertCircle className="w-12 h-12 text-yellow-500 mx-auto mb-3" />
                        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                            No Payment Configuration Found
                        </h3>
                        <p className="text-gray-500 dark:text-gray-400 mb-4 text-sm">
                            Please configure a payment gateway in settings first.
                        </p>
                    </div>
                ) : (
                    <>
                        <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Select Payment Method
                            </label>
                            <div className="space-y-2">
                                {gateways.map((g) => (
                                    <button
                                        key={g.gateway}
                                        onClick={() => setSelectedGateway(g.gateway)}
                                        className={`w-full flex items-center justify-between p-3 rounded-lg border-2 transition-all ${
                                            selectedGateway === g.gateway
                                                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                                                : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                                        }`}
                                    >
                                        <div className="flex items-center">
                                            <CreditCard className="w-5 h-5 text-gray-500 mr-3" />
                                            <span className="font-medium capitalize text-gray-900 dark:text-white">
                                                {g.gateway}
                                            </span>
                                        </div>
                                        {selectedGateway === g.gateway && (
                                            <CheckCircle className="w-5 h-5 text-blue-600" />
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <button
                            onClick={handleConfirm}
                            disabled={!selectedGateway || confirming}
                            className="w-full flex items-center justify-center px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-all"
                        >
                            {confirming ? (
                                <><Loader className="w-5 h-5 animate-spin mr-2" />Processing…</>
                            ) : (
                                'Confirm Upgrade'
                            )}
                        </button>
                    </>
                )}
            </div>
        </div>
    );
};
