import React, { useState } from 'react';
import { XIcon } from './icons';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

export const ReportsModal = ({ isOpen, onClose, frameworkId }: { isOpen: boolean; onClose: () => void; frameworkId?: string }) => {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      setLoading(true);
      api.fetchComplianceReports(frameworkId).then(setReports).finally(() => setLoading(false));
    }
  }, [isOpen, frameworkId]);

  const handleDownload = async (report: any) => {
    setDownloading(report.filename);
    try {
      await api.downloadComplianceReport(report.filename);
    } catch (error) {
      console.error('Download error:', error);
      showToast('Failed to download file. Please try again.', 'error');
    } finally {
      setDownloading(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Compliance Reports</h3>
          <button onClick={onClose}><XIcon size={20} className="text-gray-500" /></button>
        </div>
        {loading ? (
          <div className="text-center py-4 text-gray-500 dark:text-gray-400">Loading...</div>
        ) : (
          <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
            <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
              <tr>
                <th className="px-4 py-2">Filename</th>
                <th className="px-4 py-2">Created</th>
                <th className="px-4 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report, idx) => (
                <tr key={idx} className="bg-white dark:bg-gray-800 border-b dark:border-gray-700">
                  <td className="px-4 py-2 font-medium text-gray-900 dark:text-white">{report.filename}</td>
                  <td className="px-4 py-2">{report.generatedAt ? new Date(report.generatedAt).toLocaleString() : '—'}</td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => handleDownload(report)}
                      disabled={downloading === report.filename}
                      className="text-primary-600 hover:text-primary-800 dark:text-primary-400 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {downloading === report.filename ? 'Downloading...' : `Download ${report.filename.endsWith('.xlsx') ? 'Excel' : report.filename.endsWith('.pdf') ? 'PDF' : 'CSV'}`}
                    </button>
                  </td>
                </tr>
              ))}
              {reports.length === 0 && (
                <tr>
                  <td colSpan={3} className="text-center py-4">No reports found.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
