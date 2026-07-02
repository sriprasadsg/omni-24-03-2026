import React from 'react';
import { ShieldCheckIcon, AlertTriangleIcon, UploadIcon, XIcon } from './icons';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

const DEPARTMENTS = ['HR', 'Finance', 'Management', 'Legal', 'IT', 'Operations', 'Audit', 'Risk', 'Other'];

type ValidationResult = {
    verdict: 'RELEVANT' | 'IRRELEVANT' | 'UNCLEAR' | 'SKIPPED';
    confidence: number;
    reasoning: string;
    text_extracted: boolean;
    text_preview: string;
};

const VERDICT_STYLES: Record<string, { bg: string; text: string; label: string }> = {
    RELEVANT:   { bg: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',   text: 'text-green-800 dark:text-green-300', label: 'Relevant' },
    IRRELEVANT: { bg: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',           text: 'text-red-800 dark:text-red-300',     label: 'May not be relevant' },
    UNCLEAR:    { bg: 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800',    text: 'text-amber-800 dark:text-amber-300', label: 'Relevance unclear' },
    SKIPPED:    { bg: 'bg-gray-50 dark:bg-gray-700/30 border-gray-200 dark:border-gray-600',        text: 'text-gray-600 dark:text-gray-400',   label: 'Validation skipped' },
};

export const ControlEvidenceUploadModal = ({
    controlId,
    onClose,
    onUploaded,
}: {
    controlId: string;
    onClose: () => void;
    onUploaded: () => void;
}) => {
    const [file, setFile] = React.useState<File | null>(null);
    const [description, setDescription] = React.useState('');
    const [department, setDepartment] = React.useState('IT');
    const [uploading, setUploading] = React.useState(false);
    const [dragOver, setDragOver] = React.useState(false);
    const [validation, setValidation] = React.useState<ValidationResult | null>(null);
    const inputRef = React.useRef<HTMLInputElement>(null);

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files[0];
        if (f) { setFile(f); setValidation(null); }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!file) return;
        setUploading(true);
        setValidation(null);
        try {
            const res = await api.uploadControlEvidence(controlId, file, description, department);
            if (res.success) {
                const v: ValidationResult = res.validation || { verdict: 'SKIPPED', confidence: 0, reasoning: 'No validation result returned.', text_extracted: false, text_preview: '' };
                setValidation(v);
                onUploaded();
                if (v.verdict !== 'IRRELEVANT') {
                    showToast(`Evidence uploaded for ${controlId}`, 'success');
                } else {
                    showToast(`Evidence uploaded — AI flagged possible relevance issue.`, 'warning');
                }
            } else {
                showToast('Upload failed', 'error');
            }
        } catch (err: any) {
            showToast(`Upload error: ${err?.message || 'Unknown'}`, 'error');
        } finally {
            setUploading(false);
        }
    };

    const style = validation ? (VERDICT_STYLES[validation.verdict] || VERDICT_STYLES.SKIPPED) : null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-lg shadow-xl">
                <div className="flex justify-between items-center mb-4">
                    <div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">Upload Evidence</h3>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Control: <span className="font-mono font-semibold">{controlId}</span></p>
                    </div>
                    <button onClick={onClose}><XIcon size={20} className="text-gray-500" /></button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Department / Owner</label>
                        <select value={department} onChange={e => setDepartment(e.target.value)}
                            className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm">
                            {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                        <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} maxLength={1000}
                            placeholder="Briefly describe this evidence (e.g., HR policy document, signed BAA, audit report)"
                            className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm resize-none" />
                    </div>
                    <div
                        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={handleDrop}
                        onClick={() => inputRef.current?.click()}
                        className={`border-2 border-dashed rounded-lg p-5 text-center cursor-pointer transition-colors ${dragOver ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-gray-300 dark:border-gray-600 hover:border-primary-400'}`}
                    >
                        <input ref={inputRef} type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"
                            onChange={e => { if (e.target.files?.[0]) { setFile(e.target.files[0]); setValidation(null); } }} />
                        {file ? (
                            <div className="text-sm text-gray-800 dark:text-gray-200">
                                <span className="font-medium">{file.name}</span>
                                <span className="text-gray-500 ml-2">({(file.size / 1024).toFixed(0)} KB)</span>
                            </div>
                        ) : (
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                                <UploadIcon size={24} className="mx-auto mb-2 opacity-50" />
                                <p>Drop file here or click to browse</p>
                                <p className="text-xs mt-1">PDF, PNG, DOCX, XLSX — max 25 MB</p>
                            </div>
                        )}
                    </div>

                    {/* AI Validation Result */}
                    {validation && style && (
                        <div className={`rounded-lg border p-3 ${style.bg}`}>
                            <div className="flex items-start gap-2">
                                <div className="flex-shrink-0 mt-0.5">
                                    {validation.verdict === 'RELEVANT' ? (
                                        <ShieldCheckIcon size={16} className="text-green-600 dark:text-green-400" />
                                    ) : validation.verdict === 'IRRELEVANT' ? (
                                        <AlertTriangleIcon size={16} className="text-red-600 dark:text-red-400" />
                                    ) : (
                                        <AlertTriangleIcon size={16} className="text-amber-500" />
                                    )}
                                </div>
                                <div className="min-w-0">
                                    <p className={`text-xs font-semibold ${style.text}`}>
                                        AI Validation: {style.label}
                                        {validation.confidence > 0 && (
                                            <span className="font-normal ml-1 opacity-70">({Math.round(validation.confidence * 100)}% confidence)</span>
                                        )}
                                    </p>
                                    <p className={`text-xs mt-0.5 ${style.text} opacity-90`}>{validation.reasoning}</p>
                                    {!validation.text_extracted && validation.verdict !== 'SKIPPED' && (
                                        <p className="text-xs mt-1 opacity-60 italic">Note: Text could not be extracted — assessment based on filename and description only.</p>
                                    )}
                                    {validation.verdict === 'IRRELEVANT' && (
                                        <p className="text-xs mt-1 font-medium text-red-700 dark:text-red-300">
                                            The file was saved but may not satisfy this control. Consider uploading a more relevant document.
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="flex justify-between items-center gap-3">
                        <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
                            <ShieldCheckIcon size={12} />
                            AI validates document relevance after upload
                        </p>
                        <div className="flex gap-3">
                            <button type="button" onClick={onClose}
                                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 rounded-md">
                                {validation ? 'Close' : 'Cancel'}
                            </button>
                            {!validation && (
                                <button type="submit" disabled={!file || uploading}
                                    className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 rounded-md flex items-center gap-2">
                                    {uploading ? (
                                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
                                    ) : <UploadIcon size={14} />}
                                    {uploading ? 'Uploading & validating...' : 'Upload Evidence'}
                                </button>
                            )}
                        </div>
                    </div>
                </form>
            </div>
        </div>
    );
};
