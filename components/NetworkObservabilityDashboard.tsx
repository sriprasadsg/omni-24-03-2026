import React, { useState, useMemo } from 'react';
import { NetworkDevice } from '../types';
import { NetworkIcon, PlusCircleIcon } from './icons';
import { AddNetworkDeviceModal } from './AddNetworkDeviceModal';
import { NetworkDeviceList } from './NetworkDeviceList';
import { ConfigurationChangeFeed } from './ConfigurationChangeFeed';
import { NetworkVulnerabilityList } from './NetworkVulnerabilityList';
import { NetworkTopologyMap } from './NetworkTopologyMap';

interface NetworkObservabilityDashboardProps {
    networkDevices: NetworkDevice[];
    onAddDevice: (deviceData: Omit<NetworkDevice, 'id' | 'tenantId' | 'status' | 'lastSeen' | 'interfaces' | 'configBackups' | 'vulnerabilities'>) => void;
    onRefresh?: () => void;
}

const StatCard: React.FC<{ title: string; value: string | number; }> = ({ title, value }) => (
    <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
        <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
        <p className="text-2xl font-bold">{value}</p>
    </div>
);

import * as api from '../services/apiService';

export const NetworkObservabilityDashboard: React.FC<NetworkObservabilityDashboardProps> = ({ networkDevices, onAddDevice, onRefresh }) => {
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    const [isScanning, setIsScanning] = useState(false);

    const stats = useMemo(() => {
        const total = networkDevices?.length || 0;
        const up = networkDevices?.filter(d => d.status === 'Up').length || 0;
        const withChanges = networkDevices?.filter(d => d.configBackups?.some(c => c.diff !== null)).length || 0;
        const withVulns = networkDevices?.filter(d => d.vulnerabilities?.length > 0).length || 0;
        return { total, up, withChanges, withVulns };
    }, [networkDevices]);

    const handleSaveDevice = (deviceData: Omit<NetworkDevice, 'id' | 'tenantId' | 'status' | 'lastSeen' | 'interfaces' | 'configBackups' | 'vulnerabilities'>) => {
        onAddDevice(deviceData);
        setIsAddModalOpen(false);
    };



    const handleScan = async () => {
        setIsScanning(true);
        try {
            console.log(`Initiating server-side scan (all networks: ${scanAllNetworks})...`);
            await api.triggerServerNetworkScan(scanAllNetworks);
            alert("Network scan initiated. This may take a few minutes.");

            // Poll for results (simple delay for now)
            setTimeout(() => {
                if (onRefresh) onRefresh();
                loadSubnets();
                setMapRefreshKey(k => k + 1);
                setIsScanning(false);
            }, 5000);

        } catch (e) {
            console.error("Scan failed", e);
            alert("Failed to start scan");
            setIsScanning(false);
        }
    };

    const [viewMode, setViewMode] = useState<'list' | 'map'>('list');
    const [mapRefreshKey, setMapRefreshKey] = useState(Date.now());
    const [mapImageUrl, setMapImageUrl] = useState<string | null>(null);
    const [isLoadingMap, setIsLoadingMap] = useState(false);
    const [scanAllNetworks, setScanAllNetworks] = useState(true);
    const [subnets, setSubnets] = useState<string[]>([]);
    const [rescanningSubnet, setRescanningSubnet] = useState<string | null>(null);

    const handleRefreshMap = () => {
        setMapRefreshKey(Date.now());
    };

    const loadSubnets = () => {
        api.fetchNetworkSubnets().then(data => setSubnets(data));
    };

    React.useEffect(() => {
        loadSubnets();
    }, [mapRefreshKey]);

    const handleSubnetRescan = async (subnet: string) => {
        setRescanningSubnet(subnet);
        try {
            await api.triggerServerNetworkScan(false, subnet);
            alert(`Rescan initiated for ${subnet}.`);
            setTimeout(() => {
                if (onRefresh) onRefresh();
                setMapRefreshKey(k => k + 1);
            }, 3000);
        } catch (e) {
            alert(`Failed to rescan ${subnet}`);
        } finally {
            setRescanningSubnet(null);
        }
    };

    React.useEffect(() => {
        if (viewMode === 'map') {
            setIsLoadingMap(true);
            api.fetchNetworkTopologyImage()
                .then(blob => {
                    const url = URL.createObjectURL(blob);
                    setMapImageUrl(prev => {
                        if (prev) URL.revokeObjectURL(prev);
                        return url;
                    });
                    setIsLoadingMap(false);
                })
                .catch(err => {
                    console.error("Failed to load map image", err);
                    setIsLoadingMap(false);
                });
        }
        return () => {
            // Cleanup on unmount is tricky with state, but we clean up on new fetch
        };
    }, [viewMode, mapRefreshKey]);

    return (
        <div className="container mx-auto">
            <div className="flex justify-between items-center mb-2">
                <h2 className="text-2xl font-semibold text-gray-800 dark:text-white">Network Observability</h2>
                <div className="flex space-x-2">
                    <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg p-1 flex mr-2">
                        <button
                            onClick={() => setViewMode('list')}
                            className={`px-3 py-1 text-sm font-medium rounded-md ${viewMode === 'list' ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}
                        >
                            List
                        </button>
                        <button
                            onClick={() => setViewMode('map')}
                            className={`px-3 py-1 text-sm font-medium rounded-md ${viewMode === 'map' ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}
                        >
                            Map
                        </button>
                    </div>

                    {onRefresh && (
                        <button
                            onClick={onRefresh}
                            className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 dark:bg-gray-800 dark:text-white dark:border-gray-600 dark:hover:bg-gray-700"
                        >
                            Refresh List
                        </button>
                    )}
                    <div className="flex items-center space-x-2 px-3 py-2 bg-gray-50 dark:bg-gray-700 rounded-lg">
                        <input
                            type="checkbox"
                            id="scanAllNetworks"
                            checked={scanAllNetworks}
                            onChange={(e) => setScanAllNetworks(e.target.checked)}
                            className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                        />
                        <label htmlFor="scanAllNetworks" className="text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                            Scan All Networks
                        </label>
                    </div>
                    <button
                        onClick={handleScan}
                        disabled={isScanning}
                        className={`flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 ${isScanning ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {isScanning ? 'Scanning...' : 'Scan Network'}
                    </button>
                    <button
                        onClick={() => setIsAddModalOpen(true)}
                        className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700"
                    >
                        <PlusCircleIcon size={16} className="mr-2" />
                        Add Network Device
                    </button>
                </div>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">Agentless monitoring for routers, switches, and firewalls.</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
                <StatCard title="Total Devices" value={stats.total} />
                <StatCard title="Devices Up" value={`${stats.up} / ${stats.total}`} />
                <StatCard title="Devices with Config Changes" value={stats.withChanges} />
                <StatCard title="Devices with Vulnerabilities" value={stats.withVulns} />
            </div>

            {/* Subnet List Section */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 mb-6">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">Detected Subnets</h3>
                {subnets.length === 0 ? (
                    <p className="text-gray-500 text-sm">No subnets detected yet.</p>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {subnets.map(subnet => (
                            <div key={subnet} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
                                <span className="font-mono text-gray-700 dark:text-gray-300">{subnet}</span>
                                <button
                                    onClick={() => handleSubnetRescan(subnet)}
                                    disabled={rescanningSubnet === subnet}
                                    className="px-3 py-1 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-md transition-colors disabled:opacity-50"
                                >
                                    {rescanningSubnet === subnet ? 'Scanning...' : 'Rescan'}
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {viewMode === 'list' ? (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div className="lg:col-span-2">
                        <NetworkDeviceList devices={networkDevices} />
                    </div>
                    <div className="space-y-6">
                        <ConfigurationChangeFeed devices={networkDevices} />
                        <NetworkVulnerabilityList devices={networkDevices} />
                    </div>
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                    <div className="flex justify-between items-center mb-4">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Network Topology Map</h3>
                        <div className="flex space-x-2">
                            <div className="text-xs text-gray-500 flex items-center mr-4">
                                <span className="w-2 h-2 rounded-full bg-green-500 mr-1 animate-pulse"></span>
                                Live Traffic & Status
                            </div>
                            <button
                                onClick={handleRefreshMap}
                                className="text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400"
                            >
                                Refresh Data
                            </button>
                        </div>
                    </div>
                    {/* New Interactive Map Component */}
                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-gray-50 dark:bg-gray-900">
                        <NetworkTopologyMap refreshKey={mapRefreshKey} />
                    </div>
                    <p className="text-xs text-gray-500 mt-2 text-center">
                        Interactive Map: Drag nodes to rearrange. Click for details. Real-time traffic visualization enabled.
                    </p>
                </div>
            )}

            <AddNetworkDeviceModal
                isOpen={isAddModalOpen}
                onClose={() => setIsAddModalOpen(false)}
                onSave={handleSaveDevice}
            />
        </div>
    );
};
