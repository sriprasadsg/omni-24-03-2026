
import React, { useState, useRef, useEffect } from 'react';
import { UploadIcon, XIcon, AlertTriangleIcon, CheckCircleIcon } from './icons';
import * as api from '../services/apiService';

interface ManifestEntry { filename: string; control_id: string; }
interface BulkError { filename: string; error: string; }
interface BulkEvidenceUploadModalProps { onClose: () => void; onUploaded: () => void; }

export const BulkEvidenceUploadModal: React.FC<BulkEvidenceUploadModalProps> = ({ onClose, onUploaded }) => {
    const [zipFile, setZipFile] = useState<File | null>(null);
    const [manifest, setManifest] = useState<ManifestEntry[]>([]);
    const [manifestFileName, setManifestFileName] = useState('');
    const [manifestParseError, setManifestParseError] = useState<string | null>(null);
    const [uploading, setUploading] = useState(false);
    const [validationErrors, setValidationErrors] = useState<BulkError[]>([]);
    const [fatalError, setFatalError] = useState<string | null>(null);
    const [successResult, setSuccessResult] = useState<{ committed: number; batch_id: string } | null>(null);

    const zipRef = useRef<HTMLInputElement>(null);
    const manifestRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [onClose]);

    const fmtSize = (b: number) => b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${(b / 1024).toFixed(0)} KB`;

    const handleZipChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files?.[0]) setZipFile(e.target.files[0]);
    };

    const handleManifestChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const f = e.target.files?.[0];
        if (!f) return;
        try {
            const parsed = JSON.parse(await f.text());
            if (!Array.isArray(parsed) || !parsed.length) {
                return setManifestParseError('Invalid manifest: must be a non-empty JSON array');
            }
            if (parsed.some((it: any) => !it.filename || !it.control_id)) {
                return setManifestParseError('Each entry needs filename and control_id');
            }
            setManifest(parsed); setManifestFileName(f.name); setManifestParseError(null);
        } catch (err: any) { setManifestParseError(`Invalid JSON: ${err.message}`); }
    };

    const handleSubmit = async () => {
        if (!zipFile || !manifest.length || uploading) return;
        setUploading(true); setValidationErrors([]); setFatalError(null);
        try {
            const res = await api.uploadBulkEvidence(zipFile, manifest);
            setSuccessResult({ committed: res.committed, batch_id: res.batch_id });
            onUploaded();
        } catch (err: any) {
            if (Array.isArray(err.detail?.errors)) setValidationErrors(err.detail.errors);
            else if (err.status === 413) setFatalError('Zip file exceeds the 200 MB limit. Reduce the batch size and try again.');
            else if (typeof err.detail === 'string' && err.detail.includes('not a valid zip'))
                setFatalError('The selected file is not a valid zip archive. Select a .zip file and try again.');
            else if (typeof err.detail === 'string' && err.detail.includes('50 entries'))
                setFatalError('Manifest exceeds 50 entries. Split the batch and upload separately.');
            else setFatalError('Upload failed. Please try again. If the problem persists, contact support.');
        } finally { setUploading(false); }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
            role="dialog" aria-modal="true" aria-labelledby="bulk-modal-heading">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-4">
                    <h3 id="bulk-modal-heading" className="text-lg font-bold text-gray-900 dark:text-gray-100">Bulk Evidence Upload</h3>
                    <button onClick={onClose} aria-label="Close bulk evidence upload modal" className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                        <XIcon size={18} />
                    </button>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    Upload a zip file and a JSON manifest to attach multiple evidence files to controls.
                </p>

                {!successResult ? (<>
                    {/* Section 1: Zip */}
                    <div className="mb-4">
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">1. Select zip file</p>
                        <div role="button" tabIndex={0} aria-label="Select zip file for bulk upload"
                            onClick={() => zipRef.current?.click()}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') zipRef.current?.click(); }}
                            className="border-2 border-dashed rounded-lg p-4 cursor-pointer text-sm border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                            {zipFile ? (
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                                        <UploadIcon size={14} /><span>{zipFile.name}</span>
                                        <span className="text-xs text-gray-400">({fmtSize(zipFile.size)})</span>
                                    </div>
                                    <button onClick={(e) => { e.stopPropagation(); setZipFile(null); }} aria-label="Clear zip" className="text-gray-400 hover:text-gray-600">
                                        <XIcon size={14} />
                                    </button>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-1 text-gray-500 dark:text-gray-400 py-2">
                                    <UploadIcon size={20} /><span>Drop zip here or click</span>
                                    <span className="text-xs text-gray-400">.zip only — max 200 MB</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Section 2: Manifest */}
                    <div className="mb-4">
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">2. Select manifest JSON</p>
                        <div
                            role="button"
                            tabIndex={0}
                            aria-label="Select manifest JSON file"
                            onClick={() => manifestRef.current?.click()}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); manifestRef.current?.click(); } }}
                            className="border-2 border-dashed rounded-lg p-4 cursor-pointer text-sm border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-gray-500 dark:text-gray-400">
                            {manifestFileName ? <span className="text-gray-700 dark:text-gray-300">{manifestFileName}</span> : <span>Click to select manifest JSON file</span>}
                        </div>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{'Each entry: {"filename": "file.pdf", "control_id": "CC6.1"}'}</p>
                        {manifestParseError && (
                            <div className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400 mt-1">
                                <AlertTriangleIcon size={12} /><span>{manifestParseError}</span>
                            </div>
                        )}
                    </div>

                    {/* Section 3: Preview */}
                    {manifest.length > 0 && (
                        <div className="mb-4">
                            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">3. Preview — {manifest.length} files mapped</p>
                            <div className="max-h-48 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700 rounded border border-gray-200 dark:border-gray-600">
                                {manifest.map((entry, i) => (
                                    <div key={i} className="flex justify-between px-3 py-1.5 text-sm">
                                        <span className="text-gray-700 dark:text-gray-300 truncate mr-2">{entry.filename}</span>
                                        <span className="flex items-center gap-1 shrink-0">
                                            <span className="text-gray-400">→</span>
                                            <span className="text-xs text-indigo-600 dark:text-indigo-400">{entry.control_id}</span>
                                        </span>
                                    </div>
                                ))}
                            </div>
                            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">PDF, PNG, JPEG, DOCX, XLSX — max 25 MB per file, 50 files per batch</p>
                        </div>
                    )}

                    {/* Validation errors (422) */}
                    {validationErrors.length > 0 && (
                        <div role="alert" className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 divide-y divide-amber-200 dark:divide-amber-800 mt-4">
                            <div className="flex items-start gap-2 px-3 py-2.5">
                                <AlertTriangleIcon size={16} className="text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                                <span className="text-sm font-semibold text-amber-800 dark:text-amber-300">Batch rejected — {validationErrors.length} file(s) failed validation</span>
                            </div>
                            <div className="max-h-48 overflow-y-auto">
                                {validationErrors.map((e, i) => (
                                    <div key={i} className="px-3 py-2">
                                        <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{e.filename}</p>
                                        <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">{e.error}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Fatal error */}
                    {fatalError && (
                        <div className="flex items-start gap-2 rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 px-3 py-2.5 mt-4">
                            <AlertTriangleIcon size={16} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-red-800 dark:text-red-300">{fatalError}</p>
                        </div>
                    )}
                </>) : (
                    /* Success */
                    <div role="status" className="text-center py-6">
                        <CheckCircleIcon size={32} className="mx-auto text-green-600 dark:text-green-400 mb-3" />
                        <p className="text-lg font-semibold text-green-700 dark:text-green-300">{successResult.committed} files uploaded successfully</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Evidence is now visible under each control.</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">Batch ID</p>
                        <p className="text-xs font-mono text-gray-600 dark:text-gray-300 mt-0.5 break-all">{successResult.batch_id}</p>
                    </div>
                )}

                {/* Footer */}
                <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button onClick={onClose} className="text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100">
                        {successResult ? 'Close' : 'Cancel'}
                    </button>
                    {!successResult && (
                        <button onClick={handleSubmit} disabled={!zipFile || !manifest.length || uploading} aria-busy={uploading}
                            className="inline-flex items-center px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-md shadow-sm transition-colors">
                            {uploading ? 'Uploading...' : 'Upload Batch'}
                        </button>
                    )}
                </div>
            </div>

            <input ref={zipRef} type="file" accept=".zip" className="hidden" onChange={handleZipChange} />
            <input ref={manifestRef} type="file" accept=".json" className="hidden" onChange={handleManifestChange} />
        </div>
    );
};
