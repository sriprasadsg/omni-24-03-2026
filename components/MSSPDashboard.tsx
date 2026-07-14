import React, { useState, useEffect, useCallback } from 'react';
import {
  Building, Users, AlertTriangle, CheckCircle, XCircle,
  Activity, BarChart2, Globe, ChevronDown, ChevronRight, X
} from 'lucide-react';

const API = import.meta.env.VITE_API_BASE_URL || '';
const authHeaders = () => ({ Authorization: `Bearer ${sessionStorage.getItem('token')}` });

interface TenantHealth {
  id: string;
  tenant_name: string;
  health_status: 'healthy' | 'warning' | 'critical';
  agent_count: number;
  open_incidents: number;
  critical_alerts: number;
  compliance_score: number;
  last_activity: string;
  metrics?: {
    cpu_avg: number;
    memory_avg: number;
    events_24h: number;
    resolved_incidents: number;
  };
}

interface AggregatedAlert {
  id: string;
  tenant_name: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  event_type: string;
  description: string;
  timestamp: string;
}

interface MSSPOverview {
  tenants: TenantHealth[];
  total_tenants: number;
  healthy_count: number;
  warning_count: number;
  critical_count: number;
  total_agents: number;
}

interface ReportModalState {
  open: boolean;
  tenantId: string;
  tenantName: string;
  report: string | null;
  loading: boolean;
}

const HEALTH_COLORS: Record<string, string> = {
  healthy: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  warning: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  critical: 'bg-red-500/20 text-red-400 border border-red-500/30',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-yellow-400',
  low: 'text-blue-400',
};

function HealthBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${HEALTH_COLORS[status] || 'bg-slate-600 text-slate-300'}`}>
      {status}
    </span>
  );
}

function StatusBar({ value, total, color }: { value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-slate-700 rounded-full h-2">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400 w-8">{pct}%</span>
    </div>
  );
}

export default function MSSPDashboard() {
  const [overview, setOverview] = useState<MSSPOverview | null>(null);
  const [alerts, setAlerts] = useState<AggregatedAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedTenant, setExpandedTenant] = useState<string | null>(null);
  const [reportModal, setReportModal] = useState<ReportModalState>({
    open: false, tenantId: '', tenantName: '', report: null, loading: false,
  });

  const fetchOverview = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/mssp/overview`, { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setOverview(data);
      }
    } catch (e) {
      console.error('MSSP overview error:', e);
    }
  }, []);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/mssp/alerts/aggregated?severity=high&limit=50`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setAlerts(Array.isArray(data) ? data : data.alerts || []);
      }
    } catch (e) {
      console.error('MSSP alerts error:', e);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchOverview(), fetchAlerts()]).finally(() => setLoading(false));
    const interval = setInterval(() => { fetchOverview(); fetchAlerts(); }, 30000);
    return () => clearInterval(interval);
  }, [fetchOverview, fetchAlerts]);

  const openReport = async (tenant: TenantHealth) => {
    setReportModal({ open: true, tenantId: tenant.id, tenantName: tenant.tenant_name, report: null, loading: true });
    try {
      const res = await fetch(`${API}/api/mssp/tenants/${tenant.id}/report`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      setReportModal(prev => ({ ...prev, report: JSON.stringify(data, null, 2), loading: false }));
    } catch (e) {
      setReportModal(prev => ({ ...prev, report: 'Failed to load report.', loading: false }));
    }
  };

  const tenants = overview?.tenants || [];
  const total = overview?.total_tenants || 0;
  const healthy = overview?.healthy_count || 0;
  const warning = overview?.warning_count || 0;
  const critical = overview?.critical_count || 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Activity className="w-6 h-6 animate-spin text-blue-400 mr-2" />
        <span className="text-slate-400">Loading MSSP Overview...</span>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 bg-slate-900 min-h-screen">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Globe className="w-7 h-7 text-blue-400" />
        <div>
          <h1 className="text-2xl font-bold text-white">MSSP Dashboard</h1>
          <p className="text-slate-400 text-sm">Multi-tenant security operations overview</p>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: 'Total Tenants', value: total, icon: Building, color: 'text-blue-400' },
          { label: 'Healthy', value: healthy, icon: CheckCircle, color: 'text-emerald-400' },
          { label: 'Warning', value: warning, icon: AlertTriangle, color: 'text-yellow-400' },
          { label: 'Critical', value: critical, icon: XCircle, color: 'text-red-400' },
          { label: 'Total Agents', value: overview?.total_agents || 0, icon: Users, color: 'text-purple-400' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-slate-800 rounded-xl p-4 border border-slate-700">
            <div className="flex items-center justify-between mb-2">
              <span className="text-slate-400 text-xs">{label}</span>
              <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Status Summary Bar Chart */}
      <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <BarChart2 className="w-4 h-4 text-blue-400" />
          <span className="text-white font-semibold">Tenant Health Distribution</span>
        </div>
        <div className="space-y-3">
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-emerald-400">Healthy</span>
              <span className="text-slate-400">{healthy} tenants</span>
            </div>
            <StatusBar value={healthy} total={total} color="bg-emerald-500" />
          </div>
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-yellow-400">Warning</span>
              <span className="text-slate-400">{warning} tenants</span>
            </div>
            <StatusBar value={warning} total={total} color="bg-yellow-500" />
          </div>
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-red-400">Critical</span>
              <span className="text-slate-400">{critical} tenants</span>
            </div>
            <StatusBar value={critical} total={total} color="bg-red-500" />
          </div>
        </div>
      </div>

      {/* Tenant Health Grid */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Tenant Health</h2>
        {tenants.length === 0 ? (
          <div className="bg-slate-800 rounded-xl p-8 text-center border border-slate-700">
            <Building className="w-10 h-10 text-slate-600 mx-auto mb-2" />
            <p className="text-slate-400">No tenant data available</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tenants.map(tenant => (
              <div key={tenant.id} className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                {/* Tenant Card Header */}
                <div
                  className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
                  onClick={() => setExpandedTenant(expandedTenant === tenant.id ? null : tenant.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {expandedTenant === tenant.id
                        ? <ChevronDown className="w-4 h-4 text-slate-400" />
                        : <ChevronRight className="w-4 h-4 text-slate-400" />
                      }
                      <Building className="w-5 h-5 text-blue-400" />
                      <span className="text-white font-medium">{tenant.tenant_name}</span>
                      <HealthBadge status={tenant.health_status} />
                    </div>
                    <div className="flex items-center gap-6 text-sm">
                      <div className="text-center">
                        <div className="text-slate-400 text-xs">Agents</div>
                        <div className="text-white font-semibold">{tenant.agent_count}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-slate-400 text-xs">Incidents</div>
                        <div className="text-yellow-400 font-semibold">{tenant.open_incidents}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-slate-400 text-xs">Critical</div>
                        <div className="text-red-400 font-semibold">{tenant.critical_alerts}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-slate-400 text-xs">Compliance</div>
                        <div className="text-emerald-400 font-semibold">{tenant.compliance_score}%</div>
                      </div>
                      <div className="text-center hidden md:block">
                        <div className="text-slate-400 text-xs">Last Active</div>
                        <div className="text-slate-300 text-xs">
                          {tenant.last_activity ? new Date(tenant.last_activity).toLocaleString() : 'N/A'}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Expanded Details Panel */}
                {expandedTenant === tenant.id && (
                  <div className="border-t border-slate-700 bg-slate-900 p-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      {[
                        { label: 'CPU Average', value: tenant.metrics?.cpu_avg != null ? `${tenant.metrics.cpu_avg}%` : 'N/A', color: 'text-blue-400' },
                        { label: 'Memory Average', value: tenant.metrics?.memory_avg != null ? `${tenant.metrics.memory_avg}%` : 'N/A', color: 'text-purple-400' },
                        { label: 'Events (24h)', value: tenant.metrics?.events_24h != null ? tenant.metrics.events_24h : 'N/A', color: 'text-orange-400' },
                        { label: 'Resolved Incidents', value: tenant.metrics?.resolved_incidents != null ? tenant.metrics.resolved_incidents : 'N/A', color: 'text-emerald-400' },
                      ].map(item => (
                        <div key={item.label} className="bg-slate-800 rounded-lg p-3 border border-slate-700">
                          <div className="text-slate-400 text-xs mb-1">{item.label}</div>
                          <div className={`text-xl font-bold ${item.color}`}>{item.value}</div>
                        </div>
                      ))}
                    </div>
                    <div className="flex justify-end">
                      <button
                        onClick={() => openReport(tenant)}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm transition-colors"
                      >
                        <BarChart2 className="w-4 h-4" />
                        View Full Report
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Aggregated Alerts */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-5 h-5 text-red-400" />
          <h2 className="text-lg font-semibold text-white">Aggregated Critical/High Alerts</h2>
        </div>
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          {alerts.length === 0 ? (
            <div className="p-8 text-center text-slate-400">No critical or high alerts</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    {['Tenant', 'Severity', 'Event Type', 'Description', 'Timestamp'].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-slate-400 text-xs font-semibold uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {alerts.map(alert => (
                    <tr key={alert.id} className="border-b border-slate-700/50 hover:bg-slate-750">
                      <td className="px-4 py-3 text-white text-sm">{alert.tenant_name}</td>
                      <td className="px-4 py-3">
                        <span className={`text-sm font-semibold capitalize ${SEVERITY_COLORS[alert.severity]}`}>
                          {alert.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300 text-sm">{alert.event_type}</td>
                      <td className="px-4 py-3 text-slate-400 text-sm max-w-xs truncate">{alert.description}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Report Modal */}
      {reportModal.open && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div>
                <h3 className="text-white font-semibold">Tenant Summary Report</h3>
                <p className="text-slate-400 text-sm">{reportModal.tenantName}</p>
              </div>
              <button
                onClick={() => setReportModal(prev => ({ ...prev, open: false }))}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              {reportModal.loading ? (
                <div className="flex items-center justify-center h-32">
                  <Activity className="w-5 h-5 animate-spin text-blue-400 mr-2" />
                  <span className="text-slate-400">Generating report...</span>
                </div>
              ) : (
                <pre className="text-slate-300 text-xs bg-slate-900 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap">
                  {reportModal.report}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
