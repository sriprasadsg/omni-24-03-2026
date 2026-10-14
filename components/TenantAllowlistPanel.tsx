import React, { useCallback, useEffect, useState } from 'react';
import { API_BASE, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface AllowlistEntry {
  id: string;
  serialNumber?: string;
  smbiosUuid?: string;
  macAddress?: string;
  note?: string;
  addedAt: string;
}

interface ImportResult {
  imported: number;
  skipped: number;
  errors: { row: number; error: string }[];
}

const errorOf = async (res: Response) => {
  const body = await res.json().catch(() => ({}));
  return body.error || body.detail || `HTTP ${res.status}`;
};

/**
 * Hardware allowlist (spec C4). When the license enforces it, only machines whose serial,
 * SMBIOS UUID or MAC is listed enroll; others wait for approval. CSV import takes
 * `serial,uuid,mac,note` rows (up to 10,000) and reports the rows it skipped.
 */
export const TenantAllowlistPanel: React.FC<{ tenantId: string; canManage: boolean }> = ({ tenantId, canManage }) => {
  const [entries, setEntries] = useState<AllowlistEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [serial, setSerial] = useState('');
  const [mac, setMac] = useState('');
  const [note, setNote] = useState('');
  const [csv, setCsv] = useState('');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/tenants/${tenantId}/allowlist?limit=50`, { method: 'GET' });
      if (!res.ok) throw new Error(await errorOf(res));
      const body = await res.json();
      setEntries(body.entries);
      setTotal(body.total);
    } catch (e) {
      showToast(`Allowlist unavailable: ${(e as Error).message}`, 'error');
    }
  }, [tenantId]);

  useEffect(() => { load(); }, [load]);

  const post = async (path: string, body: unknown) => {
    const res = await authFetch(`${API_BASE}/tenants/${tenantId}/allowlist${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await errorOf(res));
    return res.json();
  };

  const add = async () => {
    setBusy(true);
    try {
      await post('', { serialNumber: serial.trim() || null, macAddress: mac.trim() || null, note: note.trim() || null });
      setSerial(''); setMac(''); setNote('');
      await load();
    } catch (e) {
      showToast(`Not added: ${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (entry: AllowlistEntry) => {
    setBusy(true);
    try {
      const res = await authFetch(`${API_BASE}/tenants/${tenantId}/allowlist/${entry.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await errorOf(res));
      await load();
    } catch (e) {
      showToast(`Not removed: ${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const runImport = async () => {
    setBusy(true);
    setResult(null);
    try {
      setResult(await post('/import', { csv }));
      setCsv('');
      await load();
    } catch (e) {
      showToast(`Import failed: ${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const onFile = (file?: File) => file && file.text().then(setCsv);
  const inputClass = 'rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-sm text-gray-900 dark:text-white';

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4" data-testid="tenant-allowlist">
      <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-1">Hardware allowlist ({total})</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Takes effect when the license sets the allowlist to Enforce. Matching is by BIOS serial, SMBIOS UUID or MAC address.
      </p>
      {entries.length > 0 && (
        <ul className="mb-3 max-h-40 overflow-y-auto text-xs font-mono text-gray-700 dark:text-gray-200">
          {entries.map(e => (
            <li key={e.id} className="flex justify-between gap-2 border-t border-gray-100 dark:border-gray-700 py-0.5">
              <span>{[e.serialNumber && `S/N ${e.serialNumber}`, e.smbiosUuid, e.macAddress].filter(Boolean).join(' · ')}
                {e.note && <span className="font-sans text-gray-500"> — {e.note}</span>}</span>
              {canManage && <button type="button" disabled={busy} className="font-sans text-red-600" onClick={() => remove(e)}>Remove</button>}
            </li>
          ))}
          {total > entries.length && <li className="font-sans text-gray-500 py-0.5">…and {total - entries.length} more</li>}
        </ul>
      )}
      {canManage && (
        <>
          <div className="flex flex-wrap items-end gap-2 mb-3">
            <input aria-label="Serial number" className={inputClass} placeholder="Serial number" value={serial}
                   onChange={e => setSerial(e.target.value)} />
            <input aria-label="MAC address" className={inputClass} placeholder="MAC address" value={mac}
                   onChange={e => setMac(e.target.value)} />
            <input aria-label="Note" className={inputClass} placeholder="Note" value={note} onChange={e => setNote(e.target.value)} />
            <button type="button" disabled={busy || (!serial.trim() && !mac.trim())} onClick={add}
                    className="px-3 py-1.5 text-sm rounded-md bg-primary-600 text-white disabled:opacity-50">Add</button>
          </div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-300">
            Import CSV (serial,uuid,mac,note)
            <textarea aria-label="Allowlist CSV" rows={3} className={`${inputClass} w-full font-mono`} value={csv}
                      placeholder={'serial,uuid,mac,note\nPF3ABC12,,,CFO laptop'} onChange={e => setCsv(e.target.value)} />
          </label>
          <div className="mt-2 flex items-center gap-3">
            <input aria-label="CSV file" type="file" accept=".csv,text/csv" className="text-xs"
                   onChange={e => onFile(e.target.files?.[0])} />
            <button type="button" disabled={busy || !csv.trim()} onClick={runImport}
                    className="px-3 py-1.5 text-sm rounded-md bg-primary-600 text-white disabled:opacity-50">Import</button>
          </div>
          {result && (
            <div className="mt-2 text-xs" role="status">
              <span className="text-green-700 dark:text-green-300">{result.imported} imported</span>
              {result.skipped > 0 && <span className="text-amber-700 dark:text-amber-300">, {result.skipped} skipped</span>}
              {result.errors.length > 0 && (
                <ul className="mt-1 max-h-24 overflow-y-auto text-amber-800 dark:text-amber-200">
                  {result.errors.slice(0, 50).map(e => <li key={e.row}>Row {e.row}: {e.error}</li>)}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
