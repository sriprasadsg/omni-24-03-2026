import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

interface LocalPackage {
    filename: string;
    pkg_name: string;
    pkg_version: string;
    pkg_type: string;
    checksum: string;
    size_bytes: number;
    uploaded_by: string;
    uploaded_at: string;
}

export const LocalRepoManager: React.FC = () => {
    const [packages, setPackages] = useState<LocalPackage[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [pkgType, setPkgType] = useState('pip');
    const [message, setMessage] = useState('');

    const fetchPackages = async () => {
        setLoading(true);
        try {
            const res = await authFetch('/api/repo/packages');
            if (res.ok) {
                const data = await res.json();
                setPackages(data);
            }
        } catch (e) {
            console.error('Failed to fetch local packages', e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPackages();
    }, []);

    const handleUpload = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!file) return;

        setUploading(true);
        setMessage('');

        const formData = new FormData();
        formData.append('file', file);

        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`/api/repo/upload?pkg_type=${pkgType}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });

            if (res.ok) {
                setMessage('Package uploaded securely.');
                setFile(null);
                fetchPackages();
            } else {
                const err = await res.json();
                setMessage(`Error: ${err.detail || 'Upload failed'}`);
            }
        } catch (e) {
            setMessage('Network error during upload.');
        } finally {
            setUploading(false);
        }
    };

    const handleDelete = async (filename: string) => {
        if (!confirm(`Delete ${filename} from the local repository?`)) return;

        try {
            const res = await authFetch(`/api/repo/packages/${encodeURIComponent(filename)}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                fetchPackages();
            } else {
                alert('Deletion failed. Ensure you have admin privileges.');
            }
        } catch (e) {
            alert('Error deleting package.');
        }
    };

    return (
        <div className="space-y-6">
            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md">
                <h3 className="text-xl font-bold mb-4">Upload New Package</h3>
                <form onSubmit={handleUpload} className="space-y-4 max-w-lg">
                    {message && (
                        <div className="bg-blue-50 text-blue-800 p-3 rounded text-sm">
                            {message}
                        </div>
                    )}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Package File (.whl, .tar.gz, .deb)</label>
                        <input
                            type="file"
                            required
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100 dark:file:bg-gray-700 dark:file:text-white"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Package Type</label>
                        <select
                            value={pkgType}
                            onChange={(e) => setPkgType(e.target.value)}
                            className="w-full border-gray-300 rounded-md shadow-sm focus:border-primary-500 focus:ring-primary-500 p-2 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                        >
                            <option value="pip">Python (pip / .whl)</option>
                            <option value="npm">Node.js (npm / .tgz)</option>
                            <option value="apt">Ubuntu (apt / .deb)</option>
                        </select>
                    </div>
                    <button
                        type="submit"
                        disabled={uploading || !file}
                        className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:bg-gray-400"
                    >
                        {uploading ? 'Uploading...' : 'Securely Upload Package'}
                    </button>
                </form>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                    <h3 className="text-lg font-semibold">Locally Hosted Packages</h3>
                    <button onClick={fetchPackages} className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200">
                        ↻ Refresh
                    </button>
                </div>
                {loading ? (
                    <div className="p-8 text-center text-gray-400">Loading internal repository...</div>
                ) : packages.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No packages hosted locally. Add packages above to bypass public internet registries.</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Filename</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Size</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Uploaded At</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {packages.map((pkg) => (
                                <tr key={pkg.filename}>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                                        {pkg.filename}
                                        <div className="text-xs text-gray-500">SHA256: {pkg.checksum.slice(0, 16)}...</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{pkg.pkg_type}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{(pkg.size_bytes / 1024).toFixed(1)} KB</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{new Date(pkg.uploaded_at).toLocaleString()}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                                        <button
                                            onClick={() => handleDelete(pkg.filename)}
                                            className="text-red-600 hover:text-red-900"
                                        >
                                            Delete
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};
