
import React, { useState, useMemo } from 'react';
import { Sbom, SoftwareComponent } from '../types';
// FIX: Added missing UploadIcon and ComponentIcon.
import { ComponentIcon, UploadIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import { UploadSbomModal } from './UploadSbomModal';
import { ComponentDetailModal } from './ComponentDetailModal';

interface SbomDashboardProps {
    sboms: Sbom[];
    softwareComponents: SoftwareComponent[];
    onUploadSbom: (file: File) => Promise<void>;
}

export const SbomDashboard: React.FC<SbomDashboardProps> = ({ sboms, softwareComponents, onUploadSbom }) => {
    const { hasPermission } = useUser();
    const canManage = hasPermission('manage:security_playbooks'); // Reuse permission for now

    const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
    const [viewingComponent, setViewingComponent] = useState<SoftwareComponent | null>(null);
    const [searchTerm, setSearchTerm] = useState('');

    const filteredComponents = useMemo(() => {
        return softwareComponents.filter(c =>
            c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            c.version.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }, [softwareComponents, searchTerm]);

    const totalComponents = softwareComponents.length;
    const vulnerableComponents = useMemo(() => new Set(softwareComponents.filter(c => c.vulnerabilities.length > 0).map(c => c.name)).size, [softwareComponents]);

    return (
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

            <UploadSbomModal
                isOpen={isUploadModalOpen}
                onClose={() => setIsUploadModalOpen(false)}
                onUpload={onUploadSbom}
            />

            <ComponentDetailModal
                isOpen={!!viewingComponent}
                onClose={() => setViewingComponent(null)}
                component={viewingComponent}
                sboms={sboms}
            />

        </div>
    );
};
