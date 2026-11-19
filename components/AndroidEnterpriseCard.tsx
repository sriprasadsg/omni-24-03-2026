import React, { useCallback, useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';

// Mobile Device Management: connect this organization's Android Enterprise through Google's Android Management API
// (backend/android_mdm_service.py). A Google Cloud service account with the Android Management User role does the
// calls; the key is never shown again. The enterprise is either named, or created with Google's sign-up link, which
// returns here with ?enterpriseToken=... and is completed on load.

interface AndroidState {
    connected: boolean; projectId?: string; serviceAccount?: string; enterprise?: string | null; enterpriseName?: string | null;
    lastSyncAt?: string | null; lastError?: string | null; devices?: number; signupPending?: boolean;
}
interface Enrollment { value: string; link: string; qrPng: string | null; expires?: string; hours: number }

const call = async (url: string, method = 'GET', body?: unknown) => {
    const r = await authFetch(url, method === 'GET' ? undefined : { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d?.detail === 'string' ? d.detail : `HTTP ${r.status}`);
    return d;
};
const input = 'block mt-1 w-80 max-w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white';
const button = 'px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 dark:border-gray-700 disabled:opacity-50';

function returnAddress(): string {
    const url = new URL(window.location.href);
    url.search = '';
    return url.toString();
}

export const AndroidEnterpriseCard: React.FC<{ onSynced?: () => void }> = ({ onSynced }) => {
    const [state, setState] = useState<AndroidState | null>(null);
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({ serviceAccountKey: '', enterprise: '' });
    const [enroll, setEnroll] = useState<Enrollment | null>(null);
    const [busy, setBusy] = useState(false);
    const load = useCallback(() => call('/api/mdm/android').then(setState).catch(() => setState({ connected: false })), []);

    const act = useCallback(async (fn: () => Promise<unknown>, done: string) => {
        setBusy(true);
        try { await fn(); showToast(done, 'success'); load(); onSynced?.(); }
        catch (e) { showToast(e instanceof Error ? e.message : 'Nothing changed', 'error'); load(); }
        finally { setBusy(false); }
    }, [load, onSynced]);

    useEffect(() => {
        const token = new URLSearchParams(window.location.search).get('enterpriseToken');
        if (token) {
            window.history.replaceState(null, '', returnAddress());
            act(() => call('/api/mdm/android/enterprise', 'POST', { enterpriseToken: token }), 'Android Enterprise created');
        } else {
            load();
        }
    }, [act, load]);

    const save = () => act(async () => {
        await call('/api/mdm/android', 'PUT', { serviceAccountKey: form.serviceAccountKey || undefined, enterprise: form.enterprise || undefined });
        setEditing(false); setForm(f => ({ ...f, serviceAccountKey: '' }));
        if (form.enterprise) await call('/api/mdm/android/sync', 'POST');
    }, 'Android Enterprise saved');
    const signup = () => act(async () => {
        const out = await call('/api/mdm/android/signup', 'POST', { callbackUrl: returnAddress() });
        window.location.assign(out.url);
    }, 'Opening Google sign-up');
    const newToken = () => act(async () => setEnroll(await call('/api/mdm/android/enrollment-token', 'POST')), 'Enrollment code ready');

    if (!state) return null;
    const ready = state.connected && !!state.enterprise;
    return (
        <section aria-label="Android Enterprise" className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h2 className="text-sm font-semibold">Android Enterprise</h2>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 max-w-3xl">
                        {ready
                            ? `Connected · ${state.enterpriseName || state.enterprise} · ${state.devices ?? 0} devices · last sync ${state.lastSyncAt ? new Date(state.lastSyncAt).toLocaleString() : 'never'} (hourly). Lock, restart, retire and wipe are sent through Google.`
                            : state.connected
                                ? 'Service account saved. Name the Android Enterprise, or create one with Google\'s sign-up.'
                                : 'Not connected. Manage Android phones and tablets directly through Google\'s Android Management API, without Intune.'}
                    </p>
                    {state.lastError && <p role="alert" className="text-xs text-red-700 dark:text-red-300 mt-1">Last sync failed: {state.lastError}</p>}
                </div>
                <div className="flex flex-wrap gap-2">
                    {ready && <button type="button" disabled={busy} onClick={newToken} className={button}>Enroll a device</button>}
                    {ready && <button type="button" disabled={busy} onClick={() => act(() => call('/api/mdm/android/sync', 'POST'), 'Android devices synced')} className={button}>Sync now</button>}
                    {state.connected && !state.enterprise && <button type="button" disabled={busy} onClick={signup} className={button}>Create with Google sign-up</button>}
                    <button type="button" onClick={() => { setEditing(e => !e); setForm({ serviceAccountKey: '', enterprise: state.enterprise || '' }); }} className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700">{state.connected ? 'Change' : 'Connect Android'}</button>
                    {state.connected && <button type="button" disabled={busy} onClick={() => { if (window.confirm('Disconnect Android Enterprise? Its devices stay listed but no action is sent any more. The enterprise itself stays at Google.')) act(() => call('/api/mdm/android', 'DELETE'), 'Android Enterprise disconnected'); }} className="px-3 py-1.5 text-xs font-semibold rounded-lg text-red-700 dark:text-red-300">Disconnect</button>}
                </div>
            </div>
            {editing && (
                <div className="flex flex-wrap items-end gap-3">
                    <label className="text-xs">Service account key (JSON)
                        <textarea aria-label="Service account key (JSON)" rows={3} value={form.serviceAccountKey} placeholder={state.connected ? 'Leave empty to keep the saved key' : '{"type": "service_account", ...}'} onChange={e => setForm({ ...form, serviceAccountKey: e.target.value })} className={`${input} font-mono`} />
                    </label>
                    <label className="text-xs">Enterprise (optional)<input aria-label="Enterprise" value={form.enterprise} placeholder="enterprises/LC01abcdef" onChange={e => setForm({ ...form, enterprise: e.target.value.trim() })} className={input} /></label>
                    <button type="button" disabled={busy || (!state.connected && !form.serviceAccountKey)} onClick={save} className="px-3 py-1.5 text-sm font-semibold rounded-lg bg-primary-600 text-white disabled:opacity-50">Save</button>
                    <p className="w-full text-xs text-gray-500">In Google Cloud: enable the Android Management API, create a service account with the Android Management User role and download its JSON key.</p>
                </div>
            )}
            {enroll && (
                <div className="flex flex-wrap gap-4 items-start rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                    {enroll.qrPng && <img src={`data:image/png;base64,${enroll.qrPng}`} alt="Android enrollment QR code" className="w-40 h-40 bg-white rounded" />}
                    <div className="text-xs space-y-1 max-w-xl">
                        <p><strong>Company phone or tablet:</strong> on a new or reset device, tap the welcome screen six times and scan this code.</p>
                        <p><strong>Personal phone (work profile):</strong> open <a href={enroll.link} className="text-primary-600 underline break-all" target="_blank" rel="noreferrer">{enroll.link}</a> on the phone.</p>
                        <p className="text-gray-500">Enrollment code {enroll.value}, valid for {enroll.hours} hours.</p>
                    </div>
                </div>
            )}
        </section>
    );
};
