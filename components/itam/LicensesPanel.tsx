import React, { useEffect, useState, useCallback } from 'react';
import Modal from '../ui/Modal';
import { ItamLicense, ItamConsumable, ItamComponent } from '../../types';
import {
  fetchLicenses, createLicense, assignLicenseSeat, reclaimLicenseSeat, fetchLicenseAssignments,
  fetchConsumables, createConsumable, checkoutConsumable, checkinConsumable,
  fetchComponents, createComponent, attachComponent, detachComponent,
} from '../../services/apiService';
import { showToast } from '../../utils/toast';

type Section = 'licenses' | 'consumables' | 'components';

export function LicensesPanel() {
  const [section, setSection] = useState<Section>('licenses');

  return (
    <div>
      <nav className="flex gap-1 mb-4" aria-label="Licenses & Consumables section">
        {(['licenses', 'consumables', 'components'] as Section[]).map((s) => (
          <button
            key={s}
            onClick={() => setSection(s)}
            aria-current={section === s ? 'page' : undefined}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg capitalize transition-colors ${
              section === s ? 'bg-cyan-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {s}
          </button>
        ))}
      </nav>
      {section === 'licenses' && <LicensesSection />}
      {section === 'consumables' && <ConsumablesSection />}
      {section === 'components' && <ComponentsSection />}
    </div>
  );
}

function LicensesSection() {
  const [licenses, setLicenses] = useState<ItamLicense[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ name: '', seatCount: '1', expiryDate: '' });
  const [assignTarget, setAssignTarget] = useState<ItamLicense | null>(null);
  const [assignForm, setAssignForm] = useState({ targetType: 'user' as 'user' | 'asset', targetId: '' });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLicenses(await fetchLicenses());
    } catch (e: any) {
      setError(e?.message || "Couldn't load licenses");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!form.name.trim()) return;
    try {
      await createLicense({ name: form.name.trim(), seatCount: Number(form.seatCount) || 0, expiryDate: form.expiryDate || undefined });
      showToast('License created.', 'success');
      setAddOpen(false);
      setForm({ name: '', seatCount: '1', expiryDate: '' });
      load();
    } catch (e: any) {
      showToast(e?.message || "Couldn't save license.", 'error');
    }
  }

  async function handleAssign() {
    if (!assignTarget || !assignForm.targetId.trim()) return;
    try {
      await assignLicenseSeat(assignTarget.id, { targetType: assignForm.targetType, targetId: assignForm.targetId.trim() });
      showToast('Seat assigned.', 'success');
      setAssignTarget(null);
      setAssignForm({ targetType: 'user', targetId: '' });
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to assign seat.', 'error');
    }
  }

  async function handleReclaimFirstSeat(license: ItamLicense) {
    try {
      const assignments = await fetchLicenseAssignments(license.id);
      if (assignments.length === 0) {
        showToast('No seats assigned.', 'error');
        return;
      }
      await reclaimLicenseSeat(assignments[0].id);
      showToast('Seat reclaimed.', 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to reclaim seat.', 'error');
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Software Licenses</h3>
        <button onClick={() => setAddOpen(true)} className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">Add License</button>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && licenses.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No licenses yet</h3>
            <p className="text-gray-500 text-xs">Add a software license to start tracking seats and expiry.</p>
          </div>
        )}
        {!loading && !error && licenses.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Seats</th>
                <th className="py-2 pr-4">Expiry</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {licenses.map((l) => (
                <tr key={l.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-white font-medium">{l.name}</td>
                  <td className="py-2 pr-4 text-gray-300">{l.seatsAvailable ?? '—'} / {l.seatCount}</td>
                  <td className="py-2 pr-4">
                    {l.expiryDate ? (
                      <span className={`text-xs px-2 py-0.5 rounded border ${l.isExpired ? 'text-red-400 bg-red-900/20 border-red-800' : 'text-green-500 bg-green-900/20 border-green-800'}`}>
                        {l.expiryDate.slice(0, 10)}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right whitespace-nowrap">
                    <button onClick={() => setAssignTarget(l)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3">Assign Seat</button>
                    <button onClick={() => handleReclaimFirstSeat(l)} className="text-red-400 hover:text-red-300 text-xs font-medium">Reclaim Seat</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="Add License" confirmLabel="Save" onConfirm={handleCreate}>
        <div className="space-y-3 mb-4">
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="License name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Name" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="number" min={0} placeholder="Seat count" value={form.seatCount} onChange={(e) => setForm({ ...form, seatCount: e.target.value })} aria-label="Seat Count" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="date" value={form.expiryDate} onChange={(e) => setForm({ ...form, expiryDate: e.target.value })} aria-label="Expiry Date" />
        </div>
      </Modal>

      <Modal isOpen={!!assignTarget} onClose={() => setAssignTarget(null)} title="Assign Seat" confirmLabel="Assign Seat" onConfirm={handleAssign}>
        <div className="space-y-3 mb-4">
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={assignForm.targetType} onChange={(e) => setAssignForm({ ...assignForm, targetType: e.target.value as 'user' | 'asset' })} aria-label="Target Type">
            <option value="user">User</option>
            <option value="asset">Asset</option>
          </select>
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder={assignForm.targetType === 'user' ? 'User ID' : 'Asset ID'} value={assignForm.targetId} onChange={(e) => setAssignForm({ ...assignForm, targetId: e.target.value })} aria-label="Target ID" />
        </div>
      </Modal>
    </div>
  );
}

function ConsumablesSection() {
  const [items, setItems] = useState<ItamConsumable[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ name: '', initialQuantity: '1', unitType: 'unit' });
  const [checkoutTarget, setCheckoutTarget] = useState<ItamConsumable | null>(null);
  const [checkoutForm, setCheckoutForm] = useState({ quantity: '1', assignedTo: '', assignedToType: 'user' as 'user' | 'asset' | 'location' });

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await fetchConsumables()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!form.name.trim()) return;
    try {
      await createConsumable({ name: form.name.trim(), initialQuantity: Number(form.initialQuantity) || 0, unitType: form.unitType });
      showToast('Consumable created.', 'success');
      setAddOpen(false);
      setForm({ name: '', initialQuantity: '1', unitType: 'unit' });
      load();
    } catch (e: any) {
      showToast(e?.message || "Couldn't save consumable.", 'error');
    }
  }

  async function handleCheckout() {
    if (!checkoutTarget || !checkoutForm.assignedTo.trim()) return;
    try {
      await checkoutConsumable(checkoutTarget.id, { quantity: Number(checkoutForm.quantity) || 1, assignedTo: checkoutForm.assignedTo.trim(), assignedToType: checkoutForm.assignedToType });
      showToast('Checked out.', 'success');
      setCheckoutTarget(null);
      setCheckoutForm({ quantity: '1', assignedTo: '', assignedToType: 'user' });
      load();
    } catch (e: any) {
      showToast(e?.message || 'Checkout failed.', 'error');
    }
  }

  async function handleCheckin(item: ItamConsumable) {
    const qty = window.prompt(`Check in how many units of "${item.name}"?`, '1');
    if (!qty) return;
    try {
      await checkinConsumable(item.id, Number(qty));
      showToast('Checked in.', 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Check-in failed.', 'error');
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Consumables</h3>
        <button onClick={() => setAddOpen(true)} className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">Add Consumable</button>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {!loading && items.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No consumables yet</h3>
            <p className="text-gray-500 text-xs">Add an accessory or consumable to start tracking stock.</p>
          </div>
        )}
        {!loading && items.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Available</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-white font-medium">{c.name}</td>
                  <td className="py-2 pr-4 text-gray-300">{c.availableQuantity} / {c.initialQuantity} {c.unitType}</td>
                  <td className="py-2 pr-4 text-right whitespace-nowrap">
                    <button onClick={() => setCheckoutTarget(c)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3">Check Out</button>
                    <button onClick={() => handleCheckin(c)} className="text-gray-400 hover:text-gray-200 text-xs font-medium">Check In</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="Add Consumable" confirmLabel="Save" onConfirm={handleCreate}>
        <div className="space-y-3 mb-4">
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Name" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="number" min={0} placeholder="Initial quantity" value={form.initialQuantity} onChange={(e) => setForm({ ...form, initialQuantity: e.target.value })} aria-label="Initial Quantity" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Unit type (e.g. unit, pack)" value={form.unitType} onChange={(e) => setForm({ ...form, unitType: e.target.value })} aria-label="Unit Type" />
        </div>
      </Modal>

      <Modal isOpen={!!checkoutTarget} onClose={() => setCheckoutTarget(null)} title="Check Out Consumable" confirmLabel="Check Out" onConfirm={handleCheckout}>
        <div className="space-y-3 mb-4">
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" type="number" min={1} placeholder="Quantity" value={checkoutForm.quantity} onChange={(e) => setCheckoutForm({ ...checkoutForm, quantity: e.target.value })} aria-label="Quantity" />
          <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" value={checkoutForm.assignedToType} onChange={(e) => setCheckoutForm({ ...checkoutForm, assignedToType: e.target.value as any })} aria-label="Assigned To Type">
            <option value="user">User</option>
            <option value="asset">Asset</option>
            <option value="location">Location</option>
          </select>
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Assigned To (id)" value={checkoutForm.assignedTo} onChange={(e) => setCheckoutForm({ ...checkoutForm, assignedTo: e.target.value })} aria-label="Assigned To" />
        </div>
      </Modal>
    </div>
  );
}

function ComponentsSection() {
  const [items, setItems] = useState<ItamComponent[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ name: '', type: '' });
  const [attachTarget, setAttachTarget] = useState<ItamComponent | null>(null);
  const [assetId, setAssetId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await fetchComponents()); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!form.name.trim()) return;
    try {
      await createComponent({ name: form.name.trim(), type: form.type.trim() || undefined });
      showToast('Component created.', 'success');
      setAddOpen(false);
      setForm({ name: '', type: '' });
      load();
    } catch (e: any) {
      showToast(e?.message || "Couldn't save component.", 'error');
    }
  }

  async function handleAttach() {
    if (!attachTarget || !assetId.trim()) return;
    try {
      await attachComponent(attachTarget.id, assetId.trim());
      showToast('Component attached.', 'success');
      setAttachTarget(null);
      setAssetId('');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to attach component.', 'error');
    }
  }

  async function handleDetach(item: ItamComponent) {
    if (!item.parentAssetId) return;
    try {
      await detachComponent(item.id, item.parentAssetId);
      showToast('Component detached.', 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to detach component.', 'error');
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Components</h3>
        <button onClick={() => setAddOpen(true)} className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">Add Component</button>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {!loading && items.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No components yet</h3>
            <p className="text-gray-500 text-xs">Add a RAM/HDD/GPU-style component to attach it to an asset.</p>
          </div>
        )}
        {!loading && items.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Attached To</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-white font-medium">{c.name}</td>
                  <td className="py-2 pr-4 text-gray-400">{c.type || '—'}</td>
                  <td className="py-2 pr-4 text-gray-400">{c.parentAssetId || '—'}</td>
                  <td className="py-2 pr-4 text-right whitespace-nowrap">
                    {c.parentAssetId ? (
                      <button onClick={() => handleDetach(c)} className="text-red-400 hover:text-red-300 text-xs font-medium">Detach</button>
                    ) : (
                      <button onClick={() => setAttachTarget(c)} className="text-cyan-400 hover:text-cyan-300 text-xs font-medium">Attach</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="Add Component" confirmLabel="Save" onConfirm={handleCreate}>
        <div className="space-y-3 mb-4">
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Name (e.g. RAM 16GB)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Name" />
          <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" placeholder="Type (e.g. ram, hdd, gpu)" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} aria-label="Type" />
        </div>
      </Modal>

      <Modal isOpen={!!attachTarget} onClose={() => setAttachTarget(null)} title="Attach Component" confirmLabel="Attach" onConfirm={handleAttach}>
        <input className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white mb-4" placeholder="Asset ID" value={assetId} onChange={(e) => setAssetId(e.target.value)} aria-label="Asset ID" />
      </Modal>
    </div>
  );
}
