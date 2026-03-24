
import React, { useState, useEffect } from 'react';
import { Asset, AgentPlatform } from '../types';

interface RegisterAgentModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (data: { hostname: string; ipAddress: string; platform: AgentPlatform; version: string; assetId: string | 'new'; }) => void;
    assets: Asset[];
}

const platformOptions: AgentPlatform[] = ['Linux', 'Windows', 'macOS', 'Docker', 'Kubernetes', 'AWS EC2'];

export const RegisterAgentModal: React.FC<RegisterAgentModalProps> = ({ isOpen, onClose, onSave, assets }) => {
    const [hostname, setHostname] = useState('');
    const [ipAddress, setIpAddress] = useState('');
    const [platform, setPlatform] = useState<AgentPlatform>('Linux');
    const [version, setVersion] = useState('2.2.0');
    const [assetId, setAssetId] = useState<'new' | string>('new');

    useEffect(() => {
        if (isOpen) {
            // Reset form when modal opens
            setHostname('');
            setIpAddress('');
            setPlatform('Linux');
            setVersion('2.2.0');
            setAssetId('new');
        }
    }, [isOpen]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!hostname.trim() || !ipAddress.trim() || !version.trim()) {
            alert("Please fill all required fields.");
            return;
        }

        onSave({
            hostname: hostname.trim(),
            ipAddress: ipAddress.trim(),
            platform,
            version: version.trim(),
            assetId,
        });
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Register New Agent</h2>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label htmlFor="hostname" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Hostname</label>
                        <input type="text" id="hostname" value={hostname} onChange={e => setHostname(e.target.value)} required 
                               className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
                    </div>
                     <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="ipAddress" className="block text-sm font-medium text-gray-700 dark:text-gray-300">IP Address</label>
                            <input type="text" id="ipAddress" value={ipAddress} onChange={e => setIpAddress(e.target.value)} required 
                                   className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
                        </div>
                        <div>
                            <label htmlFor="version" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Agent Version</label>
                            <input type="text" id="version" value={version} onChange={e => setVersion(e.target.value)} required 
                                   className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
                        </div>
                     </div>
                    <div>
                        <label htmlFor="platform" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Platform</label>
                        <select id="platform" value={platform} onChange={e => setPlatform(e.target.value as AgentPlatform)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm">
                            {platformOptions.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                    </div>
                     <div>
                        <label htmlFor="assetId" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Associated Asset</label>
                        <select id="assetId" value={assetId} onChange={e => setAssetId(e.target.value)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm">
                            <option value="new">-- Create New Asset --</option>
                            {assets.map(asset => (
                                <option key={asset.id} value={asset.id}>{asset.hostname} ({asset.ipAddress})</option>
                            ))}
                        </select>
                         <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                           Select an existing asset to link this agent to, or create a new asset record automatically.
                        </p>
                    </div>

                    <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                        <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Register Agent</button>
                    </div>
                </form>
            </div>
        </div>
    );
};
