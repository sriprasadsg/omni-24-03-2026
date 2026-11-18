import React, { useCallback, useEffect, useState } from 'react';
import { Ban, FileLock2, Lock, Network, RotateCcw, Unplug, XOctagon } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { ghostButton } from '../../network/NetworkKit';
import {
    fetchResponse, formatWhen, keepIsolated, respondToAlert, responseImpact, undoResponse,
    type BlockTtl, type ResponseAction, type ResponseInfo, type ResponseOption,
} from './socData';
import { field, subhead } from './SocKit';

const ICON: Record<ResponseAction, React.ElementType> = {
    isolate_host: Unplug, quarantine_file: FileLock2, block_ip: Ban, kill_process: XOctagon,
};
const TTLS: { key: BlockTtl; label: string }[] = [{ key: '1h', label: '1 hour' }, { key: '24h', label: '24 hours' }, { key: '7d', label: '7 days' }];
const dangerButton = 'inline-flex items-center gap-2 h-9 px-3 rounded-xl text-sm font-semibold bg-red-600 text-white hover:bg-red-700 disabled:opacity-60 transition-colors cursor-pointer';

/**
 * Response actions for one alert: what its evidence supports, why an action is unavailable, a
 * confirmation that says what will happen, and what was already done (with Undo / Keep isolated).
 */
export const ResponsePanel: React.FC<{ alertId: string; onChanged: () => void }> = ({ alertId, onChanged }) => {
    const [info, setInfo] = useState<ResponseInfo | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [confirming, setConfirming] = useState<ResponseOption | null>(null);
    const [ttl, setTtl] = useState<BlockTtl>('24h');
    const [busy, setBusy] = useState(false);

    const load = useCallback(() => {
        fetchResponse(authFetch, alertId).then(i => { setInfo(i); setError(null); })
            .catch(e => setError(e instanceof Error ? e.message : 'Response actions could not be loaded'));
    }, [alertId]);
    useEffect(() => { load(); }, [load]);

    const run = async (work: () => Promise<unknown>, done: string) => {
        setBusy(true);
        try {
            await work();
            showToast(done, 'success');
            setConfirming(null);
            onChanged();
        } catch (e) {
            showToast(e instanceof Error ? e.message : 'Nothing was changed', 'error');
        } finally {
            setBusy(false);
            load();
        }
    };

    if (error) return <section><h3 className={subhead}>Respond</h3><p className="mt-2 text-xs text-red-700 dark:text-red-300">{error}</p></section>;
    if (!info) return <section><h3 className={subhead}>Respond</h3><p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Loading…</p></section>;

    return (
        <section className="space-y-3">
            <h3 className={subhead}>Respond on {info.host}</h3>
            {info.isolated && (
                <p className="flex items-center gap-2 text-xs font-medium text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-500/10 rounded-lg px-2.5 py-1.5">
                    <Lock className="w-3.5 h-3.5" aria-hidden="true" />This computer reports that it is isolated now.
                </p>
            )}
            {!info.canRespond && <p className="text-xs text-gray-600 dark:text-gray-300">Acting on endpoints needs the Active Response permission.</p>}

            {confirming ? (
                <div role="alertdialog" aria-labelledby="soc-confirm-title" className="rounded-xl border border-red-300 dark:border-red-500/40 bg-red-50/60 dark:bg-red-500/[0.06] p-3">
                    <p id="soc-confirm-title" className="text-sm font-semibold text-gray-900 dark:text-white">{confirming.label}?</p>
                    <p className="mt-1 text-[13px] text-gray-700 dark:text-gray-300">{responseImpact(confirming, ttl)}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                        <button type="button" className={dangerButton} disabled={busy}
                            onClick={() => run(() => respondToAlert(authFetch, alertId, confirming.action, confirming.action === 'block_ip' ? ttl : undefined), `${confirming.label}: sent to ${info.host}`)}>
                            Confirm: {confirming.label.toLowerCase()}
                        </button>
                        <button type="button" className={ghostButton} disabled={busy} onClick={() => setConfirming(null)}>Cancel</button>
                    </div>
                </div>
            ) : (
                <ul className="space-y-2">
                    {info.options.map(o => {
                        const Icon = ICON[o.action] ?? Network;
                        return (
                            <li key={o.action} className="flex flex-wrap items-center gap-2">
                                <button id={`soc-respond-${o.action}`} type="button" className={ghostButton} disabled={!o.available || !info.canRespond || busy} onClick={() => setConfirming(o)}>
                                    <Icon className="w-4 h-4" aria-hidden="true" />{o.label}
                                </button>
                                {o.action === 'block_ip' && o.available && (
                                    <>
                                        <label className="sr-only" htmlFor={`ttl-${alertId}`}>Block for</label>
                                        <select id={`ttl-${alertId}`} value={ttl} onChange={e => setTtl(e.target.value as BlockTtl)} className={`${field} px-2`}>
                                            {TTLS.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
                                        </select>
                                    </>
                                )}
                                {!o.available && o.reason && <span className="basis-full text-[11px] text-gray-500 dark:text-gray-400">{o.reason}</span>}
                            </li>
                        );
                    })}
                </ul>
            )}

            {info.history.length > 0 && (
                <div>
                    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Done from this alert</h4>
                    <ul className="mt-1.5 divide-y divide-gray-100 dark:divide-white/[0.05]">
                        {info.history.map(h => (
                            <li key={h.actionId} className="py-2 text-[13px]">
                                <div className="flex flex-wrap items-baseline justify-between gap-2">
                                    <span className="font-medium text-gray-900 dark:text-white">{h.label}</span>
                                    <span className="text-xs text-gray-600 dark:text-gray-300">{h.stateText}</span>
                                </div>
                                <p className="text-[11px] text-gray-500 dark:text-gray-400">
                                    {h.requestedBy ? `${h.requestedBy} · ` : ''}{formatWhen(h.createdAt)}
                                    {h.blockedUntil && ` · lifts ${formatWhen(h.blockedUntil)}`}
                                    {h.revertsAt && !h.keptIsolated && ` · reconnects by itself ${formatWhen(h.revertsAt)}`}
                                    {h.keptIsolated && ' · kept isolated'}
                                </p>
                                {h.reason && <p className="text-[11px] text-red-700 dark:text-red-300">{h.reason}</p>}
                                {info.canRespond && (h.canUndo || h.canKeepIsolated) && (
                                    <div className="mt-1.5 flex gap-2">
                                        {h.canUndo && (
                                            <button type="button" className={`${ghostButton} h-8`} disabled={busy}
                                                onClick={() => run(() => undoResponse(authFetch, alertId, h.actionId), `${h.label}: undo sent`)}>
                                                <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />Undo
                                            </button>
                                        )}
                                        {h.canKeepIsolated && (
                                            <button type="button" className={`${ghostButton} h-8`} disabled={busy}
                                                onClick={() => run(() => keepIsolated(authFetch, alertId, h.actionId), 'The computer stays isolated until someone restores it')}>
                                                <Lock className="w-3.5 h-3.5" aria-hidden="true" />Keep isolated
                                            </button>
                                        )}
                                    </div>
                                )}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </section>
    );
};
