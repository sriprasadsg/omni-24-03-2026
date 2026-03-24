import React, { useState, useEffect } from 'react';
import { CreditCard, Check, AlertCircle, Loader } from 'lucide-react';
import * as api from '../services/apiService';

type PaymentGateway = 'stripe' | 'paypal' | 'razorpay' | 'square';

interface GatewayConfig {
    gateway: PaymentGateway;
    credentials: Record<string, string>;
}

export default function PaymentSettings() {
    const [selectedGateway, setSelectedGateway] = useState<PaymentGateway>('stripe');
    const [credentials, setCredentials] = useState<Record<string, string>>({});
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState('');

    const gatewayFields: Record<PaymentGateway, { label: string; key: string; placeholder: string }[]> = {
        stripe: [
            { label: 'Publishable Key', key: 'publishable_key', placeholder: 'pk_...' },
            { label: 'Secret Key', key: 'secret_key', placeholder: 'sk_...' },
            { label: 'Webhook Secret', key: 'webhook_secret', placeholder: 'whsec_...' }
        ],
        paypal: [
            { label: 'Client ID', key: 'client_id', placeholder: 'AY...' },
            { label: 'Client Secret', key: 'client_secret', placeholder: 'EL...' }
        ],
        razorpay: [
            { label: 'Key ID', key: 'key_id', placeholder: 'rzp_...' },
            { label: 'Key Secret', key: 'key_secret', placeholder: '...' }
        ],
        square: [
            { label: 'Access Token', key: 'access_token', placeholder: 'sq0atp-...' },
            { label: 'Location ID', key: 'location_id', placeholder: 'L...' }
        ]
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        setSuccess(false);

        try {
            const response = await api.authFetch('/api/payments/setup', {
                method: 'POST',
                body: JSON.stringify({
                    gateway: selectedGateway,
                    credentials
                })
            });

            if (!response.ok) {
                throw new Error('Failed to configure payment gateway');
            }

            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
        } catch (err: any) {
            setError(err.message || 'An error occurred');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6">
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Payment Settings</h1>
                <p className="text-gray-600 dark:text-gray-400 mt-1">
                    Configure your payment gateway to enable subscriptions and billing
                </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
                <form onSubmit={handleSubmit}>
                    {/* Gateway Selection */}
                    <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                            Select Payment Gateway
                        </label>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {(['stripe', 'paypal', 'razorpay', 'square'] as PaymentGateway[]).map((gateway) => (
                                <button
                                    key={gateway}
                                    type="button"
                                    onClick={() => {
                                        setSelectedGateway(gateway);
                                        setCredentials({});
                                    }}
                                    className={`p-4 border-2 rounded-lg transition-all ${selectedGateway === gateway
                                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                                        }`}
                                >
                                    <CreditCard className="w-6 h-6 mx-auto mb-2" />
                                    <div className="text-sm font-medium capitalize">{gateway}</div>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Credentials Form */}
                    <div className="space-y-4 mb-6">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white capitalize">
                            {selectedGateway} Credentials
                        </h3>
                        {gatewayFields[selectedGateway].map((field) => (
                            <div key={field.key}>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    {field.label}
                                </label>
                                <input
                                    type="password"
                                    value={credentials[field.key] || ''}
                                    onChange={(e) => setCredentials({ ...credentials, [field.key]: e.target.value })}
                                    placeholder={field.placeholder}
                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                                    required
                                />
                            </div>
                        ))}
                    </div>

                    {/* Status Messages */}
                    {success && (
                        <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg flex items-center gap-2 text-green-800 dark:text-green-200">
                            <Check className="w-5 h-5" />
                            <span>Payment gateway configured successfully!</span>
                        </div>
                    )}

                    {error && (
                        <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2 text-red-800 dark:text-red-200">
                            <AlertCircle className="w-5 h-5" />
                            <span>{error}</span>
                        </div>
                    )}

                    {/* Submit Button */}
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full md:w-auto px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                    >
                        {loading && <Loader className="w-4 h-4 animate-spin" />}
                        {loading ? 'Saving...' : 'Save Configuration'}
                    </button>
                </form>

                {/* Info Box */}
                <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                    <h4 className="font-semibold text-blue-900 dark:text-blue-200 mb-2">Security Note</h4>
                    <p className="text-sm text-blue-800 dark:text-blue-300">
                        Your payment credentials are encrypted and stored securely. We never store credit card information directly.
                        All payments are processed through your selected gateway's secure infrastructure.
                    </p>
                </div>
            </div>
        </div>
    );
}
