import React, { useEffect, useState } from 'react';
import { Timer } from 'lucide-react';
import { authFetch } from '../../../services/apiService';
import { showToast } from '../../../utils/toast';
import { SEVERITIES, SEVERITY_META } from './socData';
import { field, primaryButton, subhead } from './SocKit';

type Targets = Record<'acknowledge' | 'close', Record<string, number>>;

/** Minutes to acknowledge and to close, per severity: the queue marks alerts past them as overdue. */
export const SlaPanel: React.FC = () => {
    const [t, setT] = useState<Targets | null>(null);
    useEffect(() => { authFetch('/api/security/soc/sla').then(r => (r.ok ? r.json() : null)).then(d => d?.acknowledge && setT(d)).catch(() => {}); }, []);
    if (!t) return null;
    const save = async () => {
        const res = await authFetch('/api/security/soc/sla', { method: 'PUT', body: JSON.stringify(t) });
        const d = await res.json().catch(() => ({}));
        if (res.ok) { setT(d); showToast('Response-time targets saved', 'success'); } else showToast(typeof d?.detail === 'string' ? d.detail : 'Not saved', 'error');
    };
    return (
        <section aria-label="Response-time targets" className="rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card p-4 space-y-3">
            <h3 className={`${subhead} flex items-center gap-1.5`}><Timer className="w-3.5 h-3.5" aria-hidden="true" />Response-time targets (minutes)</h3>
            <div className="overflow-x-auto relative">
                <table className="text-sm">
                    <thead><tr><th className="pr-4 text-left">Severity</th><th className="pr-4 text-left">Acknowledge within</th><th className="text-left">Close within</th></tr></thead>
                    <tbody>
                        {SEVERITIES.map(s => (
                            <tr key={s}>
                                <td className="pr-4 py-1 text-gray-800 dark:text-gray-200">{SEVERITY_META[s].label}</td>
                                {(['acknowledge', 'close'] as const).map(k => (
                                    <td key={k} className="pr-4 py-1">
                                        <input type="number" min={1} aria-label={`${SEVERITY_META[s].label}: ${k} within minutes`} value={t[k][s]}
                                            onChange={e => setT({ ...t, [k]: { ...t[k], [s]: Math.max(1, Number(e.target.value) || 1) } })} className={`${field} w-28 px-2`} />
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <button type="button" className={primaryButton} onClick={save}>Save targets</button>
        </section>
    );
};
