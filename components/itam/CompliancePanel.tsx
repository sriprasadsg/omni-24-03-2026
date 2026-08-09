import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { AssetComplianceList } from '../AssetComplianceList';
import { Asset, AssetCompliance, Control } from '../../types';
import * as api from '../../services/apiService';
import { showToast } from '../../utils/toast';

interface ControlOption extends Control {
  frameworkName: string;
}

// Control-centric wrapper around AssetComplianceList, cloning FrameworkDetail.tsx's
// data-fetch wiring (61-UI-SPEC.md Component Inventory #1): pick a control, fetch
// every asset's compliance data for it, render the shared list component. Handlers
// reuse the exact same apiService functions FrameworkDetail.tsx already calls.
export function CompliancePanel({ assets }: { assets: Asset[] }) {
  const [controls, setControls] = useState<ControlOption[]>([]);
  const [selectedControlId, setSelectedControlId] = useState<string>('');
  const [complianceData, setComplianceData] = useState<AssetCompliance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const frameworks = await api.fetchComplianceFrameworks();
        const flat: ControlOption[] = (frameworks || []).flatMap((f: any) =>
          (f.controls || []).map((c: Control) => ({ ...c, frameworkName: f.shortName || f.name }))
        );
        setControls(flat);
        if (flat.length > 0) setSelectedControlId(flat[0].id);
      } catch (e: any) {
        setError(e?.message || 'Failed to load compliance frameworks');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const loadComplianceData = useCallback(async () => {
    if (assets.length === 0) return;
    try {
      const results = await Promise.all(assets.map((a) => api.fetchAssetCompliance(a.id)));
      const flat = results.flatMap((r: any) => (Array.isArray(r) ? r : r ? [r] : []));
      setComplianceData(flat);
    } catch (e: any) {
      setError(e?.message || 'Failed to load compliance data');
    }
  }, [assets]);

  useEffect(() => { loadComplianceData(); }, [loadComplianceData]);

  const selectedControl = useMemo(
    () => controls.find((c) => c.id === selectedControlId),
    [controls, selectedControlId]
  );

  const refreshAsset = useCallback(async (assetId: string) => {
    const fresh = await api.fetchAssetCompliance(assetId);
    setComplianceData((prev) => {
      const filtered = prev.filter((ac) => ac.assetId !== assetId);
      return Array.isArray(fresh) ? [...filtered, ...fresh] : fresh ? [...filtered, fresh] : filtered;
    });
  }, []);

  if (loading) return <p className="text-gray-400 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 text-sm">Couldn't load compliance data. Check your connection and try again.</p>;

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <label className="text-xs font-semibold text-gray-400" htmlFor="itam-control-picker">Control</label>
        <select
          id="itam-control-picker"
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
          value={selectedControlId}
          onChange={(e) => setSelectedControlId(e.target.value)}
        >
          {controls.map((c) => (
            <option key={c.id} value={c.id}>{c.frameworkName} — {c.name}</option>
          ))}
        </select>
      </div>

      {!selectedControl && <p className="text-gray-500 text-sm">No controls available.</p>}

      {selectedControl && (
        <AssetComplianceList
          control={selectedControl}
          assets={assets}
          complianceData={complianceData}
          onUpdateStatus={async (assetId, status) => {
            try {
              await api.updateAssetComplianceStatus(assetId, selectedControl.id, status);
              await refreshAsset(assetId);
            } catch (e) {
              showToast('Failed to update compliance status — please try again', 'error');
            }
          }}
          onEvidenceReviewed={(assetId) => { refreshAsset(assetId); }}
          onUploadEvidence={async (assetId, file, description) => {
            try {
              const res = await api.uploadComplianceEvidence(assetId, selectedControl.id, file, description);
              if (res?.success !== false) {
                showToast(`Successfully uploaded evidence: ${file.name}`, 'success');
                await refreshAsset(assetId);
              }
            } catch (e) {
              showToast('Failed to upload evidence.', 'error');
            }
          }}
          onIngestEvidence={async (assetId, fileName, content) => {
            try {
              const asset = assets.find((a) => a.id === assetId);
              const sourceName = `Compliance_Evidence_${selectedControl.id}_${asset?.hostname || assetId}_${fileName}`;
              await api.ingestKnowledge(content, sourceName);
            } catch (e) {
              showToast('Error ingesting evidence.', 'error');
            }
          }}
          onDeleteEvidence={async (assetId, controlId, evidenceId) => {
            try {
              await api.deleteComplianceEvidence(assetId, controlId, evidenceId);
              showToast('Evidence deleted.', 'success');
              await refreshAsset(assetId);
            } catch (e) {
              showToast('Failed to delete evidence.', 'error');
            }
          }}
        />
      )}
    </div>
  );
}
