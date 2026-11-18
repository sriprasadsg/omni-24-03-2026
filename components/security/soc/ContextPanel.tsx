import React, { useEffect, useState } from 'react';
import { Gauge, ShieldX } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { ghostButton } from '../../network/NetworkKit';
import { FEED_NAME, IMPORTANCE, fetchAlertContext, formatSince, setEndpointContext, type AlertContextInfo, type Importance } from './socData';
import { field, subhead } from './SocKit';

const riskTone = (r: number) => (r >= 75 ? 'text-red-700 dark:text-red-300' : r >= 50 ? 'text-orange-700 dark:text-orange-300' : 'text-gray-900 dark:text-white');

/** Risk, the endpoint (with importance and owner), the user, other alerts there and threat-intel hits. */
export const ContextPanel: React.FC<{ alertId: string; canEdit: boolean; onChanged: () => void }> = ({ alertId, canEdit, onChanged }) => {
    const [ctx, setCtx] = useState<AlertContextInfo | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [importance, setImportance] = useState<Importance>('medium');
    const [owner, setOwner] = useState('');
    const [busy, setBusy] = useState(false);

    const load = () => fetchAlertContext(authFetch, alertId).then(c => {
        setCtx(c); setImportance(c.host.importance); setOwner(c.host.owner || ''); setError(null);
    }).catch(e => setError(e instanceof Error ? e.message : 'The context could not be loaded'));
    useEffect(() => { load(); }, [alertId]);

    if (error) return <section><h3 className={subhead}>Context</h3><p className="mt-2 text-xs text-red-700 dark:text-red-300">{error}</p></section>;
    if (!ctx) return <section><h3 className={subhead}>Context</h3><p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Loading…</p></section>;
    const h = ctx.host;
    const changed = importance !== h.importance || owner !== (h.owner || '');
    const save = async () => {
        if (!h.agentId) return;
        setBusy(true);
        try {
            await setEndpointContext(authFetch, h.agentId, importance, owner.trim());
            showToast('Endpoint updated; risk scores use it now', 'success');
            await load();
            onChanged();
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'The endpoint was not updated', 'error');
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="space-y-3">
            <h3 className={subhead}>Context</h3>
            <p className="flex items-center gap-2 text-[13px] text-gray-700 dark:text-gray-300">
                <Gauge className="w-4 h-4 text-gray-400" aria-hidden="true" />Risk
                <span className={`font-mono tabular-nums text-[17px] font-semibold ${riskTone(ctx.risk)}`}>{ctx.risk}</span>
                <span className="text-xs text-gray-500 dark:text-gray-400">of 100: severity, endpoint importance, repeats, age and threat intel</span>
            </p>
            <div className="rounded-xl border border-gray-200/80 dark:border-white/[0.08] p-3 text-[13px] space-y-1">
                <p className="font-medium text-gray-900 dark:text-white">{h.hostname || h.agentId || 'No endpoint'}{!h.enrolled && h.agentId && <span className="ml-2 text-xs font-normal text-gray-500">no longer enrolled</span>}</p>
                {h.enrolled && <p className="text-xs text-gray-600 dark:text-gray-300">{[h.os, h.ip, h.agentVersion && `agent ${h.agentVersion}`, h.lastSeen && `seen ${formatSince(h.lastSeen)}`].filter(Boolean).join(' · ')}</p>}
                <p className="text-xs text-gray-600 dark:text-gray-300">{h.otherActiveAlerts} other active alert{h.otherActiveAlerts === 1 ? '' : 's'} on this endpoint{ctx.user ? ` · user ${ctx.user}` : ''}</p>
                {h.enrolled && (
                    <div className="pt-2 flex flex-wrap items-end gap-2">
                        <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Importance</span>
                            <select value={importance} disabled={!canEdit} onChange={e => setImportance(e.target.value as Importance)} className={`${field} px-2`}>
                                {IMPORTANCE.map(i => <option key={i} value={i}>{i[0].toUpperCase() + i.slice(1)}</option>)}
                            </select></label>
                        <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Owner</span>
                            <input value={owner} disabled={!canEdit} maxLength={120} onChange={e => setOwner(e.target.value)} className={`${field} w-40 px-2`} /></label>
                        {canEdit && <button type="button" className={`${ghostButton} h-9`} disabled={busy || !changed} onClick={save}>Save</button>}
                    </div>
                )}
            </div>
            <div className="text-[13px]">
                {ctx.threatIntel.length > 0 ? (
                    <ul className="space-y-1">
                        {ctx.threatIntel.map(t => (
                            <li key={`${t.source}-${t.value}`} className="flex items-start gap-2 text-red-800 dark:text-red-200">
                                <ShieldX className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                                <span><span className="font-mono text-[12px]">{t.value}</span> is listed by {FEED_NAME[t.source] || t.source}{t.malware ? ` (${t.malware})` : ''}</span>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className="text-xs text-gray-600 dark:text-gray-300">
                        {ctx.indicators.sha256 || ctx.indicators.ip ? 'No threat-intel feed lists this alert\'s hash or IP.' : 'The alert names no hash or public IP to check against threat intel.'}
                    </p>
                )}
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                    Feeds: {ctx.feeds.feeds.length ? ctx.feeds.feeds.map(f => `${FEED_NAME[f.source] || f.source} ${f.needsKey ? 'needs a free abuse.ch key (ABUSECH_AUTH_KEY)' : f.ok ? `${f.count ?? 0} indicator${f.count === 1 ? '' : 's'}, ${formatSince(f.at)}` : 'failed'}`).join('; ') : 'first download runs a minute after the backend starts'}
                </p>
            </div>
        </section>
    );
};
