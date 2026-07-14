import React, { useState, useEffect } from 'react';
import {
    Shield, CheckCircle, FileText, Lock, Globe, Mail,
    ExternalLink, Eye, Download, UserCheck, Clock, XCircle,
    Pencil, Copy
} from 'lucide-react';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
import TrustProfileEditForm from './TrustProfileEditForm';

interface TrustProfile {
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

interface AccessRequest {
    id: string;
    requester_email: string;
    company: string;
    reason: string;
    status: 'Pending' | 'Approved' | 'Denied';
    requested_at: string;
}

export default function TrustCenter() {
    const [activeTab, setActiveTab] = useState<'profile' | 'requests'>('profile');
    const [profile, setProfile] = useState<TrustProfile | null>(null);
    const [requests, setRequests] = useState<AccessRequest[]>([]);
    const [loading, setLoading] = useState(true);
    const [isEditing, setIsEditing] = useState(false);
    const [editForm, setEditForm] = useState<TrustProfile | null>(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const [profile, requests] = await Promise.all([
                api.fetchTrustProfile(),
                api.fetchTrustRequests()
            ]);

            if (profile) setProfile(profile);
            setRequests(requests);
        } catch (error) {
            console.error("Error fetching trust center data", error);
        } finally {
            setLoading(false);
        }
    };

    const handleRequestAction = async (id: string, status: 'Approved' | 'Denied') => {
        try {
            const result = await api.updateTrustRequest(id, status, 'Current User');
            if (result) {
                setRequests(prev => prev.map(r => r.id === id ? { ...r, status } : r));
            }
        } catch (error) {
            console.error("Error updating request", error);
        }
    };

    const startEditing = () => {
        if (!profile) return;
        setEditForm({ ...profile });
        setIsEditing(true);
    };

    const cancelEditing = () => {
        setEditForm(null);
        setIsEditing(false);
    };

    const handleSaveProfile = async () => {
        if (!editForm) return;
        setSaving(true);
        try {
            const updated = await api.updateTrustProfile(editForm);
            setProfile(updated);
            setIsEditing(false);
            setEditForm(null);
            showToast('Trust profile saved.', 'success');
        } catch (error) {
            console.error("Error saving trust profile", error);
            showToast('Could not save trust profile. Please try again.', 'error');
        } finally {
            setSaving(false);
        }
    };

    const handleCopyLink = () => {
        if (!profile?.trust_slug) return;
        const url = `${window.location.origin}/trust/${profile.trust_slug}`;
        navigator.clipboard.writeText(url);
        showToast('Public link copied to clipboard', 'success');
    };

    if (loading) return <div className="p-8 text-center text-gray-500">Loading Trust Center...</div>;
    if (!profile) return <div className="p-8 text-center text-red-500">Failed to load profile.</div>;

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">
                        Trust Center
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400">
                        Manage your public security profile and access requests.
                    </p>
                </div>
                <div className="flex bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
                    <button
                        onClick={() => setActiveTab('profile')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === 'profile'
                                ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                            }`}
                    >
                        Public Profile
                    </button>
                    <button
                        onClick={() => setActiveTab('requests')}
                        className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === 'requests'
                                ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                            }`}
                    >
                        Access Requests
                        {requests.filter(r => r.status === 'Pending').length > 0 && (
                            <span className="ml-2 px-1.5 py-0.5 text-xs bg-red-100 text-red-600 rounded-full">
                                {requests.filter(r => r.status === 'Pending').length}
                            </span>
                        )}
                    </button>
                </div>
            </div>

            {activeTab === 'profile' ? (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Profile Preview */}
                    <div className="lg:col-span-2 space-y-6">
                        <div className="bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm p-8">
                            {isEditing && editForm ? (
                                <TrustProfileEditForm
                                    editForm={editForm}
                                    saving={saving}
                                    onChange={updater => setEditForm(prev => prev ? updater(prev) : prev)}
                                    onSave={handleSaveProfile}
                                    onCancel={cancelEditing}
                                />
                            ) : (
                                <>
                                    <div className="flex items-start justify-between mb-6">
                                        <div className="flex items-center gap-4">
                                            <div className="w-16 h-16 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center text-blue-600 dark:text-blue-400">
                                                <Shield className="w-8 h-8" />
                                            </div>
                                            <div>
                                                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{profile.company_name}</h2>
                                                <div className="flex items-center gap-4 text-sm text-gray-500 mt-1">
                                                    <span className="flex items-center gap-1"><Globe className="w-3 h-3" /> Publicly Visible</span>
                                                    <span className="flex items-center gap-1"><Mail className="w-3 h-3" /> {profile.contact_email}</span>
                                                </div>
                                            </div>
                                        </div>
                                        <button
                                            onClick={startEditing}
                                            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg whitespace-nowrap"
                                        >
                                            <Pencil className="w-4 h-4" /> Edit Profile
                                        </button>
                                    </div>

                                    <p className="text-gray-600 dark:text-gray-300 mb-8 leading-relaxed">
                                        {profile.description}
                                    </p>

                                    <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Compliance & Security Frameworks</h3>
                                    <div className="flex flex-wrap gap-2 mb-8">
                                        {profile.compliance_frameworks.map((fw, i) => (
                                            <span key={i} className="px-3 py-1.5 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-full text-sm font-medium border border-green-100 dark:border-green-900/30 flex items-center gap-1.5">
                                                <CheckCircle className="w-3 h-3" /> {fw}
                                            </span>
                                        ))}
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                                        <div>
                                            <h4 className="font-medium text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                                                <Globe className="w-4 h-4 text-gray-400" /> Public Resources
                                            </h4>
                                            <ul className="space-y-2">
                                                {profile.public_documents.map((doc, i) => (
                                                    <li key={i} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg group hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                                                        <span className="text-sm text-gray-700 dark:text-gray-300">{doc.name}</span>
                                                        <button className="text-blue-500 hover:text-blue-600"><Download className="w-4 h-4" /></button>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                        <div>
                                            <h4 className="font-medium text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                                                <Lock className="w-4 h-4 text-gray-400" /> Restricted Access
                                            </h4>
                                            <ul className="space-y-2">
                                                {profile.private_documents.map((doc, i) => (
                                                    <li key={i} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-dashed border-gray-300 dark:border-gray-700">
                                                        <span className="text-sm text-gray-600 dark:text-gray-400">{doc.name}</span>
                                                        <span className="text-xs text-gray-400 flex items-center gap-1"><Lock className="w-3 h-3" /> NDA Required</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    </div>

                                    <div className="border-t border-gray-200 dark:border-gray-800 pt-6">
                                        <h4 className="font-semibold text-gray-900 dark:text-white mb-3">Sharing</h4>
                                        <div className="space-y-4">
                                            <div>
                                                <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">Public Trust Page URL</div>
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        className="w-full text-sm border border-gray-300 dark:border-gray-700 rounded-lg px-3 py-2 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white"
                                                        value={profile.trust_slug ? `${window.location.origin}/trust/${profile.trust_slug}` : ''}
                                                        readOnly
                                                    />
                                                    <button
                                                        onClick={handleCopyLink}
                                                        className="flex items-center gap-1 px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg whitespace-nowrap"
                                                    >
                                                        <Copy className="w-4 h-4" /> Copy Link
                                                    </button>
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">Custom Domain (optional)</div>
                                                <div className="text-sm text-gray-700 dark:text-gray-300">
                                                    {profile.trust_domain || <span className="text-gray-400">Not set</span>}
                                                </div>
                                                <p className="text-xs text-gray-500 mt-1">
                                                    Point a CNAME record for this domain at your platform URL, then enter it here. DNS and TLS setup are your responsibility — this only tells the app which domain to recognize.
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Quick Stats / Info */}
                    <div className="space-y-6">
                        <div className="bg-white dark:bg-[#0f1115] p-5 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm">
                            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Trust Analytics</h3>
                            <div className="space-y-4">
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-500 text-sm">Profile Views (30d)</span>
                                    <span className="font-bold">1,245</span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-500 text-sm">Document Downloads</span>
                                    <span className="font-bold">342</span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-500 text-sm">Access Requests</span>
                                    <span className="font-bold">{requests.length}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-gray-50 dark:bg-[#0b0c0e] text-gray-500 dark:text-gray-400 uppercase text-xs">
                                <tr>
                                    <th className="px-6 py-3 font-medium">Remote User</th>
                                    <th className="px-6 py-3 font-medium">Company</th>
                                    <th className="px-6 py-3 font-medium">Reason</th>
                                    <th className="px-6 py-3 font-medium">Date</th>
                                    <th className="px-6 py-3 font-medium">Status</th>
                                    <th className="px-6 py-3 font-medium text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                {requests.map(req => (
                                    <tr key={req.id}>
                                        <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                                            {req.requester_email}
                                        </td>
                                        <td className="px-6 py-4 text-gray-600 dark:text-gray-400">{req.company}</td>
                                        <td className="px-6 py-4 text-gray-600 dark:text-gray-400">{req.reason}</td>
                                        <td className="px-6 py-4 text-gray-500">{new Date(req.requested_at).toLocaleDateString()}</td>
                                        <td className="px-6 py-4">
                                            <span className={`px-2 py-1 rounded-full text-xs font-semibold ${req.status === 'Approved' ? 'bg-green-100 text-green-700' :
                                                    req.status === 'Denied' ? 'bg-red-100 text-red-700' :
                                                        'bg-yellow-100 text-yellow-700'
                                                }`}>
                                                {req.status}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            {req.status === 'Pending' && (
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        onClick={() => handleRequestAction(req.id, 'Approved')}
                                                        className="p-1 text-green-600 hover:bg-green-50 rounded"
                                                        title="Approve"
                                                    >
                                                        <UserCheck className="w-5 h-5" />
                                                    </button>
                                                    <button
                                                        onClick={() => handleRequestAction(req.id, 'Denied')}
                                                        className="p-1 text-red-600 hover:bg-red-50 rounded"
                                                        title="Deny"
                                                    >
                                                        <XCircle className="w-5 h-5" />
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {requests.length === 0 && (
                            <div className="p-8 text-center text-gray-500">No requests found.</div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
