import React, { useEffect, useState, useCallback } from 'react';
import { AuditLogEntry } from '../../types';
import { fetchAuditLogs } from '../../services/apiService';

interface ActivityLogPanelProps {
  resourceType?: string;
  resourceId?: string;
}

// Read-only activity feed over the platform's existing hash-chained audit
// ledger (Phase 65 Plan 02, ITAM-DAT-02). Filters (Task 3) narrow the
// tenant-scoped query; they never widen it — resourceType/resourceId are
// optional props so a future asset-detail view can mount this panel
// pre-filtered and hide its own filter controls.
export function ActivityLogPanel({ resourceType, resourceId }: ActivityLogPanelProps) {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filtered = resourceType !== undefined || resourceId !== undefined;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntries(await fetchAuditLogs({ resourceType, resourceId, limit: 100 }));
    } catch (e: any) {
      setError(e?.message || "Couldn't load activity log");
    } finally {
      setLoading(false);
    }
  }, [resourceType, resourceId]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && entries.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No activity recorded yet</h3>
            {filtered && <p className="text-gray-500 text-xs">No history found for this entity.</p>}
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
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-gray-400 whitespace-nowrap">{entry.timestamp}</td>
                  <td className="py-2 pr-4 text-white font-medium">{entry.userName}</td>
                  <td className="py-2 pr-4 text-cyan-400">{entry.action}</td>
                  <td className="py-2 pr-4 text-gray-400">{entry.resourceType}</td>
                  <td className="py-2 pr-4 text-gray-400">{entry.resourceId}</td>
                  <td className="py-2 pr-4 text-gray-400 max-w-[320px] truncate" title={entry.details}>{entry.details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
