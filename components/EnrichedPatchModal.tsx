import React from 'react';
import { ExternalLinkIcon, AlertTriangleIcon, ShieldAlertIcon, TrendingUpIcon } from './icons';

interface CVEDetail {
    cve_id: string;
    description: string;
    cvss_v3_score?: number;
    cvss_v3_severity?: string;
    cvss_v3_vector?: string;
    epss_score?: number;
    exploit_probability?: string;
    published_date?: string;
    references?: string[];
}

interface EnrichedPatchModalProps {
    isOpen: boolean;
    onClose: () => void;
    patch: any;
    cveDetails?: CVEDetail[];
}

export const EnrichedPatchModal: React.FC<EnrichedPatchModalProps> = ({
    isOpen,
    onClose,
    patch,
    cveDetails
}) => {
    if (!isOpen) return null;

    const cvssScore = patch.cvss_score || patch.cve_details?.[0]?.cvss_v3_score;
    const epssScore = patch.epss_score || patch.epss_details?.[0]?.epss_score;
    const priorityScore = patch.priority_score;

    const getCVSSColor = (score: number) => {
        if (score >= 9.0) return 'text-red-600 dark:text-red-400';
        if (score >= 7.0) return 'text-orange-600 dark:text-orange-400';
        if (score >= 4.0) return 'text-yellow-600 dark:text-yellow-400';
        return 'text-blue-600 dark:text-blue-400';
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 p-6 flex justify-between items-start">
                    <div className="flex-1">
                        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                            {patch.name}
                        </h2>
                        <div className="flex items-center gap-4 flex-wrap">
                            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${patch.severity === 'Critical' ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' :
                                    patch.severity === 'High' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300' :
                                        patch.severity === 'Medium' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' :
                                            'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300'
                                }`}>
                                {patch.severity}
                            </span>
                            {priorityScore && (
                                <div className="flex items-center gap-2">
                                    <TrendingUpIcon size={16} className="text-primary-500" />
                                    <span className="text-sm font-medium">
                                        Priority: <span className="text-primary-600 dark:text-primary-400 font-bold">{priorityScore.toFixed(1)}/100</span>
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="ml-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Content */}
                <div className="p-6 space-y-6">
                    {/* Scoring Section */}
                    {(cvssScore || epssScore) && (
                        <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                            <h3 className="text-lg font-semibold mb-4 flex items-center">
                                <ShieldAlertIcon size={20} className="mr-2 text-primary-500" />
                                Risk Intelligence
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {cvssScore && (
                                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
                                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">CVSS v3 Score</p>
                                        <p className={`text-3xl font-bold ${getCVSSColor(cvssScore)}`}>
                                            {cvssScore.toFixed(1)}/10
                                        </p>
                                        <p className="text-xs text-gray-500 mt-1">
                                            {patch.cve_details?.[0]?.cvss_v3_severity || 'Severity'}
                                        </p>
                                    </div>
                                )}
                                {epssScore && (
                                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4">
                                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Exploit Probability</p>
                                        <p className="text-3xl font-bold text-orange-600 dark:text-orange-400">
                                            {(epssScore * 100).toFixed(2)}%
                                        </p>
                                        <p className="text-xs text-gray-500 mt-1">EPSS Score (Next 30 days)</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* SLA Information */}
                    {patch.sla_hours && (
                        <div className="border-l-4 border-blue-500 bg-blue-50 dark:bg-blue-900/20 p-4 rounded">
                            <p className="text-sm font-semibold text-blue-900 dark:text-blue-200">
                                Compliance SLA: Deploy within {patch.sla_hours} hours
                            </p>
                            {patch.patch_deadline && (
                                <p className="text-xs text-blue-700 dark:text-blue-300 mt-1">
                                    Deadline: {new Date(patch.patch_deadline * 1000).toLocaleString()}
                                </p>
                            )}
                        </div>
                    )}

                    {/* CVE Details */}
                    {patch.cve_details && patch.cve_details.length > 0 && (
                        <div>
                            <h3 className="text-lg font-semibold mb-3">CVE Details</h3>
                            <div className="space-y-4">
                                {patch.cve_details.map((cve: CVEDetail, index: number) => (
                                    <div key={index} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                                        <div className="flex items-start justify-between mb-2">
                                            <h4 className="font-mono text-sm font-bold text-primary-600 dark:text-primary-400">
                                                {cve.cve_id}
                                            </h4>
                                            <a
                                                href={`https://nvd.nist.gov/vuln/detail/${cve.cve_id}`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-blue-600 dark:text-blue-400 hover:underline text-xs flex items-center gap-1"
                                            >
                                                View on NVD <ExternalLinkIcon size={12} />
                                            </a>
                                        </div>
                                        <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
                                            {cve.description}
                                        </p>
                                        {cve.cvss_v3_vector && (
                                            <p className="text-xs font-mono text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-900 p-2 rounded">
                                                Vector: {cve.cvss_v3_vector}
                                            </p>
                                        )}
                                        {cve.published_date && (
                                            <p className="text-xs text-gray-500 mt-2">
                                                Published: {new Date(cve.published_date).toLocaleDateString()}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Affected Assets */}
                    {patch.affectedAssets && patch.affectedAssets.length > 0 && (
                        <div>
                            <h3 className="text-lg font-semibold mb-3">
                                Affected Assets ({patch.affectedAssets.length})
                            </h3>
                            <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-3 max-h-48 overflow-y-auto">
                                <div className="space-y-1">
                                    {patch.affectedAssets.slice(0, 20).map((assetId: string) => (
                                        <div key={assetId} className="text-sm font-mono text-gray-700 dark:text-gray-300">
                                            {assetId}
                                        </div>
                                    ))}
                                    {patch.affectedAssets.length > 20 && (
                                        <p className="text-xs text-gray-500 italic mt-2">
                                            ... and {patch.affectedAssets.length - 20} more
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="sticky bottom-0 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
};
