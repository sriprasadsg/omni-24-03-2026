
import React, { useState, useEffect } from 'react';
import { X, CreditCard, Loader, Settings, CheckCircle } from 'lucide-react';
import * as api from '../services/apiService';

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
    onAddMethod,
    mode,
    planName,
    price
}) => {
    const [gateways, setGateways] = useState<ConfiguredGateway[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedGateway, setSelectedGateway] = useState<string | null>(null);
    const [confirming, setConfirming] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Mock Card Form State
    const [cardName, setCardName] = useState('');
    const [cardNumber, setCardNumber] = useState('');
    const [expiry, setExpiry] = useState('');
    const [cvc, setCvc] = useState('');

    useEffect(() => {
        if (isOpen) {
            fetchGateways();
        }
    }, [isOpen]);

    const fetchGateways = async () => {
        try {
            setLoading(true);
            const response = await api.authFetch('/api/payments/configured-gateways');
            const data = await response.json();
            if (data.success) {
                setGateways(data.gateways);
                if (data.gateways.length === 1) {
                    setSelectedGateway(data.gateways[0].gateway);
                }
            } else {
                setError("Failed to load payment methods.");
            }
        } catch (err) {
            console.error(err);
            setError("Network error loading payment methods.");
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
            // Modal should be closed by parent on success
        } catch (err: any) {
            setError(err.message || "Failed to process subscription.");
            setConfirming(false);
        }
    };

    const handleAddMethod = async (e: React.FormEvent) => {
        e.preventDefault();
        setConfirming(true);
        setError(null);

        // MOCK: Generate a fake payment method ID
        // In reality, we would use Stripe Elements to get a token
        const mockPaymentMethodId = `pm_mock_${Math.random().toString(36).substring(7)}`;

        try {
            await onAddMethod(mockPaymentMethodId);
            // Modal closed by parent
        } catch (err: any) {
            setError(err.message || "Failed to add payment method.");
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

                {mode === 'upgrade' && (
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
                ) : mode === 'add_method' ? (
                    <form onSubmit={handleAddMethod} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Cardholder Name
                            </label>
                            <input
                                type="text"
                                required
                                value={cardName}
                                onChange={e => setCardName(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                placeholder="John Doe"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Card Number
                            </label>
                            <div className="relative">
                                <CreditCard className="absolute left-3 top-2.5 w-5 h-5 text-gray-400" />
                                <input
                                    type="text"
                                    required
                                    value={cardNumber}
                                    onChange={e => setCardNumber(e.target.value.replace(/\D/g, '').substring(0, 16))}
                                    className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono"
                                    placeholder="0000 0000 0000 0000"
                                />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Expiry
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={expiry}
                                    onChange={e => {
                                        let v = e.target.value.replace(/\D/g, '').substring(0, 4);
                                        if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
                                        setExpiry(v);
                                    }}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono"
                                    placeholder="MM/YY"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    CVC
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={cvc}
                                    onChange={e => setCvc(e.target.value.replace(/\D/g, '').substring(0, 4))}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono"
                                    placeholder="123"
                                />
                            </div>
                        </div>

                        <div className="pt-4">
                            <button
                                type="submit"
                                disabled={confirming}
                                className="w-full flex items-center justify-center px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg font-medium transition-all"
                            >
                                {confirming ? <Loader className="w-5 h-5 animate-spin" /> : 'Add Card'}
                            </button>
                        </div>
                    </form>
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
                                        className={`w-full flex items-center justify-between p-3 rounded-lg border-2 transition-all ${selectedGateway === g.gateway
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
                            className="w-full flex items-center justify-center px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-all shadow-lg hover:shadow-xl"
                        >
                            {confirming ? (
                                <>
                                    <Loader className="w-5 h-5 animate-spin mr-2" />
                                    Processing...
                                </>
                            ) : (
                                `Confirm Upgrade`
                            )}
                        </button>
                    </>
                )}
            </div>
        </div>
    );
};

// Start of Import Helper Icon
import { AlertCircle } from 'lucide-react';
