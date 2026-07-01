import React, { useState } from 'react';
import { Asset, AssetCompliance, Control } from '../types';
import { CheckIcon, XIcon, AlertCircleIcon, UploadIcon, FileTextIcon, BrainCircuitIcon, TrashIcon } from './icons';
import { EvidenceMarkdownViewer } from './EvidenceMarkdownViewer';
import { EvidenceReviewPanel } from './EvidenceReviewPanel';
import { showToast } from '../utils/toast';

interface AssetComplianceListProps {
    control: Control;
    assets: Asset[];
    complianceData: AssetCompliance[];
    onUpdateStatus: (assetId: string, status: AssetCompliance['status']) => Promise<void>;
    onUploadEvidence: (assetId: string, file: File, description?: string) => void;
    onIngestEvidence: (assetId: string, fileName: string, content: string) => Promise<void>;
    onDeleteEvidence: (assetId: string, controlId: string, evidenceId: string) => Promise<void>;
}

export const AssetComplianceList: React.FC<AssetComplianceListProps> = ({ control, assets, complianceData, onUpdateStatus, onUploadEvidence, onIngestEvidence, onDeleteEvidence }) => {
    const fileInputRef = React.useRef<HTMLInputElement>(null);
    const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
    const [ingestingMap, setIngestingMap] = useState<Record<string, boolean>>({});
    const [descriptionMap, setDescriptionMap] = useState<Record<string, string>>({});
    const [deletingMap, setDeletingMap] = useState<Record<string, boolean>>({});
    const [updatingMap, setUpdatingMap] = useState<Record<string, boolean>>({});

    const handleUpdateStatus = async (assetId: string, status: AssetCompliance['status']) => {
        setUpdatingMap(prev => ({ ...prev, [assetId]: true }));
        try {
            await onUpdateStatus(assetId, status);
        } finally {
            setUpdatingMap(prev => ({ ...prev, [assetId]: false }));
        }
    };

    const handleUploadClick = (assetId: string) => {
        setSelectedAssetId(assetId);
        fileInputRef.current?.click();
    };

    const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file || !selectedAssetId) return;

        const description = descriptionMap[selectedAssetId] || undefined;

        // 1. Trigger the standard upload handler (UI update + backend upload)
        onUploadEvidence(selectedAssetId, file, description);

        // 2. Read content and trigger ingestion
        setIngestingMap(prev => ({ ...prev, [selectedAssetId]: true }));
        try {
            const text = await file.text(); // Basic text extraction
            await onIngestEvidence(selectedAssetId, file.name, text);
        } catch (error) {
            console.error("Failed to read file for ingestion", error);
            showToast('Upload failed — please try again', 'error');
        } finally {
            setIngestingMap(prev => ({ ...prev, [selectedAssetId]: false }));
            setDescriptionMap(prev => { const next = { ...prev }; delete next[selectedAssetId!]; return next; });
            setSelectedAssetId(null);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleDeleteEvidence = async (assetId: string, evidenceId: string) => {
        if (!window.confirm('Delete this evidence? This action cannot be undone.')) return;
        setDeletingMap(prev => ({ ...prev, [evidenceId]: true }));
        try {
            await onDeleteEvidence(assetId, control.id, evidenceId);
        } catch (error) {
            console.error("Failed to delete evidence", error);
            showToast('Could not delete evidence — please try again', 'error');
        } finally {
            setDeletingMap(prev => { const next = { ...prev }; delete next[evidenceId]; return next; });
        }
    };

    const getStatus = (assetId: string) => {
        return complianceData.find(c => c.assetId === assetId && c.controlId === control.id);
    };

    return (
        <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
                <h3 className="font-semibold text-gray-800 dark:text-gray-200">Asset Compliance: {control.name}</h3>
            </div>
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-800">
                    <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Asset</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Findings (Reason)</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Suggested Actions</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Evidence</th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                    </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {assets.map(asset => {
                        const statusRecord = getStatus(asset.id);
                        const status = statusRecord?.status || 'Non-Compliant';

                        return (
                            <tr key={asset.id}>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">{asset.hostname}</td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                        ${status === 'Compliant' ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300' :
                                            status === 'Pending_Evidence' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300' :
                                                'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300'}`}>
                                        {status.replace('_', ' ')}
                                    </span>
                                </td>
                                <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-xs truncate" title={statusRecord?.reason || ''}>
                                    {statusRecord?.reason || '-'}
                                </td>
                                <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-xs truncate" title={statusRecord?.remediation || ''}>
                                    {statusRecord?.remediation || '-'}
                                </td>
                                <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                                    {statusRecord?.evidence?.length ? (
                                        <div className="flex flex-col space-y-3">
                                            {statusRecord.evidence.map((ev: any, idx: number) => {
                                                const isAutomated = ev.systemGenerated === true || ev.source === 'auto';
                                                const evId = ev.id || ev.evidence_id;
                                                return (
                                                <React.Fragment key={evId ?? `idx-${idx}`}>
                                                  <div className="flex items-start gap-2">
                                                    <div className="flex-1">
                                                        {isAutomated || ev.url === '#' || ev.evidence_content || ev.content ? (
                                                            <EvidenceMarkdownViewer
                                                                evidence={{
                                                                    id: evId,
                                                                    name: (ev.name || ev.check_name || `Evidence ${idx + 1}`) + (isAutomated && ev.stale ? ` (${ev.stale_days} days old)` : ''),
                                                                    content: ev.evidence_content || ev.content,
                                                                    details: ev.details
                                                                }}
                                                            />
                                                        ) : (
                                                            <a
                                                                href={`/api/compliance/evidence/download/${evId}`}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="flex items-center text-blue-600 hover:text-blue-500 text-xs"
                                                            >
                                                                <FileTextIcon size={12} className="mr-1" /> {ev.name || ev.check_name || "Evidence Document"}{isAutomated && ev.stale ? ` (${ev.stale_days} days old)` : ''}
                                                            </a>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-1 flex-shrink-0">
                                                        {ev.agent_type === 'powershell' && (
                                                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300">
                                                                PS
                                                            </span>
                                                        )}
                                                        {isAutomated ? (
                                                            <span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">Automated</span>
                                                        ) : (
                                                            <span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">Manual</span>
                                                        )}
                                                        {isAutomated && ev.stale && (
                                                            <span className="px-1.5 py-0.5 text-xs font-semibold rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 flex items-center gap-0.5">
                                                                <AlertCircleIcon size={10} className="mr-0.5" />Stale
                                                            </span>
                                                        )}
                                                        {!isAutomated && evId && (
                                                            <button
                                                                onClick={() => handleDeleteEvidence(asset.id, evId)}
                                                                disabled={!!deletingMap[evId]}
                                                                className="text-red-500 hover:text-red-700 disabled:opacity-40"
                                                                title="Delete evidence"
                                                                aria-label="Delete evidence"
                                                            >
                                                                <TrashIcon size={13} />
                                                            </button>
                                                        )}
                                                    </div>
                                                  </div>
                                                  {evId && (
                                                    <EvidenceReviewPanel
                                                      evidenceId={evId}
                                                      evidenceStatus={ev.status}
                                                      onStatusChange={() => {
                                                        if (typeof onUpdateStatus === 'function') {
                                                          onUpdateStatus(asset.id, statusRecord?.status || 'Pending_Evidence');
                                                        }
                                                      }}
                                                    />
                                                  )}
                                                </React.Fragment>
                                                );
                                            })}

                                            {/* AI Evaluation Block */}
                                            {statusRecord.ai_evaluation && (
                                                <div className={`mt-3 p-3 rounded-md text-xs border ${statusRecord.ai_evaluation.verified ? 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/30 dark:border-green-800 dark:text-green-300' : 'bg-red-50 border-red-200 text-red-800 dark:bg-red-900/30 dark:border-red-800 dark:text-red-300'}`}>
                                                    <div className="flex items-center justify-between mb-1.5 border-b border-opacity-20 pb-1.5 border-current">
                                                        <div className="font-bold flex items-center">
                                                            <BrainCircuitIcon size={14} className="mr-1.5" />
                                                            AI Auditor: {statusRecord.ai_evaluation.verified ? 'SUFFICIENT EVIDENCE' : 'INSUFFICIENT EVIDENCE'}
                                                        </div>
                                                        <div className="opacity-70 text-xs">
                                                            {statusRecord.ai_evaluation.model_used.split('/').pop()}
                                                        </div>
                                                    </div>
                                                    <div className="italic break-words">
                                                        "{statusRecord.ai_evaluation.reasoning}"
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <span className="text-gray-400 italic text-xs">No evidence attached</span>
                                    )}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                    <div className="flex flex-col items-end gap-1">
                                        <div className="flex items-center gap-2">
                                            <button onClick={() => handleUpdateStatus(asset.id, 'Compliant')} disabled={!!updatingMap[asset.id]} className="text-green-600 hover:text-green-900 disabled:opacity-40" title="Mark Compliant" aria-label="Mark Compliant"><CheckIcon size={18} /></button>
                                            <button onClick={() => handleUpdateStatus(asset.id, 'Non-Compliant')} disabled={!!updatingMap[asset.id]} className="text-red-600 hover:text-red-900 disabled:opacity-40" title="Mark Non-Compliant" aria-label="Mark Non-Compliant"><XIcon size={18} /></button>
                                            <button
                                                onClick={() => handleUploadClick(asset.id)}
                                                className={`${ingestingMap[asset.id] ? 'text-purple-600 animate-pulse' : 'text-blue-600 hover:text-blue-900'}`}
                                                title={ingestingMap[asset.id] ? "Ingesting to LLM..." : "Upload Evidence & Ingest"}
                                                aria-label={ingestingMap[asset.id] ? "Ingesting to LLM..." : "Upload Evidence & Ingest"}
                                                disabled={ingestingMap[asset.id]}
                                            >
                                                <UploadIcon size={18} />
                                            </button>
                                        </div>
                                        <input
                                            type="text"
                                            placeholder="Description (optional)"
                                            value={descriptionMap[asset.id] || ''}
                                            onChange={e => setDescriptionMap(prev => ({ ...prev, [asset.id]: e.target.value }))}
                                            className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-0.5 w-44 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400"
                                        />
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
            <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                onChange={handleFileChange}
                accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"
            />
        </div>
    );
};
