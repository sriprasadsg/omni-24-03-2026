
import React, { useState, useMemo } from 'react';
import { ComplianceFramework, ControlStatus, Asset, AssetCompliance } from '../types';
import { AssetComplianceList } from './AssetComplianceList';
// FIX: Replaced non-existent LockIcon with ShieldLockIcon.
import { PaperclipIcon, ShieldCheckIcon, ClockIcon, AlertTriangleIcon, FilterIcon, HeartPulseIcon, CreditCardIcon, BookOpenCheckIcon, BinocularsIcon, ShieldIcon, SirenIcon, MessageSquareWarningIcon, HeartHandshakeIcon, BuildingIcon, ClipboardListIcon, ShieldLockIcon, PlusIcon, UploadIcon, XIcon, BrainCircuitIcon, ScaleIcon, DatabaseIcon, LayersIcon, ActivityIcon, RefreshCwIcon, UsersIcon, FileTextIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import * as api from '../services/apiService';

interface FrameworkDetailProps {
  framework: ComplianceFramework;
  assets: Asset[];
  assetComplianceData: AssetCompliance[];
}

const AddControlModal = ({ isOpen, onClose, onAdd }: { isOpen: boolean; onClose: () => void; onAdd: (data: any) => void }) => {
  const [formData, setFormData] = useState({ id: '', name: '', description: '', category: '' });

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd(formData);
    setFormData({ id: '', name: '', description: '', category: '' });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Add New Control</h3>
          <button onClick={onClose}><XIcon size={20} className="text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Control ID</label>
              <input type="text" required value={formData.id} onChange={e => setFormData({ ...formData, id: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" placeholder="e.g., CC1.1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
              <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" placeholder="Control Name" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
              <textarea value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" rows={3} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Category</label>
              <input type="text" value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" placeholder="Category" />
            </div>
          </div>
          <div className="mt-6 flex justify-end space-x-3">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md dark:bg-gray-700 dark:text-gray-300">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-md">Add Control</button>
          </div>
        </form>
      </div>
    </div>
  );
};

const ReportsModal = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      setLoading(true);
      api.fetchComplianceReports().then(setReports).finally(() => setLoading(false));
    }
  }, [isOpen]);

  const handleDownload = (report: any) => {
    try {
      setDownloading(report.filename);

      // Direct download using window.location since backend now sets proper Content-Disposition header
      window.location.href = report.url;

      // Clear downloading state after a short delay
      setTimeout(() => setDownloading(null), 1000);
    } catch (error) {
      console.error('Download error:', error);
      alert('Failed to download file. Please try again.');
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
                  <td className="px-4 py-2">{new Date(report.created).toLocaleString()}</td>
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

const statusClasses: Record<ControlStatus, string> = {
  Implemented: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  'In Progress': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  'Not Implemented': 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  'At Risk': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
};

// Merged category classes for all frameworks
const categoryClasses: Record<string, string> = {
  // HIPAA
  'Administrative Safeguard': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  'Physical Safeguard': 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  'Technical Safeguard': 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300',
  // NIST CSF
  'Identify': 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300',
  'Protect': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  'Detect': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
  'Respond': 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  'Recover': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  // ISO 42001 (AI)
  'AI Policy': 'bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-900/50 dark:text-fuchsia-300',
  'Internal Organization': 'bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-300',
  'Resources': 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/50 dark:text-cyan-300',
  'Impact Assessment': 'bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-300',
  'AI System Lifecycle': 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300',
  'Data for AI': 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300',
  'Third Party': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  'Use of AI Systems': 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300',
  // GDPR
  'Principles': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  'Rights of the Data Subject': 'bg-pink-100 text-pink-800 dark:bg-pink-900/50 dark:text-pink-300',
  'Controller and Processor': 'bg-slate-100 text-slate-800 dark:bg-slate-900/50 dark:text-slate-300',
  'Security of Personal Data': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  'Transfers': 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
};

const categoryIcons: Record<string, React.ReactNode> = {
  // HIPAA
  'Administrative Safeguard': <ClipboardListIcon size={12} className="mr-1.5" />,
  'Physical Safeguard': <BuildingIcon size={12} className="mr-1.5" />,
  'Technical Safeguard': <ShieldLockIcon size={12} className="mr-1.5" />,
  // NIST CSF
  'Identify': <BinocularsIcon size={12} className="mr-1.5" />,
  'Protect': <ShieldIcon size={12} className="mr-1.5" />,
  'Detect': <SirenIcon size={12} className="mr-1.5" />,
  'Respond': <MessageSquareWarningIcon size={12} className="mr-1.5" />,
  'Recover': <HeartHandshakeIcon size={12} className="mr-1.5" />,
  // ISO 42001 (AI)
  'AI Policy': <ScaleIcon size={12} className="mr-1.5" />,
  'Internal Organization': <UsersIcon size={12} className="mr-1.5" />,
  'Resources': <LayersIcon size={12} className="mr-1.5" />,
  'Impact Assessment': <ActivityIcon size={12} className="mr-1.5" />,
  'AI System Lifecycle': <RefreshCwIcon size={12} className="mr-1.5" />,
  'Data for AI': <DatabaseIcon size={12} className="mr-1.5" />,
  'Third Party': <BuildingIcon size={12} className="mr-1.5" />,
  'Use of AI Systems': <BrainCircuitIcon size={12} className="mr-1.5" />,
  // GDPR
  'Principles': <ScaleIcon size={12} className="mr-1.5" />,
  'Rights of the Data Subject': <UsersIcon size={12} className="mr-1.5" />,
  'Controller and Processor': <BuildingIcon size={12} className="mr-1.5" />,
  'Security of Personal Data': <ShieldCheckIcon size={12} className="mr-1.5" />,
  'Transfers': <ActivityIcon size={12} className="mr-1.5" />,
};


const statusOptions: (ControlStatus | 'All')[] = ['All', 'Implemented', 'In Progress', 'At Risk', 'Not Implemented'];

export const FrameworkDetail: React.FC<FrameworkDetailProps> = ({ framework, assets, assetComplianceData }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<ControlStatus | 'All'>('All');
  const [expandedControlId, setExpandedControlId] = useState<string | null>(null);
  const [isAddControlModalOpen, setIsAddControlModalOpen] = useState(false);
  const [isReportsModalOpen, setIsReportsModalOpen] = useState(false);
  const [reportFormat, setReportFormat] = useState<'csv' | 'excel' | 'pdf'>('csv');
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const { hasPermission } = useUser();
  const canManageEvidence = hasPermission('manage:compliance_evidence');

  const handleAddControl = async (data: any) => {
    try {
      await api.addComplianceControl(framework.id, data);
      alert('Control added successfully! Please refresh to see changes.'); // In real app, we'd refetch
      setIsAddControlModalOpen(false);
    } catch (e) {
      alert('Failed to add control');
    }
  };

  const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      try {
        const res = await api.importComplianceControls(framework.id, e.target.files[0]);
        alert(`Successfully imported ${res.count} controls! Please refresh.`);
      } catch (err) {
        alert('Import failed');
      }
    }
  };

  const handleCollectEvidence = async () => {
    try {
      // @ts-ignore
      const res = await api.triggerFrameworkScan(framework.id);
      if (res.success) {
        alert(`Scan initiated! ${res.message}`);
      } else {
        alert(`Failed to start scan: ${res.message}`);
      }
    } catch (e) {
      alert('Error triggering scan.');
      console.error(e);
    }
  };

  const handleGenerateReport = async () => {
    try {
      let res;
      // Select API based on format
      if (reportFormat === 'excel') {
        res = await api.generateExcelComplianceReport(framework.id);
      } else if (reportFormat === 'pdf') {
        res = await api.generatePDFComplianceReport(framework.id);
      } else {
        res = await api.generateComplianceReport(framework.id);
      }

      if (res.success) {
        alert(`${reportFormat.toUpperCase()} report generated successfully!`);
        setIsReportsModalOpen(true);
      }
    } catch (e) {
      alert('Failed to generate report');
    }
  };

  const statusSummary = useMemo(() => {
    const summary: Record<ControlStatus, number> = {
      'Implemented': 0,
      'In Progress': 0,
      'At Risk': 0,
      'Not Implemented': 0
    };
    framework.controls.forEach(control => {
      if (summary[control.status] !== undefined) {
        summary[control.status]++;
      }
    });
    return summary;
  }, [framework.controls]);

  const filteredControls = useMemo(() => {
    return framework.controls.filter(control => {
      const statusMatch = statusFilter === 'All' || control.status === statusFilter;
      const searchMatch = (
        control.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        control.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        control.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (control.category && control.category.toLowerCase().includes(searchTerm.toLowerCase()))
      );
      return statusMatch && searchMatch;
    });
  }, [framework.controls, searchTerm, statusFilter]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex justify-between items-start">
          <div>
            <h3 className="text-xl font-bold text-gray-800 dark:text-white">{framework.name}</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{framework.description}</p>
            <div className="mt-3 flex space-x-2">
              <button
                onClick={() => setIsAddControlModalOpen(true)}
                className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700"
              >
                <PlusIcon size={14} className="mr-1.5" />
                Add Control
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md shadow-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
              >
                <UploadIcon size={14} className="mr-1.5" />
                Import CSV
              </button>
              {/* Format Selector */}
              <select
                value={reportFormat}
                onChange={(e) => setReportFormat(e.target.value as 'csv' | 'excel' | 'pdf')}
                className="px-2 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md shadow-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
              >
                <option value="csv">CSV</option>
                <option value="excel">Excel (.xlsx)</option>
                <option value="pdf">PDF</option>
              </select>
              <button
                onClick={handleGenerateReport}
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md shadow-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
              >
                <FileTextIcon size={14} className="mr-1.5" />
                Generate Report
              </button>
              <button
                onClick={handleCollectEvidence}
                className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                <BinocularsIcon size={14} className="mr-1.5" />
                Collect Evidence
              </button>
              <button
                onClick={async () => {
                  if (confirm('Run local AI Auditor evaluation on all evidence for this framework? (This may take a few minutes depending on hardware)')) {
                    try {
                      const res = await api.runAIAuditor(framework.id);
                      alert(res.message);
                      window.location.reload(); // Reload to pick up the new ai_evaluations
                    } catch (e) {
                      alert('Failed to run AI Audit.');
                    }
                  }
                }}
                className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
              >
                <BrainCircuitIcon size={14} className="mr-1.5" />
                Evaluate with AI Auditor
              </button>
              <button
                onClick={() => setIsReportsModalOpen(true)}
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md shadow-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
              >
                <FileTextIcon size={14} className="mr-1.5" />
                View Reports
              </button>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".csv"
                onChange={handleImportCSV}
              />
            </div>
          </div>
          {/* Overall Progress Bar */}
          <div className="text-right min-w-[150px]">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Overall Progress</p>
            <div className="flex items-center justify-end">
              <span className="text-lg font-bold text-primary-600 dark:text-primary-400 mr-2">{framework.progress}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div className="bg-primary-600 h-2 rounded-full transition-all duration-500" style={{ width: `${framework.progress}%` }}></div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm border-t border-gray-200 dark:border-gray-700 pt-4">
          <div className="flex items-center text-green-600 dark:text-green-400">
            <ShieldCheckIcon size={16} className="mr-1.5" />
            <span className="font-semibold">{statusSummary['Implemented']}</span>
            <span className="text-gray-500 dark:text-gray-400 ml-1.5">Implemented</span>
          </div>
          <div className="flex items-center text-blue-600 dark:text-blue-400">
            <ClockIcon size={16} className="mr-1.5" />
            <span className="font-semibold">{statusSummary['In Progress']}</span>
            <span className="text-gray-500 dark:text-gray-400 ml-1.5">In Progress</span>
          </div>
          {statusSummary['At Risk'] > 0 && (
            <div className="flex items-center text-red-600 dark:text-red-400">
              <AlertTriangleIcon size={16} className="mr-1.5" />
              <span className="font-semibold">{statusSummary['At Risk']}</span>
              <span className="text-gray-500 dark:text-gray-400 ml-1.5">At Risk</span>
            </div>
          )}
        </div>
      </div>

      {framework.id === 'nistcsf' && (
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="p-3 bg-teal-50 dark:bg-teal-900/50 rounded-lg flex items-start text-sm text-teal-800 dark:text-teal-300 border border-teal-200 dark:border-teal-800">
            <BookOpenCheckIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-teal-500" />
            <div>
              <span className="font-semibold">Cybersecurity Risk Management</span>
              <p className="text-teal-700 dark:text-teal-400">The NIST CSF provides a strategic, high-level framework for managing cybersecurity risk across the enterprise, structured around five core functions.</p>
            </div>
          </div>
        </div>
      )}

      {framework.id === 'hipaa' && framework.status !== 'Compliant' && (
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="p-3 bg-amber-50 dark:bg-amber-900/50 rounded-lg flex items-start text-sm text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
            <HeartPulseIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-amber-500" />
            <div>
              <span className="font-semibold">Business Associate Agreement (BAA) Required</span>
              <p className="text-amber-700 dark:text-amber-400">Ensure a signed BAA is in place with all vendors and third parties that handle electronic Protected Health Information (ePHI).</p>
            </div>
          </div>
        </div>
      )}

      {framework.id === 'iso27001' && (
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="p-3 bg-blue-50 dark:bg-blue-900/50 rounded-lg flex items-start text-sm text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
            <ShieldLockIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-blue-500" />
            <div>
              <span className="font-semibold">Information Security Management System (ISMS)</span>
              <p className="text-blue-700 dark:text-blue-400">These controls form the foundation of your ISMS, crucial for protecting organizational information assets.</p>
            </div>
          </div>
        </div>
      )}

      {framework.id === 'pci-dss' && (
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="p-3 bg-indigo-50 dark:bg-indigo-900/50 rounded-lg flex items-start text-sm text-indigo-800 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
            <CreditCardIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-indigo-500" />
            <div>
              <span className="font-semibold">Cardholder Data Environment (CDE) Protection</span>
              <p className="text-indigo-700 dark:text-indigo-400">These controls are critical for protecting the CDE and ensuring the security of payment card transactions.</p>
            </div>
          </div>
        </div>
      )}

      <div className="p-4 flex flex-col md:flex-row gap-4">
        <div className="flex-grow">
          <input
            type="text"
            placeholder="Search controls by ID, name, or description..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
          />
        </div>
        <div className="flex-shrink-0 w-full md:w-48">
          <div className="relative">
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as ControlStatus | 'All')}
              className="w-full appearance-none px-3 py-2 pl-8 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
            >
              {statusOptions.map(opt => <option key={opt} value={opt}>{opt === 'All' ? 'All Statuses' : opt}</option>)}
            </select>
            <div className="absolute inset-y-0 left-0 flex items-center pl-2 pointer-events-none">
              <FilterIcon size={14} className="text-gray-400" />
            </div>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
          <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
              <th scope="col" className="px-6 py-3">Control ID</th>
              <th scope="col" className="px-6 py-3">Control Name</th>
              <th scope="col" className="px-6 py-3">Status</th>
              <th scope="col" className="px-6 py-3">Last Reviewed</th>
              <th scope="col" className="px-6 py-3">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {filteredControls.map(control => (
              <React.Fragment key={control.id}>
                <tr
                  className="bg-white dark:bg-gray-800 border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50 cursor-pointer"
                  onClick={() => setExpandedControlId(expandedControlId === control.id ? null : control.id)}
                >
                  <td className="px-6 py-4 font-mono text-xs font-medium text-gray-900 dark:text-white">{control.id}</td>
                  <td className="px-6 py-4">
                    <div className="font-semibold text-gray-800 dark:text-gray-200">{control.name}</div>
                    {control.category && (
                      <div className="mt-1.5">
                        <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${categoryClasses[control.category] || 'bg-gray-100 text-gray-800'}`}>
                          {categoryIcons[control.category]}
                          {control.category}
                        </span>
                      </div>
                    )}
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">{control.description}</div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusClasses[control.status]}`}>
                      {control.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-xs font-medium">{control.lastReviewed}</td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col space-y-2">
                      {control.manual_evidence_instructions && (
                        <div className="mb-2 p-2 bg-blue-50 dark:bg-blue-900/30 rounded border border-blue-100 dark:border-blue-800 text-xs text-blue-800 dark:text-blue-300">
                          <strong className="block mb-1 font-semibold">Manual Collection Guide:</strong>
                          {control.manual_evidence_instructions}
                        </div>
                      )}
                      <div className="flex items-center space-x-4">
                        <button
                          onClick={(e) => {
                            e.stopPropagation(); // prevent double toggle if row click handles it
                            setExpandedControlId(expandedControlId === control.id ? null : control.id);
                          }}
                          className="flex items-center text-primary-600 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-200 font-medium text-xs"
                        >
                          <PaperclipIcon size={12} className="mr-1.5" />
                          View ({
                            (control.evidence?.length || 0) +
                            assetComplianceData
                              .filter(ac => {
                                // DEBUG MATCHING
                                const match = ac.controlId === control.id;
                                if (match && ac.evidence?.length > 0) {
                                  console.log(`[FrameworkDetail] Found evidence for control ${control.id} in asset ${ac.assetId}:`, ac.evidence);
                                }
                                return match;
                              })
                              .reduce((sum, ac) => sum + (ac.evidence?.length || 0), 0)
                          })
                        </button>
                        {canManageEvidence && (
                          <button className="text-xs font-medium text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400">
                            Manage
                          </button>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
                {expandedControlId === control.id && (
                  <tr key={`${control.id}-details`}>
                    <td colSpan={5} className="px-6 py-4 bg-gray-50 dark:bg-gray-750">
                      <AssetComplianceList
                        control={control}
                        assets={assets}
                        complianceData={assetComplianceData}
                        onUpdateStatus={(assetId, status) => console.log('Update status', assetId, status)}
                        onUploadEvidence={async (assetId, file) => {
                          console.log('Uploading evidence', assetId, file);
                          try {
                            const res = await api.uploadComplianceEvidence(assetId, control.id, file);
                            if (res.success) {
                              alert(`Successfully uploaded evidence: ${file.name}`);
                              // Ideally trigger a refresh of the list here
                            }
                          } catch (e) {
                            console.error("Upload Error", e);
                            alert("Failed to upload evidence.");
                          }
                        }}
                        onIngestEvidence={async (assetId, fileName, content) => {
                          console.log(`Ingesting evidence for asset ${assetId}: ${fileName}`);
                          try {
                            const asset = assets.find(a => a.id === assetId);
                            const sourceName = `Compliance_Evidence_${control.id}_${asset?.hostname || assetId}_${fileName}`;
                            const res = await api.ingestKnowledge(content, sourceName);
                            if (res.success) {
                              // alert(`Successfully ingested ${fileName} into RAG Knowledge Base!`); // Reduced noise
                              console.log('Ingested into RAG');
                            } else {
                              console.error('Ingest failed', res);
                            }
                          } catch (e) {
                            console.error("Ingest Exception", e);
                            alert('Error ingesting evidence.');
                          }
                        }}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
            {filteredControls.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-8 text-gray-500 dark:text-gray-400">
                  No controls match your search criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <AddControlModal
        isOpen={isAddControlModalOpen}
        onClose={() => setIsAddControlModalOpen(false)}
        onAdd={handleAddControl}
      />
      <ReportsModal
        isOpen={isReportsModalOpen}
        onClose={() => setIsReportsModalOpen(false)}
      />
    </div>
  );
};
