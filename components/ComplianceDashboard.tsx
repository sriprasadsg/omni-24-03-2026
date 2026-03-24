import React, { useState, useEffect } from 'react';
import { ComplianceFramework, Asset, AssetCompliance } from '../types';
import { FrameworkRegistry } from './FrameworkRegistry';
import { FrameworkDetail } from './FrameworkDetail';
import { ShieldCheckIcon } from './icons';

interface ComplianceDashboardProps {
    complianceFrameworks: ComplianceFramework[];
    assets: Asset[];
    assetComplianceData: AssetCompliance[];
}

export const ComplianceDashboard: React.FC<ComplianceDashboardProps> = ({ complianceFrameworks, assets, assetComplianceData }) => {
    const [selectedFramework, setSelectedFramework] = useState<ComplianceFramework | null>(null);

    useEffect(() => {
        // When the frameworks list changes, ensure the selection is valid.
        if (selectedFramework && !complianceFrameworks.some(f => f.id === selectedFramework.id)) {
            setSelectedFramework(complianceFrameworks[0] || null);
        } else if (!selectedFramework && complianceFrameworks.length > 0) {
            setSelectedFramework(complianceFrameworks[0] || null);
        }
    }, [complianceFrameworks, selectedFramework]);


    const handleSelectFramework = (framework: ComplianceFramework) => {
        setSelectedFramework(framework);
    };

    return (
        <div className="container mx-auto">
            <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">Compliance Management</h2>
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-1">
                    <FrameworkRegistry
                        frameworks={complianceFrameworks}
                        selectedFramework={selectedFramework}
                        onSelectFramework={handleSelectFramework}
                    />
                </div>
                <div className="lg:col-span-3">
                    {selectedFramework ? (
                        <FrameworkDetail framework={selectedFramework} assets={assets} assetComplianceData={assetComplianceData} />
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
