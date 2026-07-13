import React, { useState, useEffect } from 'react';
import * as api from '../services/apiService';

/**
 * TrustPage Component
 *
 * Provides an admin-side preview of the public trust page.
 */
export default function TrustPage() {
    const [trustSlug, setTrustSlug] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchSlug = async () => {
            try {
                // Fetch existing profile to get the slug
                const profile = await api.fetchTrustProfile();
                if (profile && profile.trust_slug) {
                    setTrustSlug(profile.trust_slug);
                }
            } catch (error) {
                console.error("Error fetching trust profile slug", error);
            } finally {
                setLoading(false);
            }
        };
        fetchSlug();
    }, []);

    if (loading) return <div className="p-8 text-center text-gray-500">Loading preview...</div>;

    if (!trustSlug) {
        return (
            <div className="p-8 text-center text-gray-500">
                No trust page slug found. Please configure your public trust profile first.
            </div>
        );
    }

    // Embed the public trust page
    const publicUrl = `/trust/${trustSlug}`;

    return (
        <div className="w-full h-screen bg-gray-100 dark:bg-gray-900">
            <div className="p-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Public Preview</h2>
                <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-700 text-sm font-medium">
                    Open in new tab
                </a>
            </div>
            <iframe
                src={publicUrl}
                className="w-full h-[calc(100vh-64px)] border-none"
                title="Public Trust Page Preview"
            />
        </div>
    );
}
