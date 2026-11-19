import React, { useEffect, useState } from 'react';
import { BellRing } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { field, primaryButton, subhead } from './SocKit';

export type PagingProvider = 'pagerduty' | 'opsgenie' | 'teams' | 'slack' | 'ntfy';
type Gate = 'critical' | 'high';
interface OnCall { always: boolean; timezone?: string; days?: number[]; start?: string; end?: string }
export interface PageRecord { id: string; alertId: string; title?: string; reason: 'new' | 'ack_breach' | 'test'; status: string; sentAt: string; error?: string | null; resolveError?: string | null }
export interface PagingConfig {
    configured: boolean; provider?: PagingProvider; enabled?: boolean; minSeverity?: Gate; breachSeverity?: Gate; pageBreaches?: boolean;
    region?: 'us' | 'eu'; onCall?: OnCall; webhookHost?: string; hasToken?: boolean; suppressed?: number;
    lastResult?: { at: string; ok: boolean; error?: string | null }; recentPages?: PageRecord[];
}

const PATH = '/api/security/soc/paging';
const PROVIDERS: { key: PagingProvider; label: string; secret: string }[] = [
    { key: 'pagerduty', label: 'PagerDuty', secret: 'Routing key (Events API v2 integration)' },
    { key: 'opsgenie', label: 'Opsgenie', secret: 'API key (API integration)' },
    { key: 'teams', label: 'Microsoft Teams', secret: 'Workflow webhook URL' },
    { key: 'slack', label: 'Slack', secret: 'Incoming webhook URL' },
    { key: 'ntfy', label: 'ntfy (open source)', secret: 'Topic URL, such as https://ntfy.sh/your-topic' },
];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const REASON: Record<PageRecord['reason'], string> = { new: 'New alert', ack_breach: 'Not acknowledged in time', test: 'Test' };
const STATUS: Record<string, string> = { sending: 'Sending', triggered: 'Paged', resolved: 'Resolved', failed: 'Failed', cancelled: 'Cancelled', left_open: 'Left open' };
const localZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; } };
const detail = async (res: Response, fallback: string) => { const d = await res.json().catch(() => ({})); return typeof d?.detail === 'string' ? d.detail : fallback; };

/** Pages the on-call through PagerDuty or Opsgenie, or posts to Teams, Slack or an ntfy topic, for critical alerts and missed acknowledge targets. */
export const PagingPanel: React.FC = () => {
    const [cfg, setCfg] = useState<PagingConfig | null>(null);
    const [form, setForm] = useState({ provider: 'pagerduty' as PagingProvider, secret: '', token: '', region: 'us', minSeverity: 'critical' as Gate,
        breachSeverity: 'high' as Gate, pageBreaches: true, enabled: true, always: true, timezone: localZone(), days: [0, 1, 2, 3, 4], start: '09:00', end: '17:00' });
    const [busy, setBusy] = useState(false);
    const adopt = (c: PagingConfig) => {
        setCfg(c);
        if (!c.configured) return;
        const on = c.onCall ?? { always: true };
        setForm(f => ({ ...f, provider: c.provider ?? f.provider, secret: '', token: '', region: c.region ?? 'us', minSeverity: c.minSeverity ?? 'critical',
            breachSeverity: c.breachSeverity ?? 'high', pageBreaches: c.pageBreaches ?? true, enabled: c.enabled ?? true, always: on.always,
            timezone: on.timezone ?? f.timezone, days: on.days ?? f.days, start: on.start ?? f.start, end: on.end ?? f.end }));
    };
    useEffect(() => { authFetch(PATH).then(r => (r.ok ? r.json() : null)).then(d => d && adopt(d)).catch(() => {}); }, []);
    if (!cfg) return null;

    const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm(f => ({ ...f, [k]: v }));
    const keeps = cfg.configured && cfg.provider === form.provider;
    const meta = PROVIDERS.find(p => p.key === form.provider)!;
    const save = async () => {
        setBusy(true);
        const onCall = form.always ? { always: true } : { always: false, timezone: form.timezone, days: form.days, start: form.start, end: form.end };
        const body = { provider: form.provider, region: form.region, minSeverity: form.minSeverity, breachSeverity: form.breachSeverity,
            pageBreaches: form.pageBreaches, enabled: form.enabled, onCall, ...(form.secret.trim() ? { secret: form.secret.trim(), ...(form.provider === 'ntfy' ? { token: form.token.trim() } : {}) } : {}) };
        const res = await authFetch(PATH, { method: 'PUT', body: JSON.stringify(body) });
        if (res.ok) { adopt(await res.json()); showToast('Paging saved', 'success'); } else showToast(await detail(res, 'Paging not saved'), 'error');
        setBusy(false);
    };
    const test = async () => {
        setBusy(true);
        const res = await authFetch(`${PATH}/test`, { method: 'POST' });
        const d = res.ok ? await res.json() : null;
        if (d?.paged) showToast(`Test page sent. Close the "Paging test" alert in the queue to resolve it.`, 'success');
        else showToast(d ? `Test page not sent: ${d.error || d.why}` : await detail(res, 'Test page not sent'), 'error');
        authFetch(PATH).then(r => (r.ok ? r.json() : null)).then(c => c && setCfg(c)).catch(() => {});
        setBusy(false);
    };
    const remove = async () => {
        if (!window.confirm('Remove paging? Open pages stay open at the provider.')) return;
        const res = await authFetch(PATH, { method: 'DELETE' });
        if (res.ok) { setCfg({ configured: false }); set('secret', ''); showToast('Paging removed', 'success'); } else showToast(await detail(res, 'Not removed'), 'error');
    };
    const toggleDay = (d: number) => set('days', form.days.includes(d) ? form.days.filter(x => x !== d) : [...form.days, d].sort());
    const label = 'text-sm text-gray-700 dark:text-gray-200';

    return (
        <section aria-label="Paging" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4 space-y-3">
            <h3 className={`${subhead} flex items-center gap-1.5`}><BellRing className="w-3.5 h-3.5" aria-hidden="true" />Paging</h3>
            <p className="text-sm text-gray-600 dark:text-gray-300">
                Pages the on-call for a new alert at the paging severity, and for an open alert not acknowledged within its target above.
                Each alert pages once; closing it resolves the page within a minute.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
                <label className={`${label} space-y-1`}><span className="block">Send pages to</span>
                    <select value={form.provider} onChange={e => set('provider', e.target.value as PagingProvider)} className={`${field} w-full px-2`}>
                        {PROVIDERS.map(p => <option key={p.key} value={p.key}>{p.label}</option>)}
                    </select>
                </label>
                <label className={`${label} space-y-1`}><span className="block">{meta.secret}</span>
                    <input type="password" autoComplete="off" value={form.secret} onChange={e => set('secret', e.target.value)}
                        placeholder={keeps ? `Saved${cfg.webhookHost ? ` (${cfg.webhookHost})` : ''}; leave blank to keep` : ''} className={`${field} w-full px-2`} />
                </label>
                {form.provider === 'ntfy' && (
                    <label className={`${label} space-y-1`}><span className="block">Access token (only for a protected topic)</span>
                        <input type="password" autoComplete="off" value={form.token} onChange={e => set('token', e.target.value)}
                            placeholder={keeps && cfg.hasToken ? 'Saved; enter it again with a new topic URL' : 'tk_…'} className={`${field} w-full px-2`} />
                    </label>
                )}
                {form.provider === 'opsgenie' && (
                    <label className={`${label} space-y-1`}><span className="block">Opsgenie region</span>
                        <select value={form.region} onChange={e => set('region', e.target.value)} className={`${field} w-full px-2`}>
                            <option value="us">US (api.opsgenie.com)</option><option value="eu">EU (api.eu.opsgenie.com)</option>
                        </select>
                    </label>
                )}
                <label className={`${label} space-y-1`}><span className="block">Page new alerts that are</span>
                    <select value={form.minSeverity} onChange={e => set('minSeverity', e.target.value as Gate)} className={`${field} w-full px-2`}>
                        <option value="critical">Critical</option><option value="high">High or critical</option>
                    </select>
                </label>
            </div>
            <div className="flex flex-wrap items-center gap-2">
                <label className={`${label} inline-flex items-center gap-2`}>
                    <input type="checkbox" checked={form.pageBreaches} onChange={e => set('pageBreaches', e.target.checked)} />Also page open alerts not acknowledged in time that are
                </label>
                <select aria-label="Severity for missed acknowledge targets" value={form.breachSeverity} disabled={!form.pageBreaches}
                    onChange={e => set('breachSeverity', e.target.value as Gate)} className={`${field} px-2`}>
                    <option value="high">High or critical</option><option value="critical">Critical</option>
                </select>
            </div>
            <fieldset className="space-y-2">
                <legend className={label}>On-call hours</legend>
                <label className={`${label} inline-flex items-center gap-2`}><input type="checkbox" checked={form.always} onChange={e => set('always', e.target.checked)} />Any time</label>
                {!form.always && (
                    <div className="flex flex-wrap items-center gap-2">
                        {DAYS.map((d, i) => (
                            <label key={d} className={`${label} inline-flex items-center gap-1`}><input type="checkbox" checked={form.days.includes(i)} onChange={() => toggleDay(i)} />{d}</label>
                        ))}
                        <input type="time" aria-label="On-call from" value={form.start} onChange={e => set('start', e.target.value)} className={`${field} px-2`} />
                        <span className={label}>to</span>
                        <input type="time" aria-label="On-call until" value={form.end} onChange={e => set('end', e.target.value)} className={`${field} px-2`} />
                        <input aria-label="Time zone" value={form.timezone} onChange={e => set('timezone', e.target.value)} className={`${field} w-48 px-2`} />
                    </div>
                )}
                <p className="text-xs text-gray-500 dark:text-gray-400">Outside these hours nothing pages; an alert still unacknowledged past its target pages when they start.</p>
            </fieldset>
            <label className={`${label} inline-flex items-center gap-2`}><input type="checkbox" checked={form.enabled} onChange={e => set('enabled', e.target.checked)} />Paging on</label>
            <div className="flex flex-wrap gap-2">
                <button type="button" className={primaryButton} disabled={busy} onClick={save}>Save paging</button>
                {cfg.configured && <button type="button" className={primaryButton} disabled={busy} onClick={test}>Send test page</button>}
                {cfg.configured && <button type="button" onClick={remove} className="h-9 px-3 rounded-xl text-sm font-semibold text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20">Remove</button>}
            </div>
            {cfg.lastResult && (
                <p role="status" className={`text-sm ${cfg.lastResult.ok ? 'text-gray-600 dark:text-gray-300' : 'text-red-700 dark:text-red-300'}`}>
                    Last page {new Date(cfg.lastResult.at).toLocaleString()}: {cfg.lastResult.ok ? 'accepted' : cfg.lastResult.error}
                    {cfg.suppressed ? ` · ${cfg.suppressed} held back by the limit of 20 pages an hour` : ''}
                </p>
            )}
            {!!cfg.recentPages?.length && (
                <div className="overflow-x-auto">
                    <table className="text-sm w-full">
                        <thead><tr className="text-left text-gray-500 dark:text-gray-400"><th className="pr-4">Sent</th><th className="pr-4">Alert</th><th className="pr-4">Why</th><th>Status</th></tr></thead>
                        <tbody>
                            {cfg.recentPages.map(p => (
                                <tr key={p.id} className="text-gray-800 dark:text-gray-200">
                                    <td className="pr-4 py-1 whitespace-nowrap">{new Date(p.sentAt).toLocaleString()}</td>
                                    <td className="pr-4 py-1">{p.title || p.alertId}</td>
                                    <td className="pr-4 py-1">{REASON[p.reason] ?? p.reason}</td>
                                    <td className="py-1">{STATUS[p.status] ?? p.status}{p.error || p.resolveError ? `: ${p.error || p.resolveError}` : ''}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    );
};
