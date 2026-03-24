
import React from 'react';
import { SoftwareComponent, Sbom, VulnerabilitySeverity } from '../types';
// FIX: Added missing ComponentIcon.
import { XIcon, ComponentIcon, AlertTriangleIcon } from './icons';

interface ComponentDetailModalProps {
    isOpen: boolean;
    onClose: () => void;
    component: SoftwareComponent | null;
    sboms: Sbom[];
}

const severityClasses: Record<VulnerabilitySeverity, string> = {
    Critical: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    High: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
    Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    Low: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Informational: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
};

export const ComponentDetailModal: React.FC<ComponentDetailModalProps> = ({ isOpen, onClose, component, sboms }) => {
    if (!isOpen || !component) return null;

    // This is a simplified lookup for demonstration
    const usedInApplications = sboms.slice(0, 2).map(s => s.applicationName);

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
                            <ComponentIcon className="mr-3 text-primary-500" />
                            {component.name}
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{component.id}</p>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>

                <div className="flex-grow space-y-4 overflow-y-auto pr-2">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                        <div><strong className="block text-gray-500 dark:text-gray-400">Version</strong> {component.version}</div>
                        <div><strong className="block text-gray-500 dark:text-gray-400">Type</strong> <span className="capitalize">{component.type}</span></div>
                        <div><strong className="block text-gray-500 dark:text-gray-400">Supplier</strong> {component.supplier}</div>
                        <div><strong className="block text-gray-500 dark:text-gray-400">Licenses</strong> {component.licenses && component.licenses.length > 0 ? component.licenses.map(l => l.id || l.name).join(', ') : 'N/A'}</div>
                        {component.hashes && Object.entries(component.hashes).length > 0 && (
                            <div className="col-span-2"><strong className="block text-gray-500 dark:text-gray-400">Checksum (SHA-256/MD5)</strong>
                                <span className="font-mono text-xs break-all">
                                    {component.hashes['SHA-256'] || component.hashes['MD5'] || Object.values(component.hashes)[0]}
                                </span>
                            </div>
                        )}
                    </div>
                    <div>
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Used In Applications</h3>
                        <div className="flex flex-wrap gap-2">
                            {usedInApplications.map(app => (
                                <span key={app} className="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">{app}</span>
                            ))}
                        </div>
                    </div>
                    <div className="pt-2">
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                            <AlertTriangleIcon size={14} className="mr-1.5" />
                            Known Vulnerabilities ({component.vulnerabilities.length})
                        </h3>
                        {component.vulnerabilities.length > 0 ? (
                            <div className="space-y-2">
                                {component.vulnerabilities.map(vuln => (
                                    <div key={vuln.cve} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
                                        <div className="flex justify-between items-start">
                                            <p className="font-semibold text-gray-800 dark:text-gray-200 font-mono text-xs">{vuln.cve}</p>
                                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${severityClasses[vuln.severity]}`}>{vuln.severity}</span>
                                        </div>
                                        <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{vuln.summary}</p>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-3">No known vulnerabilities for this component version.</p>
                        )}
                    </div>

                </div>

                <div className="flex-shrink-0 mt-6 flex justify-end items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
};
