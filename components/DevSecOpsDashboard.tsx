

import React, { useState, useMemo } from 'react';
import { Sbom, SoftwareComponent, SastFinding, CodeRepository } from '../types';
// FIX: Added missing UploadIcon and ComponentIcon.
import { ComponentIcon, GitPullRequestDraftIcon, AlertTriangleIcon, CodeIcon, SparklesIcon, UploadIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { UploadSbomModal } from './UploadSbomModal';
import { ComponentDetailModal } from './ComponentDetailModal';
import { SastFindingModal } from './SastFindingModal';

interface DevSecOpsDashboardProps {
    sboms: Sbom[];
    softwareComponents: SoftwareComponent[];
    sastFindings: SastFinding[];
    repositories: CodeRepository[];
    onUploadSbom: (file: File) => Promise<void>;
    initialTab?: DevSecOpsView;
    mode?: 'sast-only' | 'sbom-only' | 'full';
}

type DevSecOpsView = 'sast' | 'sbom';

export const DevSecOpsDashboard: React.FC<DevSecOpsDashboardProps> = ({ sboms, softwareComponents, sastFindings, repositories, onUploadSbom, initialTab = 'sast', mode = 'full' }) => {
    const { hasPermission } = useUser();
    const canManage = hasPermission('manage:security_playbooks'); // Reuse permission for now

    const [activeView, setActiveView] = useState<DevSecOpsView>(initialTab);
    const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
    const [viewingComponent, setViewingComponent] = useState<SoftwareComponent | null>(null);
    const [viewingSastFinding, setViewingSastFinding] = useState<SastFinding | null>(null);
    const [searchTerm, setSearchTerm] = useState('');

    const filteredComponents = useMemo(() => {
        if (activeView !== 'sbom') return [];
        return softwareComponents.filter(c =>
            c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            c.version.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }, [softwareComponents, searchTerm, activeView]);

    const totalComponents = softwareComponents.length;
    const vulnerableComponents = useMemo(() => new Set(softwareComponents.filter(c => c.vulnerabilities.length > 0).map(c => c.name)).size, [softwareComponents]);

    const renderSbomView = () => (
        <div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Uploaded SBOMs</p>
                    <p className="text-2xl font-bold">{sboms.length}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Total Components</p>
                    <p className="text-2xl font-bold">{totalComponents}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Vulnerable Components</p>
                    <p className="text-2xl font-bold text-red-500">{vulnerableComponents}</p>
                </div>
            </div>

            <div className="flex justify-between items-center mb-4">
                <input
                    type="text"
                    placeholder="Search components..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full max-w-xs px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-md shadow-sm sm:text-sm"
                />
                {canManage && (
                    <button onClick={() => setIsUploadModalOpen(true)} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                        <UploadIcon size={16} className="mr-1.5" />
                        Upload SBOM
                    </button>
                )}
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-6 py-3">Component</th>
                            <th scope="col" className="px-6 py-3">Version</th>
                            <th scope="col" className="px-6 py-3">Type</th>
                            <th scope="col" className="px-6 py-3">Vulnerabilities</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredComponents.map(component => (
                            <tr key={component.id} onClick={() => setViewingComponent(component)} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 cursor-pointer">
                                <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{component.name}</td>
                                <td className="px-6 py-4">{component.version}</td>
                                <td className="px-6 py-4 capitalize">{component.type}</td>
                                <td className="px-6 py-4">
                                    {component.vulnerabilities.length > 0 ? (
                                        <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300">
                                            {component.vulnerabilities.length} Found
                                        </span>
                                    ) : (
                                        <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300">
                                            0 Found
                                        </span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );

    const renderSastView = () => (
        <div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Tracked Repositories</p>
                    <p className="text-2xl font-bold">{repositories.length}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">High Severity Findings</p>
                    <p className="text-2xl font-bold text-red-500">{sastFindings.filter(f => f.severity === 'High').length}</p>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md">
                    <p className="text-sm text-gray-500 dark:text-gray-400">Total SAST Findings</p>
                    <p className="text-2xl font-bold">{sastFindings.length}</p>
                </div>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-6 py-3">Finding</th>
                            <th scope="col" className="px-6 py-3">Location</th>
                            <th scope="col" className="px-6 py-3">Severity</th>
                            <th scope="col" className="px-6 py-3">Repository</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sastFindings.map(finding => {
                            const repo = repositories.find(r => r.id === finding.repositoryId);
                            return (
                                <tr key={finding.id} onClick={() => setViewingSastFinding(finding)} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 cursor-pointer">
                                    <td className="px-6 py-4 font-semibold text-gray-800 dark:text-gray-200">{finding.type}</td>
                                    <td className="px-6 py-4 font-mono text-xs">{finding.fileName}:{finding.line}</td>
                                    <td className="px-6 py-4">
                                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${finding.severity === 'High' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300'}`}>
                                            {finding.severity}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4">{repo?.name}</td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h2 className="text-4xl font-bold bg-gradient-to-r from-primary-600 via-indigo-600 to-accent-600 bg-clip-text text-transparent flex items-center gap-3">
                            <GitPullRequestDraftIcon size={36} className="text-primary-500" />
                            {mode === 'sast-only' ? 'SAST Security Analysis' : mode === 'sbom-only' ? 'Software Bill of Materials (SBOM)' : 'DevSecOps Dashboard'}
                        </h2>
                        <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                            Shift-left security by integrating SAST, DAST, and SCA into your CI/CD pipelines.
                        </p>
                    </div>
                    {canManage && activeView === 'sbom' && (
                        <button onClick={() => setIsUploadModalOpen(true)} className="bg-gradient-to-r from-primary-600 to-indigo-600 text-white px-6 py-2.5 rounded-xl font-bold shadow-lg shadow-primary-500/30 hover:scale-105 transition-all flex items-center gap-2">
                            <UploadIcon size={20} />
                            Upload SBOM
                        </button>
                    )}
                </div>
            </header>

            <div className="glass-premium rounded-3xl overflow-hidden shadow-2xl">
                {mode === 'full' && (
                    <div className="border-b border-white/10 dark:border-white/5 bg-black/5 dark:bg-white/5">
                        <nav className="flex space-x-2 px-6" aria-label="Tabs">
                            <button
                                onClick={() => setActiveView('sast')}
                                className={`flex items-center gap-2 py-5 px-4 font-bold text-sm transition-all border-b-2 ${activeView === 'sast' ? 'border-primary-500 text-primary-600 dark:text-primary-400 bg-primary-500/5' : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'}`}
                            >
                                <CodeIcon size={18} /> SAST Findings
                            </button>
                            <button
                                onClick={() => setActiveView('sbom')}
                                className={`flex items-center gap-2 py-5 px-4 font-bold text-sm transition-all border-b-2 ${activeView === 'sbom' ? 'border-primary-500 text-primary-600 dark:text-primary-400 bg-primary-500/5' : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'}`}
                            >
                                <ComponentIcon size={18} /> SBOM Management
                            </button>
                        </nav>
                    </div>
                )}
                <div className="p-8">
                    {activeView === 'sast' ? (
                        <div className="space-y-6">
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                                <div className="glass p-6 rounded-2xl border border-white/10">
                                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">Tracked Repos</p>
                                    <p className="text-3xl font-black">{repositories.length}</p>
                                </div>
                                <div className="glass p-6 rounded-2xl border border-red-500/20 bg-red-500/5">
                                    <p className="text-xs font-black text-red-500 uppercase tracking-widest mb-1">Critical Findings</p>
                                    <p className="text-3xl font-black text-red-600 dark:text-red-400">{sastFindings.filter(f => f.severity === 'High').length}</p>
                                </div>
                                <div className="glass p-6 rounded-2xl border border-white/10">
                                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">Total Issues</p>
                                    <p className="text-3xl font-black">{sastFindings.length}</p>
                                </div>
                            </div>
                            <div className="overflow-x-auto rounded-2xl border border-white/5">
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs text-gray-400 uppercase bg-black/5 dark:bg-white/5 font-black">
                                        <tr>
                                            <th className="px-6 py-4">Finding</th>
                                            <th className="px-6 py-4">Location</th>
                                            <th className="px-6 py-4">Severity</th>
                                            <th className="px-6 py-4">Repository</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {sastFindings.map(finding => {
                                            const repo = repositories.find(r => r.id === finding.repositoryId);
                                            return (
                                                <tr key={finding.id} onClick={() => setViewingSastFinding(finding)} className="hover:bg-primary-500/5 transition-colors cursor-pointer group">
                                                    <td className="px-6 py-5">
                                                        <div className="font-bold text-gray-800 dark:text-gray-100 group-hover:translate-x-1 transition-transform">{finding.type}</div>
                                                    </td>
                                                    <td className="px-6 py-5 font-mono text-[10px] text-indigo-500 font-bold uppercase">{finding.fileName}:{finding.line}</td>
                                                    <td className="px-6 py-5">
                                                        <span className={`px-3 py-1 text-[10px] font-black rounded-full uppercase tracking-widest ${finding.severity === 'High' ? 'bg-red-500 text-white animate-pulse' : 'bg-amber-500 text-white'}`}>
                                                            {finding.severity}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-5 font-semibold text-gray-500">{repo?.name}</td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                                <div className="glass p-6 rounded-2xl border border-white/10">
                                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">SBOM Inventory</p>
                                    <p className="text-3xl font-black">{sboms.length}</p>
                                </div>
                                <div className="glass p-6 rounded-2xl border border-white/10">
                                    <p className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1">Total Deps</p>
                                    <p className="text-3xl font-black">{totalComponents}</p>
                                </div>
                                <div className="glass p-6 rounded-2xl border border-red-500/20 bg-red-500/5">
                                    <p className="text-xs font-black text-red-500 uppercase tracking-widest mb-1">Vulnerable Deps</p>
                                    <p className="text-3xl font-black text-red-600 dark:text-red-400">{vulnerableComponents}</p>
                                </div>
                            </div>
                            <div className="flex gap-4">
                                <input
                                    type="text"
                                    placeholder="Search components..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2 font-semibold text-sm focus:ring-2 focus:ring-primary-500 outline-none"
                                />
                            </div>
                            <div className="overflow-x-auto rounded-2xl border border-white/5">
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs text-gray-400 uppercase bg-black/5 dark:bg-white/5 font-black">
                                        <tr>
                                            <th className="px-6 py-4">Component</th>
                                            <th className="px-6 py-4">Version</th>
                                            <th className="px-6 py-4">Type</th>
                                            <th className="px-6 py-4">Vulnerabilities</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {filteredComponents.map(component => (
                                            <tr key={component.id} onClick={() => setViewingComponent(component)} className="hover:bg-primary-500/5 transition-colors cursor-pointer group">
                                                <td className="px-6 py-5">
                                                    <div className="font-bold text-gray-800 dark:text-gray-100 group-hover:translate-x-1 transition-transform">{component.name}</div>
                                                </td>
                                                <td className="px-6 py-5 font-mono text-xs font-bold text-indigo-500">{component.version}</td>
                                                <td className="px-6 py-5 uppercase text-[10px] font-black text-gray-400 tracking-widest">{component.type}</td>
                                                <td className="px-6 py-5">
                                                    {component.vulnerabilities.length > 0 ? (
                                                        <span className="px-3 py-1 text-[10px] font-black rounded-full uppercase bg-red-500 text-white animate-pulse">
                                                            {component.vulnerabilities.length} CVEs Found
                                                        </span>
                                                    ) : (
                                                        <span className="px-3 py-1 text-[10px] font-black rounded-full uppercase bg-green-500 text-white">
                                                            Secure
                                                        </span>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <UploadSbomModal isOpen={isUploadModalOpen} onClose={() => setIsUploadModalOpen(false)} onUpload={onUploadSbom} />
            <ComponentDetailModal isOpen={!!viewingComponent} onClose={() => setViewingComponent(null)} component={viewingComponent} sboms={sboms} />
            <SastFindingModal isOpen={!!viewingSastFinding} onClose={() => setViewingSastFinding(null)} finding={viewingSastFinding} />
        </div>
    );
};
