import React, { useState, useEffect } from 'react';
import {
    Users, Shield, FileText, CheckCircle, AlertTriangle, Plus, Search,
    MoreHorizontal, Building, Globe, Mail, Calendar, Link as LinkIcon
} from 'lucide-react';
import * as api from '../services/apiService';
import { VendorFormModal } from './VendorFormModal';

interface Vendor {
    id: string;
    name: string;
    website: string;
    criticality: 'Low' | 'Medium' | 'High' | 'Critical';
    category: string;
    contact_name: string;
    contact_email: string;
    contract_start: string;
    contract_end: string;
    status: 'Active' | 'Inactive' | 'Pending Review';
    assessments: VendorAssessment[];
    linked_sboms: string[];
}

interface VendorAssessment {
    id: string;
    assessment_date: string;
    reviewer: string;
    risk_score: number;
    status: string;
    findings: string[];
}

export default function VendorManagement() {
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [showAddModal, setShowAddModal] = useState(false);
    const [selectedVendor, setSelectedVendor] = useState<Vendor | null>(null);

    useEffect(() => {
        fetchVendors();
    }, []);

    const fetchVendors = async () => {
        try {
            const data = await api.fetchVendors();
            setVendors(data);
        } catch (error) {
            console.error('Error fetching vendors:', error);
        } finally {
            setLoading(false);
        }
    };

    const getCriticalityColor = (level: string) => {
        switch (level) {
            case 'Critical': return 'text-red-600 bg-red-100 dark:bg-red-900/30 dark:text-red-400';
            case 'High': return 'text-orange-600 bg-orange-100 dark:bg-orange-900/30 dark:text-orange-400';
            case 'Medium': return 'text-yellow-600 bg-yellow-100 dark:bg-yellow-900/30 dark:text-yellow-400';
            default: return 'text-green-600 bg-green-100 dark:bg-green-900/30 dark:text-green-400';
        }
    };

    const filteredVendors = vendors.filter(v =>
        v.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        v.category.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-teal-600 to-blue-600 bg-clip-text text-transparent">
                        Vendor Risk Management
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400">
                        Manage code suppliers, SaaS providers, and third-party risk assessments.
                    </p>
                </div>
                <button
                    onClick={() => setShowAddModal(true)}
                    className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                >
                    <Plus className="w-4 h-4" />
                    Add Vendor
                </button>
            </div>

            {/* Vendor Stats */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                {[
                    { label: 'Total Vendors', value: vendors.length, icon: Users, color: 'text-blue-600' },
                    { label: 'Critical Risk', value: vendors.filter(v => v.criticality === 'Critical').length, icon: AlertTriangle, color: 'text-red-600' },
                    { label: 'Pending Assessment', value: vendors.filter(v => v.assessments.length === 0).length, icon: FileText, color: 'text-orange-600' },
                    { label: 'Active Contracts', value: vendors.filter(v => v.status === 'Active').length, icon: CheckCircle, color: 'text-green-600' },
                ].map((stat, i) => (
                    <div key={i} className="bg-white dark:bg-[#0f1115] p-5 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm flex items-center gap-4">
                        <div className={`p-3 rounded-lg bg-gray-50 dark:bg-gray-800 ${stat.color}`}>
                            <stat.icon className="w-6 h-6" />
                        </div>
                        <div>
                            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">{stat.label}</div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Vendor List */}
            <div className="bg-white dark:bg-[#0f1115] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between">
                    <div className="relative max-w-sm w-full">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                            type="text"
                            placeholder="Search vendors..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-[#0b0c0e] border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                        />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-gray-50 dark:bg-[#0b0c0e] text-gray-500 dark:text-gray-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-3 font-medium">Vendor</th>
                                <th className="px-6 py-3 font-medium">Category</th>
                                <th className="px-6 py-3 font-medium">Criticality</th>
                                <th className="px-6 py-3 font-medium">Contact</th>
                                <th className="px-6 py-3 font-medium">Last Assessment</th>
                                <th className="px-6 py-3 font-medium text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                            {filteredVendors.map(vendor => (
                                <tr key={vendor.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-full bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center text-teal-600 dark:text-teal-400 font-bold">
                                                {vendor.name.charAt(0)}
                                            </div>
                                            <div>
                                                <div className="font-medium text-gray-900 dark:text-gray-100">{vendor.name}</div>
                                                <a href={vendor.website} target="_blank" rel="noreferrer" className="text-xs text-blue-500 hover:underline flex items-center gap-1">
                                                    Website <Globe className="w-3 h-3" />
                                                </a>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                                        {vendor.category}
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className={`px-2 py-1 rounded-md text-xs font-semibold ${getCriticalityColor(vendor.criticality)}`}>
                                            {vendor.criticality}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="text-gray-900 dark:text-gray-100">{vendor.contact_name}</div>
                                        <div className="text-xs text-gray-500">{vendor.contact_email}</div>
                                    </td>
                                    <td className="px-6 py-4">
                                        {vendor.assessments.length > 0 ? (
                                            <div>
                                                <div className="text-gray-900 dark:text-gray-100">{new Date(vendor.assessments[0].assessment_date).toLocaleDateString()}</div>
                                                <div className="text-xs text-gray-500">Score: {vendor.assessments[0].risk_score}/100</div>
                                            </div>
                                        ) : (
                                            <span className="text-gray-400 italic">None</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <button className="text-gray-400 hover:text-teal-600 p-2">
                                            <MoreHorizontal className="w-5 h-5" />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
            <VendorFormModal
                isOpen={showAddModal}
                onClose={() => setShowAddModal(false)}
                onSubmit={async (data) => {
                    await api.createVendor(data);
                    fetchVendors();
                }}
            />
        </div >
    );
}

