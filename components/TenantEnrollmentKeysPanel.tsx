import React, { useCallback, useEffect, useState } from 'react';
import { API_BASE, authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

interface InstallKey {
  id: string;
  name: string;
  prefix: string;
  legacy?: boolean;
  maxUses: number | null;
  uses: number;
  expiresAt: string | null;
  defaultGroupId: string | null;
  revokedAt: string | null;
  createdAt: string;
  problem: 'revoked' | 'expired' | 'exhausted' | null;
}

const errorOf = async (res: Response) => {
  const body = await res.json().catch(() => ({}));
  return body.error || body.detail || `HTTP ${res.status}`;
};

/**
 * Install keys (spec C4): each enrolls new agents into this tenant, optionally capped by
 * uses, expiring, and putting agents into a default group. A new key is shown once.
 * Revoking stops new enrollments with it; agents it enrolled keep working.
 */
export const TenantEnrollmentKeysPanel: React.FC<{ tenantId: string; canManage: boolean }> = ({ tenantId, canManage }) => {
  const [keys, setKeys] = useState<InstallKey[] | null>(null);
  const [name, setName] = useState('');
  const [maxUses, setMaxUses] = useState('');
  const [expiresOn, setExpiresOn] = useState('');
  const [groupId, setGroupId] = useState('');
  const [fresh, setFresh] = useState<{ name: string; key: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/tenants/${tenantId}/enrollment-keys`, { method: 'GET' });
      if (!res.ok) throw new Error(await errorOf(res));
      setKeys((await res.json()).keys);
    } catch (e) {
      showToast(`Install keys unavailable: ${(e as Error).message}`, 'error');
    }
  }, [tenantId]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { name: name.trim() };
      if (maxUses) body.maxUses = Number(maxUses);
      if (expiresOn) body.expiresAt = new Date(`${expiresOn}T23:59:59Z`).toISOString();
      if (groupId.trim()) body.defaultGroupId = groupId.trim();
      const res = await authFetch(`${API_BASE}/tenants/${tenantId}/enrollment-keys`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await errorOf(res));
      const created = await res.json();
      setFresh({ name: created.name, key: created.key });
      setName(''); setMaxUses(''); setExpiresOn(''); setGroupId('');
      await load();
    } catch (e) {
      showToast(`Could not create the key: ${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (key: InstallKey) => {
    const warning = key.legacy
      ? 'Revoke the Legacy key? Installers downloaded before install keys existed will stop enrolling new machines. Agents already enrolled keep working.'
      : `Revoke "${key.name}"? It stops enrolling new machines; agents it enrolled keep working.`;
    if (!window.confirm(warning)) return;
    setBusy(true);
    try {
      const res = await authFetch(`${API_BASE}/tenants/${tenantId}/enrollment-keys/${key.id}/revoke`, { method: 'POST' });
      if (!res.ok) throw new Error(await errorOf(res));
      await load();
    } catch (e) {
      showToast(`Could not revoke: ${(e as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const inputClass = 'rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-sm text-gray-900 dark:text-white';
  const state = (k: InstallKey) => k.problem
    ? <span className="text-red-600 dark:text-red-400">{k.problem}</span>
    : <span className="text-green-600 dark:text-green-400">active</span>;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4" data-testid="tenant-install-keys">
      <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-1">Install keys</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        A key enrolls new machines into this tenant. Use it in the installer's "Install key" field. When a key is used up,
        expired or revoked, new machines wait for approval.
      </p>
      {fresh && (
        <div className="mb-3 rounded-md bg-green-50 dark:bg-green-900/30 p-3 text-xs" role="status">
          <div className="font-semibold text-green-800 dark:text-green-200">Key "{fresh.name}" created. Copy it now: it is not shown again.</div>
          <div className="mt-1 flex items-center gap-2">
            <code className="font-mono break-all">{fresh.key}</code>
            <button type="button" className="text-primary-600" onClick={() => {
              navigator.clipboard?.writeText(fresh.key).then(() => showToast('Key copied', 'success'));
            }}>Copy</button>
            <button type="button" className="text-gray-500" onClick={() => setFresh(null)}>Done</button>
          </div>
        </div>
      )}
      {keys && keys.length > 0 && (
        <table className="min-w-full text-xs text-left text-gray-700 dark:text-gray-200 mb-3">
          <thead className="text-gray-500 dark:text-gray-400">
            <tr><th className="py-1 pr-2">Name</th><th className="py-1 pr-2">Key</th><th className="py-1 pr-2">Uses</th>
              <th className="py-1 pr-2">Expires</th><th className="py-1 pr-2">State</th>{canManage && <th />}</tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id} className="border-t border-gray-200 dark:border-gray-700">
                <td className="py-1 pr-2">{k.name}{k.defaultGroupId && <div className="text-gray-500">group {k.defaultGroupId}</div>}</td>
                <td className="py-1 pr-2 font-mono">{k.prefix}…</td>
                <td className="py-1 pr-2">{k.uses}{k.maxUses !== null ? ` / ${k.maxUses}` : ''}</td>
                <td className="py-1 pr-2">{k.expiresAt ? new Date(k.expiresAt).toLocaleDateString() : 'never'}</td>
                <td className="py-1 pr-2">{state(k)}</td>
                {canManage && (
                  <td className="py-1">
                    {!k.revokedAt && <button type="button" disabled={busy} className="text-red-600" onClick={() => revoke(k)}>Revoke</button>}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage && (
        <div className="flex flex-wrap items-end gap-2">
          <input aria-label="Key name" className={inputClass} placeholder="Name, e.g. Finance laptops" value={name}
                 onChange={e => setName(e.target.value)} />
          <input aria-label="Max uses" type="number" min={1} className={`${inputClass} w-28`} placeholder="Max uses"
                 value={maxUses} onChange={e => setMaxUses(e.target.value)} />
          <input aria-label="Expires on" type="date" className={inputClass} value={expiresOn}
                 onChange={e => setExpiresOn(e.target.value)} />
          <input aria-label="Default agent group id" className={`${inputClass} w-44`} placeholder="Agent group id (optional)"
                 value={groupId} onChange={e => setGroupId(e.target.value)} />
          <button type="button" disabled={busy || !name.trim()} onClick={create}
                  className="px-3 py-1.5 text-sm rounded-md bg-primary-600 text-white disabled:opacity-50">Create key</button>
        </div>
      )}
    </div>
  );
};
