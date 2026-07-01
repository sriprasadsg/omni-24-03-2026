import React, { useState, useEffect, useCallback } from 'react';
import { ComplianceFramework, Asset, AssetCompliance } from '../types';
import { FrameworkRegistry } from './FrameworkRegistry';
import { FrameworkDetail } from './FrameworkDetail';
import { ShieldCheckIcon } from './icons';
import { fetchComplianceFrameworks } from '../services/apiService';

interface ComplianceDashboardProps {
    complianceFrameworks: ComplianceFramework[];
    assets: Asset[];
    assetComplianceData: AssetCompliance[];
}

export const ComplianceDashboard: React.FC<ComplianceDashboardProps> = ({ complianceFrameworks: initialFrameworks, assets, assetComplianceData }) => {
    const [frameworks, setFrameworks]           = useState<ComplianceFramework[]>(initialFrameworks);
    const [selectedFramework, setSelectedFramework] = useState<ComplianceFramework | null>(null);

    // Keep local list in sync when props change (initial load)
    useEffect(() => { setFrameworks(initialFrameworks); }, [initialFrameworks]);

    useEffect(() => {
        if (selectedFramework && !frameworks.some(f => f.id === selectedFramework.id)) {
            setSelectedFramework(frameworks[0] || null);
        } else if (!selectedFramework && frameworks.length > 0) {
            setSelectedFramework(frameworks[0] || null);
        }
    }, [frameworks, selectedFramework]);

    const handleSelectFramework = (framework: ComplianceFramework) => setSelectedFramework(framework);

    const handleFrameworkAdded = (newFramework: ComplianceFramework) => {
        setFrameworks(prev => [...prev, newFramework]);
        setSelectedFramework(newFramework);
    };

    const handleRefresh = useCallback(async () => {
        try {
            const fresh = await fetchComplianceFrameworks();
            if (fresh) {
                setFrameworks(fresh);
                if (selectedFramework) {
                    const updated = (fresh as ComplianceFramework[]).find(f => f.id === selectedFramework.id);
                    if (updated) setSelectedFramework(updated);
                }
            }
        } catch {
            // silently ignore — toast was already shown by FrameworkDetail
        }
    }, [selectedFramework]);

    return (
        <div className="container mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">Compliance Management</h2>
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-1">
                    <FrameworkRegistry
                        frameworks={frameworks}
                        selectedFramework={selectedFramework}
                        onSelectFramework={handleSelectFramework}
                        onFrameworkAdded={handleFrameworkAdded}
                    />
                </div>
                <div className="lg:col-span-3">
                    {selectedFramework ? (
                        <FrameworkDetail framework={selectedFramework} assets={assets} assetComplianceData={assetComplianceData}
                            key={selectedFramework.id} onRefresh={handleRefresh} />
                    ) : (
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md h-full flex items-center justify-center">
                            <div className="text-center text-gray-500 dark:text-gray-400 p-8">
                                <ShieldCheckIcon size={48} className="mx-auto text-gray-400 dark:text-gray-500" />
                                <p className="mt-4">Select a framework to view its details and controls.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
