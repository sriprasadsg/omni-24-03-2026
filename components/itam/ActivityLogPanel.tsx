import React, { useEffect, useState, useCallback } from 'react';
import { AuditLogEntry } from '../../types';
import { fetchItamAuditLogs, verifyAuditIntegrity } from '../../services/apiService';

interface ActivityLogPanelProps {
  resourceType?: string;
  resourceId?: string;
}

// Local mirror of backend/itam_audit_service.py's ITAM_RESOURCE_TYPES — that
// module is the source of truth for the vocabulary; this array only drives
// the filter dropdown's option list.
const ITAM_RESOURCE_TYPES: string[] = [
  'itam_asset',
  'itam_catalog_manufacturer',
  'itam_catalog_category',
  'itam_catalog_location',
  'itam_catalog_supplier',
  'itam_catalog_model',
  'itam_component',
  'itam_consumable',
  'itam_license',
  'itam_license_assignment',
  'itam_settings',
  'itam_import',
  'itam_export',
];

const PAGE_SIZE = 50;

// Read-only activity feed over the platform's existing hash-chained audit
// ledger (Phase 65 Plan 02, ITAM-DAT-02). Filters narrow the tenant-scoped
// query; they never widen it — resourceType/resourceId are optional props
// so a future asset-detail view can mount this panel pre-filtered and hide
// its own filter controls.
export function ActivityLogPanel({ resourceType: propResourceType, resourceId: propResourceId }: ActivityLogPanelProps) {
  const filtered = propResourceType !== undefined || propResourceId !== undefined;

  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // Local filter state — only meaningful (and only rendered) when the panel
  // was not mounted pre-filtered via props.
  const [selectedType, setSelectedType] = useState<string>('');
  const [entityIdInput, setEntityIdInput] = useState<string>('');

  const [integrityResult, setIntegrityResult] = useState<{ valid: boolean; total_records?: number; broken_links?: unknown[] } | null>(null);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const effectiveResourceType = filtered ? propResourceType : (selectedType || undefined);
  const effectiveResourceId = filtered ? propResourceId : (entityIdInput.trim() || undefined);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntries(await fetchItamAuditLogs({
        resourceType: effectiveResourceType,
        resourceId: effectiveResourceId,
        limit: PAGE_SIZE,
        skip: page * PAGE_SIZE,
      }));
    } catch (e: any) {
      setError(e?.message || "Couldn't load activity log");
    } finally {
      setLoading(false);
    }
  }, [effectiveResourceType, effectiveResourceId, page]);

  useEffect(() => { load(); }, [load]);

  // Changing either filter resets paging back to the first page.
  useEffect(() => { setPage(0); }, [selectedType, entityIdInput]);

  async function handleVerifyIntegrity() {
    setVerifying(true);
    setIntegrityError(null);
    try {
      setIntegrityResult(await verifyAuditIntegrity());
    } catch (e: any) {
      setIntegrityResult(null);
      setIntegrityError(e?.message || 'Failed to verify ledger integrity');
    } finally {
      setVerifying(false);
    }
  }

  function toggleExpanded(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const hasFullPage = entries.length >= PAGE_SIZE;

  return (
    <div>
      {!filtered && (
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <nav className="flex flex-wrap gap-1" aria-label="Filter by entity type">
            <button
              onClick={() => setSelectedType('')}
              aria-current={selectedType === '' ? 'page' : undefined}
              aria-label="All entity types"
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                selectedType === '' ? 'bg-cyan-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              All
            </button>
            {ITAM_RESOURCE_TYPES.map((rt) => (
              <button
                key={rt}
                onClick={() => setSelectedType(rt)}
                aria-current={selectedType === rt ? 'page' : undefined}
                aria-label={`Filter by ${rt}`}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                  selectedType === rt ? 'bg-cyan-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                }`}
              >
                {rt}
              </button>
            ))}
          </nav>
          <input
            type="text"
            aria-label="Filter by entity ID"
            placeholder="Filter by entity ID…"
            value={entityIdInput}
            onChange={(e) => setEntityIdInput(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-500"
          />
          <button
            onClick={handleVerifyIntegrity}
            disabled={verifying}
            aria-label="Verify ledger integrity"
            className="ml-auto bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
          >
            {verifying ? 'Verifying…' : 'Verify ledger integrity'}
          </button>
        </div>
      )}

      {filtered && (
        <div className="flex justify-end mb-4">
          <button
            onClick={handleVerifyIntegrity}
            disabled={verifying}
            aria-label="Verify ledger integrity"
            className="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
          >
            {verifying ? 'Verifying…' : 'Verify ledger integrity'}
          </button>
        </div>
      )}

      {integrityError && (
        <p role="alert" className="text-red-400 text-xs mb-3">{integrityError}</p>
      )}
      {integrityResult && !integrityError && (
        <p role="status" className={`text-xs mb-3 ${integrityResult.valid ? 'text-green-400' : 'text-red-400'}`}>
          {integrityResult.valid
            ? `Ledger verified — ${integrityResult.total_records ?? 0} record(s), chain intact.`
            : `Ledger integrity check failed — ${(integrityResult.broken_links || []).length} broken link(s).`}
        </p>
      )}

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && entries.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No activity recorded yet</h3>
            {(filtered || effectiveResourceType || effectiveResourceId) && (
              <p className="text-gray-500 text-xs">No history found for this entity.</p>
            )}
          </div>
        )}
        {!loading && !error && entries.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Time</th>
                <th className="py-2 pr-4">User</th>
                <th className="py-2 pr-4">Action</th>
                <th className="py-2 pr-4">Entity Type</th>
                <th className="py-2 pr-4">Entity ID</th>
                <th className="py-2 pr-4">Details</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <React.Fragment key={entry.id}>
                  <tr className="border-b border-gray-800">
                    <td className="py-2 pr-4 text-gray-400 whitespace-nowrap">{entry.timestamp}</td>
                    <td className="py-2 pr-4 text-white font-medium">{entry.userName}</td>
                    <td className="py-2 pr-4 text-cyan-400">{entry.action}</td>
                    <td className="py-2 pr-4 text-gray-400">{entry.resourceType}</td>
                    <td className="py-2 pr-4 text-gray-400">{entry.resourceId}</td>
                    <td className="py-2 pr-4 text-gray-400 max-w-[320px] truncate" title={entry.details}>{entry.details}</td>
                    <td className="py-2 pr-4 text-right">
                      {entry.previousState != null && (
                        <button
                          onClick={() => toggleExpanded(entry.id)}
                          aria-label={`Toggle previous state for ${entry.id}`}
                          className="text-xs text-cyan-400 hover:text-cyan-300"
                        >
                          {expanded[entry.id] ? 'Hide' : 'Show'} previous state
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded[entry.id] && entry.previousState != null && (
                    <tr className="border-b border-gray-800">
                      <td colSpan={7} className="py-2 pr-4">
                        <pre className="text-xs text-gray-400 bg-gray-900 rounded-lg p-3 overflow-x-auto">
                          {JSON.stringify(entry.previousState, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!loading && !error && (
        <div className="flex items-center justify-end gap-2 mt-3">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label="Previous page"
            className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
          >
            Previous
          </button>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasFullPage}
            aria-label="Next page"
            className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
