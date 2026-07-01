

import React, { useState } from 'react';
import { CloudAccount, CSPMFinding, CloudProvider } from '../types';
import { CloudShieldIcon, AlertTriangleIcon, PlusCircleIcon } from './icons';
import { CSPMFindingsList } from './CSPMFindingsList';
import { CSPMRemediationModal } from './CSPMRemediationModal';
import { AddCloudAccountModal } from './AddCloudAccountModal';

interface CloudSecurityDashboardProps {
    cloudAccounts: CloudAccount[];
    findings: CSPMFinding[];
    onAddAccount: (accountData: Omit<CloudAccount, 'id' | 'tenantId' | 'status'>) => Promise<void>;
}

const providerColors: Record<CloudProvider, string> = {
    AWS: 'text-orange-500',
    GCP: 'text-blue-500',
    Azure: 'text-sky-500',
};

export const CloudSecurityDashboard: React.FC<CloudSecurityDashboardProps> = ({ cloudAccounts, findings, onAddAccount }) => {
    const [viewingFinding, setViewingFinding] = useState<CSPMFinding | null>(null);
    const [isAddAccountModalOpen, setIsAddAccountModalOpen] = useState(false);

    const criticalCount = findings.filter(f => f.severity === 'Critical').length;
    const highCount = findings.filter(f => f.severity === 'High').length;
    
    const handleSaveAccount = async (accountData: Omit<CloudAccount, 'id' | 'tenantId' | 'status'>) => {
        await onAddAccount(accountData);
        setIsAddAccountModalOpen(false);
    };

    return (
        <div className="container mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-2">Cloud Security Posture Management (CSPM)</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Continuously monitor your cloud environments for misconfigurations and security risks.</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Connected Accounts</p>
                    <p className="text-2xl font-bold">{cloudAccounts.length}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Total Findings</p>
                    <p className="text-2xl font-bold">{findings.length}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Critical Findings</p>
                    <p className="text-2xl font-bold text-red-500">{criticalCount}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">High Severity Findings</p>
                    <p className="text-2xl font-bold text-orange-500">{highCount}</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                            <h3 className="text-lg font-semibold">Connected Cloud Accounts</h3>
                            <button
                                onClick={() => setIsAddAccountModalOpen(true)}
                                className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                            >
                                <PlusCircleIcon size={16} className="mr-1.5" />
                                Add Account
                            </button>
                        </div>
                        <div className="p-4 space-y-3">
                            {cloudAccounts.map(account => (
                                <div key={account.id} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                                    <div className="flex justify-between items-start">
                                        <div>
                                            <p className={`font-bold ${providerColors[account.provider]}`}>{account.provider}</p>
                                            <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">{account.name}</p>
                                        </div>
                                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${account.status === 'Connected' ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300'}`}>
                                            {account.status}
                                        </span>
                                    </div>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 font-mono">{account.accountId}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
                <div className="lg:col-span-2">
                     <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                            <h3 className="text-lg font-semibold flex items-center">
                                <CloudShieldIcon className="mr-2 text-primary-500" />
                                Security Findings
                            </h3>
                        </div>
                        <CSPMFindingsList findings={findings} onSelectFinding={setViewingFinding} />
                    </div>
                </div>
            </div>

            <CSPMRemediationModal 
                isOpen={!!viewingFinding}
                onClose={() => setViewingFinding(null)}
                finding={viewingFinding}
            />

            <AddCloudAccountModal
                isOpen={isAddAccountModalOpen}
                onClose={() => setIsAddAccountModalOpen(false)}
                onSave={handleSaveAccount}
            />
        </div>
    );
};
