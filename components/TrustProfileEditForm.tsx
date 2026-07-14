import React from 'react';
import { Plus, Trash2, Copy } from 'lucide-react';
import { showToast } from '../utils/toast';

export interface TrustProfileFormData {
    company_name: string;
    description: string;
    contact_email: string;
    logo_url: string;
    trust_slug?: string;
    trust_domain?: string;
    compliance_frameworks: string[];
    public_documents: { name: string, url: string }[];
    private_documents: { name: string, url: string }[];
}

interface TrustProfileEditFormProps {
    editForm: TrustProfileFormData;
    saving: boolean;
    onChange: (updater: (prev: TrustProfileFormData) => TrustProfileFormData) => void;
    onSave: () => void;
    onCancel: () => void;
}

const labelClass = "text-sm font-medium text-gray-900 dark:text-white mb-1";
const inputClass = "w-full text-sm border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-white";

export default function TrustProfileEditForm({ editForm, saving, onChange, onSave, onCancel }: TrustProfileEditFormProps) {
    const updateFrameworkAt = (index: number, value: string) => {
        onChange(prev => ({
            ...prev,
            compliance_frameworks: prev.compliance_frameworks.map((f, i) => i === index ? value : f)
        }));
    };

    const addFramework = () => {
        onChange(prev => ({ ...prev, compliance_frameworks: [...prev.compliance_frameworks, ''] }));
    };

    const removeFramework = (index: number) => {
        onChange(prev => ({
            ...prev,
            compliance_frameworks: prev.compliance_frameworks.filter((_, i) => i !== index)
        }));
    };

    const updateDocAt = (
        key: 'public_documents' | 'private_documents',
        index: number,
        field: 'name' | 'url',
        value: string
    ) => {
        onChange(prev => ({
            ...prev,
            [key]: prev[key].map((d, i) => i === index ? { ...d, [field]: value } : d)
        }));
    };

    const addDoc = (key: 'public_documents' | 'private_documents') => {
        onChange(prev => ({ ...prev, [key]: [...prev[key], { name: '', url: '' }] }));
    };

    const removeDoc = (key: 'public_documents' | 'private_documents', index: number) => {
        onChange(prev => ({ ...prev, [key]: prev[key].filter((_, i) => i !== index) }));
    };

    const publicUrl = editForm.trust_slug ? `${window.location.origin}/trust/${editForm.trust_slug}` : '';

    const handleCopyLink = () => {
        if (!publicUrl) return;
        navigator.clipboard.writeText(publicUrl);
        showToast('Public link copied to clipboard', 'success');
    };

    return (
        <div className="space-y-6">
            <div>
                <div className={labelClass}>Company Name</div>
                <input
                    className={inputClass}
                    value={editForm.company_name}
                    onChange={e => onChange(prev => ({ ...prev, company_name: e.target.value }))}
                />
            </div>

            <div>
                <div className={labelClass}>Description</div>
                <textarea
                    className={`${inputClass} min-h-[96px]`}
                    value={editForm.description}
                    onChange={e => onChange(prev => ({ ...prev, description: e.target.value }))}
                />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <div className={labelClass}>Contact Email</div>
                    <input
                        className={inputClass}
                        value={editForm.contact_email}
                        onChange={e => onChange(prev => ({ ...prev, contact_email: e.target.value }))}
                    />
                </div>
                <div>
                    <div className={labelClass}>Logo URL</div>
                    <input
                        className={inputClass}
                        value={editForm.logo_url}
                        onChange={e => onChange(prev => ({ ...prev, logo_url: e.target.value }))}
                    />
                </div>
            </div>

            <div>
                <div className={labelClass}>Compliance Frameworks</div>
                <div className="space-y-2">
                    {editForm.compliance_frameworks.map((fw, i) => (
                        <div key={i} className="flex items-center gap-2">
                            <input
                                className={inputClass}
                                value={fw}
                                onChange={e => updateFrameworkAt(i, e.target.value)}
                            />
                            <button type="button" onClick={() => removeFramework(i)} className="p-2 text-red-500 hover:bg-red-50 rounded" aria-label="Remove framework">
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}
                    <button type="button" onClick={addFramework} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
                        <Plus className="w-4 h-4" /> Add Framework
                    </button>
                </div>
            </div>

            <div>
                <div className={labelClass}>Public Documents</div>
                <div className="space-y-2">
                    {editForm.public_documents.map((doc, i) => (
                        <div key={i} className="flex items-center gap-2">
                            <input
                                className={inputClass}
                                placeholder="Name"
                                value={doc.name}
                                onChange={e => updateDocAt('public_documents', i, 'name', e.target.value)}
                            />
                            <input
                                className={inputClass}
                                placeholder="URL"
                                value={doc.url}
                                onChange={e => updateDocAt('public_documents', i, 'url', e.target.value)}
                            />
                            <button type="button" onClick={() => removeDoc('public_documents', i)} className="p-2 text-red-500 hover:bg-red-50 rounded" aria-label="Remove public document">
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}
                    <button type="button" onClick={() => addDoc('public_documents')} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
                        <Plus className="w-4 h-4" /> Add Public Document
                    </button>
                </div>
            </div>

            <div>
                <div className={labelClass}>Restricted Documents</div>
                <p className="text-xs text-gray-500 mb-2">The URL here is your internal admin reference only — it is never shown on the public page.</p>
                <div className="space-y-2">
                    {editForm.private_documents.map((doc, i) => (
                        <div key={i} className="flex items-center gap-2">
                            <input
                                className={inputClass}
                                placeholder="Name"
                                value={doc.name}
                                onChange={e => updateDocAt('private_documents', i, 'name', e.target.value)}
                            />
                            <input
                                className={inputClass}
                                placeholder="URL (admin-only reference)"
                                value={doc.url}
                                onChange={e => updateDocAt('private_documents', i, 'url', e.target.value)}
                            />
                            <button type="button" onClick={() => removeDoc('private_documents', i)} className="p-2 text-red-500 hover:bg-red-50 rounded" aria-label="Remove restricted document">
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}
                    <button type="button" onClick={() => addDoc('private_documents')} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
                        <Plus className="w-4 h-4" /> Add Restricted Document
                    </button>
                </div>
            </div>

            <div className="border-t border-gray-200 dark:border-gray-800 pt-6">
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3">Sharing</h4>
                <div className="space-y-4">
                    <div>
                        <div className={labelClass}>Public Trust Page URL</div>
                        <div className="flex items-center gap-2">
                            <input className={`${inputClass} bg-gray-50 dark:bg-gray-800`} value={publicUrl} readOnly />
                            <button
                                type="button"
                                onClick={handleCopyLink}
                                className="flex items-center gap-1 px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg whitespace-nowrap"
                            >
                                <Copy className="w-4 h-4" /> Copy Link
                            </button>
                        </div>
                    </div>
                    <div>
                        <div className={labelClass}>Custom Domain (optional)</div>
                        <input
                            className={inputClass}
                            placeholder="trust.example.com"
                            value={editForm.trust_domain || ''}
                            onChange={e => onChange(prev => ({ ...prev, trust_domain: e.target.value }))}
                        />
                        <p className="text-xs text-gray-500 mt-1">
                            Point a CNAME record for this domain at your platform URL, then enter it here. DNS and TLS setup are your responsibility — this only tells the app which domain to recognize.
                        </p>
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
                <button
                    type="button"
                    onClick={onSave}
                    disabled={saving}
                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
                >
                    {saving ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                    type="button"
                    onClick={onCancel}
                    disabled={saving}
                    className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}
