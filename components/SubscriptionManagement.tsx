
import React, { useState, useEffect } from 'react';
import { TrendingUp, AlertTriangle, Check, X, Loader, CreditCard, ShieldCheck, Settings } from 'lucide-react';
import * as api from '../services/apiService';
import { PaymentMethodModal } from './PaymentMethodModal';
import { showToast } from '../utils/toast';

interface SubscriptionInfo {
    subscriptionTier: string;
    subscription: any;
    limits: {
        within_limits: boolean;
        warnings: any[];
        usage: Record<string, number>;
        limits: Record<string, number>;
    };
}

const PLAN_DETAILS = {
    Free: {
        price: 0,
        features: ['10 GB Data Ingestion', '100K API Calls', '1 vCPU Hour AI Compute', 'Community Support']
    },
    Pro: {
        price: 99,
        features: ['100 GB Data Ingestion', '1M API Calls', '10 vCPU Hours AI Compute', 'Email Support', 'Advanced Analytics']
    },
    Enterprise: {
        price: 499,
        features: ['1 TB Data Ingestion', '10M API Calls', '100 vCPU Hours AI Compute', '24/7 Priority Support', 'Custom Integrations', 'SLA Guarantee']
    },
    Custom: {
        price: null,
        features: ['Unlimited Resources', 'Dedicated Support', 'Custom SLA', 'On-Premise Deployment Options']
    }
};

interface PaymentMethod {
    id: string;
    brand: string;
    last4: string;
    exp_month: number;
    exp_year: number;
    created: number;
}

export default function SubscriptionManagement() {
    const [subscriptionInfo, setSubscriptionInfo] = useState<SubscriptionInfo | null>(null);
    const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
    const [configuredGateways, setConfiguredGateways] = useState<{ gateway: string; gatewayName: string; isActive: boolean }[]>([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState(false);

    // Payment Modal State
    const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
    const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
    const [modalMode, setModalMode] = useState<'upgrade' | 'add_method'>('upgrade');

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        await Promise.all([loadSubscriptionInfo(), loadPaymentMethods(), loadConfiguredGateways()]);
        setLoading(false);
    };

    const loadConfiguredGateways = async () => {
        try {
            const res = await api.authFetch('/api/payments/configured-gateways');
            if (res.ok) {
                const data = await res.json();
                setConfiguredGateways(data.gateways || []);
            }
        } catch { /* silent */ }
    };

    const loadSubscriptionInfo = async () => {
        try {
            const response = await api.authFetch('/api/payments/subscription-info');
            const data = await response.json();
            if (data.success) {
                setSubscriptionInfo(data);
            }
        } catch (error) {
            console.error('Failed to load subscription info:', error);
        }
    };

    const loadPaymentMethods = async () => {
        try {
            const response = await api.authFetch('/api/payments/methods');
            const data = await response.json();
            if (data.success && data.methods) {
                setPaymentMethods(data.methods);
            }
        } catch (error) {
            console.error('Failed to load payment methods:', error);
        }
    };

    const handleUpgradeClick = (plan: string) => {
        if (plan === 'Custom') {
            window.location.href = 'mailto:sales@omni.ai?subject=Enterprise%20Custom%20Plan';
            return;
        }
        setSelectedPlan(plan);
        setModalMode('upgrade');
        setIsPaymentModalOpen(true);
    };

    const handleAddPaymentMethod = () => {
        setSelectedPlan(null);
        setModalMode('add_method');
        setIsPaymentModalOpen(true);
    };

    const handleDeletePaymentMethod = async (methodId: string) => {
        if (!confirm('Are you sure you want to remove this payment method?')) return;

        try {
            const response = await api.authFetch(`/api/payments/methods/${methodId}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            if (data.success) {
                loadPaymentMethods();
            }
        } catch (error) {
            console.error('Failed to delete payment method:', error);
        }
    };

    const processUpgrade = async (gateway: string, paymentMethodId?: string) => {
        if (!selectedPlan) return;

        // Map plan to price ID (in a real app these would come from config/backend)
        const priceIds: Record<string, string> = {
            'Pro': 'price_pro_monthly',
            'Enterprise': 'price_enterprise_monthly'
        };

        try {
            const response = await api.authFetch('/api/payments/subscribe', {
                method: 'POST',
                body: JSON.stringify({
                    plan: selectedPlan,
                    price_id: priceIds[selectedPlan] || 'price_unknown'
                })
            });
            const data = await response.json();

            if (data.success) {
                showToast(`Successfully upgraded to ${selectedPlan}!`, 'success');
                setIsPaymentModalOpen(false);
                loadSubscriptionInfo(); // Refresh state
            } else {
                throw new Error(data.detail || 'Upgrade failed');
            }
        } catch (error: any) {
            console.error('Upgrade failed:', error);
            throw error; // Let modal handle display
        }
    };

    const processAddMethod = async (paymentMethodId: string) => {
        try {
            const response = await api.authFetch('/api/payments/methods', {
                method: 'POST',
                body: JSON.stringify({
                    payment_method_id: paymentMethodId
                })
            });
            const data = await response.json();

            if (data.success) {
                showToast('Payment method added successfully!', 'success');
                setIsPaymentModalOpen(false);
                loadPaymentMethods();
            } else {
                throw new Error(data.detail || 'Failed to add payment method');
            }
        } catch (error: any) {
            console.error('Add method failed:', error);
            throw error;
        }
    };

    const handleCancelSubscription = async () => {
        if (!confirm('Are you sure you want to cancel your subscription?')) return;

        setActionLoading(true);
        try {
            const response = await api.authFetch('/api/payments/cancel-subscription', {
                method: 'POST'
            });
            const data = await response.json();
            if (data.success) {
                showToast('Subscription canceled successfully', 'info');
                loadSubscriptionInfo();
            }
        } catch (error) {
            console.error('Cancellation failed:', error);
        } finally {
            setActionLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader className="w-8 h-8 animate-spin text-blue-600" />
            </div>
        );
    }

    const currentTier = subscriptionInfo?.subscriptionTier || 'Free';

    return (
        <div className="p-6">
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Subscription & Billing</h1>
                <p className="text-gray-600 dark:text-gray-400 mt-1">
                    Manage your subscription plan and view usage
                </p>
            </div>

            {/* Current Plan */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 mb-6">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Current Plan</h2>
                <div className="flex items-center justify-between">
                    <div>
                        <div className="text-3xl font-bold text-blue-600">{currentTier}</div>
                        {PLAN_DETAILS[currentTier as keyof typeof PLAN_DETAILS]?.price !== null && (
                            <div className="text-gray-600 dark:text-gray-400 mt-1">
                                ${PLAN_DETAILS[currentTier as keyof typeof PLAN_DETAILS]?.price}/month
                            </div>
                        )}
                    </div>
                    {currentTier !== 'Free' && (
                        <button
                            onClick={handleCancelSubscription}
                            disabled={actionLoading}
                            className="px-4 py-2 border border-red-600 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        >
                            Cancel Subscription
                        </button>
                    )}
                </div>
            </div>

            {/* Payment Methods */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 mb-6">
                <div className="flex justify-between items-center mb-4">
                    <div>
                        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Payment Methods</h2>
                        {configuredGateways.length > 0 && (
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex items-center gap-1">
                                <ShieldCheck className="w-3 h-3 text-green-500" />
                                Active gateway:&nbsp;
                                <span className="font-medium text-gray-700 dark:text-gray-300">
                                    {configuredGateways.find(g => g.isActive)?.gatewayName
                                        || configuredGateways[0]?.gatewayName
                                        || configuredGateways[0]?.gateway}
                                </span>
                            </p>
                        )}
                    </div>
                    <button
                        onClick={handleAddPaymentMethod}
                        disabled={configuredGateways.length === 0}
                        title={configuredGateways.length === 0 ? 'Configure a payment gateway first' : 'Add a payment method'}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
                    >
                        <CreditCard className="w-4 h-4" />
                        Add Method
                    </button>
                </div>

                {/* No gateway configured */}
                {configuredGateways.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 px-4 text-center border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
                        <Settings className="w-10 h-10 text-gray-300 dark:text-gray-600 mb-3" />
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">No payment gateway configured</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                            Set up a payment gateway in Payment Settings before adding card details.
                        </p>
                        <a href="#payment-settings"
                            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors">
                            <Settings className="w-3.5 h-3.5" /> Go to Payment Settings
                        </a>
                    </div>
                ) : paymentMethods.length === 0 ? (
                    /* Gateway configured but no saved cards yet */
                    <div className="flex flex-col items-center justify-center py-10 px-4 text-center border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
                        <CreditCard className="w-10 h-10 text-gray-300 dark:text-gray-600 mb-3" />
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">No payment methods saved</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                            Add a card or bank account to enable automatic billing and plan upgrades.
                        </p>
                        <button onClick={handleAddPaymentMethod}
                            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors">
                            <CreditCard className="w-3.5 h-3.5" /> Add Payment Method
                        </button>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {paymentMethods.map(method => (
                            <div key={method.id} className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg">
                                <div className="flex items-center gap-3">
                                    <div className="w-12 h-8 bg-gray-100 dark:bg-gray-700 rounded-md flex items-center justify-center text-xs font-bold text-gray-600 dark:text-gray-300 uppercase border border-gray-200 dark:border-gray-600">
                                        {method.brand}
                                    </div>
                                    <div>
                                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                                            •••• •••• •••• {method.last4}
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400">
                                            Expires {String(method.exp_month).padStart(2, '0')}/{method.exp_year}
                                        </div>
                                    </div>
                                </div>
                                <button
                                    onClick={() => handleDeletePaymentMethod(method.id)}
                                    className="p-2 text-gray-400 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                                    title="Remove payment method"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Usage & Limits */}
            {subscriptionInfo?.limits && (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 mb-6">
                    <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Usage & Limits</h2>

                    {subscriptionInfo.limits.warnings.length > 0 && (
                        <div className="mb-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                            <div className="flex items-center gap-2 text-yellow-800 dark:text-yellow-200 mb-2">
                                <AlertTriangle className="w-5 h-5" />
                                <span className="font-semibold">Usage Warnings</span>
                            </div>
                            {subscriptionInfo.limits.warnings.map((warning, idx) => (
                                <div key={idx} className="text-sm text-yellow-700 dark:text-yellow-300">
                                    {warning.message}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="space-y-6">
                        {Object.entries(subscriptionInfo.limits.usage).map(([metric, usage]) => {
                            const limit = subscriptionInfo.limits.limits[metric];
                            const usageNum = Number(usage);
                            const limitNum = Number(limit);
                            const percent = limitNum === Infinity ? 0 : (usageNum / limitNum) * 100;
                            const isWarning = percent >= 90;

                            return (
                                <div key={metric} className="group">
                                    <div className="grid grid-cols-2 gap-4 mb-2 items-end">
                                        <div className="flex flex-col">
                                            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 capitalize">
                                                {metric.replace(/_/g, ' ')}
                                            </span>
                                        </div>
                                        <div className="text-right">
                                            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                                {usageNum.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                                            </span>
                                            <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                                                / {limitNum === Infinity ? '∞' : limitNum.toLocaleString()}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-3 overflow-hidden border border-gray-200 dark:border-gray-600">
                                        <div
                                            className={`h-full rounded-full transition-all duration-500 ease-out ${isWarning ? 'bg-amber-500' : 'bg-blue-600'
                                                } shadow-sm relative`}
                                            style={{ width: `${Math.min(percent, 100)}%` }}
                                        >
                                            <div className="absolute inset-0 bg-white/20 w-full h-full animate-[shimmer_2s_infinite] origin-top-left skew-x-12"></div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}


            {/* Available Plans */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Available Plans</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {Object.entries(PLAN_DETAILS).map(([plan, details]) => (
                        <div
                            key={plan}
                            className={`p-4 border-2 rounded-lg ${currentTier === plan
                                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                                : 'border-gray-200 dark:border-gray-700'
                                }`}
                        >
                            <div className="text-lg font-semibold text-gray-900 dark:text-white mb-2">{plan}</div>
                            <div className="text-2xl font-bold text-blue-600 mb-4">
                                {details.price === null ? 'Contact Us' : details.price === 0 ? 'Free' : `$${details.price}/mo`}
                            </div>
                            <ul className="space-y-2 mb-4">
                                {details.features.map((feature, idx) => (
                                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
                                        <Check className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                                        <span>{feature}</span>
                                    </li>
                                ))}
                            </ul>
                            {currentTier !== plan && (
                                <button
                                    onClick={() => handleUpgradeClick(plan)}
                                    disabled={actionLoading}
                                    className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg transition-colors"
                                >
                                    {plan === 'Custom' ? 'Contact Sales' : 'Upgrade'}
                                </button>
                            )}
                            {currentTier === plan && (
                                <div className="w-full px-4 py-2 bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-200 rounded-lg text-center font-medium">
                                    Current Plan
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            <PaymentMethodModal
                isOpen={isPaymentModalOpen}
                onClose={() => setIsPaymentModalOpen(false)}
                onConfirm={processUpgrade}
                onAddMethod={processAddMethod}
                mode={modalMode}
                planName={selectedPlan || ''}
                price={selectedPlan ? PLAN_DETAILS[selectedPlan as keyof typeof PLAN_DETAILS]?.price : 0}
            />
        </div>
    );
}
