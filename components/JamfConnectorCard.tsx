import React, { useCallback, useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

// Mobile Device Management: connect this organization's Jamf Pro (Apple devices; backend/jamf_service.py) with its
// address and an API client from Settings > API Roles and Clients. The client secret is never shown again. Macs and
// iPhones/iPads are listed; sync, lock, restart and wipe are sent through Jamf.

interface JamfState { connected: boolean; baseUrl?: string; clientId?: string; lastSyncAt?: string | null; lastSyncCount?: number; lastError?: string | null; devices?: number }

const call = async (url: string, method = 'GET', body?: unknown) => {
    const r = await authFetch(url, method === 'GET' ? undefined : { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d?.detail === 'string' ? d.detail : `HTTP ${r.status}`);
    return d;
};
const input = 'block mt-1 w-80 max-w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white';

export const JamfConnectorCard: React.FC<{ onSynced?: () => void }> = ({ onSynced }) => {
    const [state, setState] = useState<JamfState | null>(null);
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({ baseUrl: '', clientId: '', clientSecret: '' });
    const [busy, setBusy] = useState(false);
    const load = useCallback(() => call('/api/mdm/jamf').then(setState).catch(() => setState({ connected: false })), []);
    useEffect(() => { load(); }, [load]);

    const act = async (fn: () => Promise<unknown>, done: string) => {
        setBusy(true);
        try { await fn(); showToast(done, 'success'); load(); onSynced?.(); }
        catch (e) { showToast(e instanceof Error ? e.message : 'Nothing changed', 'error'); load(); }
        finally { setBusy(false); }
    };
    const save = () => act(async () => {
        await call('/api/mdm/jamf', 'PUT', { baseUrl: form.baseUrl, clientId: form.clientId, clientSecret: form.clientSecret || undefined });
        setEditing(false); setForm(f => ({ ...f, clientSecret: '' }));
        await call('/api/mdm/jamf/sync', 'POST');
    }, 'Jamf Pro connected and synced');

    if (!state) return null;
    return (
        <section aria-label="Jamf Pro" className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h2 className="text-sm font-semibold">Jamf Pro <span className="font-normal text-gray-500">(Apple devices)</span></h2>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 max-w-3xl">
                        {state.connected
                            ? `Connected to ${state.baseUrl} · ${state.devices ?? 0} devices · last sync ${state.lastSyncAt ? new Date(state.lastSyncAt).toLocaleString() : 'never'} (hourly). Sync, lock, restart and wipe on these Macs, iPhones and iPads are sent through Jamf Pro.`
                            : 'Not connected. Connect your Jamf Pro to manage Macs, iPhones and iPads without Intune.'}
                    </p>
                    {state.lastError && <p role="alert" className="text-xs text-red-700 dark:text-red-300 mt-1">Last sync failed: {state.lastError}</p>}
                </div>
                <div className="flex gap-2">
                    {state.connected && <button type="button" disabled={busy} onClick={() => act(() => call('/api/mdm/jamf/sync', 'POST'), 'Jamf Pro synced')} className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50">Sync now</button>}
                    <button type="button" onClick={() => { setEditing(e => !e); setForm({ baseUrl: state.baseUrl || '', clientId: state.clientId || '', clientSecret: '' }); }} className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700">{state.connected ? 'Change' : 'Connect Jamf Pro'}</button>
                    {state.connected && <button type="button" disabled={busy} onClick={() => { if (window.confirm('Disconnect Jamf Pro? Its devices stay listed but no action is sent any more.')) act(() => call('/api/mdm/jamf', 'DELETE'), 'Jamf Pro disconnected'); }} className="px-3 py-1.5 text-xs font-semibold rounded-lg text-red-700 dark:text-red-300">Disconnect</button>}
                </div>
            </div>
            {editing && (
                <div className="flex flex-wrap items-end gap-3">
                    <label className="text-xs">Jamf Pro address<input aria-label="Jamf Pro address" value={form.baseUrl} placeholder="https://yourorg.jamfcloud.com" onChange={e => setForm({ ...form, baseUrl: e.target.value.trim() })} className={input} /></label>
                    <label className="text-xs">Client ID<input aria-label="Client ID" value={form.clientId} onChange={e => setForm({ ...form, clientId: e.target.value.trim() })} className={input} /></label>
                    <label className="text-xs">Client secret<input aria-label="Client secret" type="password" autoComplete="off" value={form.clientSecret} placeholder={state.connected ? 'Leave empty to keep the saved secret' : ''} onChange={e => setForm({ ...form, clientSecret: e.target.value })} className={input} /></label>
                    <button type="button" disabled={busy || !form.baseUrl || !form.clientId || (!state.connected && !form.clientSecret)} onClick={save} className="px-3 py-1.5 text-sm font-semibold rounded-lg bg-primary-600 text-white disabled:opacity-50">Save and sync</button>
                    <p className="w-full text-xs text-gray-500">Create the API client in Jamf Pro under Settings &gt; API Roles and Clients (Jamf Pro 10.49 or later). Its role needs Read Computers and Read Mobile Devices; for actions add View MDM command information in Jamf Pro API and the remote lock, wipe, restart and blank push privileges. The address must be public https, or on this server's self-hosted list.</p>
                </div>
            )}
        </section>
    );
};
