
import React, { useState, useMemo, useCallback } from 'react';
import { ComplianceFramework, ControlStatus, Asset, AssetCompliance } from '../types';
import { AssetComplianceList } from './AssetComplianceList';
import { ChainOfCustodyPanel } from './ChainOfCustodyPanel';
import { BulkEvidenceUploadModal } from './BulkEvidenceUploadModal';
import { ControlEvidenceUploadModal } from './ControlEvidenceUploadModal';
import { AddControlModal } from './AddControlModal';
import { ReportsModal } from './ReportsModal';
import { FrameworkInfoBanner } from './FrameworkInfoBanner';
import { statusClasses, categoryClasses, categoryIcons, statusOptions } from './frameworkDetailStyles';
// FIX: Replaced non-existent LockIcon with ShieldLockIcon.
import { PaperclipIcon, ShieldCheckIcon, ClockIcon, AlertTriangleIcon, FilterIcon, BinocularsIcon, PlusIcon, UploadIcon, BrainCircuitIcon, FileTextIcon } from './icons';
import { useUser } from '../contexts/UserContext';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';

interface FrameworkDetailProps {
  framework: ComplianceFramework;
  assets: Asset[];
  assetComplianceData: AssetCompliance[];
  onRefresh?: () => void;
}

export const FrameworkDetail: React.FC<FrameworkDetailProps> = ({ framework, assets, assetComplianceData: initialAssetComplianceData, onRefresh }) => {
  const [localAssetCompliance, setLocalAssetCompliance] = useState(initialAssetComplianceData);
  const assetComplianceData = localAssetCompliance;

  const refreshAssetCompliance = useCallback(async (assetId: string) => {
    const fresh = await api.fetchAssetCompliance(assetId);
    if (fresh) {
      setLocalAssetCompliance(prev => {
        const filtered = prev.filter(ac => ac.assetId !== assetId);
        return Array.isArray(fresh) ? [...filtered, ...fresh] : [...filtered, fresh];
      });
    }
    if (onRefresh) onRefresh();
  }, [onRefresh]);

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<ControlStatus | 'All'>('All');
  const [expandedControlId, setExpandedControlId] = useState<string | null>(null);
  const [isAddControlModalOpen, setIsAddControlModalOpen] = useState(false);
  const [isReportsModalOpen, setIsReportsModalOpen] = useState(false);
  const [evidenceUploadControlId, setEvidenceUploadControlId] = useState<string | null>(null);
  const [isBulkUploadOpen, setIsBulkUploadOpen] = useState(false);
  const [reportFormat, setReportFormat] = useState<'csv' | 'excel' | 'pdf'>('csv');
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const { hasPermission } = useUser();
  const canManageEvidence = hasPermission('manage:compliance_evidence');
  const canViewCoC = hasPermission('view:audit_log');

  const handleAddControl = async (data: any) => {
    try {
      await api.addComplianceControl(framework.id, data);
      showToast('Control added successfully!', 'success');
      setIsAddControlModalOpen(false);
    } catch (e) {
      showToast('Failed to add control', 'error');
    }
  };

  const handleImportDoc = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      try {
        const res = await api.importComplianceControls(framework.id, file);
        showToast(`Successfully imported ${res.count} controls from ${file.name}`, 'success');
      } catch (err: any) {
        showToast(`Import failed: ${err?.message ?? 'Unknown error'}`, 'error');
      }
      // Reset so the same file can be re-uploaded
      e.target.value = '';
    }
  };

  const handleCollectEvidence = async () => {
    try {
      // @ts-ignore
      const res = await api.triggerFrameworkScan(framework.id);
      if (res.success) {
        showToast(`Scan initiated! ${res.message}`, 'success');
      } else {
        showToast(`Failed to start scan: ${res.message}`, 'error');
      }
    } catch (e) {
      showToast('Error triggering scan.', 'error');
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

      if (res?.filename) {
        showToast(`${reportFormat.toUpperCase()} report generated successfully!`, 'success');
        setIsReportsModalOpen(true);
      } else {
        showToast('Report generation returned an unexpected response.', 'error');
      }
    } catch (e: any) {
      showToast(`Failed to generate report: ${e?.message || 'Unknown error'}`, 'error');
    }
  };

  const statusSummary = useMemo(() => {
    const summary: Record<ControlStatus, number> = {
      'Implemented': 0,
      'In Progress': 0,
      'At Risk': 0,
      'Not Implemented': 0
    };
    (framework.controls ?? []).forEach(control => {
      if (summary[control.status] !== undefined) {
        summary[control.status]++;
      }
    });
    return summary;
  }, [framework.controls]);

  const filteredControls = useMemo(() => {
    return (framework.controls ?? []).filter(control => {
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
                title="Import controls from CSV, Excel (.xlsx), PDF, or Word (.docx)"
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md shadow-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
              >
                <UploadIcon size={14} className="mr-1.5" />
                Import Controls
              </button>
              {canManageEvidence && (
                <button
                  onClick={() => setIsBulkUploadOpen(true)}
                  className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md shadow-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
                  aria-label="Open bulk evidence upload modal"
                >
                  <UploadIcon size={14} className="mr-1.5" />
                  Bulk Upload Evidence
                </button>
              )}
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
                      showToast(res.message, 'success');
                      if (onRefresh) onRefresh();
                    } catch (e) {
                      showToast('Failed to run AI Audit.', 'error');
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
                accept=".csv,.xlsx,.xls,.pdf,.docx"
                onChange={handleImportDoc}
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

      <FrameworkInfoBanner framework={framework} />

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
                      <div className="flex items-center space-x-3 flex-wrap gap-y-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedControlId(expandedControlId === control.id ? null : control.id);
                          }}
                          className="flex items-center text-primary-600 hover:text-primary-800 dark:text-primary-400 dark:hover:text-primary-200 font-medium text-xs"
                        >
                          <PaperclipIcon size={12} className="mr-1.5" />
                          View ({
                            (control.evidence?.length || 0) +
                            assetComplianceData
                              .filter(ac => ac.controlId === control.id)
                              .reduce((sum, ac) => sum + (ac.evidence?.length || 0), 0)
                          })
                        </button>
                        {canManageEvidence && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEvidenceUploadControlId(control.id);
                            }}
                            className="flex items-center text-xs font-medium text-emerald-700 dark:text-emerald-400 hover:text-emerald-900 dark:hover:text-emerald-200 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded px-2 py-0.5 transition-colors"
                            title="Upload policy document, audit report, or other evidence for this control"
                          >
                            <UploadIcon size={11} className="mr-1" />
                            Upload
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
                        onUpdateStatus={async (assetId, status) => {
                            try {
                                await api.updateAssetComplianceStatus(assetId, control.id, status);
                                await refreshAssetCompliance(assetId);
                            } catch (e) {
                                console.error('Failed to update compliance status', e);
                                showToast('Failed to update compliance status — please try again', 'error');
                            }
                        }}
                        onEvidenceReviewed={(assetId) => {
                          // Non-mutating refresh trigger (WR-04) — a review decision doesn't
                          // change the asset's overall compliance status, so this refetches
                          // directly instead of reusing onUpdateStatus's mutating write.
                          refreshAssetCompliance(assetId);
                        }}
                        onUploadEvidence={async (assetId, file, description) => {
                          try {
                            const res = await api.uploadComplianceEvidence(assetId, control.id, file, description);
                            if (res.success) {
                              showToast(`Successfully uploaded evidence: ${file.name}`, 'success');
                              await refreshAssetCompliance(assetId);
                            }
                          } catch (e) {
                            console.error("Upload Error", e);
                            showToast("Failed to upload evidence.", 'error');
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
                            showToast('Error ingesting evidence.', 'error');
                          }
                        }}
                        onDeleteEvidence={async (assetId, controlId, evidenceId) => {
                          try {
                            await api.deleteComplianceEvidence(assetId, controlId, evidenceId);
                            showToast('Evidence deleted.', 'success');
                            await refreshAssetCompliance(assetId);
                          } catch (e) {
                            console.error("Delete Error", e);
                            showToast("Failed to delete evidence.", 'error');
                          }
                        }}
                      />
                      {canViewCoC && <ChainOfCustodyPanel controlId={control.id} />}
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
        frameworkId={framework.id}
      />
      {evidenceUploadControlId && (
        <ControlEvidenceUploadModal
          controlId={evidenceUploadControlId}
          onClose={() => setEvidenceUploadControlId(null)}
          onUploaded={() => { if (onRefresh) onRefresh(); }}
        />
      )}
      {isBulkUploadOpen && (
        <BulkEvidenceUploadModal
          onClose={() => setIsBulkUploadOpen(false)}
          onUploaded={() => { setIsBulkUploadOpen(false); if (onRefresh) onRefresh(); }}
        />
      )}
    </div>
  );
};
