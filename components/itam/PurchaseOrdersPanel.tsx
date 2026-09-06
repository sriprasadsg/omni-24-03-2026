import React, { useEffect, useState, useCallback } from 'react';
import Modal from '../ui/Modal';
import { ItamPurchaseOrder, ItamPurchaseOrderItem } from '../../types';
import { fetchPurchaseOrders, createPurchaseOrder, updatePurchaseOrder, deletePurchaseOrder } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { PlusIcon, TrashIcon } from '../icons';

type ItemDraft = { name: string; quantity: string; unit_price: string };

const EMPTY_ITEM: ItemDraft = { name: '', quantity: '1', unit_price: '0' };

function emptyForm() {
  return { order_number: '', supplier_name: '', order_date: '', notes: '', items: [{ ...EMPTY_ITEM }] as ItemDraft[] };
}

function computeTotal(items: ItemDraft[]): number {
  return items.reduce((sum, it) => sum + (Number(it.quantity) || 0) * (Number(it.unit_price) || 0), 0);
}

export function PurchaseOrdersPanel() {
  const [orders, setOrders] = useState<ItamPurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOrders(await fetchPurchaseOrders());
    } catch (e: any) {
      setError(e?.message || "Couldn't load purchase orders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm());
    setModalOpen(true);
  }

  function openEdit(po: ItamPurchaseOrder) {
    setEditingId(po.id);
    setForm({
      order_number: po.order_number,
      supplier_name: po.supplier_name,
      order_date: po.order_date.slice(0, 10),
      notes: po.notes || '',
      items: po.items.map((it) => ({ name: it.name, quantity: String(it.quantity), unit_price: String(it.unit_price) })),
    });
    setModalOpen(true);
  }

  function updateItem(index: number, patch: Partial<ItemDraft>) {
    setForm((f) => ({ ...f, items: f.items.map((it, i) => (i === index ? { ...it, ...patch } : it)) }));
  }

  function addItem() {
    setForm((f) => ({ ...f, items: [...f.items, { ...EMPTY_ITEM }] }));
  }

  function removeItem(index: number) {
    setForm((f) => ({ ...f, items: f.items.length > 1 ? f.items.filter((_, i) => i !== index) : f.items }));
  }

  async function handleSubmit() {
    const items: ItamPurchaseOrderItem[] = form.items
      .filter((it) => it.name.trim())
      .map((it) => ({ name: it.name.trim(), quantity: Math.max(1, Number(it.quantity) || 1), unit_price: Math.max(0, Number(it.unit_price) || 0) }));

    if (!form.order_number.trim() || !form.supplier_name.trim() || !form.order_date || items.length === 0) return;

    const payload = {
      order_number: form.order_number.trim(),
      supplier_name: form.supplier_name.trim(),
      order_date: form.order_date,
      total_cost: computeTotal(form.items),
      items,
      notes: form.notes.trim() || undefined,
    };

    try {
      if (editingId) {
        await updatePurchaseOrder(editingId, payload);
        showToast('Purchase order updated.', 'success');
      } else {
        await createPurchaseOrder(payload);
        showToast('Purchase order created.', 'success');
      }
      setModalOpen(false);
      load();
    } catch (e: any) {
      showToast(e?.message || `Couldn't ${editingId ? 'update' : 'create'} purchase order.`, 'error');
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this purchase order? This cannot be undone.')) return;
    setSavingId(id);
    try {
      await deletePurchaseOrder(id);
      showToast('Purchase order deleted.', 'success');
      load();
    } catch (e: any) {
      showToast(e?.message || "Couldn't delete purchase order.", 'error');
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Purchase Orders</h3>
        <button onClick={openCreate} className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
          New Purchase Order
        </button>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && orders.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No purchase orders yet</h3>
            <p className="text-gray-500 text-xs">Create a purchase order to track supplier details and cost.</p>
          </div>
        )}
        {!loading && !error && orders.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Order #</th>
                <th className="py-2 pr-4">Supplier</th>
                <th className="py-2 pr-4">Order Date</th>
                <th className="py-2 pr-4">Items</th>
                <th className="py-2 pr-4">Total</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {orders.map((po) => (
                <tr key={po.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-white font-medium">{po.order_number}</td>
                  <td className="py-2 pr-4 text-gray-300">{po.supplier_name}</td>
                  <td className="py-2 pr-4 text-gray-300">{po.order_date.slice(0, 10)}</td>
                  <td className="py-2 pr-4 text-gray-300">{po.items.length}</td>
                  <td className="py-2 pr-4 text-gray-300">${po.total_cost.toFixed(2)}</td>
                  <td className="py-2 pr-4 text-right whitespace-nowrap">
                    <button
                      onClick={() => openEdit(po)}
                      className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-3"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(po.id)}
                      disabled={savingId === po.id}
                      className="text-red-400 hover:text-red-300 text-xs font-medium disabled:opacity-50"
                      aria-label={`Delete purchase order ${po.order_number}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingId ? 'Edit Purchase Order' : 'New Purchase Order'}
        confirmLabel={editingId ? 'Save' : 'Create'}
        onConfirm={handleSubmit}
      >
        <div className="space-y-3 mb-4">
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Order number"
            value={form.order_number}
            onChange={(e) => setForm({ ...form, order_number: e.target.value })}
            aria-label="Order Number"
          />
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Supplier name"
            value={form.supplier_name}
            onChange={(e) => setForm({ ...form, supplier_name: e.target.value })}
            aria-label="Supplier Name"
          />
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            type="date"
            value={form.order_date}
            onChange={(e) => setForm({ ...form, order_date: e.target.value })}
            aria-label="Order Date"
          />

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-gray-400">Items</span>
              <button type="button" onClick={addItem} className="text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 text-xs" aria-label="Add item">
                <PlusIcon size={12} /> Add item
              </button>
            </div>
            <div className="space-y-2">
              {form.items.map((item, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
                    placeholder="Item name"
                    value={item.name}
                    onChange={(e) => updateItem(idx, { name: e.target.value })}
                    aria-label={`Item ${idx + 1} name`}
                  />
                  <input
                    className="w-16 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
                    type="number"
                    min={1}
                    value={item.quantity}
                    onChange={(e) => updateItem(idx, { quantity: e.target.value })}
                    aria-label={`Item ${idx + 1} quantity`}
                  />
                  <input
                    className="w-24 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-white"
                    type="number"
                    min={0}
                    step="0.01"
                    value={item.unit_price}
                    onChange={(e) => updateItem(idx, { unit_price: e.target.value })}
                    aria-label={`Item ${idx + 1} unit price`}
                  />
                  <button
                    type="button"
                    onClick={() => removeItem(idx)}
                    disabled={form.items.length <= 1}
                    className="text-gray-500 hover:text-red-400 disabled:opacity-30"
                    aria-label={`Remove item ${idx + 1}`}
                  >
                    <TrashIcon size={14} />
                  </button>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">Total: ${computeTotal(form.items).toFixed(2)}</p>
          </div>

          <textarea
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Notes (optional)"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            aria-label="Notes"
            rows={2}
          />
        </div>
      </Modal>
    </div>
  );
}
