import React, { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/apiService';

interface InventoryItem {
  asset_id: string;
  asset_name: string;
  component: string;
  type: 'driver' | 'firmware';
  version: string;
  manufacturer: string;
  date: string;
  status: 'current' | 'outdated';
}

interface UpdateItem {
  id: string;
  type: 'driver' | 'firmware';
  component: string;
  current_version: string;
  available_version: string;
  manufacturer: string;
  severity: 'critical' | 'recommended' | 'optional';
  release_date: string;
  kb_article: string;
}

interface DeployJob {
  id: string;
  name: string;
  update_ids: string[];
  status: string;
  created_at: string;
  success_count: number;
  failure_count: number;
}

interface ComplianceReport {
  total_assets: number;
  assets_with_outdated_drivers: number;
  assets_with_outdated_firmware: number;
  critical_updates_pending: number;
  driver_compliance_pct: number;
  firmware_compliance_pct: number;
}

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-900/50 text-red-300 border border-red-700',
  recommended: 'bg-orange-900/50 text-orange-300 border border-orange-700',
  optional: 'bg-slate-700 text-slate-300',
};

const STATUS_BADGE: Record<string, string> = {
  current: 'bg-green-900/50 text-green-300',
  outdated: 'bg-red-900/50 text-red-300',
};

const JOB_STATUS_BADGE: Record<string, string> = {
  pending: 'bg-yellow-900/50 text-yellow-300',
  running: 'bg-blue-900/50 text-blue-300',
  completed: 'bg-green-900/50 text-green-300',
  failed: 'bg-red-900/50 text-red-300',
};

export default function FirmwareDriverDashboard() {
  const [tab, setTab] = useState<'drivers' | 'firmware' | 'updates' | 'jobs'>('drivers');
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [updates, setUpdates] = useState<UpdateItem[]>([]);
  const [jobs, setJobs] = useState<DeployJob[]>([]);
  const [compliance, setCompliance] = useState<ComplianceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deploying, setDeploying] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [inv, upd, jobList, comp] = await Promise.all([
        apiService.get('/api/firmware-drivers/inventory'),
        apiService.get('/api/firmware-drivers/updates/available'),
        apiService.get('/api/firmware-drivers/updates/jobs'),
        apiService.get('/api/firmware-drivers/reports/compliance'),
      ]);
      setInventory(Array.isArray((inv as any)?.items) ? (inv as any).items : []);
      setUpdates(Array.isArray(upd) ? upd : []);
      setJobs(Array.isArray(jobList) ? jobList : []);
      setCompliance(comp);
    } catch {
      // empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const deploySelected = async () => {
    if (selected.size === 0) return;
    setDeploying(true);
    try {
      const job = await apiService.post('/api/firmware-drivers/updates/deploy', {
        update_ids: Array.from(selected),
        name: `Driver/Firmware Update ${new Date().toISOString().slice(0, 10)}`,
      });
      setJobs(prev => [job, ...prev]);
      setSelected(new Set());
      setTab('jobs');
    } finally {
      setDeploying(false);
    }
  };

  const toggleSelect = (id: string) => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const drivers = inventory.filter(i => i.type === 'driver');
  const firmware = inventory.filter(i => i.type === 'firmware');

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Firmware & Driver Updates</h1>
          <p className="text-slate-400 text-sm mt-1">Driver inventory, firmware versions, and update deployment</p>
        </div>
        <button onClick={loadData} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm">
          Refresh
        </button>
      </div>

      {compliance && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
            <div className="text-slate-400 text-xs mb-1">Driver Compliance</div>
            <div className="text-2xl font-bold text-white">{compliance.driver_compliance_pct}%</div>
            <div className="text-slate-500 text-xs">{compliance.assets_with_outdated_drivers} assets need updates</div>
          </div>
          <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
            <div className="text-slate-400 text-xs mb-1">Firmware Compliance</div>
            <div className="text-2xl font-bold text-white">{compliance.firmware_compliance_pct}%</div>
            <div className="text-slate-500 text-xs">{compliance.assets_with_outdated_firmware} assets need updates</div>
          </div>
          <div className="bg-slate-800 rounded-xl p-4 border border-red-900">
            <div className="text-slate-400 text-xs mb-1">Critical Updates</div>
            <div className="text-2xl font-bold text-red-400">{compliance.critical_updates_pending}</div>
            <div className="text-slate-500 text-xs">require immediate action</div>
          </div>
        </div>
      )}

      <div className="flex gap-2 flex-wrap items-center">
        <div className="flex border border-slate-700 rounded-lg overflow-hidden">
          {(['drivers', 'firmware', 'updates', 'jobs'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'}`}>
              {t === 'drivers' ? `Drivers (${drivers.length})` :
               t === 'firmware' ? `Firmware (${firmware.length})` :
               t === 'updates' ? `Available Updates (${updates.length})` :
               `Jobs (${jobs.length})`}
            </button>
          ))}
        </div>
        {tab === 'updates' && selected.size > 0 && (
          <button onClick={deploySelected} disabled={deploying}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm disabled:opacity-50">
            {deploying ? 'Deploying...' : `Deploy Selected (${selected.size})`}
          </button>
        )}
      </div>

      {loading ? <div className="text-slate-400 text-center py-12">Loading...</div> : (
        <>
          {(tab === 'drivers' || tab === 'firmware') && (
            <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
              {(tab === 'drivers' ? drivers : firmware).length === 0 ? (
                <div className="text-slate-400 text-center py-12">No {tab} inventory data</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b border-slate-700">
                    <tr className="text-left text-slate-400">
                      <th className="px-4 py-3">Asset</th>
                      <th className="px-4 py-3">Component</th>
                      <th className="px-4 py-3">Manufacturer</th>
                      <th className="px-4 py-3">Version</th>
                      <th className="px-4 py-3">Date</th>
                      <th className="px-4 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    {(tab === 'drivers' ? drivers : firmware).map((item, i) => (
                      <tr key={i} className="hover:bg-slate-700/30">
                        <td className="px-4 py-3 text-slate-300">{item.asset_name}</td>
                        <td className="px-4 py-3 text-white font-medium">{item.component}</td>
                        <td className="px-4 py-3 text-slate-400">{item.manufacturer}</td>
                        <td className="px-4 py-3 text-slate-300 font-mono text-xs">{item.version}</td>
                        <td className="px-4 py-3 text-slate-400 text-xs">{item.date}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_BADGE[item.status]}`}>{item.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {tab === 'updates' && (
            <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
              {updates.length === 0 ? (
                <div className="text-slate-400 text-center py-12">No available updates</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b border-slate-700">
                    <tr className="text-left text-slate-400">
                      <th className="px-4 py-3 w-8"></th>
                      <th className="px-4 py-3">Component</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Current</th>
                      <th className="px-4 py-3">Available</th>
                      <th className="px-4 py-3">Severity</th>
                      <th className="px-4 py-3">KB/Article</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    {updates.map(upd => (
                      <tr key={upd.id} className={`hover:bg-slate-700/30 ${selected.has(upd.id) ? 'bg-blue-900/20' : ''}`}>
                        <td className="px-4 py-3">
                          <input type="checkbox" checked={selected.has(upd.id)} onChange={() => toggleSelect(upd.id)} className="rounded" />
                        </td>
                        <td className="px-4 py-3 text-white font-medium">{upd.component}</td>
                        <td className="px-4 py-3 text-slate-400 capitalize">{upd.type}</td>
                        <td className="px-4 py-3 text-slate-400 font-mono text-xs">{upd.current_version}</td>
                        <td className="px-4 py-3 text-green-400 font-mono text-xs">{upd.available_version}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs ${SEVERITY_BADGE[upd.severity]}`}>{upd.severity}</span>
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-xs">{upd.kb_article || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {tab === 'jobs' && (
            <div className="space-y-3">
              {jobs.length === 0 ? (
                <div className="text-slate-400 text-center py-12">No deployment jobs yet</div>
              ) : (
                jobs.map(job => (
                  <div key={job.id} className="bg-slate-800 rounded-xl border border-slate-700 p-5">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-white font-semibold">{job.name}</h3>
                      <span className={`px-2 py-0.5 rounded text-xs ${JOB_STATUS_BADGE[job.status] || 'bg-slate-700 text-slate-300'}`}>{job.status}</span>
                    </div>
                    <div className="flex gap-6 text-sm text-slate-400">
                      <span>{job.update_ids?.length || 0} updates</span>
                      <span className="text-green-400">{job.success_count} succeeded</span>
                      {job.failure_count > 0 && <span className="text-red-400">{job.failure_count} failed</span>}
                      <span>{job.created_at?.slice(0, 16).replace('T', ' ')}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
