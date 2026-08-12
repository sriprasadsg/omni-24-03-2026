import React, { useEffect, useState, useCallback } from 'react';
import Modal from '../ui/Modal';
import { ItamCatalogEntity, ItamCatalogKind } from '../../types';
import { fetchCatalogEntities, createCatalogEntity, deleteCatalogEntity } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { CustomFieldsManager } from './CustomFieldsManager';

const KINDS: { id: ItamCatalogKind; label: string; singular: string }[] = [
  { id: 'manufacturers', label: 'Manufacturers', singular: 'Manufacturer' },
  { id: 'categories', label: 'Categories', singular: 'Category' },
  { id: 'locations', label: 'Locations', singular: 'Location' },
  { id: 'suppliers', label: 'Suppliers', singular: 'Supplier' },
  { id: 'models', label: 'Models', singular: 'Model' },
];

export function CatalogPanel() {
  const [kind, setKind] = useState<ItamCatalogKind>('manufacturers');
  const [entities, setEntities] = useState<ItamCatalogEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<ItamCatalogEntity | null>(null);
  const [fieldsTarget, setFieldsTarget] = useState<ItamCatalogEntity | null>(null);

  const kindMeta = KINDS.find((k) => k.id === kind)!;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntities(await fetchCatalogEntities(kind));
    } catch (e: any) {
      setError(e?.message || `Couldn't load ${kindMeta.label.toLowerCase()}`);
    } finally {
      setLoading(false);
    }
  }, [kind, kindMeta.label]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!name.trim()) return;
    try {
      await createCatalogEntity(kind, { name: name.trim(), notes: notes.trim() || undefined });
      showToast(`${kindMeta.singular} created.`, 'success');
      setAddOpen(false);
      setName('');
      setNotes('');
      load();
    } catch (e: any) {
      showToast(e?.message || `Couldn't save ${kindMeta.singular.toLowerCase()}.`, 'error');
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteCatalogEntity(kind, deleteTarget.id);
      showToast(`${kindMeta.singular} deleted.`, 'success');
      setDeleteTarget(null);
      load();
    } catch (e: any) {
      showToast(e?.message || `Couldn't delete ${kindMeta.singular.toLowerCase()}.`, 'error');
      setDeleteTarget(null);
    }
  }

  if (fieldsTarget) {
    return (
      <CustomFieldsManager
        modelId={fieldsTarget.id}
        modelName={fieldsTarget.name}
        onClose={() => setFieldsTarget(null)}
      />
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <nav className="flex gap-1" aria-label="Catalog kind">
          {KINDS.map((k) => (
            <button
              key={k.id}
              onClick={() => setKind(k.id)}
              aria-current={kind === k.id ? 'page' : undefined}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                kind === k.id ? 'bg-cyan-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              {k.label}
            </button>
          ))}
        </nav>
        <button
          onClick={() => setAddOpen(true)}
          className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          Add {kindMeta.singular}
        </button>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm">{error}</p>}
        {!loading && !error && entities.length === 0 && (
          <div className="text-center py-8">
            <h3 className="text-sm font-semibold text-white mb-1">No {kind} yet</h3>
            <p className="text-gray-500 text-xs">Add your first {kindMeta.singular.toLowerCase()} to start building the asset catalog.</p>
          </div>
        )}
        {!loading && !error && entities.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Notes</th>
                <th className="py-2 pr-4" />
              </tr>
            </thead>
            <tbody>
              {entities.map((e) => (
                <tr key={e.id} className="border-b border-gray-800">
                  <td className="py-2 pr-4 text-white font-medium">{e.name}</td>
                  <td className="py-2 pr-4 text-gray-400 max-w-[320px] truncate" title={e.notes}>{e.notes || '—'}</td>
                  <td className="py-2 pr-4 text-right">
                    {kind === 'models' && (
                      <button
                        onClick={() => setFieldsTarget(e)}
                        className="text-cyan-400 hover:text-cyan-300 text-xs font-medium mr-4"
                        aria-label={`Manage fields for ${e.name}`}
                      >
                        Manage Fields
                      </button>
                    )}
                    <button
                      onClick={() => setDeleteTarget(e)}
                      className="text-red-400 hover:text-red-300 text-xs font-medium"
                      aria-label={`Delete ${e.name}`}
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
        isOpen={addOpen}
        onClose={() => setAddOpen(false)}
        title={`Add ${kindMeta.singular}`}
        confirmLabel="Save"
        onConfirm={handleCreate}
      >
        <div className="space-y-3 mb-4">
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Name"
          />
          <textarea
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white"
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            aria-label="Notes"
          />
        </div>
      </Modal>

      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title={`Delete ${kindMeta.singular}?`}
        description="This can't be undone. If any asset still references it, deletion will be blocked."
        confirmLabel="Delete"
        onConfirm={handleDelete}
      />
    </div>
  );
}
