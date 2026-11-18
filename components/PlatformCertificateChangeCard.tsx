import React, { useEffect, useState } from 'react';
import { authFetch } from '../services/apiService';

// Platform health, Wave 6: a server certificate change (scripts/tls_rollover.sh, backend/agent_tls_trust.py).
// Agents trust only pinned certificates, so the switch waits until every active agent has the new one and has
// tested it. Fingerprints and dates only; the steps themselves run on the server.

interface CertInfo { fingerprint: string; subject: string; notAfter: string }
interface NotReady { hostname: string; platform?: string; version?: string; status: string; detail: string }
interface Rollover {
    phase: 'none' | 'published' | 'prepared' | 'switched' | 'finished';
    served: CertInfo | null;
    next: string[];
    probePort: number | null;
    counts: Record<string, number>;
    notReady: NotReady[];
}

const TLS_ROLLOVER_PATH = '/api/platform/autonomous-ops/health/tls-rollover';

const STATUS_LABEL: Record<string, string> = {
    update_agent: 'Update the agent', not_pinned: 'Not pinned', waiting: 'Has not taken the new list',
    probe_pending: 'Not tested yet', probe_failed: 'Test failed',
};

const short = (fp: string) => `${fp.slice(0, 12)}…`;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });

function phaseText(r: Rollover, active: number, ready: number): string {
    const step = (s: string) => `sudo scripts/tls_rollover.sh ${s}`;
    switch (r.phase) {
        case 'prepared':
            return `Prepared: agents get the new certificate and test it on port ${r.probePort}. ${ready} of ${active} active agents are ready. `
                + (ready === active ? `All are ready: switch with ${step('switch')}.` : `Switch with ${step('switch')} once all are.`);
        case 'switched':
            return `Switched: the server presents the new certificate and agents still trust the old one too. `
                + `${ready} of ${active} active agents trust the new one; finish with ${step('finish')} once all do.`;
        case 'finished':
            return `Finished: agents are asked to trust only the new certificate. ${ready} of ${active} active agents do.`;
        case 'published':
            return `A certificate list is published to agents. ${ready} of ${active} active agents trust it.`;
        default:
            return `No certificate change in progress. To start one: ${step('prepare')}.`;
    }
}

export const PlatformCertificateChangeCard: React.FC = () => {
    const [data, setData] = useState<Rollover | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let current = true;
        (async () => {
            try {
                const r = await authFetch(TLS_ROLLOVER_PATH);
                const body = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `HTTP ${r.status}`);
                if (current) setData(body as Rollover);
            } catch (e) {
                if (current) setError(e instanceof Error ? e.message : 'unknown error');
            }
        })();
        return () => { current = false; };
    }, []);

    const active = data?.counts?.active ?? 0;
    const ready = data?.counts?.ready ?? 0;

    return (
        <section aria-labelledby="platform-cert-change-title" className="rounded-2xl border border-gray-200/80 dark:border-white/[0.07] bg-white dark:bg-gray-800 p-5 space-y-3">
            <div>
                <h3 id="platform-cert-change-title" className="text-sm font-semibold text-gray-900 dark:text-white">Certificate change</h3>
                {data?.served && (
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        The server presents <span className="font-mono">{short(data.served.fingerprint)}</span>, valid until {day(data.served.notAfter)}.
                    </p>
                )}
            </div>
            {/* A plain note, not an alert: the health page has its own alert for a failed load. */}
            {error && <p className="text-sm text-gray-600 dark:text-gray-400">The certificate change status could not be loaded ({error}).</p>}
            {data && <p className="text-sm text-gray-700 dark:text-gray-300">{phaseText(data, active, ready)}</p>}
            {data && data.notReady.length > 0 && (
                <table className="w-full text-sm" aria-label="Agents not ready for the certificate change">
                    <thead>
                        <tr className="text-left text-xs text-gray-500 dark:text-gray-400">
                            <th className="py-1.5 pr-3 font-medium">Agent</th>
                            <th className="py-1.5 pr-3 font-medium">Version</th>
                            <th className="py-1.5 font-medium">What it still needs</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-white/[0.05]">
                        {data.notReady.map((a, i) => (
                            <tr key={`${a.hostname}-${i}`}>
                                <td className="py-2 pr-3 text-gray-900 dark:text-white">{a.hostname}<span className="ml-1 text-xs text-gray-500 dark:text-gray-400">{a.platform}</span></td>
                                <td className="py-2 pr-3 text-gray-600 dark:text-gray-400">{a.version || '—'}</td>
                                <td className="py-2 text-gray-700 dark:text-gray-300">
                                    <span className="font-medium">{STATUS_LABEL[a.status] ?? a.status}</span>
                                    {a.detail && <span className="block text-xs text-gray-500 dark:text-gray-400">{a.detail}</span>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
};
