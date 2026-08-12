import React, { useEffect, useState, useCallback } from 'react';
import { ItamModelFields } from '../../types';
import { fetchAssetModelFields } from '../../services/apiService';

interface CustomFieldsManagerProps {
  modelId: string;
  modelName: string;
  onClose: () => void;
}

export function CustomFieldsManager({ modelId, modelName, onClose }: CustomFieldsManagerProps) {
  const [data, setData] = useState<ItamModelFields | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAssetModelFields(modelId));
    } catch (e: any) {
      setError(e?.message || "Couldn't load custom fields");
    } finally {
      setLoading(false);
    }
  }, [modelId]);

  useEffect(() => { load(); }, [load]);

  const fieldsByFieldset: Record<string, ItamModelFields['fields']> = {};
  (data?.fields || []).forEach((f) => {
    const groupName = f.fieldsetName || 'Ungrouped';
    if (!fieldsByFieldset[groupName]) fieldsByFieldset[groupName] = [];
    fieldsByFieldset[groupName].push(f);
  });
  const fieldsetNames = Object.keys(fieldsByFieldset);

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
        {!loading && !error && fieldsetNames.length === 0 && (
          <p className="text-gray-500 text-sm">No custom fields on this model yet.</p>
        )}
        {!loading && !error && fieldsetNames.map((fieldsetName) => (
          <div key={fieldsetName} className="mb-6 last:mb-0">
            <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wide mb-2">{fieldsetName}</h4>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs border-b border-gray-700">
                  <th className="py-2 pr-4">Key</th>
                  <th className="py-2 pr-4">Label</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Required</th>
                </tr>
              </thead>
              <tbody>
                {fieldsByFieldset[fieldsetName].map((field) => (
                  <tr key={field.key} className="border-b border-gray-800">
                    <td className="py-2 pr-4 text-white font-medium">{field.key}</td>
                    <td className="py-2 pr-4 text-gray-300">{field.label}</td>
                    <td className="py-2 pr-4 text-gray-400">{field.type}</td>
                    <td className="py-2 pr-4 text-gray-400">{field.required ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}
