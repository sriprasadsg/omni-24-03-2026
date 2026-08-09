import React, { useEffect, useState, useCallback } from 'react';
import { Asset, ItamBookValue, ItamWarrantyStatus } from '../../types';
import { fetchAssets, updateAssetPurchase, fetchAssetBookValue, fetchAssetWarranty } from '../../services/apiService';
import { showToast } from '../../utils/toast';

const WARRANTY_COLOR: Record<string, string> = {
  active: 'text-green-500 bg-green-900/20 border-green-800',
  expiring: 'text-amber-500 bg-amber-900/20 border-amber-800',
  expired: 'text-red-400 bg-red-900/20 border-red-800',
  none: 'text-gray-400 bg-gray-800 border-gray-700',
};

export function FinancePanel() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [bookValue, setBookValue] = useState<ItamBookValue | null>(null);
  const [warranty, setWarranty] = useState<ItamWarrantyStatus | null>(null);
  const [form, setForm] = useState({ purchaseCostCents: '', purchaseDate: '', poNumber: '', warrantyMonths: '' });

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        setAssets((await fetchAssets()) || []);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const loadFinance = useCallback(async (assetId: string) => {
    const [bv, w] = await Promise.all([fetchAssetBookValue(assetId), fetchAssetWarranty(assetId)]);
    setBookValue(bv);
    setWarranty(w);
    setForm({
      purchaseCostCents: bv.purchaseCostCents != null ? String(bv.purchaseCostCents / 100) : '',
      purchaseDate: w.purchaseDate || '',
      poNumber: '',
      warrantyMonths: w.warrantyMonths != null ? String(w.warrantyMonths) : '',
    });
  }, []);

  useEffect(() => {
    if (selectedId) loadFinance(selectedId);
    else { setBookValue(null); setWarranty(null); }
  }, [selectedId, loadFinance]);

  async function handleSave() {
    if (!selectedId) return;
    setSaving(true);
    try {
      await updateAssetPurchase(selectedId, {
        purchaseCostCents: form.purchaseCostCents ? Math.round(Number(form.purchaseCostCents) * 100) : undefined,
        purchaseDate: form.purchaseDate || undefined,
        poNumber: form.poNumber || undefined,
        warrantyMonths: form.warrantyMonths ? Number(form.warrantyMonths) : undefined,
      });
      showToast('Purchase record saved.', 'success');
      await loadFinance(selectedId);
    } catch (e: any) {
      showToast(e?.message || "Couldn't save purchase record.", 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <label className="text-xs font-semibold text-gray-400" htmlFor="itam-finance-asset">Asset</label>
        <select
          id="itam-finance-asset"
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white min-w-[240px]"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          disabled={loading}
        >
          <option value="">Select an asset…</option>
          {assets.map((a) => <option key={a.id} value={a.id}>{a.hostname || a.assetTag || a.id}</option>)}
        </select>
      </div>

      {!selectedId && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-8 text-center">
          <h3 className="text-sm font-semibold text-white mb-1">Select an asset</h3>
          <p className="text-gray-500 text-xs">Choose an asset from the list to view its purchase record, warranty status, and book value.</p>
        </div>
      )}

      {selectedId && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Purchase Record</h3>
            <div className="space-y-3">
              <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="number" placeholder="Purchase Cost ($)" value={form.purchaseCostCents} onChange={(e) => setForm({ ...form, purchaseCostCents: e.target.value })} aria-label="Purchase Cost" />
              <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="date" value={form.purchaseDate ? form.purchaseDate.slice(0, 10) : ''} onChange={(e) => setForm({ ...form, purchaseDate: e.target.value })} aria-label="Purchase Date" />
              <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="PO Number" value={form.poNumber} onChange={(e) => setForm({ ...form, poNumber: e.target.value })} aria-label="PO Number" />
              <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="number" placeholder="Warranty (months)" value={form.warrantyMonths} onChange={(e) => setForm({ ...form, warrantyMonths: e.target.value })} aria-label="Warranty Months" />
              <button
                onClick={handleSave}
                disabled={saving}
                className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
              >
                {saving ? 'Saving…' : 'Save Purchase Record'}
              </button>
            </div>
          </div>

          <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Warranty & Book Value</h3>
            {warranty && (
              <div className="mb-4">
                <span className={`text-xs px-2 py-0.5 rounded border ${WARRANTY_COLOR[warranty.warrantyStatus] || WARRANTY_COLOR.none}`}>
                  {warranty.warrantyStatus}
                </span>
                {warranty.warrantyExpiresAt && (
                  <p className="text-gray-400 text-xs mt-2">Expires {warranty.warrantyExpiresAt.slice(0, 10)} ({warranty.daysToExpiry} days)</p>
                )}
              </div>
            )}
            {bookValue && (
              <div>
                {bookValue.bookValueCents != null ? (
                  <p className="text-white text-lg font-semibold">${(bookValue.bookValueCents / 100).toLocaleString()}</p>
                ) : (
                  <p className="text-gray-500 text-xs italic">
                    {bookValue.reason === 'no_purchase_record' ? 'No purchase record yet.' : 'No depreciation policy set on this asset\'s Model.'}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
