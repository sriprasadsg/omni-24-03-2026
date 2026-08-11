import React, { useEffect, useState, useCallback } from 'react';
import Modal from '../ui/Modal';
import { Asset, ItamCatalogEntity, ItamLifecycleStatus, Tenant } from '../../types';
import { fetchAssets, createManualAsset, checkoutAsset, checkinAsset, markAssetAudited, fetchCatalogEntities, fetchAssetQrLabel } from '../../services/apiService';
import { showToast } from '../../utils/toast';

const STATUS_COLORS: Record<string, string> = {
  deployable: 'text-green-500 bg-green-900/20 border-green-800',
  deployed: 'text-amber-500 bg-amber-900/20 border-amber-800',
  archived: 'text-gray-400 bg-gray-800 border-gray-700',
  retired: 'text-gray-400 bg-gray-800 border-gray-700',
  disposed: 'text-gray-400 bg-gray-800 border-gray-700',
  broken: 'text-red-400 bg-red-900/20 border-red-800',
};

interface LifecyclePanelProps {
  tenants?: Tenant[];
  isSuperAdminView?: boolean;
}

export function LifecyclePanel({ tenants = [], isSuperAdminView = false }: LifecyclePanelProps) {
  const tenantName = (tenantId?: string) => tenants.find((t) => t.id === tenantId)?.name || tenantId || '—';
  const [assets, setAssets] = useState<Asset[]>([]);
  const [manufacturers, setManufacturers] = useState<ItamCatalogEntity[]>([]);
  const [categories, setCategories] = useState<ItamCatalogEntity[]>([]);
  const [locations, setLocations] = useState<ItamCatalogEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [newAsset, setNewAsset] = useState({ name: '', assetTag: '', lifecycleStatus: 'deployable' as ItamLifecycleStatus, manufacturerId: '', categoryId: '', locationId: '' });

  const [checkoutTarget, setCheckoutTarget] = useState<Asset | null>(null);
  const [checkoutForm, setCheckoutForm] = useState({ targetType: 'user' as 'user' | 'location', targetId: '', note: '' });
  const [checkinTarget, setCheckinTarget] = useState<Asset | null>(null);
  const [auditTarget, setAuditTarget] = useState<Asset | null>(null);
  const [actionNote, setActionNote] = useState('');
  const [labelMenuAssetId, setLabelMenuAssetId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, m, c, l] = await Promise.all([
        fetchAssets(),
        fetchCatalogEntities('manufacturers'),
        fetchCatalogEntities('categories'),
        fetchCatalogEntities('locations'),
      ]);
      setAssets(a || []);
      setManufacturers(m);
      setCategories(c);
      setLocations(l);
    } catch (e: any) {
      setError(e?.message || "Couldn't load assets");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleAddAsset() {
    if (!newAsset.name.trim()) return;
    try {
      await createManualAsset({
        name: newAsset.name.trim(),
        assetTag: newAsset.assetTag.trim() || undefined,
        lifecycleStatus: newAsset.lifecycleStatus,
        manufacturerId: newAsset.manufacturerId || undefined,
        categoryId: newAsset.categoryId || undefined,
        locationId: newAsset.locationId || undefined,
      });
      showToast('Asset created.', 'success');
      setAddOpen(false);
      setNewAsset({ name: '', assetTag: '', lifecycleStatus: 'deployable', manufacturerId: '', categoryId: '', locationId: '' });
      load();
    } catch (e: any) {
      showToast(e?.message || "Couldn't save asset.", 'error');
    }
  }

  async function handleCheckout() {
    if (!checkoutTarget || !checkoutForm.targetId.trim()) return;
    try {
      await checkoutAsset(checkoutTarget.id, {
        targetType: checkoutForm.targetType,
        targetId: checkoutForm.targetId.trim(),
        note: checkoutForm.note.trim() || undefined,
      });
      showToast('Asset checked out.', 'success');
      setCheckoutTarget(null);
      setCheckoutForm({ targetType: 'user', targetId: '', note: '' });
      load();
    } catch (e: any) {
      showToast(e?.message || 'Checkout failed.', 'error');
    }
  }

  async function handleCheckin() {
    if (!checkinTarget) return;
    try {
      await checkinAsset(checkinTarget.id, actionNote.trim() || undefined);
      showToast('Asset checked in.', 'success');
      setCheckinTarget(null);
      setActionNote('');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Check-in failed.', 'error');
    }
  }

  async function handleAudit() {
    if (!auditTarget) return;
    try {
      await markAssetAudited(auditTarget.id, actionNote.trim() || undefined);
      showToast('Audit recorded.', 'success');
      setAuditTarget(null);
      setActionNote('');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to record audit.', 'error');
    }
  }

  async function handleLabelDownload(assetId: string, kind: 'qr' | 'barcode' | 'sheet') {
    setLabelMenuAssetId(null);
    try {
      switch (kind) {
        case 'qr':
          await fetchAssetQrLabel(assetId);
          break;
      }
    } catch (e: any) {
      showToast(e?.message || 'Failed to generate label.', 'error');
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Assets</h3>
        <button
          onClick={() => setAddOpen(true)}
          className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          Add Asset
        </button>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && assets.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No assets yet</h3>
            <p className="text-gray-500 text-xs">Add a manual asset, or check back once agent-discovered assets sync.</p>
          </div>
        )}
        {!loading && !error && assets.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                  <th className="py-2 pr-4">Tag</th>
                  <th className="py-2 pr-4">Name</th>
                  {isSuperAdminView && <th className="py-2 pr-4">Tenant</th>}
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Assigned To</th>
                  <th className="py-2 pr-4">Logged-in User</th>
                  <th className="py-2 pr-4" />
                </tr>
              </thead>
              <tbody>
                {assets.slice(0, 500).map((a) => {
                  const status = a.lifecycleStatus || 'deployable';
                  return (
                    <tr key={a.id} className="border-b border-gray-800">
                      <td className="py-2 pr-4 text-gray-400 font-mono text-xs">{a.assetTag || '—'}</td>
                      <td className="py-2 pr-4 text-white max-w-[200px] truncate" title={a.hostname}>{a.hostname || '—'}</td>
                      {isSuperAdminView && <td className="py-2 pr-4 text-gray-400 max-w-[160px] truncate" title={tenantName(a.tenantId)}>{tenantName(a.tenantId)}</td>}
                      <td className="py-2 pr-4">
                        <span className={`text-xs px-2 py-0.5 rounded border ${STATUS_COLORS[status] || STATUS_COLORS.deployable}`}>
                          {status}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-gray-400">{a.assignedToId ? `${a.assignedToType}: ${a.assignedToId}` : '—'}</td>
                      <td className="py-2 pr-4 text-gray-400">{a.loggedInUser || '—'}</td>
                      <td className="py-2 pr-4 text-right whitespace-nowrap">
                        {a.assignedToId ? (
                          <button onClick={() => setCheckinTarget(a)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3">Check In</button>
                        ) : (
                          <button onClick={() => setCheckoutTarget(a)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3">Check Out</button>
                        )}
                        <button onClick={() => setAuditTarget(a)} className="text-gray-400 hover:text-gray-200 text-xs font-medium">Mark Audited</button>
                        <div className="relative inline-block">
                          <button
                            onClick={() => setLabelMenuAssetId(labelMenuAssetId === a.id ? null : a.id)}
                            className="text-gray-400 hover:text-gray-200 text-xs font-medium ml-3"
                            aria-haspopup="true"
                            aria-expanded={labelMenuAssetId === a.id}
                          >
                            Label
                          </button>
                          {labelMenuAssetId === a.id && (
                            <div className="absolute right-0 mt-1 w-44 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10">
                              <button onClick={() => handleLabelDownload(a.id, 'qr')} className="block w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-700">QR Code</button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="Add Asset" confirmLabel="Save" onConfirm={handleAddAsset}>
        <div className="space-y-3 mb-4">
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Name" value={newAsset.name} onChange={(e) => setNewAsset({ ...newAsset, name: e.target.value })} aria-label="Name" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Asset Tag (optional — auto-generated if blank)" value={newAsset.assetTag} onChange={(e) => setNewAsset({ ...newAsset, assetTag: e.target.value })} aria-label="Asset Tag" />
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={newAsset.lifecycleStatus} onChange={(e) => setNewAsset({ ...newAsset, lifecycleStatus: e.target.value as ItamLifecycleStatus })} aria-label="Lifecycle Status">
            {['deployable', 'deployed', 'archived', 'retired', 'disposed', 'broken'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={newAsset.manufacturerId} onChange={(e) => setNewAsset({ ...newAsset, manufacturerId: e.target.value })} aria-label="Manufacturer">
            <option value="">No manufacturer</option>
            {manufacturers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={newAsset.categoryId} onChange={(e) => setNewAsset({ ...newAsset, categoryId: e.target.value })} aria-label="Category">
            <option value="">No category</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={newAsset.locationId} onChange={(e) => setNewAsset({ ...newAsset, locationId: e.target.value })} aria-label="Location">
            <option value="">No location</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>
      </Modal>

      <Modal isOpen={!!checkoutTarget} onClose={() => setCheckoutTarget(null)} title="Check Out Asset" confirmLabel="Check Out" onConfirm={handleCheckout}>
        <div className="space-y-3 mb-4">
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={checkoutForm.targetType} onChange={(e) => setCheckoutForm({ ...checkoutForm, targetType: e.target.value as 'user' | 'location' })} aria-label="Assign To Type">
            <option value="user">User</option>
            <option value="location">Location</option>
          </select>
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder={checkoutForm.targetType === 'user' ? 'User ID' : 'Location ID'} value={checkoutForm.targetId} onChange={(e) => setCheckoutForm({ ...checkoutForm, targetId: e.target.value })} aria-label="Target ID" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Note (optional)" value={checkoutForm.note} onChange={(e) => setCheckoutForm({ ...checkoutForm, note: e.target.value })} aria-label="Note" />
        </div>
      </Modal>

      <Modal isOpen={!!checkinTarget} onClose={() => { setCheckinTarget(null); setActionNote(''); }} title="Check In Asset" confirmLabel="Check In" onConfirm={handleCheckin}>
        <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mb-4" placeholder="Note (optional)" value={actionNote} onChange={(e) => setActionNote(e.target.value)} aria-label="Note" />
      </Modal>

      <Modal isOpen={!!auditTarget} onClose={() => { setAuditTarget(null); setActionNote(''); }} title="Mark Asset Audited" confirmLabel="Mark Audited" onConfirm={handleAudit}>
        <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mb-4" placeholder="Note (optional)" value={actionNote} onChange={(e) => setActionNote(e.target.value)} aria-label="Note" />
      </Modal>
    </div>
  );
}
