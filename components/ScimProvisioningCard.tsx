import React, { useCallback, useEffect, useState } from 'react';
import { KeyIcon, TrashIcon } from './icons';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

// SCIM provisioning (backend/scim_endpoints.py): an organization's admins create the bearer token their identity
// provider (Entra ID, Okta) uses to create, update and disable users here. A token is shown once; the list only
// ever shows its prefix. Users removed in the identity provider are disabled here, never deleted.

interface ScimToken { id: string; prefix: string; label?: string | null; createdBy?: string; createdAt?: string; lastUsedAt?: string | null; revokedAt?: string | null }

const call = async (url: string, method = 'GET', body?: unknown) => {
    const res = await authFetch(url, method === 'GET' ? undefined : { method, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`), { status: res.status });
    return data;
};
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : 'never');

export function ScimProvisioningCard() {
    const [tokens, setTokens] = useState<ScimToken[] | null>(null);
    const [basePath, setBasePath] = useState('/api/scim/v2');
    const [note, setNote] = useState<string | null>(null);
    const [hidden, setHidden] = useState(false);
    const [label, setLabel] = useState('');
    const [fresh, setFresh] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const load = useCallback(() => call('/api/admin/sso/scim/tokens')
        .then(d => { setTokens(d.items ?? []); setBasePath(d.basePath || '/api/scim/v2'); setNote(null); })
        .catch((e: Error & { status?: number }) => {
            if (e.status === 403) setHidden(true);
            else setNote(e.status === 400 ? 'Open a tenant first: a SCIM token belongs to one organization.' : e.message);
        }), []);
    useEffect(() => { load(); }, [load]);

    if (hidden) return null;
    const url = `${window.location.origin}${basePath}`;
    const active = (tokens ?? []).filter(t => !t.revokedAt);

    const create = async () => {
        setBusy(true);
        try {
            const out = await call('/api/admin/sso/scim/tokens', 'POST', { label: label.trim() || undefined });
            setFresh(out.token); setLabel(''); load();
        } catch (e) { showToast(e instanceof Error ? e.message : 'The token was not created', 'error'); } finally { setBusy(false); }
    };
    const revoke = async (t: ScimToken) => {
        if (!window.confirm(`Revoke the SCIM token ${t.prefix}…? The identity provider using it stops provisioning at once.`)) return;
        try { await call(`/api/admin/sso/scim/tokens/${encodeURIComponent(t.id)}`, 'DELETE'); showToast('Token revoked', 'success'); load(); }
        catch (e) { showToast(e instanceof Error ? e.message : 'Nothing was revoked', 'error'); }
    };
    const copy = (text: string) => navigator.clipboard?.writeText(text).then(() => showToast('Copied', 'success')).catch(() => undefined);

    return (
        <section aria-label="SCIM provisioning" className="mt-6 border border-gray-200 dark:border-gray-700 rounded-xl p-4 space-y-3">
            <div>
                <h4 className="text-sm font-semibold text-gray-800 dark:text-white flex items-center gap-1.5"><KeyIcon size={14} />SCIM provisioning</h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-3xl">
                    Let Microsoft Entra ID or Okta create, update and disable this organization's users. Users removed there are disabled here,
                    never deleted. Roles come from your directory group mappings (the same ones SAML uses); new users start as Viewer.
                </p>
            </div>
            {note && <p role="status" className="text-sm text-gray-600 dark:text-gray-300">{note}</p>}
            {tokens && (
                <>
                    <div className="text-xs text-gray-600 dark:text-gray-300">
                        Tenant URL <code className="ml-1 px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100">{url}</code>
                        <button type="button" onClick={() => copy(url)} className="ml-2 text-primary-600 dark:text-primary-400 font-medium">Copy</button>
                    </div>
                    {fresh && (
                        <div role="alert" className="rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3 text-xs text-amber-900 dark:text-amber-100">
                            <p className="font-semibold">Copy this secret token now. It is not shown again.</p>
                            <code className="block mt-1 break-all font-mono text-[12px]">{fresh}</code>
                            <div className="mt-2 flex gap-3">
                                <button type="button" onClick={() => copy(fresh)} className="font-medium text-primary-700 dark:text-primary-300">Copy token</button>
                                <button type="button" onClick={() => setFresh(null)} className="font-medium">Done</button>
                            </div>
                        </div>
                    )}
                    <div className="flex flex-wrap items-end gap-2">
                        <label className="text-xs text-gray-600 dark:text-gray-300">Label
                            <input value={label} maxLength={80} onChange={e => setLabel(e.target.value)} placeholder="e.g. Entra ID"
                                className="block mt-1 w-56 px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white" />
                        </label>
                        <button type="button" disabled={busy || active.length >= 5} onClick={create}
                            className="px-3 py-1.5 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-60">Create token</button>
                    </div>
                    {tokens.length === 0 ? <p className="text-xs text-gray-500">No tokens yet.</p> : (
                        <ul className="divide-y divide-gray-100 dark:divide-gray-700 text-xs">
                            {tokens.map(t => (
                                <li key={t.id} className={`py-2 flex items-center gap-3 ${t.revokedAt ? 'opacity-60' : ''}`}>
                                    <code className="font-mono text-gray-900 dark:text-gray-100">{t.prefix}…</code>
                                    <span className="flex-1 text-gray-600 dark:text-gray-300">{t.label || 'No label'} · created {when(t.createdAt)} by {t.createdBy || '—'} · last used {when(t.lastUsedAt)}{t.revokedAt ? ` · revoked ${when(t.revokedAt)}` : ''}</span>
                                    {!t.revokedAt && (
                                        <button type="button" onClick={() => revoke(t)} aria-label={`Revoke token ${t.prefix}`} className="flex items-center gap-1 text-red-700 dark:text-red-300 font-medium">
                                            <TrashIcon size={12} />Revoke
                                        </button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                </>
            )}
        </section>
    );
}
