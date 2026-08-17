import React, { useState } from 'react';
import { NetworkDeviceType } from '../types';
import { Modal } from './Modal';

interface AddNetworkDeviceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: { hostname: string; ipAddress: string; deviceType: NetworkDeviceType; model: string; osVersion: string; }) => void;
}

const deviceTypeOptions: NetworkDeviceType[] = ['Router', 'Switch', 'Firewall'];

export const AddNetworkDeviceModal: React.FC<AddNetworkDeviceModalProps> = ({ isOpen, onClose, onSave }) => {
    const [hostname, setHostname] = useState('');
    const [ipAddress, setIpAddress] = useState('');
    const [deviceType, setDeviceType] = useState<NetworkDeviceType>('Router');
    const [model, setModel] = useState('');
    const [osVersion, setOsVersion] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({ hostname, ipAddress, deviceType, model, osVersion });
    };

    const footer = (
        <>
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium border border-slate-300 dark:border-slate-600 rounded-md text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700">Cancel</button>
            <button type="submit" form="add-network-device-form" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add Device</button>
        </>
    );

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Add Network Device for Monitoring" size="lg" footer={footer}>
            <form id="add-network-device-form" onSubmit={handleSubmit} className="space-y-4">
                <input value={hostname} onChange={e => setHostname(e.target.value)} required placeholder="Hostname (e.g., core-router-01.dc1)" className="w-full input-style" />
                <input value={ipAddress} onChange={e => setIpAddress(e.target.value)} required placeholder="IP Address" className="w-full input-style" />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <select value={deviceType} onChange={e => setDeviceType(e.target.value as NetworkDeviceType)} className="w-full input-style">
                        {deviceTypeOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                    <input value={model} onChange={e => setModel(e.target.value)} required placeholder="Model (e.g., Cisco ASR 9000)" className="w-full input-style" />
                </div>
                <input value={osVersion} onChange={e => setOsVersion(e.target.value)} required placeholder="OS Version (e.g., IOS XR 7.5.1)" className="w-full input-style" />

                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Simulated Credentials</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <input placeholder="SNMP Community (e.g., public)" className="w-full input-style" />
                        <input placeholder="SSH Username (e.g., admin)" className="w-full input-style" />
                    </div>
                </div>
                <style>{`.input-style { padding: 0.5rem 0.75rem; background-color: white; border: 1px solid #d1d5db; border-radius: 0.375rem; } .dark .input-style { background-color: #374151; border-color: #4b5563; }`}</style>
            </form>
        </Modal>
    );
};
