import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { ComplianceFramework, Asset, AssetCompliance } from '../types';
import { FrameworkRegistry } from './FrameworkRegistry';
import { FrameworkDetail } from './FrameworkDetail';
import { ShieldCheckIcon, CheckCircleIcon, AlertTriangleIcon, ClockIcon } from './icons';
import { fetchComplianceFrameworks } from '../services/apiService';
import { StatTile, bigNumber } from './StatTile';

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
            // fetchComplianceFrameworks answers [] when the request fails; keep what is on screen.
            if (fresh && fresh.length > 0) {
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

    const totals = useMemo(() => {
        const t = { controls: 0, implemented: 0, inProgress: 0, atRisk: 0, notImplemented: 0 };
        frameworks.forEach(f => (f.controls ?? []).forEach(c => {
            t.controls++;
            if (c.status === 'Implemented') t.implemented++;
            else if (c.status === 'In Progress') t.inProgress++;
            else if (c.status === 'At Risk') t.atRisk++;
            else if (c.status === 'Not Implemented') t.notImplemented++;
        }));
        return t;
    }, [frameworks]);
    const compliantCount = frameworks.filter(f => f.status === 'Compliant').length;
    const implementedShare = totals.controls ? (totals.implemented / totals.controls) * 100 : 0;

    return (
        <div className="space-y-6 fade-in">
            <header>
                <h2 className="text-[30px] font-semibold tracking-[-0.03em] text-gray-900 dark:text-white">Compliance</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    The frameworks your organization follows, their controls and the evidence behind them.
                </p>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
                <StatTile icon={<ShieldCheckIcon size={18} />} label="Frameworks" tone="blue" footnote={`${compliantCount} compliant`}>
                    <p className={`${bigNumber} text-gray-900 dark:text-white`}>{frameworks.length}</p>
                </StatTile>
                <StatTile icon={<CheckCircleIcon size={18} />} label="Controls implemented" tone="primary" footnote={`${totals.inProgress} in progress`}>
                    <p>
                        <span className={`${bigNumber} text-gray-900 dark:text-white`}>{totals.implemented}</span>
                        <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">of {totals.controls}</span>
                    </p>
                    <div className="mt-3 h-1.5 rounded-full overflow-hidden bg-gray-200 dark:bg-white/10" aria-hidden="true">
                        <div className="h-full rounded-full bg-primary-500 dark:bg-primary-400" style={{ width: `${implementedShare}%` }} />
                    </div>
                </StatTile>
                <StatTile icon={<AlertTriangleIcon size={18} />} label="Controls at risk" tone="red" footnote="Across all frameworks">
                    <p className={`${bigNumber} ${totals.atRisk > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>{totals.atRisk}</p>
                </StatTile>
                <StatTile icon={<ClockIcon size={18} />} label="Not implemented" tone="amber" footnote="Across all frameworks">
                    <p className={`${bigNumber} ${totals.notImplemented > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-gray-900 dark:text-white'}`}>{totals.notImplemented}</p>
                </StatTile>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                <div className="lg:col-span-4 xl:col-span-3 lg:self-start lg:h-[720px]">
                    <FrameworkRegistry
                        frameworks={frameworks}
                        selectedFramework={selectedFramework}
                        onSelectFramework={handleSelectFramework}
                        onFrameworkAdded={handleFrameworkAdded}
                    />
                </div>
                <div className="lg:col-span-8 xl:col-span-9 min-w-0">
                    {selectedFramework ? (
                        <FrameworkDetail framework={selectedFramework} assets={assets} assetComplianceData={assetComplianceData}
                            key={selectedFramework.id} onRefresh={handleRefresh} />
                    ) : (
                        <div className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card min-h-[320px] lg:h-[720px] grid place-items-center p-8 text-center">
                            <div>
                                <ShieldCheckIcon size={32} className="mx-auto text-gray-400" />
                                <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                                    {frameworks.length === 0 ? 'No compliance frameworks yet' : 'Select a framework'}
                                </p>
                                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 max-w-sm">
                                    {frameworks.length === 0
                                        ? 'No compliance frameworks are enabled for your organization yet. Contact your provider to purchase one.'
                                        : 'Select a framework to view its details and controls.'}
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
