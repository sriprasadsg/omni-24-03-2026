import React, { useEffect, useState } from 'react';
import { Eye, Trash2 } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { ghostButton } from '../../network/NetworkKit';
import { formatSince } from './socData';
import { field, primaryButton, subhead } from './SocKit';

interface Item { id: string; value: string; kind: string; note?: string | null; addedBy?: string; addedAt?: string; retroMatches?: number }

const call = async (url: string, method?: string, body?: unknown) => {
    const res = await authFetch(url, method ? { method, body: body === undefined ? undefined : JSON.stringify(body) } : undefined);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`);
    return data;
};

/** The organization's own indicators: adding one checks the last 90 days of alerts, new alerts are checked as they arrive. */
export const WatchlistPanel: React.FC = () => {
    const [items, setItems] = useState<Item[] | null>(null);
    const [value, setValue] = useState('');
    const [note, setNote] = useState('');
    const [busy, setBusy] = useState(false);
    const load = () => call('/api/security/soc/watchlist').then(d => setItems(d.items ?? [])).catch(() => setItems([]));
    useEffect(() => { load(); }, []);

    const add = async () => {
        setBusy(true);
        try {
            const out = await call('/api/security/soc/watchlist', 'POST', { value: value.trim(), note: note.trim() || undefined });
            showToast(`Watching ${out.value}: ${out.retroMatches} past alert${out.retroMatches === 1 ? '' : 's'} in the last 90 days name it`, 'success');
            setValue(''); setNote(''); load();
        } catch (e) { showToast(e instanceof Error ? e.message : 'Not added', 'error'); } finally { setBusy(false); }
    };

    return (
        <section aria-label="Watchlist" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4 space-y-3">
            <h3 className={`${subhead} flex items-center gap-1.5`}><Eye className="w-3.5 h-3.5" aria-hidden="true" />Watchlist</h3>
            <p className="text-xs text-gray-600 dark:text-gray-300">Your own IPs, SHA-256 hashes and domains. Adding one checks the last 90 days of alerts (retro-hunt); new alerts are checked as they arrive and get +20 risk.</p>
            <div className="flex flex-wrap items-end gap-2">
                <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Indicator</span>
                    <input value={value} maxLength={253} onChange={e => setValue(e.target.value)} placeholder="IP, SHA-256 or domain" className={`${field} w-64 px-3`} /></label>
                <label><span className="block text-[11px] text-gray-500 dark:text-gray-400">Note</span>
                    <input value={note} maxLength={200} onChange={e => setNote(e.target.value)} className={`${field} w-48 px-3`} /></label>
                <button type="button" className={primaryButton} disabled={busy || !value.trim()} onClick={add}>Watch</button>
            </div>
            {items && items.length > 0 && (
                <ul className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                    {items.map(i => (
                        <li key={i.id} className="py-2 flex items-center gap-3 text-[13px]">
                            <span className="font-mono text-[12px] text-gray-900 dark:text-white break-all">{i.value}</span>
                            <span className="text-xs text-gray-500 dark:text-gray-400 flex-1">{i.kind}{i.note ? ` · ${i.note}` : ''} · {i.retroMatches ?? 0} past match{i.retroMatches === 1 ? '' : 'es'} · added {formatSince(i.addedAt)}</span>
                            <button type="button" className={`${ghostButton} h-8 px-2`} aria-label={`Stop watching ${i.value}`}
                                onClick={() => call(`/api/security/soc/watchlist/${i.id}`, 'DELETE').then(load).catch(e => showToast(e.message, 'error'))}>
                                <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            {items && items.length === 0 && <p className="text-xs text-gray-500 dark:text-gray-400">Nothing on the watchlist yet.</p>}
        </section>
    );
};
