import React, { useEffect, useState } from 'react';
import { CloudDownload } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { field, primaryButton, subhead } from './SocKit';

export type LogProvider = 'entra' | 'm365' | 'aws' | 'google';
export interface LogSource {
    name: string; connected: boolean; enabled?: boolean; azureTenantId?: string; clientId?: string; accessKeyId?: string; regions?: string[];
    adminEmail?: string; serviceAccount?: string; lastRunAt?: string | null; lastSuccessAt?: string | null; lastError?: string | null;
    lastCount?: number | null; totalEvents?: number | null;
}
type Sources = Record<LogProvider, LogSource>;

const PATH = '/api/security/soc/log-sources';
const ORDER: LogProvider[] = ['entra', 'm365', 'aws', 'google'];
const NEEDS: Record<LogProvider, string> = {
    entra: 'An Entra app registration with the Graph application permission AuditLog.Read.All and admin consent. Sign-in logs need Entra ID P1 or P2.',
    m365: 'An Entra app registration with the Office 365 Management APIs permission ActivityFeed.Read and admin consent, and audit logging on in Microsoft Purview.',
    aws: 'An IAM user or role key allowed only cloudtrail:LookupEvents. Management events, per region.',
    google: 'A service account with domain-wide delegation for admin.reports.audit.readonly, acting as a Workspace admin.',
};
const when = (t?: string | null) => (t ? new Date(t).toLocaleString() : 'never');
const detail = async (res: Response, fallback: string) => { const d = await res.json().catch(() => ({})); return typeof d?.detail === 'string' ? d.detail : fallback; };

const SourceForm: React.FC<{ provider: LogProvider; source: LogSource; onSaved: (s: LogSource) => void }> = ({ provider, source, onSaved }) => {
    const [v, setV] = useState({ azureTenantId: source.azureTenantId ?? '', clientId: source.clientId ?? '', accessKeyId: source.accessKeyId ?? '',
        regions: (source.regions ?? ['us-east-1']).join(', '), adminEmail: source.adminEmail ?? '', secret: '', enabled: source.enabled ?? true });
    const set = (k: keyof typeof v, value: string | boolean) => setV(x => ({ ...x, [k]: value }));
    const keep = source.connected ? 'Saved; leave blank to keep' : '';
    const input = (k: keyof typeof v, label: string, type = 'text') => (
        <label className="text-sm text-gray-700 dark:text-gray-200 space-y-1"><span className="block">{label}</span>
            <input type={type} autoComplete="off" value={v[k] as string} placeholder={type === 'password' ? keep : ''} onChange={e => set(k, e.target.value)} className={`${field} w-full px-2`} />
        </label>
    );
    const save = async () => {
        const base = provider === 'aws' ? { accessKeyId: v.accessKeyId.trim(), regions: v.regions.split(',').map(r => r.trim()).filter(Boolean) }
            : provider === 'google' ? { adminEmail: v.adminEmail.trim() } : { azureTenantId: v.azureTenantId.trim(), clientId: v.clientId.trim() };
        const res = await authFetch(`${PATH}/${provider}`, { method: 'PUT', body: JSON.stringify({ ...base, enabled: v.enabled, ...(v.secret.trim() ? { secret: v.secret.trim() } : {}) }) });
        if (res.ok) { onSaved(await res.json()); setV(x => ({ ...x, secret: '' })); showToast(`${source.name} saved`, 'success'); } else showToast(await detail(res, 'Not saved'), 'error');
    };
    return (
        <div className="space-y-2 pt-2">
            <p className="text-xs text-gray-500 dark:text-gray-400">{NEEDS[provider]}</p>
            <div className="grid gap-2 sm:grid-cols-2">
                {(provider === 'entra' || provider === 'm365') && <>{input('azureTenantId', 'Directory (tenant) id')}{input('clientId', 'Application (client) id')}{input('secret', 'Client secret', 'password')}</>}
                {provider === 'aws' && <>{input('accessKeyId', 'Access key id')}{input('secret', 'Secret access key', 'password')}{input('regions', 'Regions (comma-separated)')}</>}
                {provider === 'google' && <>{input('adminEmail', 'Admin email')}
                    <label className="text-sm text-gray-700 dark:text-gray-200 space-y-1 sm:col-span-2"><span className="block">Service account JSON key</span>
                        <textarea rows={3} value={v.secret} placeholder={keep} onChange={e => set('secret', e.target.value)} className={`${field} w-full h-auto px-2 py-1 font-mono text-xs`} />
                    </label></>}
            </div>
            <label className="text-sm text-gray-700 dark:text-gray-200 inline-flex items-center gap-2"><input type="checkbox" checked={v.enabled} onChange={e => set('enabled', e.target.checked)} />Pull every 5 minutes</label>
            <div><button type="button" className={primaryButton} onClick={save}>Save {source.name}</button></div>
        </div>
    );
};

/** Entra ID, Microsoft 365, AWS CloudTrail and Google Workspace logs into the SIEM pipeline: rules, Hunting and the queue see them. */
export const LogSourcesPanel: React.FC = () => {
    const [sources, setSources] = useState<Sources | null>(null);
    const [open, setOpen] = useState<LogProvider | null>(null);
    const [busy, setBusy] = useState<LogProvider | null>(null);
    // An answer without every source (an older platform, an error body) shows nothing rather than breaking the tab.
    const load = () => authFetch(PATH).then(r => (r.ok ? r.json() : null))
        .then(d => d && ORDER.every(p => typeof d[p]?.name === 'string') && setSources(d)).catch(() => {});
    useEffect(() => { load(); }, []);
    if (!sources) return null;
    const pull = async (p: LogProvider) => {
        setBusy(p);
        const res = await authFetch(`${PATH}/${p}/pull`, { method: 'POST' });
        const d = res.ok ? await res.json() : null;
        if (d?.ok) showToast(`${sources[p].name}: ${d.new} new events, ${d.hits} rule hits`, 'success');
        else showToast(d ? d.error : await detail(res, 'Pull failed'), 'error');
        await load();
        setBusy(null);
    };
    const remove = async (p: LogProvider) => {
        if (!window.confirm(`Disconnect ${sources[p].name}? Events already read stay in the SIEM.`)) return;
        const res = await authFetch(`${PATH}/${p}`, { method: 'DELETE' });
        if (res.ok) { setOpen(null); await load(); showToast(`${sources[p].name} disconnected`, 'success'); } else showToast(await detail(res, 'Not removed'), 'error');
    };
    return (
        <section aria-label="Cloud log sources" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4 space-y-3">
            <h3 className={`${subhead} flex items-center gap-1.5`}><CloudDownload className="w-3.5 h-3.5" aria-hidden="true" />Cloud log sources</h3>
            <p className="text-sm text-gray-600 dark:text-gray-300">Sign-ins and audit events from your cloud services, read-only, every 5 minutes. SIEM rules, Hunting and the alert queue use them like agent logs.</p>
            <ul className="divide-y divide-gray-200/80 dark:divide-white/[0.07]">
                {ORDER.map(p => {
                    const s = sources[p];
                    return (
                        <li key={p} className="py-2">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium text-gray-900 dark:text-white">{s.name}</span>
                                <span className="text-sm text-gray-600 dark:text-gray-300">
                                    {!s.connected ? 'Not connected' : `${s.enabled ? 'On' : 'Paused'} · last success ${when(s.lastSuccessAt)} · ${s.totalEvents ?? 0} events`}
                                </span>
                                <span className="ml-auto flex gap-2">
                                    <button type="button" className="h-9 px-3 rounded-xl text-sm font-semibold text-primary-700 dark:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20"
                                        aria-expanded={open === p} onClick={() => setOpen(open === p ? null : p)}>{s.connected ? 'Edit' : 'Connect'}</button>
                                    {s.connected && <button type="button" className={primaryButton} disabled={busy === p} onClick={() => pull(p)}>{busy === p ? 'Pulling…' : 'Pull now'}</button>}
                                    {s.connected && <button type="button" onClick={() => remove(p)} className="h-9 px-3 rounded-xl text-sm font-semibold text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20">Disconnect</button>}
                                </span>
                            </div>
                            {s.connected && s.lastError && <p role="status" className="text-sm text-red-700 dark:text-red-300">Last pull {when(s.lastRunAt)} failed: {s.lastError}</p>}
                            {open === p && <SourceForm provider={p} source={s} onSaved={saved => setSources({ ...sources, [p]: saved })} />}
                        </li>
                    );
                })}
            </ul>
        </section>
    );
};
