import React, { useCallback, useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

// Mobile Device Management: connect this organization's own Fleet (open source, osquery; backend/fleet_service.py)
// with its address and the API token of an API-only user. The token is never shown again. Fleet's free edition can
// refetch a host; lock and wipe are Fleet Premium and are not offered.

interface FleetState { connected: boolean; baseUrl?: string; lastSyncAt?: string | null; lastSyncCount?: number; lastError?: string | null; devices?: number }

const call = async (url: string, method = 'GET', body?: unknown) => {
    const r = await authFetch(url, method === 'GET' ? undefined : { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d?.detail === 'string' ? d.detail : `HTTP ${r.status}`);
    return d;
};
const input = 'block mt-1 w-80 max-w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white';

export const FleetConnectorCard: React.FC<{ onSynced?: () => void }> = ({ onSynced }) => {
    const [state, setState] = useState<FleetState | null>(null);
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({ baseUrl: '', apiToken: '' });
    const [busy, setBusy] = useState(false);
    const load = useCallback(() => call('/api/mdm/fleet').then(setState).catch(() => setState({ connected: false })), []);
    useEffect(() => { load(); }, [load]);

    const act = async (fn: () => Promise<unknown>, done: string) => {
        setBusy(true);
        try { await fn(); showToast(done, 'success'); load(); onSynced?.(); }
        catch (e) { showToast(e instanceof Error ? e.message : 'Nothing changed', 'error'); load(); }
        finally { setBusy(false); }
    };
    const save = () => act(async () => {
        await call('/api/mdm/fleet', 'PUT', { baseUrl: form.baseUrl, apiToken: form.apiToken || undefined });
        setEditing(false); setForm(f => ({ ...f, apiToken: '' }));
        await call('/api/mdm/fleet/sync', 'POST');
    }, 'Fleet connected and synced');

    if (!state) return null;
    return (
        <section aria-label="Fleet" className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h2 className="text-sm font-semibold">Fleet <span className="font-normal text-gray-500">(open source)</span></h2>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 max-w-3xl">
                        {state.connected
                            ? `Connected to ${state.baseUrl} · ${state.devices ?? 0} devices · last sync ${state.lastSyncAt ? new Date(state.lastSyncAt).toLocaleString() : 'never'} (hourly). Sync on these devices asks Fleet to refetch the host.`
                            : 'Not connected. Fleet is open-source device management on osquery: connect your own Fleet server to list its hosts here with their policy compliance.'}
                    </p>
                    {state.lastError && <p role="alert" className="text-xs text-red-700 dark:text-red-300 mt-1">Last sync failed: {state.lastError}</p>}
                </div>
                <div className="flex gap-2">
                    {state.connected && <button type="button" disabled={busy} onClick={() => act(() => call('/api/mdm/fleet/sync', 'POST'), 'Fleet synced')} className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50">Sync now</button>}
                    <button type="button" onClick={() => { setEditing(e => !e); setForm({ baseUrl: state.baseUrl || '', apiToken: '' }); }} className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700">{state.connected ? 'Change' : 'Connect Fleet'}</button>
                    {state.connected && <button type="button" disabled={busy} onClick={() => { if (window.confirm('Disconnect Fleet? Its devices stay listed but no action is sent any more.')) act(() => call('/api/mdm/fleet', 'DELETE'), 'Fleet disconnected'); }} className="px-3 py-1.5 text-xs font-semibold rounded-lg text-red-700 dark:text-red-300">Disconnect</button>}
                </div>
            </div>
            {editing && (
                <div className="flex flex-wrap items-end gap-3">
                    <label className="text-xs">Fleet address<input aria-label="Fleet address" value={form.baseUrl} placeholder="https://fleet.example.com" onChange={e => setForm({ ...form, baseUrl: e.target.value.trim() })} className={input} /></label>
                    <label className="text-xs">API token<input aria-label="API token" type="password" autoComplete="off" value={form.apiToken} placeholder={state.connected ? 'Leave empty to keep the saved token' : ''} onChange={e => setForm({ ...form, apiToken: e.target.value })} className={input} /></label>
                    <button type="button" disabled={busy || !form.baseUrl || (!state.connected && !form.apiToken)} onClick={save} className="px-3 py-1.5 text-sm font-semibold rounded-lg bg-primary-600 text-white disabled:opacity-50">Save and sync</button>
                    <p className="w-full text-xs text-gray-500">Create the token with <code>fleetctl user create --api-only --global-role observer</code> (maintainer to allow Sync). The address must be public https, or on this server's self-hosted list.</p>
                </div>
            )}
        </section>
    );
};
