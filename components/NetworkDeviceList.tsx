
import React from 'react';
import { NetworkDevice, NetworkDeviceStatus } from '../types';
import { CheckIcon, XCircleIcon } from './icons';

interface NetworkDeviceListProps {
    devices: NetworkDevice[];
}

const statusInfo: Record<NetworkDeviceStatus, { icon: React.ReactNode; classes: string; }> = {
    Up: { icon: <CheckIcon size={14} />, classes: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300' },
    Down: { icon: <XCircleIcon size={14} />, classes: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' },
    Warning: { icon: <XCircleIcon size={14} />, classes: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' },
};


export const NetworkDeviceList: React.FC<NetworkDeviceListProps> = ({ devices }) => {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold">Device Inventory</h3>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-6 py-3">Status</th>
                            <th scope="col" className="px-6 py-3">Hostname</th>
                            <th scope="col" className="px-6 py-3">Type</th>
                            <th scope="col" className="px-6 py-3">Vendor</th>
                            <th scope="col" className="px-6 py-3">OS</th>
                            <th scope="col" className="px-6 py-3">Open Ports</th>
                            <th scope="col" className="px-6 py-3">IP Address</th>
                            <th scope="col" className="px-6 py-3">MAC Address</th>
                            <th scope="col" className="px-6 py-3">VLAN</th>
                            <th scope="col" className="px-6 py-3">Last Scanned</th>
                        </tr>
                    </thead>
                    <tbody>
                        {devices.map(device => (
                            <tr key={device.id} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                <td className="px-6 py-4">
                                    {statusInfo[device.status as NetworkDeviceStatus] ? (
                                        <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${statusInfo[device.status as NetworkDeviceStatus].classes}`}>
                                            {statusInfo[device.status as NetworkDeviceStatus].icon} <span className="ml-1.5">{device.status}</span>
                                        </span>
                                    ) : (
                                        <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
                                            <span className="ml-1.5">{device.status || 'Unknown'}</span>
                                        </span>
                                    )}
                                </td>
                                <td className="px-6 py-4 font-semibold text-gray-800 dark:text-gray-200">
                                    {device.hostname}
                                    {device.scanEngine === 'nmap' && <span className="ml-1 text-[10px] bg-blue-100 text-blue-800 px-1 rounded">Nmap</span>}
                                </td>
                                <td className="px-6 py-4">{device.deviceType}</td>
                                <td className="px-6 py-4">{device.vendor || '-'}</td>
                                <td className="px-6 py-4 text-xs">{device.osVersion || 'Unknown'}</td>
                                <td className="px-6 py-4">
                                    <div className="flex flex-wrap gap-1">
                                        {device.openPorts && device.openPorts.length > 0 ? (
                                            device.openPorts.slice(0, 3).map(p => (
                                                <span key={p} className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-xs font-mono border border-gray-200 dark:border-gray-600">
                                                    {p}
                                                </span>
                                            ))
                                        ) : (
                                            <span className="text-gray-400 text-xs">-</span>
                                        )}
                                        {device.openPorts && device.openPorts.length > 3 && (
                                            <span className="text-xs text-gray-500">+{device.openPorts.length - 3}</span>
                                        )}
                                    </div>
                                </td>
                                <td className="px-6 py-4 font-mono text-xs">{device.ipAddress}</td>
                                <td className="px-6 py-4 font-mono text-xs">{device.macAddress || '-'}</td>
                                <td className="px-6 py-4">
                                    {device.vlanId ? (
                                        <span className="px-2 py-0.5 rounded-md bg-indigo-100 dark:bg-indigo-900/50 text-indigo-800 dark:text-indigo-300 font-mono text-xs border border-indigo-200 dark:border-indigo-800">
                                            {device.vlanId}
                                        </span>
                                    ) : (
                                        <span className="text-gray-400 text-xs">-</span>
                                    )}
                                </td>
                                <td className="px-6 py-4 text-xs">{new Date(device.lastSeen).toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
