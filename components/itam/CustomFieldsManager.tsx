import React, { useEffect, useState, useCallback } from 'react';
import { ItamCustomFieldDef, ItamFieldsetDef, ItamModelFields } from '../../types';
import { fetchAssetModelFields, updateAssetModelFieldsets } from '../../services/apiService';
import { showToast } from '../../utils/toast';

interface CustomFieldsManagerProps {
  modelId: string;
  modelName: string;
  onClose: () => void;
}

type FieldType = ItamCustomFieldDef['type'];

const FIELD_TYPES: FieldType[] = ['text', 'number', 'date', 'boolean', 'select'];

/** Draft-only field shape: keeps the select options as raw comma-separated text while the
 * admin is editing, so a trailing comma while typing doesn't get silently dropped on every
 * keystroke. Split into the real string[] only when the draft is sent to the server. */
interface DraftField {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  optionsText: string;
}

interface DraftFieldset {
  name: string;
  fields: DraftField[];
}

function toDraftFieldsets(fieldsets: ItamFieldsetDef[] | undefined): DraftFieldset[] {
  return (fieldsets || []).map((fs) => ({
    name: fs.name,
    fields: (fs.fields || []).map((f) => ({
      key: f.key,
      label: f.label,
      type: f.type,
      required: !!f.required,
      optionsText: (f.options || []).join(', '),
    })),
  }));
}

function toApiFieldsets(draft: DraftFieldset[]): ItamFieldsetDef[] {
  return draft.map((fs) => ({
    name: fs.name,
    fields: fs.fields.map((f) => ({
      key: f.key,
      label: f.label,
      type: f.type,
      required: f.required,
      options: f.type === 'select'
        ? f.optionsText.split(',').map((s) => s.trim()).filter(Boolean)
        : undefined,
    })),
  }));
}

export function CustomFieldsManager({ modelId, modelName, onClose }: CustomFieldsManagerProps) {
  const [data, setData] = useState<ItamModelFields | null>(null);
  const [draft, setDraft] = useState<DraftFieldset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newFieldsetName, setNewFieldsetName] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAssetModelFields(modelId);
      setData(result);
      setDraft(toDraftFieldsets(result.fieldsets));
    } catch (e: any) {
      setError(e?.message || "Couldn't load custom fields");
    } finally {
      setLoading(false);
    }
  }, [modelId]);

  useEffect(() => { load(); }, [load]);

  function addFieldset() {
    const name = newFieldsetName.trim();
    if (!name) return;
    setDraft((prev) => [...prev, { name, fields: [] }]);
    setNewFieldsetName('');
  }

  function addField(fsIndex: number) {
    setDraft((prev) => prev.map((fs, i) => (
      i === fsIndex
        ? { ...fs, fields: [...fs.fields, { key: '', label: '', type: 'text', required: false, optionsText: '' }] }
        : fs
    )));
  }

  function updateField(fsIndex: number, fieldIndex: number, patch: Partial<DraftField>) {
    setDraft((prev) => prev.map((fs, i) => (
      i === fsIndex
        ? { ...fs, fields: fs.fields.map((f, j) => (j === fieldIndex ? { ...f, ...patch } : f)) }
        : fs
    )));
  }

  function removeField(fsIndex: number, fieldIndex: number) {
    setDraft((prev) => prev.map((fs, i) => (
      i === fsIndex ? { ...fs, fields: fs.fields.filter((_, j) => j !== fieldIndex) } : fs
    )));
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await updateAssetModelFieldsets(modelId, toApiFieldsets(draft));
      showToast('Custom fields saved.', 'success');
      await load();
    } catch (e: any) {
      const message = e?.message || "Couldn't save custom fields.";
      setSaveError(message);
      showToast(message, 'error');
    } finally {
      setSaving(false);
    }
  }

  const usageCounts = data?.usageCounts || {};

  // Warn (advisory only — never blocks Save) when a field key the model already declared,
  // and that at least one asset currently carries a value for, is about to be removed or
  // retyped by the in-progress draft. Existing values for those keys will no longer
  // validate against the model once saved.
  const currentTypeByKey: Record<string, FieldType> = {};
  draft.forEach((fs) => fs.fields.forEach((f) => { currentTypeByKey[f.key] = f.type; }));
  const affectedFields = (data?.fields || [])
    .filter((f) => (usageCounts[f.key] || 0) > 0)
    .filter((f) => !(f.key in currentTypeByKey) || currentTypeByKey[f.key] !== f.type)
    .map((f) => ({ key: f.key, count: usageCounts[f.key] || 0 }));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Custom fields — {modelName}</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white text-xs font-medium"
          aria-label="Close custom fields manager"
        >
          Back to Models
        </button>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
        {loading && <p className="text-gray-400 text-sm">Loading…</p>}
        {error && !loading && <p className="text-red-400 text-sm" role="alert">{error}</p>}

        {!loading && !error && draft.length === 0 && (
          <p className="text-gray-500 text-sm mb-4">No custom fields on this model yet.</p>
        )}

        {!loading && !error && draft.map((fieldset, fsIndex) => (
          <div key={`${fieldset.name}-${fsIndex}`} className="mb-6 last:mb-0">
            <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wide mb-2">{fieldset.name}</h4>
            <table className="w-full text-sm mb-2">
              <thead>
                <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                  <th className="py-2 pr-4">Key</th>
                  <th className="py-2 pr-4">Label</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Required</th>
                  <th className="py-2 pr-4">Options</th>
                  <th className="py-2 pr-4" />
                </tr>
              </thead>
              <tbody>
                {fieldset.fields.map((field, fieldIndex) => {
                  const rowId = `${fsIndex}-${fieldIndex}`;
                  const usage = usageCounts[field.key] || 0;
                  return (
                    <tr key={rowId} className="border-b border-gray-800 align-top">
                      <td className="py-2 pr-4">
                        <input
                          className="w-28 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-white"
                          value={field.key}
                          onChange={(e) => updateField(fsIndex, fieldIndex, { key: e.target.value })}
                          aria-label={`Key for field ${rowId}`}
                        />
                        {usage > 0 && (
                          <div className="text-[11px] text-amber-400 mt-1">in use by {usage} asset{usage === 1 ? '' : 's'}</div>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <input
                          className="w-28 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-white"
                          value={field.label}
                          onChange={(e) => updateField(fsIndex, fieldIndex, { label: e.target.value })}
                          aria-label={`Label for field ${rowId}`}
                        />
                      </td>
                      <td className="py-2 pr-4">
                        <select
                          className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-white"
                          value={field.type}
                          onChange={(e) => updateField(fsIndex, fieldIndex, { type: e.target.value as FieldType })}
                          aria-label={`Type for field ${rowId}`}
                        >
                          {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </td>
                      <td className="py-2 pr-4">
                        <input
                          type="checkbox"
                          checked={field.required}
                          onChange={(e) => updateField(fsIndex, fieldIndex, { required: e.target.checked })}
                          aria-label={`Required for field ${rowId}`}
                        />
                      </td>
                      <td className="py-2 pr-4">
                        {field.type === 'select' && (
                          <input
                            className="w-36 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-white"
                            placeholder="option1, option2"
                            value={field.optionsText}
                            onChange={(e) => updateField(fsIndex, fieldIndex, { optionsText: e.target.value })}
                            aria-label={`Options for field ${rowId}`}
                          />
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <button
                          onClick={() => removeField(fsIndex, fieldIndex)}
                          className="text-red-400 hover:text-red-300 text-xs font-medium"
                          aria-label={`Remove field ${rowId}`}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <button
              onClick={() => addField(fsIndex)}
              className="text-cyan-400 hover:text-cyan-300 text-xs font-medium"
              aria-label={`Add field to ${fieldset.name}`}
            >
              + Add field
            </button>
          </div>
        ))}

        {!loading && !error && (
          <div className="flex items-center gap-2 mt-4 mb-4">
            <input
              className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white"
              placeholder="New fieldset name"
              value={newFieldsetName}
              onChange={(e) => setNewFieldsetName(e.target.value)}
              aria-label="New fieldset name"
            />
            <button
              onClick={addFieldset}
              className="bg-gray-700 hover:bg-gray-600 text-white text-xs font-semibold px-3 py-2 rounded-lg"
            >
              Add fieldset
            </button>
          </div>
        )}

        {affectedFields.length > 0 && (
          <div className="text-xs text-amber-400 bg-amber-950/40 border border-amber-800 rounded-lg px-3 py-2 mb-3" role="alert">
            Caution: {affectedFields.map((f) => `'${f.key}' (in use by ${f.count} asset${f.count === 1 ? '' : 's'})`).join(', ')}{' '}
            {affectedFields.length === 1 ? 'is' : 'are'} being removed or retyped. Existing asset values for{' '}
            {affectedFields.length === 1 ? 'this key' : 'these keys'} will no longer validate against this model.
          </div>
        )}

        {saveError && (
          <p className="text-red-400 text-sm mb-3" role="alert">{saveError}</p>
        )}

        {!loading && !error && (
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            {saving ? 'Saving…' : 'Save custom fields'}
          </button>
        )}
      </div>
    </div>
  );
}
