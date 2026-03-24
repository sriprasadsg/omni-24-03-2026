import React from 'react';
import { ZapIcon, XCircleIcon, AlertTriangleIcon, ArrowRightIcon } from './icons';

interface UpgradeModalProps {
    isOpen: boolean;
    onClose: () => void;
    agentCount: number;
    agentLimit: number;
    subscriptionTier?: string;
}

export const UpgradeModal: React.FC<UpgradeModalProps> = ({
    isOpen,
    onClose,
    agentCount,
    agentLimit,
    subscriptionTier = 'Free',
}) => {
    if (!isOpen) return null;

    const usagePercent = Math.min((agentCount / agentLimit) * 100, 100);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal */}
            <div className="relative w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                {/* Top gradient accent */}
                <div className="h-1.5 bg-gradient-to-r from-amber-400 via-orange-500 to-red-500" />

                {/* Header */}
                <div className="flex items-start justify-between p-6 pb-4">
                    <div className="flex items-center">
                        <div className="p-3 rounded-xl bg-amber-100 dark:bg-amber-900/30 mr-4">
                            <AlertTriangleIcon className="text-amber-600 dark:text-amber-400" size={24} />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white">Agent Limit Reached</h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                                {subscriptionTier} plan · {agentCount}/{agentLimit} agents
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                        aria-label="Close"
                    >
                        <XCircleIcon size={20} />
                    </button>
                </div>

                {/* Usage Bar */}
                <div className="px-6 pb-4">
                    <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1.5">
                        <span>Agent Usage</span>
                        <span className="font-semibold text-amber-600 dark:text-amber-400">{agentCount} / {agentLimit}</span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                        <div
                            className="h-2 rounded-full bg-gradient-to-r from-amber-400 to-red-500 transition-all duration-500"
                            style={{ width: `${usagePercent}%` }}
                        />
                    </div>
                </div>

                {/* Body */}
                <div className="px-6 pb-6">
                    <p className="text-sm text-gray-600 dark:text-gray-300 mb-5">
                        Your <strong>{subscriptionTier}</strong> plan allows up to <strong>{agentLimit} agents</strong>.
                        You've reached this limit. Upgrade to a paid plan to add unlimited agents and unlock priority support.
                    </p>

                    {/* Plans comparison */}
                    <div className="grid grid-cols-2 gap-3 mb-6">
                        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center">
                            <p className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Professional</p>
                            <p className="text-2xl font-extrabold text-gray-900 dark:text-white">$49<span className="text-xs font-normal text-gray-500">/mo</span></p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Up to 50 agents</p>
                        </div>
                        <div className="rounded-xl border-2 border-primary-500 bg-primary-50 dark:bg-primary-900/20 p-3 text-center relative">
                            <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-primary-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">Popular</span>
                            <p className="text-xs font-bold text-primary-600 dark:text-primary-400 uppercase tracking-wider mb-1">Enterprise</p>
                            <p className="text-2xl font-extrabold text-gray-900 dark:text-white">$149<span className="text-xs font-normal text-gray-500">/mo</span></p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Unlimited agents</p>
                        </div>
                    </div>

                    {/* CTA Buttons */}
                    <div className="flex gap-3">
                        <button
                            onClick={onClose}
                            className="flex-1 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={() => {
                                onClose();
                                // Navigate to billing settings
                                window.location.hash = '#settings/billing';
                            }}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-primary-600 to-indigo-600 hover:from-primary-700 hover:to-indigo-700 rounded-xl transition-all duration-200 shadow-md hover:shadow-lg"
                        >
                            <ZapIcon size={16} />
                            Upgrade Plan
                            <ArrowRightIcon size={14} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
