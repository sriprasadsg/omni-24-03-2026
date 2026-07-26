import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SaaSConnection {
  id: string;
  provider: string;
  status: string;
  last_synced: string | null;
  evidence_count: number;
  tenant_id: string;
}

interface ProviderCatalogEntry {
  id: string;
  name: string;
  logo: string;
  description: string;
  controls: string[];
}

// ---------------------------------------------------------------------------
// Provider catalog
// ---------------------------------------------------------------------------

const PROVIDER_CATALOG: ProviderCatalogEntry[] = [
  {
    id: 'github',
    name: 'GitHub',
    logo: '🐙',
    description: 'Branch protection, PR evidence, SAST alerts',
    controls: ['Secure Development & Coding', 'Access to Source Code', 'Security Patch Status'],
  },
  {
    id: 'jira',
    name: 'Jira',
    logo: '🎯',
    description: 'Compliance-tagged issue evidence for change management',
    controls: ['Change Management'],
  },
  {
    id: 'okta',
    name: 'Okta',
    logo: '🔐',
    description: 'MFA enrollment, user identity & authentication records',
    controls: ['MFA for All Users', 'Identity & Authentication'],
  },
  {
    id: 'google_workspace',
    name: 'Google Workspace',
    logo: '🔷',
    description: '2-step verification enrollment, user audit logs',
    controls: ['Account Security', 'Data Leakage Prevention'],
  },
  {
    id: 'slack',
    name: 'Slack',
    logo: '💬',
    description: 'Channel retention policy for audit logging evidence',
    controls: ['Audit Logging Extension'],
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(isoStr: string | null | undefined): string {
  if (!isoStr) return 'Never';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60_000);
  const hrs  = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (diff < 60_000)   return 'just now';
  if (mins < 60)       return `${mins}m ago`;
  if (hrs  < 24)       return `${hrs}h ago`;
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const SaaSIntegrationsDashboard: React.FC = () => {
  const [connections, setConnections] = useState<SaaSConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [pulling, setPulling] = useState<Record<string, boolean>>({});
  const [disconnecting, setDisconnecting] = useState<Record<string, boolean>>({});

  // ── Fetch connections ────────────────────────────────────────────────────

  const fetchConnections = useCallback(async () => {
    try {
      const r = await authFetch('/api/saas/connections');
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        showToast(d.detail || 'Failed to load connections', 'error');
        return;
      }
      const data = await r.json();
      setConnections(data.connections ?? []);
    } catch {
      showToast('Network error loading SaaS connections', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  // ── OAuth popup ──────────────────────────────────────────────────────────

  const connectProvider = useCallback((providerId: string) => {
    const popup = window.open(
      `/api/saas/connect/${providerId}`,
      'oauth',
      'width=600,height=700,left=200,top=100',
    );

    if (!popup) {
      showToast('Popup blocked — allow popups for this site and try again', 'error');
      return;
    }

    const expectedOrigin = window.location.origin;

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== expectedOrigin) return;
      if (event.data === 'saas_connected') {
        clearInterval(pollClosed);
        window.removeEventListener('message', onMessage);
        popup.close();
        showToast('Integration connected', 'success');
        setLoading(true);
        fetchConnections();
      }
    };

    window.addEventListener('message', onMessage);

    // Cleanup listener if popup is closed without completing OAuth
    const pollClosed = setInterval(() => {
      if (popup.closed) {
        clearInterval(pollClosed);
        window.removeEventListener('message', onMessage);
      }
    }, 500);
  }, [fetchConnections]);

  // ── Pull evidence ────────────────────────────────────────────────────────

  const pullEvidence = useCallback(async (connectionId: string) => {
    setPulling(p => ({ ...p, [connectionId]: true }));
    try {
      const r = await authFetch(`/api/saas/connections/${connectionId}/pull-evidence`, {
        method: 'POST',
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        showToast(d.detail || 'Evidence pull failed', 'error');
        return;
      }
      const data = await r.json();
      showToast(`Collected ${data.count ?? 0} evidence records`, 'success');
      fetchConnections();
    } catch {
      showToast('Network error during evidence pull', 'error');
    } finally {
      setPulling(p => ({ ...p, [connectionId]: false }));
    }
  }, [fetchConnections]);

  // ── Disconnect ───────────────────────────────────────────────────────────

  const disconnectProvider = useCallback(async (connectionId: string, providerName: string) => {
    if (!window.confirm(`Disconnect ${providerName}? This will remove the stored credentials.`)) {
      return;
    }
    setDisconnecting(d => ({ ...d, [connectionId]: true }));
    try {
      const r = await authFetch(`/api/saas/connections/${connectionId}`, {
        method: 'DELETE',
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        showToast(d.detail || 'Disconnect failed', 'error');
        return;
      }
      showToast(`${providerName} disconnected`, 'success');
      setConnections(prev => prev.filter(c => c.id !== connectionId));
    } catch {
      showToast('Network error during disconnect', 'error');
    } finally {
      setDisconnecting(d => ({ ...d, [connectionId]: false }));
    }
  }, []);

  // ── Render helpers ───────────────────────────────────────────────────────

  const getConnection = (providerId: string): SaaSConnection | undefined =>
    connections.find(c => c.provider === providerId);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            SaaS Integrations
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Connect your SaaS tools to automatically collect compliance evidence.
          </p>
        </div>
        <button
          onClick={() => { setLoading(true); fetchConnections(); }}
          className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          Refresh
        </button>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4, 5].map(i => (
            <div
              key={i}
              className="animate-pulse bg-gray-100 dark:bg-gray-800 rounded-xl h-48"
            />
          ))}
        </div>
      )}

      {/* Provider cards */}
      {!loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {PROVIDER_CATALOG.map(provider => {
            const conn = getConnection(provider.id);
            const isConnected = !!conn;
            const isPulling = conn ? !!pulling[conn.id] : false;
            const isDisconnecting = conn ? !!disconnecting[conn.id] : false;

            return (
              <div
                key={provider.id}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 flex flex-col gap-3 shadow-sm"
              >
                {/* Card header */}
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl" role="img" aria-label={provider.name}>
                      {provider.logo}
                    </span>
                    <div>
                      <h2 className="font-semibold text-gray-900 dark:text-white text-base">
                        {provider.name}
                      </h2>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {provider.description}
                      </p>
                    </div>
                  </div>
                  {/* Connection status badge */}
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      isConnected
                        ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                        : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                    }`}
                  >
                    {isConnected ? '● Connected' : '○ Not connected'}
                  </span>
                </div>

                {/* Connected details */}
                {isConnected && conn && (
                  <div className="text-xs text-gray-600 dark:text-gray-400 space-y-0.5">
                    <div>
                      <span className="font-medium">Last sync:</span>{' '}
                      {relativeTime(conn.last_synced)}
                    </div>
                    <div>
                      <span className="font-medium">Evidence collected:</span>{' '}
                      {conn.evidence_count} records
                    </div>
                  </div>
                )}

                {/* Controls mapped */}
                <div className="flex flex-wrap gap-1">
                  {provider.controls.map(ctrl => (
                    <span
                      key={ctrl}
                      className="text-xs bg-blue-50 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-2 py-0.5 rounded"
                    >
                      {ctrl}
                    </span>
                  ))}
                </div>

                {/* Action buttons */}
                <div className="flex gap-2 pt-1">
                  {!isConnected ? (
                    <button
                      onClick={() => connectProvider(provider.id)}
                      className="flex-1 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-3 py-2 transition-colors"
                    >
                      Connect
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => conn && pullEvidence(conn.id)}
                        disabled={isPulling}
                        className="flex-1 text-sm font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg px-3 py-2 transition-colors flex items-center justify-center gap-1.5"
                      >
                        {isPulling ? (
                          <>
                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                              <circle
                                className="opacity-25"
                                cx="12" cy="12" r="10"
                                stroke="currentColor" strokeWidth="4"
                              />
                              <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                              />
                            </svg>
                            Pulling…
                          </>
                        ) : (
                          'Pull Evidence Now'
                        )}
                      </button>
                      <button
                        onClick={() => conn && disconnectProvider(conn.id, provider.name)}
                        disabled={isDisconnecting}
                        className="text-sm font-medium border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900 disabled:opacity-50 rounded-lg px-3 py-2 transition-colors"
                      >
                        {isDisconnecting ? 'Removing…' : 'Disconnect'}
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty state when no providers at all (shouldn't happen) */}
      {!loading && PROVIDER_CATALOG.length === 0 && (
        <p className="text-center text-gray-500 dark:text-gray-400 py-12">
          No SaaS providers configured.
        </p>
      )}
    </div>
  );
};

export default SaaSIntegrationsDashboard;
